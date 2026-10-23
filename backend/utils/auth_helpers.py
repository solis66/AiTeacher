"""
JWT 鉴权与管理员权限辅助

职责：
- get_token_user()：从 Authorization: Bearer <token> 中解析出当前账号与角色。
- admin_required()：管理员接口装饰器，数据库角色必须回查，不信任 token 内的角色声明。

依赖方向刻意保持单向：只依赖 flask / jwt / services.user_service / utils.request_helpers，
不导入 api.py，避免与主应用形成循环导入。
"""

import logging
from functools import wraps

import jwt
from flask import current_app, request

from services import user_service
from utils.request_helpers import json_error

logger = logging.getLogger(__name__)


def get_token_user():
    """
    解析请求头中的 JWT。

    返回：
        dict | None - {'account': str, 'role': str}；缺少令牌或令牌非法时返回 None
    """
    header = (request.headers.get('Authorization') or '').strip()
    if not header.startswith('Bearer '):
        return None
    token = header[len('Bearer '):].strip()
    if not token:
        return None
    try:
        payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
    except jwt.PyJWTError:
        return None
    except Exception:
        logger.exception('[鉴权] 解析 JWT 失败')
        return None

    account = (payload.get('username') or payload.get('account') or '').strip()
    if not account:
        return None
    return {'account': account, 'role': payload.get('role') or ''}


def admin_required(fn):
    """
    管理员权限装饰器。

    判定顺序：
        1. 无有效 token → 401
        2. 按账号回查数据库 users.role，不是 'admin' → 403
    数据库角色必须回查：token 里的 role 只是登录时的界面分流依据，不能作为权限依据。
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            token_user = get_token_user()
        except Exception:
            logger.exception('[鉴权] 读取令牌信息失败')
            return json_error('需要管理员权限', '登录状态无效', status=401)

        if not token_user:
            return json_error('需要管理员权限', '请先登录管理员账号', status=401)

        try:
            role = user_service.get_user_role(token_user['account'])
        except Exception:
            logger.exception('[鉴权] 查询用户角色失败: %s', token_user.get('account'))
            return json_error('权限校验失败', '暂时无法校验管理员权限，请稍后重试', status=500)

        if role != 'admin':
            return json_error('需要管理员权限', '当前账号无管理员权限', status=403)

        return fn(*args, **kwargs)

    return wrapper
