"""
咨询记忆服务（滚动摘要 + 长期语义记忆）

解决两个此前没覆盖的问题：
    1. 短期记忆只有最近 6 条 / 2000 字，早于窗口的内容在一次刷新后彻底消失，
       用户问「我们最开始聊的那个问题」时模型完全接不上。
       → 滚动摘要：窗口外的旧消息折叠成一段不超过 300 字的摘要，随会话增量合并。
    2. 换一个会话（甚至第二天）就完全失忆，无法累积「这个学生总在开头写不具体」
       这类长期事实。
       → 长期记忆：从对话里抽取用户本人说过、且长期有效的信息存入 user_memories，
       下个会话按语义相关度取回注入。

为什么摘要与抽取放在后台线程：
    两者都要调用大模型，放在请求路径上会直接拉长回答时间。回答落盘之后异步整理，
    失败只记日志——记忆是增强项，不该让对话失败。
"""

import json
import math
import re
import threading
from datetime import datetime
from typing import Dict, List, Optional

from services.memory_store import MemoryStore, pack_embedding, unpack_embedding
from utils.config_handler import chroma_conf
from utils.logger_handler import logger

_CONSULT = chroma_conf.get('consult') or {}

# 最近 N 条消息保持原文注入，更早的折叠进摘要。与 chat_memory.MAX_MESSAGES 对齐：
# 模型实际能看到的就是这 N 条 + 摘要，两个数字错开会出现"记忆空洞"。
RECENT_WINDOW = max(2, int(_CONSULT.get('memory_recent_window', 6)))
SUMMARY_MAX_CHARS = max(120, int(_CONSULT.get('memory_summary_max_chars', 300)))
# 累计新增多少条消息才抽取一次长期记忆。抽取要调用模型，不能每轮都做。
MEMORY_MIN_NEW_MESSAGES = max(2, int(_CONSULT.get('memory_min_new_messages', 8)))
MEMORY_TOP_K = max(1, int(_CONSULT.get('memory_top_k', 4)))
# 条目数不超过该值时直接全量注入：小规模下语义检索是负收益
# （多一次 embedding 调用、还要调阈值），与知识库 full_inject_limit 的取舍一致。
MEMORY_INLINE_LIMIT = max(1, int(_CONSULT.get('memory_inline_limit', 8)))
MEMORY_MAX_ITEMS = max(1, int(_CONSULT.get('memory_max_items_per_extract', 5)))

KINDS = ('fact', 'preference', 'weakness', 'goal')
KIND_LABELS = {
    'fact': '情况',
    'preference': '偏好',
    'weakness': '薄弱点',
    'goal': '目标',
}

SUMMARY_PROMPT = """你是对话记忆整理助手。请把「已有摘要」与「新增对话」合并成一段中文摘要。

要求：
1. 总长度不超过 {max_chars} 字；
2. 保留：用户问过的核心问题、已经给出的结论、用户明确说过的自身情况（年级、写作习惯、
   薄弱点、目标）、尚未解决的问题；
3. 不要编造对话里没有的信息，不要评价语气，不要记录寒暄；
4. 直接输出摘要正文，不要加标题、不要解释。

已有摘要：
{summary}

新增对话：
{dialogue}
"""

EXTRACT_PROMPT = """你是记忆整理助手。请从下面的对话里提取关于「这位用户」长期有效的信息。

只提取用户明确说过的、以后仍然适用的内容：
- fact：自身情况（年级、学校要求、写作基础等）
- preference：偏好（喜欢的写法、希望的讲解方式等）
- weakness：反复出现的薄弱点
- goal：明确表达的目标

不要提取一次性的具体问题，不要猜测，不要评价语气。
只输出 JSON 数组，元素形如 {{"kind": "fact", "content": "..."}}，最多 {max_items} 条；
没有可提取的内容就输出 []。

对话：
{dialogue}
"""

STORE = MemoryStore()

_running = set()
_running_lock = threading.Lock()


# ---------------------------------------------------------------- 模型调用

def _chat_model():
    """惰性获取聊天模型；未就绪时返回 None（记忆整理失败不影响对话）。"""
    try:
        from model.factory import get_chat_model
        return get_chat_model()
    except Exception as exc:
        logger.warning('[记忆] 模型不可用: %s', exc)
        return None


def _invoke(prompt: str, label: str) -> Optional[str]:
    """调用模型并返回正文；任何异常返回 None，由调用方决定是否推进游标。"""
    model = _chat_model()
    if model is None:
        return None
    try:
        response = model.invoke(prompt)
        content = response.content if hasattr(response, 'content') else str(response)
        content = (content or '').strip()
        return content or None
    except Exception as exc:
        logger.warning('[记忆] %s调用失败: %s', label, exc)
        return None


def _embed_documents(texts: List[str]) -> List[List[float]]:
    """批量向量化记忆条目；不可用时返回空列表（条目仍会入库，只是暂不参与语义排序）。"""
    try:
        from model.factory import embed_model
        if embed_model is None or not texts:
            return []
        return embed_model.embed_documents(list(texts))
    except Exception as exc:
        logger.warning('[记忆] 向量化失败: %s', exc)
        return []


def _embed_query(text: str) -> List[float]:
    """向量化检索问句。"""
    try:
        from model.factory import embed_model
        if embed_model is None or not text:
            return []
        return embed_model.embed_query(text)
    except Exception as exc:
        logger.warning('[记忆] 问句向量化失败: %s', exc)
        return []


# ---------------------------------------------------------------- 文本工具

def _dialogue_text(messages: List[Dict], limit: int = 40, clip: int = 400) -> str:
    """把消息渲染成摘要/抽取用的对话文本，做条数与单条长度双重截断。"""
    lines = []
    for item in (messages or [])[-limit:]:
        content = (item.get('content') or '').strip()
        if not content:
            continue
        if len(content) > clip:
            content = content[:clip] + '……'
        role = '学生' if item.get('role') == 'user' else '老师'
        lines.append(f'{role}：{content}')
    return '\n'.join(lines)


def _parse_items(raw: str) -> Optional[List[Dict]]:
    """
    解析抽取结果。

    返回 None 表示"解析失败"（游标不推进，下次重试）；返回 [] 表示
    "确实没有可提取的内容"（游标推进，避免同一段对话反复调用模型）。
    """
    if not raw:
        return []
    match = re.search(r'\[[\s\S]*\]', raw)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except (TypeError, ValueError):
        return None
    if not isinstance(data, list):
        return None

    items = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        content = (entry.get('content') or '').strip()
        if not content or len(content) > 80:
            continue
        kind = entry.get('kind')
        items.append({
            'kind': kind if kind in KINDS else 'fact',
            'content': content,
        })
        if len(items) >= MEMORY_MAX_ITEMS:
            break
    return items


def _cosine(left: List[float], right: List[float]) -> float:
    """余弦相似度；维度不一致或为零向量时返回 0（视为不相关）。"""
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    norm_left = math.sqrt(sum(a * a for a in left))
    norm_right = math.sqrt(sum(b * b for b in right))
    if not norm_left or not norm_right:
        return 0.0
    return dot / (norm_left * norm_right)


# ---------------------------------------------------------------- 读取（注入 prompt）

def get_session_summary(owner: str, session_id: str) -> str:
    """取某会话的滚动摘要；不存在时返回空串。"""
    if not owner or not session_id:
        return ''
    try:
        return (STORE.get_session_state(owner, session_id).get('summary') or '').strip()
    except Exception as exc:
        logger.warning('[记忆] 读取会话摘要失败: %s', exc)
        return ''


def retrieve_memories(owner: str, question: str, limit: int = None) -> List[Dict]:
    """
    取与当前问题相关的长期记忆。

    条目少（<= MEMORY_INLINE_LIMIT）时全量返回：这个规模下语义检索只会多一次
    embedding 调用，还可能因为阈值把相关内容过滤掉。条目多时才做向量排序。
    """
    if not owner:
        return []
    try:
        items = STORE.list_memories(owner)
    except Exception as exc:
        logger.warning('[记忆] 读取长期记忆失败: %s', exc)
        return []
    if not items:
        return []

    limit = max(1, int(limit or MEMORY_TOP_K))
    if len(items) <= MEMORY_INLINE_LIMIT:
        # 小规模全量注入：条数已被 MEMORY_INLINE_LIMIT 兜住，最多也就几条短句，
        # 比"多一次 embedding + 阈值调参"更稳。
        return items

    query_vector = _embed_query((question or '').strip())
    if not query_vector:
        return items[:limit]

    scored, unscored = [], []
    for item in items:
        vector = unpack_embedding(item.get('embedding'))
        if vector:
            scored.append((_cosine(query_vector, vector), item))
        else:
            unscored.append(item)
    if not scored:
        return items[:limit]

    scored.sort(key=lambda pair: pair[0], reverse=True)
    result = [item for _, item in scored[:limit]]
    # 向量缺失的旧条目仍然可能有用，补齐到 limit，避免它们永远无法被注入
    if len(result) < limit:
        result.extend(unscored[:limit - len(result)])
    return result


def build_prompt_block(owner: str, session_id: str, question: str) -> str:
    """
    组装注入 prompt 的记忆文本块（会话摘要 + 长期记忆）。

    返回空串表示没有可用记忆，调用方无需额外分支。
    """
    blocks = []

    summary = get_session_summary(owner, session_id)
    if summary:
        blocks.append(f'【本会话更早内容的摘要】\n{summary}')

    memories = retrieve_memories(owner, question)
    if memories:
        lines = [
            f'- [{KIND_LABELS.get(item.get("kind"), "信息")}] {item.get("content")}'
            for item in memories
        ]
        blocks.append(
            '【关于这位用户的长期记忆】\n' + '\n'.join(lines) +
            '\n以上内容来自用户本人此前的表述，回答时可用于贴合他的情况；与当前问题无关时不要强行引用。'
        )

    return '\n\n'.join(blocks)


# ---------------------------------------------------------------- 后台整理

def schedule_refresh(owner: str, session_id: str, messages: List[Dict]) -> None:
    """
    在后台线程整理摘要与长期记忆。

    同一会话同一时刻只允许一个整理任务：两个线程同时读同一个游标会重复摘要、
    重复抽取（多花一次模型调用，还可能写出两条重复记忆）。
    """
    if not owner or not session_id or not messages:
        return
    key = (owner, session_id)
    with _running_lock:
        if key in _running:
            return
        _running.add(key)
    threading.Thread(
        target=_refresh,
        args=(owner, session_id, list(messages)),
        name='memory-refresh',
        daemon=True,
    ).start()


def _refresh(owner: str, session_id: str, messages: List[Dict]) -> None:
    try:
        refresh_now(owner, session_id, messages)
    except Exception as exc:
        logger.warning('[记忆] 后台整理失败: %s', exc)
    finally:
        with _running_lock:
            _running.discard((owner, session_id))


def refresh_now(owner: str, session_id: str, messages: List[Dict]) -> None:
    """
    同步执行一次整理（后台线程调用，也便于单独验证）。

    两条独立游标：
        covered_upto：摘要已覆盖到第几条消息；
        memory_upto：长期记忆已抽取到第几条消息。
    任何一步失败都不推进对应游标，下次继续从断点重试。
    """
    state = STORE.get_session_state(owner, session_id)
    covered = int(state.get('covered_upto') or 0)
    memory_upto = int(state.get('memory_upto') or 0)
    total = len(messages)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 1) 滚动摘要：最近 RECENT_WINDOW 条仍以原文注入，只把滑出窗口的部分折叠进摘要
    boundary = max(0, total - RECENT_WINDOW)
    if boundary > covered:
        segment = messages[covered:boundary]
        dialogue = _dialogue_text(segment, limit=30)
        if dialogue:
            summary = _invoke(
                SUMMARY_PROMPT.format(
                    max_chars=SUMMARY_MAX_CHARS,
                    summary=(state.get('summary') or '（暂无）'),
                    dialogue=dialogue,
                ),
                '滚动摘要',
            )
            if summary:
                summary = summary[:SUMMARY_MAX_CHARS]
                STORE.save_summary(owner, session_id, summary, boundary, memory_upto, now)
                covered = boundary

    # 2) 长期记忆：攒够一批再抽取，避免每轮一次模型调用
    if total - memory_upto >= MEMORY_MIN_NEW_MESSAGES:
        dialogue = _dialogue_text(messages[memory_upto:], limit=20)
        if dialogue:
            raw = _invoke(
                EXTRACT_PROMPT.format(max_items=MEMORY_MAX_ITEMS, dialogue=dialogue),
                '长期记忆抽取',
            )
            items = _parse_items(raw)
            if items is not None:
                _save_items(owner, items, now)
                STORE.save_memory_upto(owner, session_id, total, now)


def _save_items(owner: str, items: List[Dict], now: str) -> None:
    """写入抽取到的记忆条目（已存在的跳过，避免重复向量化）。"""
    if not items:
        return
    try:
        existing = {item['content'] for item in STORE.list_memories(owner)}
    except Exception:
        existing = set()
    fresh = [item for item in items if item['content'] not in existing]
    if not fresh:
        return

    vectors = _embed_documents([item['content'] for item in fresh])
    for index, item in enumerate(fresh):
        vector = vectors[index] if index < len(vectors) else None
        try:
            STORE.upsert_memory(owner, item['kind'], item['content'], pack_embedding(vector), now)
        except Exception as exc:
            logger.warning('[记忆] 写入记忆失败: %s', exc)
