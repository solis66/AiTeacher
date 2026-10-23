"""
管理员聚合服务

职责：把「用户列表 + 批改统计」「用户批改记录」「用户学情报告」等聚合逻辑收敛在这里，
路由层只做参数接收与响应封装，保持轻薄。

数据来源：
- 账号与在线状态：services.user_service（PostgreSQL users 表）
- 批改记录：routes.review.workbench.store（SQLite reviews 表，按 owner 隔离）
- 学情报告：services.consult_context.get_index()（只读聚合，不调模型）
"""

from services import user_service
from services.consult_context import get_index


def _numeric_score(record):
    """取批改结果中的分数；仅接受 int/float（排除 bool），否则返回 None。"""
    score = (record.get('result') or {}).get('score')
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return None
    return float(score)


def list_users_with_stats(store):
    """
    用户列表 + 每个账号的批改统计。

    参数：
        store: ReviewStore 实例（使用 store.list(account)）

    返回：
        list - 用户字典列表，额外字段：
            review_count  批改记录总数
            done_count    已完成（status == 'done'）数量
            avg_score     已完成且分数为数值的平均分（保留 1 位小数，无则 None）
            latest_score  最新一条已完成记录的分数（无则 None）
            latest_at     最新一条已完成记录的更新时间（无则 None）
        排序：在线优先，其次批改记录数从多到少。
    """
    items = []
    for user in user_service.list_users():
        account = user['account']
        records = store.list(account)

        scores = []
        done_count = 0
        latest_record = None
        for record in records:
            if record.get('status') != 'done':
                continue
            done_count += 1
            if latest_record is None:
                latest_record = record
            score = _numeric_score(record)
            if score is not None:
                scores.append(score)

        latest_score = _numeric_score(latest_record) if latest_record else None
        item = dict(user)
        item.update({
            'review_count': len(records),
            'done_count': done_count,
            'avg_score': round(sum(scores) / len(scores), 1) if scores else None,
            'latest_score': latest_score,
            'latest_at': (latest_record.get('updated_at') or latest_record.get('created_at'))
            if latest_record else None,
        })
        items.append(item)

    items.sort(
        key=lambda item: (1 if item.get('online') else 0, item.get('review_count') or 0),
        reverse=True,
    )
    return items


def list_user_reviews(store, account):
    """
    某个账号的全部批改记录（按存储顺序，最新在前）。

    异常：
        ValueError - 账号不存在
    """
    if user_service.get_user_role(account) is None:
        raise ValueError('用户不存在')
    return store.list(account)


def user_profile(account):
    """
    指定账号的学情报告。

    学情报告按 owner 隔离，管理员查看时以被查看账号本身作为 owner，
    因此只聚合该账号名下的记录。
    """
    index = get_index()
    index.sync()
    return index.student_profile(account, None)


def get_user_review(store, account, rid):
    """
    取单条批改记录（严格按 owner 限定，不提供跨用户读取）。

    返回：
        dict | None - 记录不存在或不属于该账号时返回 None
    """
    return store.get(rid, account)
