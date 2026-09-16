"""
Flask 请求处理公共辅助模块

抽取 api.py 各路由中重复出现的请求校验、统一响应、身份解析与重试逻辑，
保证所有接口的校验口径与响应结构一致。

设计原则：
- 行为不变：仅收敛重复代码，不改变任何接口的请求/响应格式与状态码
- 统一口径：错误响应统一为 {'success': False, 'error': ..., 'message': ...}
- 身份约定：数据隔离身份统一从 X-Username 请求头读取（前端填充，非认证手段）
"""

import logging
import random
import time

from flask import jsonify, request

logger = logging.getLogger(__name__)

# 支持的作文体裁白名单（与前端下拉选项、评分标准保持一致）
SUPPORTED_ESSAY_TYPES = ('议论文', '记叙文', '说明文')


def json_ok(message='', **data):
    """
    构造统一的成功响应

    参数：
        message: string - 可选的提示信息
        **data: 附加到响应体的字段（如 data、token、history 等）

    返回：
        Flask JSON 响应（{'success': True, ...}）
    """
    body = {'success': True}
    if message:
        body['message'] = message
    body.update(data)
    return jsonify(body)


def json_error(error, message='', status=400):
    """
    构造统一的错误响应

    参数：
        error: string - 简短错误标识（如 '请输入内容'）
        message: string - 可选的详细错误说明
        status: int - HTTP 状态码，默认 400

    返回：
        tuple: (Flask JSON 响应, 状态码)，响应格式 {'success': False, 'error': ..., 'message': ...}
    """
    body = {'success': False, 'error': error}
    if message:
        body['message'] = message
    return jsonify(body), status


def get_json_body():
    """
    读取并校验 JSON 请求体

    返回：
        dict|None - 合法的 JSON 对象；请求非 JSON 格式或解析结果不是对象时返回 None
    """
    if not request.is_json:
        return None
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def get_request_username(default='anonymous'):
    """
    读取当前请求的数据隔离身份（X-Username 请求头）

    参数：
        default: string - 请求头缺失或为空时的默认身份

    返回：
        string - 去除首尾空白后的用户名
    """
    username = (request.headers.get('X-Username') or '').strip()
    return username or default


def validate_essay_type(essay_type):
    """
    校验作文体裁是否在支持列表内

    参数：
        essay_type: string - 待校验的作文体裁

    返回：
        boolean - 是否为支持的体裁（议论文/记叙文/说明文）
    """
    return essay_type in SUPPORTED_ESSAY_TYPES


def call_with_retry(func, label, max_retries=3, delay=2.0, backoff=2.0):
    """
    通用同步重试调用器：func 抛异常时按指数退避 + 随机抖动重试

    等价于原先 api.py 中 retry_on_failure 装饰器 + 三个 *_with_retry 包装函数，
    收敛为一个函数，避免每种服务都复制一份重试样板。

    参数：
        func: callable - 无参可调用对象（需要参数时用 lambda / functools.partial 包装）
        label: string - 服务名称，用于日志定位（如 '作文批改服务'）
        max_retries: int - 最大尝试次数（含首次）
        delay: float - 初始重试延迟（秒）
        backoff: float - 延迟倍增因子

    返回：
        Any - func 的返回值

    异常：
        func 最后一次尝试仍失败时，原样抛出最后一个异常
    """
    current_delay = delay
    for attempt in range(1, max_retries + 1):
        try:
            logger.info('[重试机制] 调用%s（第%d/%d次）', label, attempt, max_retries)
            return func()
        except Exception as exc:
            if attempt >= max_retries:
                logger.error('[重试机制] %s 已达最大重试次数 %d，放弃重试: %s',
                             label, max_retries, exc)
                raise
            # 随机抖动，避免重试风暴
            jitter = random.uniform(0, current_delay * 0.1)
            sleep_time = current_delay + jitter
            logger.warning('[重试机制] %s 第%d/%d次失败: %s，%.2f 秒后重试',
                           label, attempt, max_retries, exc, sleep_time)
            time.sleep(sleep_time)
            current_delay *= backoff
