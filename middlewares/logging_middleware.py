"""
日志中间件模块

提供统一的请求日志记录功能，包括：
- 请求信息记录（方法、路径、参数）
- 响应时间统计
- 错误日志记录
- 请求ID追踪

设计原则：
- 不记录敏感信息（如密码、API密钥）
- 结构化日志输出，便于分析
- 性能影响最小化
"""

import logging
import time
import uuid
from flask import request, g

# 配置日志
logger = logging.getLogger(__name__)


def log_request_middleware(app):
    """
    注册请求日志中间件
    
    参数：
        app: Flask应用实例
    """
    
    @app.before_request
    def before_request():
        """
        请求前处理：记录请求开始时间和生成请求ID
        """
        # 生成请求ID
        g.request_id = str(uuid.uuid4())[:8]
        
        # 记录请求开始时间
        g.start_time = time.time()
        
        # 记录请求信息（脱敏处理）
        request_info = {
            'request_id': g.request_id,
            'method': request.method,
            'path': request.path,
            'remote_addr': request.remote_addr,
            'user_agent': request.user_agent.string[:100]
        }
        
        # 记录查询参数（脱敏）
        if request.args:
            request_info['query_params'] = _sanitize_dict(request.args.to_dict())
        
        # 记录请求体（脱敏，仅记录JSON类型）
        if request.is_json and request.get_json(silent=True):
            request_info['json_body'] = _sanitize_dict(request.get_json())
        
        logger.info(f"请求开始 - {request.method} {request.path} - ID: {g.request_id}", extra=request_info)
    
    @app.after_request
    def after_request(response):
        """
        请求后处理：记录响应时间和状态
        """
        if hasattr(g, 'start_time'):
            duration = (time.time() - g.start_time) * 1000  # 毫秒
            
            response_info = {
                'request_id': g.get('request_id', 'unknown'),
                'status_code': response.status_code,
                'duration_ms': round(duration, 2)
            }
            
            logger.info(f"请求完成 - {request.method} {request.path} - {response.status_code} - {round(duration, 2)}ms", extra=response_info)
        
        return response


def _sanitize_dict(data: dict) -> dict:
    """
    脱敏字典数据，移除敏感信息
    
    参数：
        data: 待脱敏的字典
        
    返回：
        dict: 脱敏后的字典
    """
    sensitive_keys = {'password', 'api_key', 'secret', 'token', 'key', 'auth'}
    
    sanitized = {}
    for key, value in data.items():
        # 检查键名是否包含敏感词
        if any(sensitive in key.lower() for sensitive in sensitive_keys):
            sanitized[key] = '***'
        else:
            sanitized[key] = value
    
    return sanitized


def log_exception_handler(error):
    """
    异常日志处理器
    
    参数：
        error: 异常对象
    """
    request_id = getattr(g, 'request_id', 'unknown')
    
    error_info = {
        'request_id': request_id,
        'method': request.method if request else 'unknown',
        'path': request.path if request else 'unknown',
        'error_type': type(error).__name__,
        'error_message': str(error)
    }
    
    logger.error(f"请求异常 - ID: {request_id}", exc_info=True, extra=error_info)
    
    return error
