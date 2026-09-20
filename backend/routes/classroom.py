"""
班级与作业路由

老师端：
    POST   /api/class/create                     创建班级（返回邀请码）
    GET    /api/class/mine                       我创建的班级
    GET    /api/class/<cid>/members              班级学生名单
    POST   /api/class/<cid>/remove-member        移出某个学生
    POST   /api/assignment/create                发布作文训练
    GET    /api/assignment/class/<cid>           某班的作业列表
    DELETE /api/assignment/<aid>                 删除作业
    GET    /api/assignment/<aid>/submissions     某作业的全部提交（含未交名单）
    GET    /api/class/<cid>/submissions          班级全部提交（按作业聚合）
    GET    /api/class/<cid>/report               班级学情报告（按学生汇总）

学生端：
    POST   /api/class/join                       凭邀请码加入班级
    GET    /api/class/joined                     我已加入的班级
    POST   /api/class/<cid>/leave                退出班级
    GET    /api/assignment/mine                  我可见的作业（标注是否已提交）
    GET    /api/assignment/<aid>/submission      我在某作业下的提交

身份与权限：
    账号取自既有的 X-Username 请求头（与项目其它接口一致），但**角色一律回查
    users 表**——X-Username 是前端可随意填写的，若再采信前端声明的 role 做权限判断，
    等于没有权限控制。班级归属（classes.teacher / class_members.student）在 SQL 层
    强制过滤，越权访问得到的是 400 而不是别人的数据。
"""

import logging
from functools import wraps

from flask import Blueprint, request

from services import classroom_service, user_service
from services.classroom_service import ClassroomError
from utils.request_helpers import (
    get_json_body,
    get_request_username,
    json_error,
    json_ok,
)

logger = logging.getLogger(__name__)

classroom_bp = Blueprint('classroom', __name__)


def _current_user(required_role=None):
    """
    解析当前账号并校验角色（角色回查数据库，不信任前端）。

    异常：
        ClassroomError - 未登录 / 账号不存在 / 角色不符
    """
    account = get_request_username('')
    if not account or account == 'anonymous':
        raise ClassroomError('请先登录')
    try:
        user = user_service.get_user_by_account(account)
    except user_service.DatabaseUnavailableError as exc:
        raise ClassroomError(str(exc)) from exc
    if not user:
        raise ClassroomError('账号不存在，请重新登录')
    if required_role and user.get('role') != required_role:
        label = user_service.ROLE_LABELS.get(required_role, required_role)
        raise ClassroomError(f'该功能仅限{label}账号使用')
    return user


def _handle(fn):
    """把 ClassroomError 统一转成 400，其余异常转 500，避免把堆栈抛给前端。"""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ClassroomError as exc:
            return json_error('操作失败', str(exc), status=400)
        except Exception as exc:            # noqa: BLE001 - 兜底，避免 500 页面
            logger.exception('[班级] %s 处理失败', fn.__name__)
            return json_error('服务器错误', str(exc)[:200], status=500)
    return wrapper


def _score_of(record):
    """
    取一条记录的分数与评级。

    注意分数**不在记录顶层**，而在 result 里（顶层只有状态、输入、页面等）。
    这里收敛成一个函数，避免各处凭直觉写 record['score'] 拿到 None ——
    那会让提交列表显示空分数、学情报告的平均分永远算不出来，
    而且不会报错，只是安静地全是 null，极难发现。
    """
    result = record.get('result') or {}
    return result.get('score'), result.get('rating')


def _brief(record):
    """提交记录的精简结构（剔除分页文字等大字段，供列表与统计使用）。"""
    score, rating = _score_of(record)
    return {
        'id': record.get('id'),
        'owner': record.get('owner'),
        'student': record.get('student') or record.get('owner'),
        'assignment_id': record.get('assignment_id'),
        'status': record.get('status'),
        'error': record.get('error'),
        'score': score,
        'rating': rating,
        'title': (record.get('input') or {}).get('title') or '',
        'created_at': record.get('created_at'),
        'updated_at': record.get('updated_at'),
    }


def _workbench():
    """延迟取批改工作台实例，避免模块级循环导入。"""
    from routes.review import workbench
    return workbench


# ---------------------------------------------------------------- 班级

@classroom_bp.route('/api/class/create', methods=['POST'])
@_handle
def create_class():
    """老师创建班级。"""
    data = get_json_body() or {}
    user = _current_user('teacher')
    info = classroom_service.create_class(user['account'], data.get('name'))
    logger.info('[班级] %s 创建班级 %s（邀请码 %s）',
                user['account'], info['name'], info['join_code'])
    return json_ok('班级创建成功', data=info)


@classroom_bp.route('/api/class/mine', methods=['GET'])
@_handle
def my_classes():
    """老师：我创建的班级。"""
    user = _current_user('teacher')
    return json_ok('', data=classroom_service.list_teacher_classes(user['account']))


@classroom_bp.route('/api/class/<int:class_id>/members', methods=['GET'])
@_handle
def class_members(class_id):
    """老师：班级学生名单。"""
    user = _current_user('teacher')
    return json_ok('', data=classroom_service.list_class_members(class_id, user['account']))


@classroom_bp.route('/api/class/<int:class_id>/remove-member', methods=['POST'])
@_handle
def remove_member(class_id):
    """老师：把学生移出班级。"""
    data = get_json_body() or {}
    user = _current_user('teacher')
    classroom_service.remove_member(class_id, user['account'],
                                    (data.get('student') or '').strip())
    return json_ok('已将该学生移出班级')


@classroom_bp.route('/api/class/join', methods=['POST'])
@_handle
def join_class():
    """学生：凭邀请码加入班级。"""
    data = get_json_body() or {}
    user = _current_user('student')
    info = classroom_service.join_class(user['account'], data.get('join_code'))
    logger.info('[班级] %s 加入班级 %s', user['account'], info['name'])
    return json_ok('加入班级成功', data=info)


@classroom_bp.route('/api/class/joined', methods=['GET'])
@_handle
def joined_classes():
    """学生：我已加入的班级。"""
    user = _current_user('student')
    return json_ok('', data=classroom_service.list_student_classes(user['account']))


@classroom_bp.route('/api/class/<int:class_id>/leave', methods=['POST'])
@_handle
def leave_class(class_id):
    """学生：退出班级。"""
    user = _current_user('student')
    classroom_service.leave_class(user['account'], class_id)
    return json_ok('已退出班级')


# ---------------------------------------------------------------- 作业

@classroom_bp.route('/api/assignment/create', methods=['POST'])
@_handle
def create_assignment():
    """老师：向自己的班级发布作文训练。"""
    data = get_json_body() or {}
    user = _current_user('teacher')
    info = classroom_service.create_assignment(
        user['account'], data.get('class_id'), data.get('title'),
        data.get('requirements'), data.get('grade'), data.get('essay_type'),
    )
    logger.info('[作业] %s 在班级 %s 发布《%s》', user['account'], info['class_id'], info['title'])
    return json_ok('作文训练发布成功', data=info)


@classroom_bp.route('/api/assignment/class/<int:class_id>', methods=['GET'])
@_handle
def class_assignments(class_id):
    """老师：某班的作业列表（含已提交人数 / 班级人数）。"""
    user = _current_user('teacher')
    items = classroom_service.list_class_assignments(class_id, user['account'])

    records = _workbench().store.list_by_assignment_ids([str(i['id']) for i in items])
    counter = {}
    for rec in records:
        key = str(rec.get('assignment_id') or '')
        counter[key] = counter.get(key, 0) + 1
    for item in items:
        item['submitted_count'] = counter.get(str(item['id']), 0)
    return json_ok('', data=items)


@classroom_bp.route('/api/assignment/<int:assignment_id>', methods=['DELETE'])
@_handle
def delete_assignment(assignment_id):
    """老师：删除自己发布的作业。"""
    user = _current_user('teacher')
    classroom_service.delete_assignment(assignment_id, user['account'])
    return json_ok('作业已删除')


@classroom_bp.route('/api/assignment/mine', methods=['GET'])
@_handle
def my_assignments():
    """学生：我可见的作业（来自已加入的班级），并标注我是否已提交。"""
    user = _current_user('student')
    items = classroom_service.list_student_assignments(user['account'])

    submitted = {}
    for rec in _workbench().store.list(user['account']):
        aid = rec.get('assignment_id')
        if aid:
            score, rating = _score_of(rec)
            submitted[str(aid)] = {
                'review_id': rec.get('id'),
                'status': rec.get('status'),
                'score': score,
                'rating': rating,
                'error': rec.get('error'),
            }
    for item in items:
        info = submitted.get(str(item['id']))
        item['submitted'] = bool(info)
        item['submission'] = info
    return json_ok('', data=items)


@classroom_bp.route('/api/assignment/<int:assignment_id>/submission', methods=['GET'])
@_handle
def my_submission(assignment_id):
    """学生：我在某作业下的提交。"""
    user = _current_user('student')
    classroom_service.get_assignment_for_student(assignment_id, user['account'])
    target = str(assignment_id)
    for rec in _workbench().store.list(user['account']):
        if str(rec.get('assignment_id') or '') == target:
            return json_ok('', data=_brief(rec))
    return json_ok('', data=None)


# ---------------------------------------------------------------- 老师视角的提交与学情

@classroom_bp.route('/api/assignment/<int:assignment_id>/submissions', methods=['GET'])
@_handle
def assignment_submissions(assignment_id):
    """老师：某作业下的全部提交，并给出未提交名单。"""
    user = _current_user('teacher')
    info = classroom_service.get_assignment_owned_by_class(assignment_id, user['account'])
    records = _workbench().store.list_by_assignment_ids([str(assignment_id)])

    handed = {str(r.get('student') or r.get('owner') or '') for r in records}
    members = classroom_service.list_class_members(info['class_id'], user['account'])
    missing = [m['student'] for m in members if m['student'] not in handed]

    return json_ok('', data={
        'assignment': info,
        'submissions': [_brief(r) for r in records],
        'missing': missing,
    })


@classroom_bp.route('/api/class/<int:class_id>/submissions', methods=['GET'])
@_handle
def class_submissions(class_id):
    """老师：班级全部提交（同时返回作业与成员，便于前端一次渲染）。"""
    user = _current_user('teacher')
    assignments = classroom_service.list_class_assignments(class_id, user['account'])
    records = _workbench().store.list_by_assignment_ids([str(a['id']) for a in assignments])
    return json_ok('', data={
        'assignments': assignments,
        'submissions': [_brief(r) for r in records],
        'members': classroom_service.list_class_members(class_id, user['account']),
    })


@classroom_bp.route('/api/class/<int:class_id>/report', methods=['GET'])
@_handle
def class_report(class_id):
    """
    老师：班级学情报告 —— 按学生汇总其在本班作业中的批改结果。

    统计口径：只把 status=done 且 score 为整数的记录计入分数统计，
    进行中/失败的任务只计入提交次数，避免把未完成的 0 分拉低平均分。
    """
    user = _current_user('teacher')
    assignments = classroom_service.list_class_assignments(class_id, user['account'])
    members = classroom_service.list_class_members(class_id, user['account'])
    records = _workbench().store.list_by_assignment_ids([str(a['id']) for a in assignments])

    buckets = {}

    def bucket_of(account):
        if account not in buckets:
            buckets[account] = {'student': account, 'submitted': 0, 'finished': 0,
                                'scores': [], 'latest_at': '', 'latest_score': None}
        return buckets[account]

    for member in members:
        bucket_of(member['student'])

    for rec in records:
        who = str(rec.get('student') or rec.get('owner') or '')
        bucket = bucket_of(who)
        bucket['submitted'] += 1
        score, _rating = _score_of(rec)
        if rec.get('status') == 'done' and isinstance(score, int):
            bucket['scores'].append(score)
            bucket['finished'] += 1
            at = rec.get('updated_at') or rec.get('created_at') or ''
            if at > bucket['latest_at']:
                bucket['latest_at'] = at
                bucket['latest_score'] = score

    students = []
    for bucket in buckets.values():
        scores = bucket['scores']
        students.append({
            'student': bucket['student'],
            'submitted': bucket['submitted'],
            'finished': bucket['finished'],
            'avg': round(sum(scores) / len(scores), 1) if scores else None,
            'best': max(scores) if scores else None,
            'worst': min(scores) if scores else None,
            'latest_score': bucket['latest_score'],
            'latest_at': bucket['latest_at'],
        })
    # 有平均分的排前面，同分按提交次数
    students.sort(key=lambda x: (x['avg'] is None, -(x['avg'] or 0), -x['submitted']))

    all_scores = [s for b in buckets.values() for s in b['scores']]
    return json_ok('', data={
        'class_id': class_id,
        'assignment_count': len(assignments),
        'member_count': len(members),
        'submission_count': len(records),
        'avg_score': round(sum(all_scores) / len(all_scores), 1) if all_scores else None,
        'students': students,
    })


@classroom_bp.route('/api/class/submission/<rid>', methods=['GET'])
@_handle
def submission_detail(rid):
    """
    老师：查看本班学生某条提交的完整批改结果。

    这是全项目唯一会读到「别人名下」记录的接口，所以做了两层校验：
      1. 记录必须挂着 assignment_id（普通批改记录一律拒绝，
         否则这里会变成「凭记录 id 读任意人作文」的后门）；
      2. 该作业必须属于当前老师（get_assignment_owned_by_class 内部校验）。
    """
    user = _current_user('teacher')
    record = _workbench().store.get_any(rid)
    if not record:
        raise ClassroomError('批改记录不存在')
    assignment_id = record.get('assignment_id')
    if not assignment_id:
        raise ClassroomError('该记录不是作业提交，无法在班级中查看')
    classroom_service.get_assignment_owned_by_class(assignment_id, user['account'])

    from routes.review import summarize
    return json_ok('', data=summarize(record, detail=True))
