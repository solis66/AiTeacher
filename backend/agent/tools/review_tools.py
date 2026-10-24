"""
咨询 Agent 的批改记录工具（只读、仅限本人）

为什么单独一个模块：
    `agent_tools.py` 装的是「知识检索」类工具（返回资料片段），这里是「数据查询」类：
    直接读该账号的批改记录。两者的数据边界、失败模式与输出形态都不同，混在一起会让
    「只读本人数据」这条约束变得难以复核。

数据隔离是机制而不是提示词：
    owner 来自 `ToolRuntime.context`（由 /chat 的 X-Username 经 ReactAgent 注入），
    模型可见的入参 schema 里根本没有账号字段——它无法指定要查谁。
    `ReviewStore.get(record_id, owner)` 也以 owner 为条件，跨账号 id 只会查不到。

输出形态：
    返回纯文本摘录而不是 JSON。历史 payload 里有分页全文、批注坐标等几十 KB 的大字段，
    原样回给模型会直接吃掉上下文，而且没有一处是回答需要的。
"""

import re
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from langchain_core.tools import tool
from langgraph.prebuilt.tool_node import ToolRuntime

from services.review_store import ReviewStore
from utils.path_tool import get_abs_path

# 单次详情返回的最大字符数：够写清一篇的批改结论，又不至于把上下文挤满
MAX_DETAIL_CHARS = 1500
# 摘要里最多列出几条"主要问题"
SUMMARY_ISSUES = 2
# 检索条数上限（模型给再大的数也只取这么多）
MAX_SEARCH_LIMIT = 8
DEFAULT_SEARCH_LIMIT = 5
# 原文片段长度：只够模型对上"开头/结尾"这类具体位置
BODY_PREVIEW_CHARS = 400

_ROOT = get_abs_path('data/reviews')
_store: Optional[ReviewStore] = None
_store_lock = threading.Lock()


@dataclass
class AgentContext:
    """Agent 单次运行的上下文（目前只有数据隔离键）。"""

    owner: str = ''


def _get_store() -> ReviewStore:
    """进程内单例：ReviewStore 只做 SQLite 读写，复用连接配置即可。"""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = ReviewStore(_ROOT)
    return _store


def _owner(runtime: ToolRuntime) -> str:
    """从运行时上下文取当前账号；取不到时返回空串（调用方按"无权限"处理）。"""
    context = getattr(runtime, 'context', None)
    return (getattr(context, 'owner', '') or '').strip()


def _text_list(values) -> List[str]:
    """把 payload 里的字符串列表清洗成非空文本。"""
    return [str(item).strip() for item in (values or []) if isinstance(item, str) and item.strip()]


def _correction_list(values) -> List[str]:
    """corrections 是 [{'suggestion': ...}] 结构，只取建议正文。"""
    result = []
    for item in values or []:
        if isinstance(item, dict):
            text = (item.get('suggestion') or '').strip()
        else:
            text = str(item).strip()
        if text:
            result.append(text)
    return result


def _normalize(text: str) -> str:
    """关键词匹配前的归一化：去掉空白、英文转小写（中文不受影响）。"""
    return re.sub(r'\s+', '', (text or '')).lower()


def _haystack(record: Dict) -> str:
    """一篇记录里参与关键词匹配的文本。"""
    result = record.get('result') or {}
    inp = record.get('input') or {}
    parts = [
        inp.get('title') or '',
        inp.get('body') or '',
        result.get('overall_comment') or '',
        ' '.join(_text_list(result.get('suggestions'))),
        ' '.join(_text_list(result.get('highlights'))),
    ]
    return _normalize(' '.join(parts))


def _parse_day(text: str) -> Optional[datetime]:
    """记录时间形如 'YYYY-MM-DD HH:MM:SS'，解析失败返回 None（视为不参与时间过滤）。"""
    text = (text or '').strip()
    if len(text) >= 19:
        try:
            return datetime.strptime(text[:19], '%Y-%m-%d %H:%M:%S')
        except ValueError:
            pass
    try:
        return datetime.strptime(text[:10], '%Y-%m-%d')
    except ValueError:
        return None


def _record_id(record: Dict) -> str:
    return str(record.get('id') or '')


def _score_of(record: Dict) -> Optional[int]:
    score = (record.get('result') or {}).get('score')
    return score if isinstance(score, int) else None


def _essay_type(record: Dict) -> str:
    result = record.get('result') or {}
    inp = record.get('input') or {}
    return (result.get('essay_type') or inp.get('essay_type') or '').strip()


@tool(description=(
    '检索当前账号（提问者本人）的批改记录，可按体裁、分数区间、最近天数、关键词筛选。'
    '返回每条记录的 id、日期、题目、体裁、分数与主要问题。'
    '需要查看某一篇的完整批改时，把返回的 id 传给 review_detail。'
    '只能查提问者本人的记录，无法查询他人。'
))
def search_reviews(runtime: ToolRuntime[AgentContext],
                   query: str = '',
                   essay_type: str = '',
                   min_score: int = 0,
                   max_score: int = 0,
                   days: int = 0,
                   limit: int = DEFAULT_SEARCH_LIMIT) -> str:
    """
    检索本人的批改记录。

    @param {string} query - 关键词（匹配题目、原文、总评、建议），可空
    @param {string} essay_type - 体裁（议论文/记叙文/说明文），可空
    @param {int} min_score - 最低总分，0 表示不限
    @param {int} max_score - 最高总分，0 表示不限
    @param {int} days - 只看最近 N 天，0 表示不限
    @param {int} limit - 返回条数，默认 5，上限 8
    """
    owner = _owner(runtime)
    if not owner:
        return '无法确定当前账号，已跳过查询。'

    records = _get_store().list(owner) or []
    keywords = [term for term in re.split(r'\s+', (query or '').strip()) if term]
    normalized_keywords = [_normalize(term) for term in keywords]
    min_score = int(min_score or 0)
    max_score = int(max_score or 0)
    days = int(days or 0)
    limit = max(1, min(int(limit or DEFAULT_SEARCH_LIMIT), MAX_SEARCH_LIMIT))
    deadline = datetime.now() - timedelta(days=days) if days > 0 else None

    matched = []
    for record in records:
        if record.get('status') != 'done' or not record.get('result'):
            continue
        if essay_type and _essay_type(record) != essay_type.strip():
            continue
        score = _score_of(record)
        if min_score > 0 and (score is None or score < min_score):
            continue
        if max_score > 0 and (score is None or score > max_score):
            continue
        if deadline is not None:
            created = _parse_day(record.get('created_at') or '')
            if created is not None and created < deadline:
                continue
        hits = 0
        if normalized_keywords:
            haystack = _haystack(record)
            hits = sum(1 for term in normalized_keywords if term and term in haystack)
            if hits == 0:
                continue
        matched.append({'record': record, 'hits': hits, 'created': record.get('created_at') or ''})

    matched.sort(key=lambda item: (item['hits'], item['created']), reverse=True)
    if not matched:
        return '没有找到符合条件的批改记录。可放宽分数区间/时间范围，或去掉关键词再试。'

    lines = [f'找到 {len(matched)} 条符合条件的记录，以下为前 {min(limit, len(matched))} 条：']
    for index, item in enumerate(matched[:limit], start=1):
        record = item['record']
        result = record.get('result') or {}
        score = _score_of(record)
        issues = _text_list(result.get('suggestions'))[:SUMMARY_ISSUES]
        lines.append(
            f'{index}. id={_record_id(record)} | {(record.get("created_at") or "")[:10]} | '
            f'《{(record.get("input") or {}).get("title") or "无题"}》 | '
            f'{_essay_type(record) or "未标注体裁"} | '
            f'{score if score is not None else "无分数"}分 | {result.get("rating") or "无等级"}'
        )
        if issues:
            lines.append('   主要问题：' + '；'.join(issues))
    lines.append('提示：查看某一篇的完整批改，请调用 review_detail 并传入对应 id。')
    return '\n'.join(lines)


@tool(description=(
    '查看当前账号某一条批改记录的完整详情：五维得分、总评、改进建议、亮点、原文纠正与原文片段。'
    'record_id 必须来自 search_reviews 返回的 id。只能查提问者本人的记录。'
))
def review_detail(runtime: ToolRuntime[AgentContext], record_id: str) -> str:
    """
    查看单条批改详情。

    @param {string} record_id - 批改记录 id（来自 search_reviews）
    """
    owner = _owner(runtime)
    if not owner:
        return '无法确定当前账号，已跳过查询。'
    record_id = (record_id or '').strip()
    if not record_id:
        return '缺少 record_id，请先用 search_reviews 检索，再把返回的 id 传进来。'

    record = _get_store().get(record_id, owner)
    if record is None:
        # 他人账号的 id 同样会落到这里——不区分"不存在"与"无权访问"，避免被用来探测
        return '未找到该记录。请确认 id 来自 search_reviews 的返回结果。'
    status = record.get('status') or ''
    if status != 'done' or not record.get('result'):
        return f'该记录当前状态为「{status or "未知"}」，还没有可查看的批改结果。'

    result = record.get('result') or {}
    inp = record.get('input') or {}
    score = _score_of(record)
    dims = result.get('dimensions') or []

    lines = [
        '【批改详情】',
        f'题目：{inp.get("title") or "无题"}',
        f'体裁：{_essay_type(record) or "未标注"}',
        f'日期：{(record.get("created_at") or "")[:10]}',
        f'总分：{score if score is not None else "无"} / 50（{result.get("rating") or "无等级"}）',
    ]
    if dims:
        parts = []
        for dim in dims:
            if not isinstance(dim, dict) or not dim.get('name'):
                continue
            parts.append(f'{dim.get("name")} {dim.get("score")}/{dim.get("max_score")}')
        if parts:
            lines.append('五维得分：' + '；'.join(parts))
    if (result.get('overall_comment') or '').strip():
        lines.append('总评：' + result['overall_comment'].strip())

    for label, values in (
        ('改进建议', _text_list(result.get('suggestions'))),
        ('亮点', _text_list(result.get('highlights'))),
        ('原文纠正', _correction_list(result.get('corrections'))),
    ):
        if values:
            lines.append(f'{label}：')
            lines.extend(f'- {item}' for item in values)

    body = (inp.get('body') or '').strip()
    if body:
        lines.append('原文（节选）：')
        lines.append(body[:BODY_PREVIEW_CHARS] + ('……' if len(body) > BODY_PREVIEW_CHARS else ''))
    else:
        lines.append('原文：提交的是图片，原文见批改页面的识别结果。')

    text = '\n'.join(lines)
    if len(text) > MAX_DETAIL_CHARS:
        text = text[:MAX_DETAIL_CHARS] + '……（内容过长，已截断）'
    return text
