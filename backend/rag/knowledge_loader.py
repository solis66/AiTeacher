"""
教研知识库（静态参考资料的加载与检索）

职责边界：只负责「把 data/knowledge 下的教研语料变成可注入 prompt 的文本」。
不做生成，不拼提示词——拼接由 consultation_service 负责。

语料规模决定策略（这是刻意的设计，不是临时妥协）：
  - 小语料（总字数 <= full_inject_limit）：**全文注入** prompt。
    零漏检、零延迟、无需调参。此规模下向量检索是负收益。
  - 大语料：构建向量索引，按问题检索相关小节，并按相似度阈值过滤。

为什么不是一律走向量检索：语料小的时候，向量检索有漏检、有 embedding 延迟、
还要调 chunk_size / overlap / k / threshold 四个参数，而全量注入三者皆无。
判断依据与推导见 docs/咨询RAG检索服务设计.md §10。

与批改链路的关系：本模块使用独立的 collection（默认 consult_knowledge）与独立的
切片参数，与批改用的 collection（默认 agent，装权威评分标准）互不影响。
"""

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from utils.config_handler import chroma_conf
from utils.path_tool import get_abs_path
from utils.retrieval_timeout import run_with_timeout
from rag.hybrid import rerank

_CONSULT = chroma_conf.get('consult') or {}

KNOWLEDGE_DIR = Path(get_abs_path(_CONSULT.get('knowledge_path', 'knowledge')))
COLLECTION_NAME = _CONSULT.get('knowledge_collection', 'consult_knowledge')
CHUNK_SIZE = int(_CONSULT.get('knowledge_chunk_size', 400))
CHUNK_OVERLAP = int(_CONSULT.get('knowledge_chunk_overlap', 50))
FULL_INJECT_LIMIT = int(_CONSULT.get('full_inject_limit', 12000))
DEFAULT_K = int(_CONSULT.get('k_knowledge', 4))
# 兜底阈值必须与 config/chroma.yaml 的 consult.score_threshold 一致（0.20 为实测标定值）。
# 此前这里写 0.35、review_index 写 0.20：配置项缺失时两个模块会各自按不同阈值过滤，
# 同一句问句在"教研资料"和"批改案例"上的召回标准悄悄分叉，且没有任何报错提示。
DEFAULT_THRESHOLD = float(_CONSULT.get('score_threshold', 0.20))
# 单次检索超时（秒）。与 config/chroma.yaml 的 consult.timeout 对齐；
# 之前这个配置项没人读，检索卡住时请求会一直挂着。
RETRIEVAL_TIMEOUT = float(_CONSULT.get('timeout', 8))
STATE_FILE = get_abs_path(_CONSULT.get('knowledge_md5_store', 'md5_knowledge.text'))

HYBRID_CANDIDATE_FACTOR = max(1, int(_CONSULT.get('hybrid_candidate_factor', 3)))
HYBRID_VECTOR_WEIGHT = float(_CONSULT.get('hybrid_vector_weight', 0.7))
HYBRID_LEXICAL_WEIGHT = float(_CONSULT.get('hybrid_lexical_weight', 0.3))

# 建库串行化锁。Flask 多线程下两个并发咨询会同时触发建库/更新，
# 各自对本文件的 source 执行 delete + add，交错后同一份资料被写入两次，
# 检索结果里出现重复片段。锁只在真正需要重建时才产生等待（毫秒级）。
_ENSURE_LOCK = threading.Lock()

# 检索为空时的固定话术。
# 这句比任何提示词技巧都重要：它让模型在无资料时降低表述的确定性，而不是编造出处。
NO_REFERENCE_NOTE = '未检索到直接相关的教研资料，请基于通用教学常识回答，并说明这是通用建议。'

_corpus_cache: Optional[List[Dict]] = None
_corpus_signature: Optional[str] = None
_chroma = None
_index_ready = False

# 小语料启动时不再预先建库（全文注入根本读不到索引）。真正需要检索时才按需构建。
# 这两个变量避免并发请求重复建库，以及构建失败后每轮对话都重打 embedding 接口。
_warm_lock = threading.Lock()
_warming = False
_last_warm_attempt = 0.0
WARM_INTERVAL_SECONDS = 300


# --------------------------------------------------------------------------- 语料

def _md5(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()


def _iter_files() -> List[Path]:
    """列出语料文件。递归扫描——此前批改侧用 os.listdir 不递归，子目录语料会被静默忽略。"""
    if not KNOWLEDGE_DIR.is_dir():
        return []
    return sorted(p for p in KNOWLEDGE_DIR.rglob('*.md') if p.is_file())


def _split_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('# '):
            return line[2:].strip() or fallback
    return fallback


def load_corpus(force: bool = False) -> List[Dict]:
    """
    读取全部教研语料（带进程内缓存，按文件签名失效）。

    返回：
        [{'source': 相对路径, 'title': 文档标题, 'text': 全文, 'md5': ...}, ...]
    """
    global _corpus_cache, _corpus_signature

    files = _iter_files()
    signature = '|'.join(f'{p.relative_to(KNOWLEDGE_DIR).as_posix()}:{p.stat().st_mtime_ns}' for p in files)
    if not force and _corpus_cache is not None and signature == _corpus_signature:
        return _corpus_cache

    corpus: List[Dict] = []
    for path in files:
        try:
            text = path.read_text(encoding='utf-8').strip()
        except Exception:
            continue
        if not text:
            continue
        rel = path.relative_to(KNOWLEDGE_DIR).as_posix()
        corpus.append({
            'source': rel,
            'title': _split_title(text, path.stem),
            'text': text,
            'md5': _md5(text),
        })

    _corpus_cache = corpus
    _corpus_signature = signature
    return corpus


def stats() -> Dict:
    """语料规模统计，供命中率埋点与调试使用。"""
    corpus = load_corpus()
    total = sum(len(item['text']) for item in corpus)
    return {
        'files': len(corpus),
        'chars': total,
        'mode': 'full' if total <= FULL_INJECT_LIMIT else 'retrieval',
        'full_inject_limit': FULL_INJECT_LIMIT,
    }


def is_small_corpus() -> bool:
    return stats()['chars'] <= FULL_INJECT_LIMIT


# --------------------------------------------------------------------------- 向量索引

def _get_chroma():
    """惰性创建咨询知识库的 Chroma 实例。模型不可用时返回 None（调用方降级）。"""
    global _chroma
    if _chroma is not None:
        return _chroma
    try:
        from langchain_chroma import Chroma
        from model.factory import embed_model

        if embed_model is None:
            return None
        _chroma = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embed_model,
            persist_directory=chroma_conf['persist_directory'],
        )
        return _chroma
    except Exception:
        return None


def _load_state() -> Dict[str, str]:
    path = Path(STATE_FILE)
    if not path.exists():
        return {}
    state: Dict[str, str] = {}
    try:
        for line in path.read_text(encoding='utf-8').splitlines():
            if '\t' in line:
                md5, rel = line.split('\t', 1)
                state[rel.strip()] = md5.strip()
    except Exception:
        return {}
    return state


def _save_state(state: Dict[str, str]) -> None:
    try:
        lines = [f'{md5}\t{rel}' for rel, md5 in sorted(state.items())]
        Path(STATE_FILE).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    except Exception:
        pass


def _chunks(text: str) -> List[str]:
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            # 优先按 Markdown 标题切分：教研语料是按小节组织的，
            # 按标题切出的片段自带完整语义；按字数硬切会把一条方法切成半句。
            separators=['\n## ', '\n### ', '\n\n', '\n', '。', '；', ''],
            length_function=len,
        )
        return [c for c in splitter.split_text(text) if c.strip()]
    except Exception:
        # 兜底：按段落粗切，保证建库不因切分器问题整体失败
        return [text[i:i + CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE - CHUNK_OVERLAP) if text[i:i + CHUNK_SIZE].strip()]


def ensure_index(force: bool = False) -> Dict:
    """
    构建 / 增量更新教研知识库索引。

    去重策略：按 source 先删后加。
    此前批改侧只判断 md5「是否出现过」，文件更新后 md5 是新的 → 只新增不删除，
    库里会同时存在同一文件的两代内容，检索时随机命中旧版。这里按 source 清理，
    保证一个 source 在库中只有一份当前内容。

    返回：
        dict: {'ok': bool, 'added': n, 'removed': n, 'skipped': n, 'reason': str}
    """
    # 串行化：并发触发时只让一个线程真正建库，其余线程等锁后走 md5 命中跳过。
    with _ENSURE_LOCK:
        return _ensure_index_locked(force)


def _ensure_index_locked(force: bool = False) -> Dict:
    global _index_ready

    corpus = load_corpus(force=force)
    if not corpus:
        return {'ok': False, 'added': 0, 'removed': 0, 'skipped': 0, 'reason': '语料目录为空'}

    store = _get_chroma()
    if store is None:
        return {'ok': False, 'added': 0, 'removed': 0, 'skipped': 0, 'reason': '向量模型不可用'}

    state = _load_state()
    added = removed = skipped = 0
    try:
        from langchain_core.documents import Document

        # 1) 清理已删除的语料文件对应的旧分片
        current = {item['source'] for item in corpus}
        for stale in [rel for rel in state if rel not in current]:
            store.delete(where={'source': stale})
            state.pop(stale, None)
            removed += 1

        # 2) 逐文件增量
        for item in corpus:
            if not force and state.get(item['source']) == item['md5']:
                skipped += 1
                continue
            store.delete(where={'source': item['source']})       # 先删旧版
            docs = [
                Document(page_content=chunk,
                         metadata={'source': item['source'], 'title': item['title'], 'kind': 'knowledge'})
                for chunk in _chunks(item['text'])
            ]
            if docs:
                store.add_documents(docs)
                added += len(docs)
            state[item['source']] = item['md5']

        _save_state(state)
        _index_ready = True
        return {'ok': True, 'added': added, 'removed': removed, 'skipped': skipped, 'reason': ''}
    except Exception as exc:
        return {'ok': False, 'added': added, 'removed': removed, 'skipped': skipped, 'reason': f'建库失败: {exc}'}


# --------------------------------------------------------------------------- 检索与渲染

def render_full(corpus: List[Dict]) -> str:
    blocks = [f'### {item["title"]}（{item["source"]}）\n{item["text"]}' for item in corpus]
    return '\n\n'.join(blocks)


def render_hits(hits: List) -> str:
    blocks = []
    for index, (doc, _score) in enumerate(hits, start=1):
        meta = doc.metadata or {}
        blocks.append(f'【教研资料{index} · 来源：{meta.get("source", "未知")}】\n{doc.page_content.strip()}')
    return '\n\n'.join(blocks)


def search_text(query: str, k: int = None, threshold: float = None) -> str:
    """
    检索教研资料并直接渲染成文本（供 agent 工具调用）。

    与 get_context 的区别：本函数**总是走检索**，不做"小语料全文注入"的切换。
    工具调用的语义就是"按需取资料"，返回全文会让模型误以为这就是全部答案。
    """
    hits = search(query, k, threshold)
    return render_hits(hits) if hits else NO_REFERENCE_NOTE


def _ensure_index_async():
    """
    索引未就绪时后台构建一次（按需构建）。

    为什么不在启动时无条件建库：小语料走全文注入，索引根本读不到——启动时建库
    纯粹是几十次 embedding 调用换一个"永远用不上"的集合。改为按需：语料增长到
    需要检索时，第一次检索触发构建，本次请求降级为"无参考资料"，后台建完恢复。

    失败冷却：建库调外部接口，失败后 5 分钟内不再尝试，避免每轮对话都重打。
    """
    global _warming, _last_warm_attempt

    if _index_ready:
        return
    now = time.monotonic()
    with _warm_lock:
        if _index_ready or _warming:
            return
        if now - _last_warm_attempt < WARM_INTERVAL_SECONDS:
            return
        _warming = True
        _last_warm_attempt = now

    def _run():
        global _warming
        try:
            ensure_index()
        finally:
            with _warm_lock:
                _warming = False

    threading.Thread(target=_run, name='knowledge-index-warm', daemon=True).start()


def search(query: str, k: int = None, threshold: float = None) -> List:
    """
    向量检索教研资料（仅大语料路径使用）。

    返回 [(Document, score), ...]，已按阈值过滤。
    任何异常都返回空列表——检索失败不能中断咨询。
    """
    store = _get_chroma()
    if store is None or not (query or '').strip():
        return []
    if not _index_ready:
        # 启动时跳过了建库（小语料用不到）。这里按需触发构建并先返回空结果：
        # 建库要调 embedding 接口，不能把几分钟压进一次用户请求。
        _ensure_index_async()
        return []
    limit = DEFAULT_THRESHOLD if threshold is None else threshold
    top_k = max(1, int(k or DEFAULT_K))
    candidate_k = top_k * HYBRID_CANDIDATE_FACTOR
    try:
        raw = run_with_timeout(
            lambda: store.similarity_search_with_relevance_scores(query, k=candidate_k),
            RETRIEVAL_TIMEOUT,
            default=[],
        )
    except Exception:
        return []
    survivors = [(doc, score) for doc, score in raw if score is not None and score >= limit]
    return rerank(query, survivors, top_k, HYBRID_VECTOR_WEIGHT, HYBRID_LEXICAL_WEIGHT)


def get_context(query: str = '') -> str:
    """
    取得可注入 prompt 的教研资料文本。

    决策只看语料规模（实测 6182 字，远低于 full_inject_limit=12000）：
        小语料 → 全文注入。这个规模下向量检索是负收益——会漏检，还要多一次
        embedding 调用；而全文只有约 6k 字，prompt 完全放得下。
        大语料 → 按问题检索相关小节，避免把几十万字塞进上下文。

    重新评估的结论：个人学情类提问不再强制走向量检索。
    此前对 scope != 'none' 的提问传 force_retrieval=True，等于在"全文本来就放得下"
    时主动放弃完整性，只为省几千字——省下的 token 与漏掉资料的风险不成比例。

    参数：
        query: 用户提问（大语料下用于检索；小语料下不参与决策）

    返回：
        str - 可直接拼进 prompt 的资料文本；无内容时返回 NO_REFERENCE_NOTE
    """
    corpus = load_corpus()
    if not corpus:
        return NO_REFERENCE_NOTE
    if is_small_corpus():
        return render_full(corpus)

    hits = search(query)
    return render_hits(hits) if hits else NO_REFERENCE_NOTE
