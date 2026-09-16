"""
作文批改路由模块

负责处理作文批改相关的HTTP请求，包括：
- 提交作文进行批改
- 获取批改结果
- 查询历史记录

路由设计遵循RESTful原则，提供清晰的API接口。

安全设计：
- 输入验证：对用户输入进行严格校验
- 错误处理：使用统一的错误处理机制
- 日志记录：记录关键操作和异常
"""

from flask import Blueprint, request, jsonify
from services.review_service import EssayReviewService
from utils.error_handler import ValidationError, handle_error
import logging

# 创建蓝图
essay_bp = Blueprint('essay', __name__)

# 初始化服务
review_service = EssayReviewService()

# 配置日志
logger = logging.getLogger(__name__)


@essay_bp.route('/api/essay/review', methods=['POST'])
def review_essay():
    """
    提交作文进行批改
    
    请求体：
    {
        "content": "作文内容",
        "essay_type": "议论文|记叙文|说明文"（可选）,
        "user_id": "用户ID"（可选）
    }
    
    成功响应：
    {
        "success": true,
        "data": {
            "score": 45,
            "total_score": 50,
            "essay_type": "议论文",
            "dimensions": [...],
            "overall_comment": "...",
            "improvements": [...],
            "summary": {...},
            "raw_response": "..."
        }
    }
    
    失败响应：
    {
        "success": false,
        "error": {
            "code": "ERROR_CODE",
            "message": "错误信息",
            "suggestion": "解决建议"
        }
    }
    """
    try:
        # 获取请求数据
        data = request.get_json()
        
        # 验证输入
        if not data or 'content' not in data:
            raise ValidationError("缺少作文内容", field="content")
        
        content = data.get('content', '').strip()
        essay_type = data.get('essay_type', '')
        user_id = data.get('user_id')
        
        # 验证内容长度
        if len(content) < 10:
            raise ValidationError("作文内容过短，请输入至少10个字符", field="content")
        
        if len(content) > 10000:
            raise ValidationError("作文内容过长，最大支持10000字符", field="content")
        
        # 验证体裁（如果提供）
        valid_types = ['议论文', '记叙文', '说明文']
        if essay_type and essay_type not in valid_types:
            raise ValidationError(f"无效的作文体裁，支持：{', '.join(valid_types)}", field="essay_type")
        
        logger.info(f"收到作文批改请求，用户ID: {user_id}，体裁: {essay_type}，字数: {len(content)}")
        
        # 调用服务进行批改
        result = review_service.review_essay(content, essay_type, user_id)
        
        logger.info(f"作文批改完成，得分: {result.get('score')}")
        
        return jsonify({
            "success": True,
            "data": result
        })
        
    except Exception as e:
        logger.error(f"作文批改失败: {str(e)}")
        return handle_error(e)


@essay_bp.route('/api/essay/history', methods=['GET'])
def get_history():
    """
    获取用户的作文批改历史
    
    查询参数：
    - user_id: 用户ID（可选）
    - page: 页码，默认1
    - limit: 每页数量，默认10
    
    成功响应：
    {
        "success": true,
        "data": {
            "items": [...],
            "total": 100,
            "page": 1,
            "limit": 10
        }
    }
    """
    try:
        user_id = request.args.get('user_id')
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        
        # 验证参数
        if page < 1:
            raise ValidationError("页码必须大于0", field="page")
        
        if limit < 1 or limit > 100:
            raise ValidationError("每页数量必须在1-100之间", field="limit")
        
        logger.info(f"查询作文批改历史，用户ID: {user_id}，页码: {page}，每页: {limit}")
        
        result = review_service.get_history(user_id, page, limit)
        
        return jsonify({
            "success": True,
            "data": result
        })
        
    except Exception as e:
        logger.error(f"查询历史失败: {str(e)}")
        return handle_error(e)


@essay_bp.route('/api/essay/history/<history_id>', methods=['GET'])
def get_history_detail(history_id):
    """
    获取单条批改记录详情
    
    路径参数：
    - history_id: 历史记录ID
    
    成功响应：
    {
        "success": true,
        "data": {...}
    }
    """
    try:
        logger.info(f"查询批改记录详情，ID: {history_id}")
        
        result = review_service.get_history_detail(history_id)
        
        if not result:
            from utils.error_handler import ResourceNotFoundError
            raise ResourceNotFoundError("批改记录", history_id)
        
        return jsonify({
            "success": True,
            "data": result
        })
        
    except Exception as e:
        logger.error(f"查询记录详情失败: {str(e)}")
        return handle_error(e)


@essay_bp.route('/api/essay/history/<history_id>', methods=['DELETE'])
def delete_history(history_id):
    """
    删除单条批改记录
    
    路径参数：
    - history_id: 历史记录ID
    
    成功响应：
    {
        "success": true,
        "message": "删除成功"
    }
    """
    try:
        logger.info(f"删除批改记录，ID: {history_id}")
        
        success = review_service.delete_history(history_id)
        
        if not success:
            from utils.error_handler import ResourceNotFoundError
            raise ResourceNotFoundError("批改记录", history_id)
        
        return jsonify({
            "success": True,
            "message": "删除成功"
        })
        
    except Exception as e:
        logger.error(f"删除记录失败: {str(e)}")
        return handle_error(e)


@essay_bp.route('/api/essay/types', methods=['GET'])
def get_essay_types():
    """
    获取支持的作文体裁列表
    
    成功响应：
    {
        "success": true,
        "data": [
            {"value": "议论文", "label": "议论文", "description": "..."},
            {"value": "记叙文", "label": "记叙文", "description": "..."},
            {"value": "说明文", "label": "说明文", "description": "..."}
        ]
    }
    """
    try:
        types = review_service.get_supported_types()
        
        return jsonify({
            "success": True,
            "data": types
        })
        
    except Exception as e:
        logger.error(f"获取体裁列表失败: {str(e)}")
        return handle_error(e)
