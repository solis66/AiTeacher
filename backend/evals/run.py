"""
咨询 Agent 评测 harness

用法（工作目录 backend/，Linux/服务器）：
    .venv/bin/python evals/run.py --owner admin
    .venv/bin/python evals/run.py --owner admin --tag tool-use
    .venv/bin/python evals/run.py --cases evals/cases.yaml --limit 5

设计：
    只断言可自动判定的行为（工具是否调用、是否降级、事实是否对得上），
    不评判文笔好坏——后者留给人工抽检。
    用例里需要「某一篇」时用模板从账号真实记录取值，不造数据；
    取不到值就记为 skipped，而不是失败。

观测复用：
    每次评测都开一条 consult_trace（kind='eval'），工具调用与耗时直接从
    logs/consult_trace.jsonl 读取，harness 不重复实现一套采集。

退出码：
    0 全部通过（含 skipped）；1 有失败用例。
"""

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from string import Formatter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml

from agent.tools.review_tools import AgentContext, review_detail, search_reviews
from services.consultation_service import stream_answer_consultation
from services.review_store import ReviewStore
from utils import consult_trace
from utils.path_tool import get_abs_path

TRACE_FILE = Path(get_abs_path('logs/consult_trace.jsonl'))
REVIEW_ROOT = get_abs_path('data/reviews')
RESULT_DIR = Path(__file__).resolve().parent / 'results'
DEFAULT_CASES = Path(__file__).resolve().parent / 'cases.yaml'
# 与 config/agent.yaml 的 agent_max_tool_calls 对齐；超出即视为异常
MAX_TOOLS = 3


class _Runtime:
    """只给直接调用工具用的最小 runtime（隔离检查不经过模型）。"""

    def __init__(self, owner: str):
        self.context = AgentContext(owner=owner)


def _db_path() -> Path:
    return Path(REVIEW_ROOT) / 'reviews.sqlite3'


def _pick_owner() -> str:
    """默认选记录最多的账号，避免每次都要手填 --owner。"""
    db = _db_path()
    if not db.exists():
        return ''
    try:
        con = sqlite3.connect(f'file:{db}?mode=ro', uri=True, timeout=10)
        try:
            row = con.execute(
                'SELECT owner, COUNT(*) AS c FROM reviews GROUP BY owner ORDER BY c DESC LIMIT 1'
            ).fetchone()
        finally:
            con.close()
        return (row[0] or '') if row else ''
    except Exception:
        return ''


def _valid_score(record):
    """记录的整数总分；未评分（None/非整数）返回 None，避免模板渲染出 None。"""
    score = (record.get('result') or {}).get('score')
    return score if isinstance(score, int) else None


def _essay_type_of(record):
    """体裁取值口径与 review_tools/_record 保持一致：result 优先，回退 input。"""
    result = record.get('result') or {}
    inp = record.get('input') or {}
    return (result.get('essay_type') or inp.get('essay_type') or '').strip()


def _build_vars(records, student):
    """
    从真实记录里取模板变量。

    只取「student 归属为该账号本人」的记录：账号下可能代传过别人的作文，
    学情画像与回答口径都只统计本人，模板若取了别人的篇目，断言就会对不上
    （实测：owner 名下 7 篇完成记录，但属于本人学生的只有 4 篇）。

    另有两类变量刻意用「owner 全量」口径：
        review_date / review_date_score / essay_type_max_score
    因为 search_reviews 按 owner 过滤（含代传记录），以工具实际能看到的数据为准，
    否则断言会跟工具返回对不上。
    """
    done = [
        record for record in records
        if record.get('status') == 'done' and record.get('result')
        and ((record.get('student') or record.get('owner') or '') == student)
    ]
    titled = [r for r in done if len(((r.get('input') or {}).get('title') or '').strip()) >= 3]
    types = {}
    for record in done:
        essay_type = _essay_type_of(record)
        if essay_type:
            types[essay_type] = types.get(essay_type, 0) + 1

    # 学情画像按时间升序统计：平均分/最高/最低/最近一次都必须与页源头一致
    ordered = sorted(done, key=lambda record: record.get('created_at') or '')
    scores = [score for score in (_valid_score(record) for record in ordered) if score is not None]
    avg = round(sum(scores) / len(scores), 1) if scores else None

    latest = titled[0] if titled else None
    score = (latest or {}).get('result', {}).get('score')
    essay_type = max(types, key=types.get) if types else ''

    # 按天分组，挑「当天只有一篇」的最近日期：模型无法按具体日期过滤，
    # 同一天多篇时它只能靠列表里的人工比对，断言会带上不必要的歧义。
    owner_done = [
        record for record in records
        if record.get('status') == 'done' and record.get('result')
    ]
    by_day = {}
    for record in owner_done:
        day = (record.get('created_at') or '')[:10]
        if day:
            by_day.setdefault(day, []).append(record)
    unique_days = sorted((day for day, items in by_day.items() if len(items) == 1), reverse=True)

    review_date = unique_days[0] if unique_days else ''
    review_date_score = _valid_score(by_day[review_date][0]) if review_date else None

    typed_scores = [
        value for value in (
            _valid_score(record) for record in owner_done
            if essay_type and _essay_type_of(record) == essay_type
        ) if value is not None
    ]

    return {
        'title': ((latest or {}).get('input') or {}).get('title') or '',
        # score 为 None 时置空串：否则模板会渲染成「为什么只有 None 分」
        'score': '' if score is None else score,
        'essay_type': essay_type,
        'n_reviews': len(done),
        # 平均分用 :g 去掉无意义的 .0，避免「42.0」与模型口头的「42 分」对不上
        'avg_score': '' if avg is None else f'{avg:g}',
        'best_score': max(scores) if scores else '',
        'worst_score': min(scores) if scores else '',
        'review_date': review_date,
        'review_date_score': '' if review_date_score is None else review_date_score,
        'essay_type_max_score': max(typed_scores) if typed_scores else '',
    }


def _render(template, variables) -> str:
    """
    展开 {title}/{score} 等占位符。

    任一占位符取值为空就返回空串（调用方记为 skipped）：
    否则会拼出「我那篇《》为什么只有分？」这种无意义问句，
    评测结果会被一句无效提问污染，而不是给出"缺数据"的信号。
    """
    if not template:
        return ''
    text = str(template)
    try:
        names = [name for _, name, _, _ in Formatter().parse(text) if name]
    except Exception:
        return ''
    for name in names:
        if variables.get(name) in ('', None):
            return ''
    try:
        return text.format(**variables)
    except (KeyError, IndexError):
        return ''


def _last_trace(trace_id: str) -> dict:
    if not trace_id or not TRACE_FILE.exists():
        return {}
    try:
        for line in reversed(TRACE_FILE.read_text(encoding='utf-8').splitlines()):
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get('trace_id') == trace_id:
                return record
    except Exception:
        return {}
    return {}


def _run_query(case, owner, variables):
    """跑一条问答，返回 (answer, trace)。"""
    query = case.get('query') or _render(case.get('query_template'), variables)
    trace_id = consult_trace.start(owner, kind='eval')
    answer = ''
    try:
        for event in stream_answer_consultation(query, [], owner=owner, trace_id=trace_id):
            if event.get('type') == 'delta':
                answer += event.get('content') or ''
    finally:
        consult_trace.finish(trace_id, answer_chars=len(answer))
    return query, answer, _last_trace(trace_id)


def _judge(case, answer, trace, variables):
    """返回失败原因列表；空列表表示通过。"""
    reasons = []
    expect = case.get('expect') or {}
    tools = [item.get('name') for item in (trace.get('tools') or [])]

    for name in expect.get('tools_include') or []:
        if name not in tools:
            reasons.append(f'未调用 {name}')
    for name in expect.get('tools_exclude') or []:
        if name in tools:
            reasons.append(f'不应调用 {name}')
    for term in expect.get('answer_contains') or []:
        wanted = _render(term, variables)
        if wanted and wanted not in answer:
            reasons.append(f'回答缺少「{wanted}」')
    # 任一命中即可：用于「没有查到 / 未找到」这类同义表述，避免措辞不同就误判
    any_terms = [
        term for term in (_render(item, variables) for item in (expect.get('answer_contains_any') or []))
        if term
    ]
    if any_terms and not any(term in answer for term in any_terms):
        reasons.append(f"回答不含任一预期表述（{'/'.join(any_terms)}）")
    for term in expect.get('answer_not_contains') or []:
        forbidden = _render(term, variables)
        if forbidden and forbidden in answer:
            reasons.append(f"回答出现了不应包含的「{forbidden}」")
    min_chars = int(expect.get('min_answer_chars') or 0)
    if min_chars and len(answer.strip()) < min_chars:
        reasons.append(f'回答过短（{len(answer.strip())} < {min_chars}）')
    if expect.get('no_degraded') and trace.get('degraded'):
        reasons.append('走了降级路径')
    if expect.get('no_error') and trace.get('error'):
        reasons.append(f"错误：{trace.get('error')}")
    if len(tools) > MAX_TOOLS:
        reasons.append(f'工具调用超预算（{len(tools)} > {MAX_TOOLS}）')
    return reasons


def _done_id(records) -> str:
    """取一条带批改结果的记录 id（详情才有可返回内容，避免状态提示干扰隔离判断）。"""
    for record in records or []:
        if record.get('status') == 'done' and record.get('result'):
            return str(record.get('id') or '')
    return ''


def _pick_other_owner(owner: str) -> str:
    """
    挑一个隔离对照账号。

    优先用已有批改记录的其它 owner；没有时再查 users 表里的其它账号。
    线上第二个账号往往还没提交过作文，但它依然可以用自己的身份去尝试访问
    他人的记录 id——这正是需要验证的隔离边界，不能因为"没有记录"就跳过。
    """
    db = _db_path()
    if db.exists():
        try:
            con = sqlite3.connect(f'file:{db}?mode=ro', uri=True, timeout=10)
            try:
                row = con.execute(
                    'SELECT owner FROM reviews WHERE owner <> ? '
                    'GROUP BY owner ORDER BY COUNT(*) DESC LIMIT 1',
                    (owner,),
                ).fetchone()
            finally:
                con.close()
            if row and (row[0] or '').strip():
                return row[0].strip()
        except Exception:
            pass

    try:
        from services.user_service import list_users
        for item in list_users():
            account = (item.get('account') or '').strip()
            if account and account != owner:
                return account
    except Exception:
        pass
    return ''


def _run_isolation(owner, records, other_owner):
    """
    数据隔离检查（不调模型，确定性）：
        1. 每个账号检索到的 id 必须都属于自己；
        2. 用他人记录 id 调详情必须查不到（双向验证）。
    对照账号可以没有任何批改记录：此时它的检索应为空、拿本人 id 也应查不到。
    返回 (reasons, skipped) 。
    """
    reasons = []
    mine = {str(r.get('id')) for r in records}

    listing = search_reviews.func(_Runtime(owner), limit=8)
    leaked = [rid for rid in re.findall(r'id=([0-9a-f]+)', listing) if rid not in mine]
    if leaked:
        reasons.append(f'检索返回了他人记录：{leaked[:2]}')

    if not other_owner or other_owner == owner:
        return reasons, True

    other_records = ReviewStore(REVIEW_ROOT).list(other_owner) or []
    other_ids = {str(r.get('id')) for r in other_records}
    other_listing = search_reviews.func(_Runtime(other_owner), limit=8)
    leaked_to_other = [
        rid for rid in re.findall(r'id=([0-9a-f]+)', other_listing) if rid not in other_ids
    ]
    if leaked_to_other:
        reasons.append(f'第二账号检索返回了他人记录：{leaked_to_other[:2]}')

    checked_detail = False
    my_id = _done_id(records)
    if my_id:
        checked_detail = True
        detail = review_detail.func(_Runtime(other_owner), record_id=my_id)
        if '未找到' not in detail:
            reasons.append('第二账号可查看他人记录详情')

    other_id = _done_id(other_records)
    if other_id:
        checked_detail = True
        detail = review_detail.func(_Runtime(owner), record_id=other_id)
        if '未找到' not in detail:
            reasons.append('跨账号详情未被拒绝')

    # 双向都没有可用的 done 记录时，详情隔离实际上没被执行到
    if not checked_detail and not reasons:
        return reasons, True
    return reasons, False


def main() -> int:
    parser = argparse.ArgumentParser(description='咨询 Agent 评测 harness')
    parser.add_argument('--owner', default='', help='被评测账号（默认取记录最多的账号）')
    parser.add_argument('--other-owner', default='',
                        help='隔离检查用的第二账号（可以没有批改记录；默认自动挑选）')
    parser.add_argument('--cases', default=str(DEFAULT_CASES), help='用例文件')
    parser.add_argument('--tag', default='', help='只跑指定标签')
    parser.add_argument('--case', default='', help='只跑指定用例 id（失败复跑用）')
    parser.add_argument('--limit', type=int, default=0, help='最多跑几条（0 表示全部）')
    args = parser.parse_args()

    owner = args.owner or _pick_owner()
    if not owner:
        print('[评测] 找不到有批改记录的账号，请用 --owner 指定')
        return 1

    records = ReviewStore(REVIEW_ROOT).list(owner) or []
    variables = _build_vars(records, owner)
    print(f"[评测] 账号={owner} 记录={len(records)} 篇数={variables['n_reviews']}")

    with open(args.cases, 'r', encoding='utf-8') as fh:
        cases = (yaml.safe_load(fh) or {}).get('cases') or []
    if args.tag:
        cases = [c for c in cases if args.tag in (c.get('tags') or [])]
    if args.case:
        cases = [c for c in cases if c.get('id') == args.case]
    if args.limit > 0:
        cases = cases[:args.limit]

    # 隔离检查需要第二账号；只在本次确实要跑隔离用例时才去查库/用户表
    other_owner = ''
    if any(case.get('check') == 'tool_isolation' for case in cases):
        other_owner = (args.other_owner or '').strip() or _pick_other_owner(owner)
        if other_owner == owner:
            other_owner = ''
        print(f"[评测] 隔离对照账号={other_owner or '未找到（将跳过）'}")

    results = []
    passed = failed = skipped = 0
    for case in cases:
        case_id = case.get('id') or 'unnamed'
        check = case.get('check')

        if check == 'tool_isolation':
            reasons, was_skipped = _run_isolation(owner, records, other_owner)
            status = 'skipped' if was_skipped else ('failed' if reasons else 'passed')
            results.append({'id': case_id, 'status': status, 'reasons': reasons,
                            'tools': [], 'other_owner': other_owner})
            if status == 'passed':
                passed += 1
            elif status == 'failed':
                failed += 1
            else:
                skipped += 1
            print(f"[{status}] {case_id}" + (f" :: {'; '.join(reasons)}" if reasons else ''))
            continue

        query = case.get('query') or _render(case.get('query_template'), variables)
        if not query:
            skipped += 1
            results.append({'id': case_id, 'status': 'skipped', 'reasons': ['模板缺少可用数据'], 'tools': []})
            print(f"[skipped] {case_id} :: 模板缺少可用数据")
            continue

        query, answer, trace = _run_query(case, owner, variables)
        reasons = _judge(case, answer, trace, variables)
        status = 'failed' if reasons else 'passed'
        passed += status == 'passed'
        failed += status == 'failed'
        tools = [item.get('name') for item in (trace.get('tools') or [])]
        results.append({
            'id': case_id, 'status': status, 'reasons': reasons,
            'tools': tools, 'total_ms': trace.get('total_ms'),
            'answer_chars': len(answer),
        })
        print(f"[{status}] {case_id}" + (f" :: {'; '.join(reasons)}" if reasons else '')
              + f"  ({','.join(tools) or '无工具'})")

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = RESULT_DIR / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    summary = {
        'run_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'owner': owner,
        'total': len(cases),
        'passed': passed,
        'failed': failed,
        'skipped': skipped,
        'cases': results,
    }
    out_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"[评测] 通过 {passed} / 失败 {failed} / 跳过 {skipped}；结果：{out_file}")
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
