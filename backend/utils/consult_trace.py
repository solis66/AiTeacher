"""
咨询请求的结构化观测记录（logs/consult_trace.jsonl）

为什么需要：
    指标来源散在三个层：检索层知道命中数与分数，Agent 层知道调了哪些工具，
    接口层知道耗时与错误。没有统一载体时，线上只能翻多个日志按时间对齐，
    回答不了"这次为什么慢 / 为什么没调工具 / 上下文到底多大"。

做法：
    每个咨询请求生成 trace_id，随调用链显式传递（Agent 侧挂在 LangGraph 的
    runtime context 上）。各层只往登记表里记一笔，请求结束时统一落一行 JSONL。
    不用 contextvars：工具可能在别的线程执行，contextvar 会丢；
    挂在 runtime context 上的 trace_id，工具层一定拿得到。

隐私：
    不落原始问句与回答，只落长度、账号哈希与必要统计；
    case_query 与既有检索日志保持同一口径（截断 200 字）。

可靠性：
    所有写日志动作都吞异常——观测失败绝不能让对话失败。
    客户端断流时 finish 不会执行，因此 start 时按时间清理超期条目。
"""

import hashlib
import json
import threading
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from utils.logger_handler import logger
from utils.path_tool import get_abs_path

TRACE_FILE = get_abs_path('logs/consult_trace.jsonl')
# 未结束的 trace 最多保留多久（秒）：断流/异常时 finish 不会执行，
# 不清扫的话内存里的登记表只增不减。
MAX_PENDING_SECONDS = 1800
# 工具入参在记录里最多保留多少字符（足够判断"传了什么条件"，又不至于带出长文本）
MAX_ARGS_CHARS = 200
# case_query 与 consult_retrieval.jsonl 保持一致
MAX_QUERY_CHARS = 200

_lock = threading.Lock()
_pending: Dict[str, Dict] = {}


def hash_owner(owner: str) -> str:
    """账号哈希：既能按用户聚合，又不把账号明文写进日志。"""
    return hashlib.sha256((owner or '').encode('utf-8')).hexdigest()[:8]


def start(owner: str, kind: str = 'consultation') -> str:
    """
    开启一条 trace，返回 trace_id。

    参数：
        owner: 当前账号（只保存哈希）
        kind:  请求类型（目前只有 consultation）

    返回：
        str - trace_id；任何异常都返回空串，调用方按"无观测"处理
    """
    try:
        trace_id = uuid.uuid4().hex[:12]
        now = time.monotonic()
        with _lock:
            _prune(now)
            _pending[trace_id] = {
                'trace_id': trace_id,
                'ts': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'kind': kind,
                'owner_hash': hash_owner(owner),
                'started': now,
                'first_token_ms': None,
                'tools': [],
            }
        return trace_id
    except Exception as exc:
        logger.warning('[观测] 创建 trace 失败: %s', exc)
        return ''


def _prune(now: float) -> None:
    expired = [key for key, item in _pending.items() if now - item['started'] > MAX_PENDING_SECONDS]
    for key in expired:
        _pending.pop(key, None)


def _update(trace_id: str, **fields) -> None:
    if not trace_id:
        return
    try:
        with _lock:
            item = _pending.get(trace_id)
            if item is not None:
                item.update(fields)
    except Exception:
        pass


def mark_context(trace_id: str, scope: str = '', n_cases: int = 0,
                 top_scores: Optional[List[float]] = None, case_query: str = '') -> None:
    """记录检索层结果（范围解析、命中数、最高分、实际检索问句）。"""
    _update(
        trace_id,
        scope=scope,
        n_cases=int(n_cases or 0),
        top_scores=list(top_scores or [])[:5],
        case_query=(case_query or '')[:MAX_QUERY_CHARS],
    )


def mark_prompt(trace_id: str, prompt_chars: int, memory_chars: int) -> None:
    """记录上下文成本：主提示词长度与记忆块长度（字符数）。"""
    _update(trace_id, prompt_chars=int(prompt_chars or 0), memory_chars=int(memory_chars or 0))


def mark_degraded(trace_id: str, reason: str = '') -> None:
    """标记本次回答走了降级路径（Agent 失败/空响应 → 直接调模型）。"""
    item = _read(trace_id)
    if item is None:
        return
    _update(trace_id, degraded=True, degraded_reason=(reason or '')[:120])


def mark_first_token(trace_id: str) -> None:
    """记录首字时间：流式回答的实际体感延迟。"""
    item = _read(trace_id)
    if item is None or item.get('first_token_ms') is not None:
        return
    try:
        _update(trace_id, first_token_ms=int((time.monotonic() - item['started']) * 1000))
    except Exception:
        pass


def record_tool(trace_id: str, name: str, args, elapsed_ms: int, ok: bool, result_chars: int) -> None:
    """记录一次工具调用（由 middleware 在工具执行后调用）。"""
    if not trace_id:
        return
    try:
        text = json.dumps(args, ensure_ascii=False, default=str) if args is not None else ''
    except Exception:
        text = str(args)
    entry = {
        'name': (name or '')[:40],
        'args': text[:MAX_ARGS_CHARS],
        'ms': round(float(elapsed_ms or 0), 1),
        'ok': bool(ok),
        'result_chars': int(result_chars or 0),
    }
    try:
        with _lock:
            item = _pending.get(trace_id)
            if item is not None:
                item['tools'].append(entry)
    except Exception:
        pass


def _read(trace_id: str) -> Optional[Dict]:
    if not trace_id:
        return None
    try:
        with _lock:
            return _pending.get(trace_id)
    except Exception:
        return None


def finish(trace_id: str, answer_chars: int = 0, error: str = '', total_ms: int = None) -> None:
    """
    结束并落盘一行 JSONL。

    参数：
        answer_chars: 回答正文长度（不落正文本身）
        error:        错误摘要（为空表示正常完成）
        total_ms:     总耗时；不传时按 started 计算
    """
    if not trace_id:
        return
    try:
        with _lock:
            item = _pending.pop(trace_id, None)
        if not item:
            return
        if total_ms is None:
            total_ms = int((time.monotonic() - item['started']) * 1000)
        record = {
            'trace_id': item['trace_id'],
            'ts': item['ts'],
            'kind': item['kind'],
            'owner_hash': item['owner_hash'],
            'scope': item.get('scope', ''),
            'n_cases': item.get('n_cases', 0),
            'top_scores': item.get('top_scores', []),
            'case_query': item.get('case_query', ''),
            'prompt_chars': item.get('prompt_chars', 0),
            'memory_chars': item.get('memory_chars', 0),
            'tools': item.get('tools', []),
            'first_token_ms': item.get('first_token_ms'),
            'total_ms': total_ms,
            'answer_chars': int(answer_chars or 0),
            'degraded': bool(item.get('degraded', False)),
            'degraded_reason': item.get('degraded_reason', ''),
            'error': (error or '')[:200],
        }
        _append(record)
    except Exception as exc:
        logger.warning('[观测] 写入 trace 失败: %s', exc)


def _append(record: Dict) -> None:
    try:
        with open(TRACE_FILE, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + '\n')
    except Exception as exc:
        logger.warning('[观测] 追加 trace 文件失败: %s', exc)
