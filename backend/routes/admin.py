"""
管理员接口

接口清单（全部需要管理员权限）：
    GET /api/admin/users                              用户列表（在线状态 + 批改统计）
    GET /api/admin/users/<account>/reviews            某用户的批改记录列表
    GET /api/admin/users/<account>/profile            某用户的学情报告
    GET /api/admin/users/<account>/reviews/<rid>      某用户的单条批改记录详情

数据隔离：批改记录一律按被查看账号作为 owner 读取，管理员不绕过隔离直接读全库。
权限：@admin_required 会回查数据库 users.role，token 中的角色声明不作为权限依据。
"""

import logging

from flask import Blueprint, jsonify

from routes.review import summarize, workbench
from services import admin_service, user_service
from utils.auth_helpers import admin_required
from utils.request_helpers import json_error, json_ok

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/api/admin/users', methods=['GET'])
@admin_required
def list_users():
    """查看全部用户：在线/离线状态、登录时间、批改数量与平均分。"""
    try:
        items = admin_service.list_users_with_stats(workbench.store)
        for item in items:
            role = item.get('role')
            item['role_label'] = user_service.ROLE_LABELS.get(role, role)
        return json_ok(data=items)
    except Exception:
        logger.exception('[管理员] 查询用户列表失败')
        return json_error('查询失败', '查询用户列表失败，请稍后重试', status=500)


@admin_bp.route('/api/admin/users/<account>/reviews', methods=['GET'])
@admin_required
def list_user_reviews(account):
    """查看指定用户的批改记录列表。"""
    try:
        records = admin_service.list_user_reviews(workbench.store, account)
    except ValueError as exc:
        return json_error('用户不存在', str(exc), status=404)
    except Exception:
        logger.exception('[管理员] 查询用户批改记录失败: %s', account)
        return json_error('查询失败', '查询批改记录失败，请稍后重试', status=500)

    try:
        return json_ok(data=[summarize(record) for record in records])
    except Exception:
        logger.exception('[管理员] 汇总用户批改记录失败: %s', account)
        return json_error('查询失败', '查询批改记录失败，请稍后重试', status=500)


@admin_bp.route('/api/admin/users/<account>/profile', methods=['GET'])
@admin_required
def user_profile(account):
    """查看指定用户的学情报告。"""
    try:
        return json_ok(data=admin_service.user_profile(account))
    except Exception:
        logger.exception('[管理员] 查询用户学情失败: %s', account)
        return json_error('查询失败', '查询学情报告失败，请稍后重试', status=500)


@admin_bp.route('/api/admin/users/<account>/reviews/<rid>', methods=['GET'])
@admin_required
def get_user_review(account, rid):
    """查看指定用户的单条批改记录详情。"""
    try:
        record = admin_service.get_user_review(workbench.store, account, rid)
    except Exception:
        logger.exception('[管理员] 查询批改详情失败: %s/%s', account, rid)
        return json_error('查询失败', '查询批改详情失败，请稍后重试', status=500)

    if record is None:
        return jsonify({'success': False, 'message': '批改记录不存在'}), 404
    return json_ok(data=summarize(record, detail=True))
