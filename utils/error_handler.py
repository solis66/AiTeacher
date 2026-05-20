"""
统一错误处理模块

提供统一的错误处理机制，将后端技术错误转换为用户友好的错误提示。

设计原则：
1. 安全性：不向用户暴露技术细节（如堆栈跟踪、内部错误码）
2. 用户友好：提供清晰、易懂的错误信息和解决建议
3. 可追溯性：内部记录详细的错误日志，便于问题排查
4. 一致性：统一的错误响应格式，便于前端处理

错误分类：
- 配置错误：API密钥未配置、配置文件缺失等
- 业务错误：参数校验失败、资源不存在等
- 服务错误：外部API调用失败、数据库连接失败等
- 系统错误：未知异常、内部错误等
"""

import logging
from typing import Optional, Dict, Any
from flask import jsonify

# 配置日志
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class APIError(Exception):
    """
    自定义API错误类
    
    用于封装所有业务和系统错误，提供统一的错误格式。
    
    属性：
        code: HTTP状态码
        error_code: 业务错误码，便于前端识别和处理
        message: 用户友好的错误信息
        details: 可选的详细信息（仅在开发模式下返回）
        suggestion: 解决建议，指导用户如何处理
    """
    
    def __init__(
        self,
        code: int = 500,
        error_code: str = "UNKNOWN_ERROR",
        message: str = "系统内部错误，请稍后重试",
        details: Optional[Dict[str, Any]] = None,
        suggestion: Optional[str] = None
    ):
        super().__init__(message)
        self.code = code
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        self.suggestion = suggestion


class ConfigurationError(APIError):
    """配置错误 - 当系统配置不正确时抛出"""
    
    def __init__(self, message: str, suggestion: Optional[str] = None):
        super().__init__(
            code=400,
            error_code="CONFIGURATION_ERROR",
            message=message,
            suggestion=suggestion or "请检查系统配置是否正确"
        )


class ValidationError(APIError):
    """验证错误 - 当用户输入不符合要求时抛出"""
    
    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(
            code=400,
            error_code="VALIDATION_ERROR",
            message=message,
            details={"field": field} if field else {},
            suggestion="请检查输入内容是否正确"
        )


class ResourceNotFoundError(APIError):
    """资源未找到错误 - 当请求的资源不存在时抛出"""
    
    def __init__(self, resource_type: str, resource_id: Optional[str] = None):
        message = f"{resource_type}不存在"
        if resource_id:
            message = f"{resource_type} '{resource_id}' 不存在"
        
        super().__init__(
            code=404,
            error_code="RESOURCE_NOT_FOUND",
            message=message,
            suggestion="请确认请求的资源是否存在"
        )


class ServiceUnavailableError(APIError):
    """服务不可用错误 - 当依赖的外部服务不可用时抛出"""
    
    def __init__(self, service_name: str, suggestion: Optional[str] = None):
        super().__init__(
            code=503,
            error_code="SERVICE_UNAVAILABLE",
            message=f"{service_name}服务暂时不可用",
            suggestion=suggestion or "请稍后重试，或联系管理员"
        )


class RateLimitError(APIError):
    """限流错误 - 当请求频率超过限制时抛出"""
    
    def __init__(self, retry_after: int = 60):
        super().__init__(
            code=429,
            error_code="RATE_LIMIT_EXCEEDED",
            message="请求过于频繁，请稍后重试",
            details={"retry_after": retry_after},
            suggestion=f"请在{retry_after}秒后重试"
        )


def handle_error(error: Exception, debug_mode: bool = False) -> tuple:
    """
    统一错误处理函数
    
    将异常转换为标准化的错误响应格式。
    
    参数：
        error: 异常对象
        debug_mode: 是否为调试模式，调试模式下返回详细错误信息
    
    返回：
        tuple: (response, status_code)
    """
    # 记录错误日志
    logger.error(f"错误处理: {type(error).__name__} - {str(error)}", exc_info=True)
    
    # 根据异常类型生成响应
    if isinstance(error, APIError):
        response_data = {
            "success": False,
            "error": {
                "code": error.error_code,
                "message": error.message,
                "suggestion": error.suggestion
            }
        }
        
        # 调试模式下返回详细信息
        if debug_mode and error.details:
            response_data["error"]["details"] = error.details
        
        return jsonify(response_data), error.code
    
    # 处理环境变量错误（安全配置模块抛出的错误）
    if isinstance(error, EnvironmentError):
        response_data = {
            "success": False,
            "error": {
                "code": "CONFIGURATION_ERROR",
                "message": "系统配置错误",
                "suggestion": "请联系管理员检查系统配置",
                "details": {"original_message": str(error)[:200]} if debug_mode else {}
            }
        }
        return jsonify(response_data), 500
    
    # 处理其他未知异常
    response_data = {
        "success": False,
        "error": {
            "code": "UNKNOWN_ERROR",
            "message": "系统内部错误，请稍后重试",
            "suggestion": "如果问题持续存在，请联系管理员"
        }
    }
    
    # 调试模式下返回详细错误信息
    if debug_mode:
        response_data["error"]["details"] = {
            "type": type(error).__name__,
            "message": str(error)
        }
    
    return jsonify(response_data), 500


def register_error_handlers(app):
    """
    注册Flask应用的错误处理器
    
    参数：
        app: Flask应用实例
    """
    
    @app.errorhandler(Exception)
    def handle_exception(error):
        """处理所有未捕获的异常"""
        debug_mode = app.config.get('DEBUG', False)
        return handle_error(error, debug_mode)
    
    @app.errorhandler(400)
    def handle_bad_request(error):
        """处理400错误"""
        response_data = {
            "success": False,
            "error": {
                "code": "BAD_REQUEST",
                "message": "请求参数错误",
                "suggestion": "请检查请求参数是否正确"
            }
        }
        return jsonify(response_data), 400
    
    @app.errorhandler(404)
    def handle_not_found(error):
        """处理404错误"""
        response_data = {
            "success": False,
            "error": {
                "code": "NOT_FOUND",
                "message": "请求的资源不存在",
                "suggestion": "请确认请求地址是否正确"
            }
        }
        return jsonify(response_data), 404
    
    @app.errorhandler(405)
    def handle_method_not_allowed(error):
        """处理405错误"""
        response_data = {
            "success": False,
            "error": {
                "code": "METHOD_NOT_ALLOWED",
                "message": "不支持的请求方法",
                "suggestion": "请使用正确的HTTP方法"
            }
        }
        return jsonify(response_data), 405
    
    @app.errorhandler(500)
    def handle_internal_error(error):
        """处理500错误"""
        debug_mode = app.config.get('DEBUG', False)
        response_data = {
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "系统内部错误，请稍后重试",
                "suggestion": "如果问题持续存在，请联系管理员"
            }
        }
        
        if debug_mode and error:
            response_data["error"]["details"] = {
                "message": str(error)
            }
        
        return jsonify(response_data), 500


# 前端错误提示映射
ERROR_MESSAGES: Dict[str, Dict[str, str]] = {
    "CONFIGURATION_ERROR": {
        "title": "配置错误",
        "message": "系统配置异常，无法正常服务",
        "suggestion": "请联系管理员检查系统配置"
    },
    "VALIDATION_ERROR": {
        "title": "输入错误",
        "message": "输入内容不符合要求",
        "suggestion": "请检查输入内容是否正确"
    },
    "RESOURCE_NOT_FOUND": {
        "title": "资源不存在",
        "message": "请求的资源未找到",
        "suggestion": "请确认请求内容是否正确"
    },
    "SERVICE_UNAVAILABLE": {
        "title": "服务暂不可用",
        "message": "相关服务暂时无法访问",
        "suggestion": "请稍后重试，或联系管理员"
    },
    "RATE_LIMIT_EXCEEDED": {
        "title": "请求过于频繁",
        "message": "当前请求频率过高",
        "suggestion": "请稍等片刻后重试"
    },
    "API_KEY_ERROR": {
        "title": "API密钥错误",
        "message": "API密钥配置不正确或已过期",
        "suggestion": "请联系管理员检查API密钥配置"
    },
    "UNKNOWN_ERROR": {
        "title": "系统错误",
        "message": "系统内部发生错误",
        "suggestion": "请稍后重试，如果问题持续存在请联系管理员"
    }
}


def get_user_friendly_message(error_code: str) -> Dict[str, str]:
    """
    获取用户友好的错误提示信息
    
    参数：
        error_code: 错误码
    
    返回：
        Dict: 包含title、message、suggestion的字典
    """
    return ERROR_MESSAGES.get(error_code, ERROR_MESSAGES["UNKNOWN_ERROR"])
