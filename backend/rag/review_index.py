"""
批改案例索引与检索

职责：把「AI 批改多篇作文后的结果」变成可被咨询检索的知识。

为什么需要它：
    老师在账号下积累几十上百次批改之后，`reviews.sqlite3` 里其实已经躺着这个项目
    最值钱的教学数据——每篇作文的维度得分、总体评价、亮点、改进建议、原文纠正。
    但这些数据此前只能一篇一篇点开看，无法回答「我哪里总是写不好」「这个学生的
    学情如何」这类跨篇问题。本模块把它们变成跨篇可检索的案例库。

两个来源，两种检索方式（刻意分开，各有各的正确性保证）：
    1) 确定性聚合 student_profile()：读 SQLite 直接计算——维度得分率、进步轨迹、
       反复出现的通病。**数字必须来自计算，不能来自向量检索**，否则会出现
       "模型算错了平均分"这类不可接受的错误。
    2) 语义检索 search()：把每篇的评语拆成细粒度片段入库，回答"我开头为什么总
       写不好"时按语义找回相关评语。**跨篇问句与单篇评语之间没有共同关键词**，
       所以这里是向量的用武之地。

索引粒度是关键设计：一篇作文拆成 summary / analysis / issue / strength 四类多个片段，
而不是整篇存一条。粒度太粗时检索等于没有——学生问"开头怎么写"，整篇评语文档的
向量会被"分数、结构、语言"等信息稀释，命中率极低。

性能设计（"作文会越来越多"是明确前提）：
    `reviews` 表有独立的 version 列，任何写入（批改完成、人工保存、重启标记失败）
    都会推进它。因此增量同步只需 `SELECT id, owner, version`（不解析 payload），
    只对 version 变化的记录读 payload 并重建索引。
    若每次咨询都解析全部 payload（含分页全文与批注坐标，单条可达数十 KB），
    500 篇时单次解析就上秒级——那会让咨询响应不可接受。
    同步产出的**紧凑指标缓存**（metrics）供学情聚合直接读取，避免重复解析大 JSON。
"""

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from utils.config_handler import chroma_conf
from utils.path_tool import get_abs_path

_CONSULT = chroma_conf.get('consult') or {}

COLLECTION_NAME = _CONSULT.get('case_collection', 'review_cases')
STATE_FILE = get_abs_path(_CONSULT.get('index_state', 'review_index_state.json'))
DEFAULT_K = int(_CONSULT.get('k_cases', 6))
# 兜底阈值与 config/chroma.yaml 的 consult.score_threshold 保持一致（0.20 为实测标定值）
DEFAULT_THRESHOLD = float(_CONSULT.get('score_threshold', 0.20))
MAX_REVIEWS = int(_CONSULT.get('case_max_reviews', 500))


def _canonical_dim(dim) -> str:
    """把保存的维度名归一化为固定五维中文名（需求 D1）。

    历史/异常数据里维度 name 可能是数字下标（0~4）或未知名，这里统一归并：
    - 已是我们五维中文名 → 直接保留；
    - 数字下标（0~4）→ 按固定顺序映射到对应维度；
    - 其余未知名称 → 丢弃，避免把下标/乱码当作维度名展示。
    """
    from utils.essay_constants import UNIFIED_DIMENSIONS
    if not isinstance(dim, dict):
        return ''
    name = dim.get('name')
    if not name or not str(name).strip():
        return ''
    name = str(name).strip()
    if name in UNIFIED_DIMENSIONS:
        return name
    if name.isdigit() and 0 <= int(name) < len(UNIFIED_DIMENSIONS):
        return UNIFIED_DIMENSIONS[int(name)]
    return ''

# 学情注入的「最近 N 篇」篇数（需求 D3，可配置，默认 3）。
# 优先级：环境变量 MOST_RECENT_ESSAYS > config/chroma.yaml 的 consult.most_recent_essays > 默认 3。
def _read_most_recent_essays() -> int:
    raw = os.environ.get('MOST_RECENT_ESSAYS') or _CONSULT.get('most_recent_essays')
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 3

MOST_RECENT_ESSAYS = _read_most_recent_essays()

REVIEW_ROOT = Path(get_abs_path('data/reviews'))
METRICS_FILE = REVIEW_ROOT / 'consult_metrics.json'

# AI 分析的固定字段 → 中文标签（与 services/review_grader.ANALYSIS_FIELDS 对应）
ANALYSIS_LABELS = {
    'content': '内容',
    'structure': '结构',
    'language': '语言',
    'technique': '写作技巧',
    'emotion': '情感',
}

# 问题归类词表。
# 用途：把「改进建议」按主题归并，找出反复出现的通病。
# 为什么用词表而不是聚类：词表可解释、可调试、结果稳定；聚类在数据量小的时候飘忽
# 不定，而且给出的类别名无法保证可读，教师端看到"类别3"是没有意义的。
ASPECT_KEYWORDS = {
    '开头': ['开头', '起笔', '首段'],
    '结尾': ['结尾', '收尾', '末段', '点题'],
    '结构': ['结构', '层次', '条理', '过渡', '照应', '详略', '顺序'],
    '立意中心': ['立意', '中心', '主题', '切题', '偏题', '跑题'],
    '内容选材': ['选材', '材料', '事例', '内容空', '空洞', '具体'],
    '语言表达': ['语言', '用词', '句子', '句式', '语病', '病句', '表达'],
    '修辞手法': ['修辞', '比喻', '拟人', '排比', '夸张'],
    '描写细节': ['描写', '细节', '动作', '神态', '心理', '环境'],
    '论证': ['论证', '论点', '论据', '分析', '说理'],
    '标点格式': ['标点', '格式', '书写', '字迹', '卷面'],
    '错别字': ['错别字', '错字', '别字'],
    '字数': ['字数', '篇幅', '不足500', '写不长'],
}

# 维度结论所需的最小样本数：某维度只出现在 1 篇作文上时，其得分率不足以支撑
# 「这是你最薄弱的维度」这类结论（不同体裁同名维度的满分都不一样）。
MIN_DIM_SAMPLES = 2

# 趋势结论所需的最小篇数。少于 5 篇时"更早"的样本只有一两个，且不同体裁的作文
# （记叙文与说明文维度满分都不同）分数本来就不直接可比，此时给出
# "下降 14 分"是误导而非洞察。
MIN_TREND_SAMPLES = 5

NO_CASE_NOTE = '未检索到该学生相关的批改记录。'

# 同步串行化锁。Flask 是多线程的，两个并发咨询会同时进入 sync()：
# 两者都判定"该记录已变化"，各自执行 delete + add，交错后同一篇作文的分片
# 被写入两次——检索结果出现重复条目，k 条召回里有一半是同一篇的同一段。
# 它同时是那对 state/metrics 侧车文件（读-改-写、无事务）的写锁，
# 否则并发写会互相覆盖，已索引的记录被误判为"没索引过"而重复建库。
# 代价可忽略：同步本身是毫秒级的，只有真有内容变化时才会调用 embedding。
_SYNC_LOCK = threading.Lock()


def _meta_text(value) -> str:
    """
    归一化 metadata 取值。

    Chroma 的 metadata 只接受 str/int/float/bool；空值统一换成 '-'，
    过滤语义仍是"该维度无信息"，同时避免部分版本对空字符串的过滤异常。
    """
    text = str(value or '').strip()
    return text if text else '-'


def _clip(text: str, limit: int) -> str:
    text = (text or '').strip()
    return text if len(text) <= limit else text[:limit].rstrip() + '…'


def student_of(record: Dict) -> str:
    """学生归属，兼容 student 字段引入前的历史记录（回退为 owner，即提交者本人）。"""
    return (record.get('student') or '').strip() or (record.get('owner') or '').strip() or 'anonymous'


# --------------------------------------------------------------------------- 文档构建

def build_documents(record: Dict) -> List:
    """
    把一条已完成的批改记录拆成可检索片段。

    只处理 status == 'done' 且带 result 的记录；未完成/失败的记录没有可检索内容，
    跳过而不是索引半成品（否则会把"批改失败"当成学生的问题）。
    """
    if not record or record.get('status') != 'done':
        return []
    result = record.get('result') or {}
    if not result:
        return []

    from langchain_core.documents import Document

    inp = record.get('input') or {}
    student = student_of(record)

    title = (inp.get('title') or '').strip()
    label = title if title else '未提供题目'
    essay_type = (result.get('essay_type') or inp.get('essay_type') or '').strip() or '体裁未限定'
    score = result.get('score')
    score_int = score if isinstance(score, int) else 0
    score_text = f'{score}/50' if isinstance(score, int) else '未评分'
    rating = (result.get('rating') or '').strip()
    grade = (inp.get('grade') or '').strip()

    base = {
        'owner': _meta_text(record.get('owner')),
        'student': _meta_text(student),
        'review_id': _meta_text(record.get('id')),
        'grade': _meta_text(grade),
        'essay_type': _meta_text(essay_type),
        'title': _meta_text(title),
        'score': score_int,
        'rating': _meta_text(rating),
        'created_at': _meta_text((record.get('created_at') or '')[:10]),
        'kind': 'summary',
    }

    def make(text: str, kind: str):
        text = (text or '').strip()
        return Document(page_content=text, metadata={**base, 'kind': kind}) if text else None

    docs: List = []

    # ① summary：一篇一条，用于回答"总体怎么样""这个学生学情如何"
    parts = [f'{student}的作文《{label}》（{grade}{essay_type}）得分{score_text}，评级{rating}。']
    dimensions = result.get('dimensions') or []
    if dimensions:
        dim_text = '、'.join(
            f'{d.get("name")}{d.get("score")}/{d.get("max_score")}'
            for d in dimensions if isinstance(d, dict) and d.get('name')
        )
        if dim_text:
            parts.append(f'各维度得分：{dim_text}。')
    if result.get('overall_comment'):
        parts.append(f'总体评价：{_clip(result["overall_comment"], 500)}')

    highlights = [h for h in (result.get('highlights') or []) if isinstance(h, str) and h.strip()]
    suggestions = [s for s in (result.get('suggestions') or []) if isinstance(s, str) and s.strip()]
    if highlights:
        parts.append('亮点：' + '；'.join(_clip(h, 80) for h in highlights) + '。')
    if suggestions:
        parts.append('改进建议：' + '；'.join(_clip(s, 80) for s in suggestions) + '。')

    doc = make(''.join(parts), 'summary')
    if doc:
        docs.append(doc)

    # ② analysis：内容/结构/语言/技巧/情感，每个方面一条
    analysis = result.get('analysis') or {}
    if isinstance(analysis, dict):
        for field, label_cn in ANALYSIS_LABELS.items():
            text = analysis.get(field)
            if isinstance(text, str) and text.strip():
                doc = make(f'《{label}》（{score_text}）{label_cn}方面点评：{_clip(text, 400)}', 'analysis')
                if doc:
                    docs.append(doc)

    # ③ issue：每条改进建议、每条原文纠正各一条
    for suggestion in suggestions:
        doc = make(f'《{label}》（{score_text}，{essay_type}）存在的问题与改进建议：{_clip(suggestion, 300)}', 'issue')
        if doc:
            docs.append(doc)

    corrections = result.get('corrections') or []
    if isinstance(corrections, list):
        for item in corrections:
            if not isinstance(item, dict):
                continue
            advice = (item.get('suggestion') or '').strip()
            if not advice:
                continue
            quote = (item.get('quote') or '').strip()
            text = f'《{label}》（{score_text}）原句「{_clip(quote, 80)}」存在表达问题，建议：{_clip(advice, 200)}'
            doc = make(text, 'issue')
            if doc:
                docs.append(doc)

    # ④ strength：每条亮点一条，用于回答"我哪里写得好"
    for highlight in highlights:
        doc = make(f'《{label}》（{score_text}）的优点与亮点：{_clip(highlight, 200)}', 'strength')
        if doc:
            docs.append(doc)

    return docs


def build_metrics(record: Dict) -> Optional[Dict]:
    """
    抽取学情聚合所需的紧凑字段。

    单独抽出来的理由：原始 payload 里含分页全文、行坐标、批注框等大字段，
    学情聚合完全用不到它们。把这几百字节抽出来存成侧车文件，
    聚合时就不必解析几十 KB 的 JSON。
    """
    if not record or record.get('status') != 'done':
        return None
    result = record.get('result') or {}
    if not result:
        return None
    inp = record.get('input') or {}
    return {
        'id': record.get('id') or '',
        'owner': (record.get('owner') or '').strip(),
        'student': student_of(record),
        'version': int(record.get('version') or 0),
        'created_at': (record.get('created_at') or '')[:10],
        'grade': (inp.get('grade') or '').strip(),
        'title': (inp.get('title') or '').strip(),
        'essay_type': (result.get('essay_type') or inp.get('essay_type') or '').strip(),
        'score': result.get('score') if isinstance(result.get('score'), int) else None,
        'rating': (result.get('rating') or '').strip(),
        'dimensions': [{'name': d.get('name'), 'score': d.get('score'), 'max_score': d.get('max_score')}
                       for d in (result.get('dimensions') or []) if isinstance(d, dict) and d.get('name')],
        'suggestions': [s for s in (result.get('suggestions') or []) if isinstance(s, str) and s.strip()],
        'corrections': [c.get('suggestion') for c in (result.get('corrections') or [])
                        if isinstance(c, dict) and (c.get('suggestion') or '').strip()],
        'highlights': [h for h in (result.get('highlights') or []) if isinstance(h, str) and h.strip()],
    }


# --------------------------------------------------------------------------- 索引

def _load_json(path: Path) -> Dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_json(path: Path, data: Dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    except Exception:
        pass


class ReviewIndex:
    """批改案例库：建索引、语义检索、确定性学情聚合。"""

    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root else REVIEW_ROOT
        self.db = self.root / 'reviews.sqlite3'
        self.metrics_file = self.root / 'consult_metrics.json'
        self._chroma = None
        self._metrics_cache: Optional[Dict] = None

    # ------------------------------------------------------------------ 读取

    def _query(self, sql: str, params: tuple = ()) -> List[tuple]:
        """只读打开数据库，不干扰工作台的乐观锁写入。"""
        if not self.db.exists():
            return []
        try:
            con = sqlite3.connect(f'file:{self.db}?mode=ro', uri=True, timeout=10)
            try:
                return con.execute(sql, params).fetchall()
            finally:
                con.close()
        except Exception:
            return []

    def _read_meta(self) -> Dict[str, int]:
        """轻量读取 id→version。不解析 payload，因此记录再多也只有毫秒级开销。"""
        rows = self._query('SELECT id, version FROM reviews ORDER BY rowid DESC LIMIT ?', (MAX_REVIEWS,))
        return {str(rid): int(ver or 0) for rid, ver in rows}

    def _read_record(self, review_id: str) -> Optional[Dict]:
        rows = self._query('SELECT payload FROM reviews WHERE id=?', (review_id,))
        if not rows:
            return None
        try:
            return json.loads(rows[0][0])
        except Exception:
            return None

    def _load_state(self) -> Dict[str, int]:
        return {str(k): int(v) for k, v in _load_json(Path(STATE_FILE)).items()}

    def _metrics(self, refresh: bool = False) -> Dict[str, Dict]:
        if not refresh and self._metrics_cache is not None:
            return self._metrics_cache
        self._metrics_cache = _load_json(self.metrics_file)
        return self._metrics_cache

    # ------------------------------------------------------------------ 学生

    def students(self, owner: Optional[str] = None) -> List[str]:
        """
        该账号名下出现过的学生名（按记录数降序）。

        名单从既有数据推导，不需要额外维护一张学生表——老师第一次上传作文时
        学生就已经「存在」了。学情检索的范围也因此天然被限制在真实存在的学生里。
        """
        counts: Dict[str, int] = {}
        for metric in self._metrics().values():
            if owner and metric.get('owner') != owner:
                continue
            name = metric.get('student') or ''
            if name:
                counts[name] = counts.get(name, 0) + 1
        return sorted(counts, key=lambda n: (-counts[n], n))

    def _for_student(self, student: str, owner: Optional[str] = None) -> List[Dict]:
        """取某学生的紧凑指标，按时间升序。owner 为 None 时不限提交者。"""
        student = (student or '').strip()
        matched = []
        for metric in self._metrics().values():
            if (metric.get('student') or '') != student:
                continue
            if owner and (metric.get('owner') or '') != owner:
                continue
            matched.append(metric)
        matched.sort(key=lambda m: (m.get('created_at') or '', m.get('id') or ''))
        return matched

    # ------------------------------------------------------------------ 建索引

    def _get_chroma(self):
        if self._chroma is not None:
            return self._chroma
        try:
            from langchain_chroma import Chroma
            from model.factory import embed_model

            if embed_model is None:
                return None
            self._chroma = Chroma(
                collection_name=COLLECTION_NAME,
                embedding_function=embed_model,
                persist_directory=chroma_conf['persist_directory'],
            )
            return self._chroma
        except Exception:
            return None

    def sync(self, force: bool = False) -> Dict:
        """
        增量同步批改记录到向量库与指标缓存。

        增量依据：`reviews` 表的 version 列。每次写入（批改完成 / 人工保存 /
        重启中断标记）都会推进 version，因此 version 变化 = 内容变化。
        变化的记录按 review_id **先删后加**，保证库里只有当前版本——
        否则同一篇作文的新旧两版评语会同时存在，检索时随机命中旧版。

        同时清理：数据库中已不存在的记录（记录被删除）。

        本方法在"无变化"时只做一次 `SELECT id, version`（毫秒级），
        不解析 payload、不加载指标文件、也不构造向量库客户端，
        因此可以在每次咨询前无负担地调用。

        并发安全：整个流程在模块级锁内执行（见 _SYNC_LOCK 的说明）。
        """
        with _SYNC_LOCK:
            return self._sync_locked(force)

    def _sync_locked(self, force: bool = False) -> Dict:
        alive = self._read_meta()

        # 快速路径：先判断有没有变化，再决定是否碰数据库与向量库
        if not force and self._metrics_cache is not None:
            state = self._load_state()
            changed = [rid for rid, ver in alive.items() if state.get(rid) != ver]
            stale = [rid for rid in state if rid not in alive]
            if not changed and not stale:
                return {'ok': True, 'added': 0, 'removed': 0, 'skipped': len(alive),
                        'reviews_done': len(self._metrics_cache), 'reviews_total': len(alive),
                        'reason': ''}

        store = self._get_chroma()
        state = self._load_state()
        metrics = dict(self._metrics(refresh=True))

        added = removed = skipped = 0
        pending: List[Tuple[str, List]] = []
        errors: List[str] = []

        # 1) 清理已删除的记录
        for stale_id in {rid for rid in list(state) if rid not in alive} | \
                        {rid for rid in list(metrics) if rid not in alive}:
            state.pop(stale_id, None)
            metrics.pop(stale_id, None)
            removed += 1
            pending.append((stale_id, []))

        # 2) 处理新增与变更
        for rid, version in alive.items():
            if not force and state.get(rid) == version and rid in metrics:
                skipped += 1
                continue
            record = self._read_record(rid)
            if record is None:
                continue
            metric = build_metrics(record)
            if metric is None:
                # 未完成 / 失败的记录：清掉旧索引与旧指标，
                # 避免把半成品当成学生的问题。
                metrics.pop(rid, None)
                pending.append((rid, []))
            else:
                metrics[rid] = metric
                docs = build_documents(record)
                if docs:
                    pending.append((rid, docs))
                    added += len(docs)
            state[rid] = version

        # 3) 写向量库（先删后加）
        if store is not None and pending:
            for rid, docs in pending:
                try:
                    store.delete(where={'review_id': rid})
                    if docs:
                        store.add_documents(docs)
                except Exception as exc:
                    errors.append(f'{rid[:8]}: {exc}')

        _save_json(Path(STATE_FILE), state)
        _save_json(self.metrics_file, metrics)
        self._metrics_cache = metrics

        return {
            'ok': store is not None and not errors,
            'added': added, 'removed': removed, 'skipped': skipped,
            'reviews_done': len(metrics), 'reviews_total': len(alive),
            'reason': ('向量模型不可用' if store is None else '; '.join(errors)),
        }

    def remove(self, review_id: str) -> None:
        """删除某篇记录的索引与指标（记录被删除时调用；sync 也会兜住这种情况）。"""
        with _SYNC_LOCK:
            state = self._load_state()
            state.pop(review_id, None)
            _save_json(Path(STATE_FILE), state)

            metrics = dict(self._metrics(refresh=True))
            metrics.pop(review_id, None)
            _save_json(self.metrics_file, metrics)
            self._metrics_cache = metrics

            store = self._get_chroma()
            if store is not None:
                try:
                    store.delete(where={'review_id': review_id})
                except Exception:
                    pass

    def stats(self) -> Dict:
        metrics = self._metrics()
        return {
            'reviews_indexed': len(metrics),
            'students': len({m.get('student') for m in metrics.values() if m.get('student')}),
        }

    # ------------------------------------------------------------------ 语义检索

    def search(self, query: str, student: str, owner: Optional[str] = None,
               kinds: Optional[Tuple[str, ...]] = None,
               k: int = None, threshold: float = None) -> List:
        """
        按学生范围检索相关批改片段。

        参数：
            query:   学生/老师的问题
            student: 目标学生（必填——跨学生检索会让建议张冠李戴）
            owner:   限定提交者。为 None 表示不限（学生查自己：无论作文由谁代传都能查到）；
                     老师咨询某个学生时传自己的账号，避免读到他人账号下的数据。
            kinds:   限定片段类型，如 ('issue',) 只看问题、('strength',) 只看亮点
            k / threshold: 召回条数与相似度阈值

        返回：
            [(Document, score), ...]，已按阈值过滤。异常一律返回空列表——
            检索失败不能中断咨询。
        """
        store = self._get_chroma()
        query = (query or '').strip()
        student = (student or '').strip()
        if store is None or not query or not student:
            return []

        clauses: List[Dict] = [{'student': student}]
        if owner:
            clauses.append({'owner': owner})
        if kinds:
            clauses.append({'kind': {'$in': list(kinds)}})
        where = clauses[0] if len(clauses) == 1 else {'$and': clauses}

        try:
            raw = store.similarity_search_with_relevance_scores(query, k=k or DEFAULT_K, filter=where)
        except Exception:
            return []

        limit = DEFAULT_THRESHOLD if threshold is None else threshold
        return [(d, s) for d, s in raw if s is not None and s >= limit]

    # ------------------------------------------------------------- 学情聚合

    def student_profile(self, student: str, owner: Optional[str] = None) -> Dict:
        """
        确定性学情聚合。

        这些数字全部来自直接计算（读指标缓存），**不经过模型，也不经过向量检索**。
        "平均分"这类数字一旦由模型生成就可能算错，而学情报告里算错平均分
        是不可接受的。
        """
        student = (student or '').strip()
        records = self._for_student(student, owner)
        if not records:
            return {'student': student, 'n_reviews': 0, 'has_data': False}

        scores: List[Dict] = []
        dim_agg: Dict[str, Dict] = {}
        issue_by_review: List[str] = []
        strength_by_review: List[str] = []

        for metric in records:
            scores.append({
                'date': metric.get('created_at') or '',
                'score': metric.get('score'),
                'rating': metric.get('rating') or '',
                'title': metric.get('title') or '',
                'essay_type': metric.get('essay_type') or '',
                'review_id': metric.get('id') or '',
            })
            for dim in (metric.get('dimensions') or []):
                name, value, maximum = _canonical_dim(dim), dim.get('score'), dim.get('max_score')
                if not name or not isinstance(value, int) or not isinstance(maximum, int) or maximum <= 0:
                    continue
                bucket = dim_agg.setdefault(name, {'sum_score': 0, 'sum_max': 0, 'n': 0})
                bucket['sum_score'] += value
                bucket['sum_max'] += maximum
                bucket['n'] += 1

            # 按「篇」归并本篇的全部问题/优点文本。
            # 口径很重要：若按「条」统计，一篇里提到三次标点就会让标点问题刷到 3 次，
            # 学生会误以为那是最严重的问题。按篇统计才得到「4篇里有3篇提到标点」。
            review_issues = list(metric.get('suggestions') or []) + list(metric.get('corrections') or [])
            if review_issues:
                issue_by_review.append('\n'.join(review_issues))
            if metric.get('highlights'):
                strength_by_review.append('\n'.join(metric['highlights']))

        valid_scores = [s['score'] for s in scores if isinstance(s['score'], int)]
        dim_rates = {}
        for name, bucket in dim_agg.items():
            if bucket['sum_max'] > 0:
                dim_rates[name] = {
                    'rate': float(round(bucket['sum_score'] / bucket['sum_max'], 3)),
                    'avg_score': float(round(bucket['sum_score'] / bucket['n'], 1)),
                    'n': bucket['n'],
                }

        # 弱项排序：得分率从低到高，用于回答"我最该补哪里"。
        # 只让样本量达标的维度参与结论——只出现过 1 次的维度（往往是某篇文章特有的
        # 体裁维度，满分与别篇都不同）得出"最薄弱"会误导，因此排除在结论之外，
        # 但仍保留在 dim_rates 里供模型自行参考。
        eligible = [(name, info) for name, info in dim_rates.items() if info['n'] >= MIN_DIM_SAMPLES]
        weak_dims = sorted(eligible, key=lambda kv: kv[1]['rate'])
        strong_dims = list(reversed(weak_dims))

        return {
            'student': student,
            'n_reviews': len(records),
            'has_data': True,
            'scores': scores,
            'avg_score': round(sum(valid_scores) / len(valid_scores), 1) if valid_scores else None,
            'best_score': max(valid_scores) if valid_scores else None,
            'worst_score': min(valid_scores) if valid_scores else None,
            'latest_score': valid_scores[-1] if valid_scores else None,
            'dim_rates': dim_rates,
            'weak_dims': [name for name, _ in weak_dims],
            'strong_dims': [name for name, _ in strong_dims],
            'low_confidence_dims': [n for n, i in dim_rates.items() if i['n'] < MIN_DIM_SAMPLES],
            'recurring_issues': self._tally(issue_by_review),
            'recurring_strengths': self._tally(strength_by_review),
            'trend': self._trend(valid_scores),
            'first_date': scores[0]['date'] if scores else '',
            'last_date': scores[-1]['date'] if scores else '',
        }

    @staticmethod
    def _tally(per_review_texts: List[str]) -> List[Dict]:
        """
        按主题词表归并问题/亮点，统计**有多少篇作文**的评语提到了该主题。

        入参是「每篇一份的合并文本」，不是扁平条目列表——这样才能得到
        「4篇里有3篇提到标点」这种可解释口径，而不是被重复条目刷高的计数。
        """
        counted: Dict[str, int] = {}
        for text in per_review_texts:
            hit = {aspect for aspect, words in ASPECT_KEYWORDS.items() if any(w in text for w in words)}
            for aspect in hit:
                counted[aspect] = counted.get(aspect, 0) + 1
        result = [{'aspect': k, 'count': v} for k, v in counted.items() if v > 0]
        result.sort(key=lambda item: (-item['count'], item['aspect']))
        return result

    @staticmethod
    def _trend(scores: List[int]) -> Dict:
        """
        最近三次与更早成绩对比，给出趋势描述。

        少于 5 篇时如实说样本不足：此时"更早"只有一两个样本，且不同体裁的作文
        分数本来就不直接可比，硬给趋势是误导。
        """
        if len(scores) < MIN_TREND_SAMPLES:
            return {'direction': '样本不足', 'delta': None, 'recent': scores[-3:],
                    'note': f'目前仅{len(scores)}篇，少于{MIN_TREND_SAMPLES}篇，不足以判断成绩趋势'}
        recent = scores[-3:]
        earlier = scores[:-3]
        delta = round(sum(recent) / len(recent) - sum(earlier) / len(earlier), 1)
        if delta >= 2:
            direction = '上升'
        elif delta <= -2:
            direction = '下降'
        else:
            direction = '基本持平'
        return {'direction': direction, 'delta': delta, 'recent': recent}


# --------------------------------------------------------------------------- 渲染

def render_profile(profile: Dict) -> str:
    """
    把学情聚合渲染成可注入 prompt 的文本。

    刻意保留真实的数字与篇数：这些是模型无法自行推断的事实，
    也是防止它编造"你一共有20篇作文"这类内容的唯一手段。
    """
    if not profile or not profile.get('has_data'):
        student = (profile or {}).get('student') or '该学生'
        return f'（{student}暂无已完成的批改记录）'

    lines = [f'学生：{profile["student"]}']
    lines.append(f'已完成批改：{profile["n_reviews"]}篇（{profile["first_date"]} 至 {profile["last_date"]}）')
    if profile.get('avg_score') is not None:
        lines.append(f'平均分：{profile["avg_score"]}/50（最高{profile["best_score"]}，最低{profile["worst_score"]}，最近一次{profile["latest_score"]}）')

    trend = profile.get('trend') or {}
    if trend.get('direction') and trend['direction'] != '样本不足':
        lines.append(f'成绩趋势：{trend["direction"]}（最近三次 {trend.get("recent")}，较此前变化 {trend.get("delta")} 分）')
    elif trend.get('note'):
        lines.append(f'成绩趋势：{trend["note"]}')

    dim_rates = profile.get('dim_rates') or {}
    if dim_rates:
        ordered = sorted(dim_rates.items(), key=lambda kv: kv[1]['rate'])
        # 只报得分率与出现篇数：不同体裁的维度满分不同，绝对分数不可比，
        # 得分率才是跨体裁、跨篇数可比的指标。
        dim_text = '；'.join(f'{name} 得分率{round(info["rate"] * 100)}%（{info["n"]}篇）'
                            for name, info in ordered)
        lines.append(f'各维度得分率（由低到高）：{dim_text}')
        if profile.get('weak_dims'):
            weakest = profile['weak_dims'][0]
            info = dim_rates[weakest]
            lines.append(f'最薄弱维度：{weakest}（得分率{round(info["rate"] * 100)}%，{info["n"]}篇）')
        else:
            lines.append('最薄弱维度：篇数不足，暂无足够样本支撑结论')
    if profile.get('low_confidence_dims'):
        lines.append(f'（样本过少的维度，仅供参考不作结论：{"、".join(profile["low_confidence_dims"])}）')

    recurring = profile.get('recurring_issues') or []
    if recurring:
        items = '；'.join(f'{i["aspect"]}（{i["count"]}篇提到）' for i in recurring[:6])
        lines.append(f'反复出现的问题：{items}')

    strengths = profile.get('recurring_strengths') or []
    if strengths:
        items = '；'.join(f'{i["aspect"]}（{i["count"]}篇）' for i in strengths[:5])
        lines.append(f'相对稳定的优点：{items}')

    # 「最近 N 篇」由 MOST_RECENT_ESSAYS 配置控制（需求 D3，默认 3）
    recent_essays = (profile.get('scores') or [])[-MOST_RECENT_ESSAYS:]
    if recent_essays:
        items = '；'.join(
            f'{s["date"]}《{s["title"] or "未命题"}》{s["score"]}分{s["rating"]}' for s in recent_essays
        )
        lines.append(f'最近几篇：{items}')

    return '\n'.join(lines)


KIND_LABELS = {
    'summary': '整体',
    'analysis': '分项点评',
    'issue': '问题',
    'strength': '亮点',
}


def render_hits(hits: List, header: str = '历史批改片段') -> str:
    """
    把检索到的批改片段渲染成可注入 prompt 的文本。

    带上片段类型（整体/分项点评/问题/亮点）：模型需要知道每条是"批评"还是"表扬"，
    否则可能把亮点当成问题来提建议。
    """
    if not hits:
        return NO_CASE_NOTE
    blocks = []
    for index, (doc, _score) in enumerate(hits, start=1):
        meta = doc.metadata or {}
        stamp = meta.get('created_at', '-')
        kind = KIND_LABELS.get(meta.get('kind'), '片段')
        blocks.append(f'【{header}{index} · {stamp} · {kind}】{doc.page_content.strip()}')
    return '\n'.join(blocks)
