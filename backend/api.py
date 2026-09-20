"""
AI智能批改系统 - API服务模块

功能概述：
- 提供作文批改和AI咨询服务的RESTful API接口
- 支持作文自动检测、智能批改、咨询问答等功能
- 完善的错误处理和日志记录机制
- 支持JWT认证和用户历史记录管理

安全设计：
- API密钥通过环境变量配置，不在代码中硬编码
- 使用JWT令牌进行用户认证
- 请求日志记录（敏感信息已过滤）
- 输入验证和长度限制防止攻击

错误处理：
- 统一的异常处理和错误响应格式
- 启动时配置验证
- 运行时健康检查接口
"""

from utils.win_env import load as _load_win_env

# 必须在导入模型工厂之前执行：受限宿主（IDE 终端/服务/沙箱）不会继承系统级
# 环境变量，这里从注册表补齐 DASHSCOPE / 阿里云 OCR 凭据，避免误报“未配置”。
_load_win_env()

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from agent.tools.react_agent import ReactAgent
from agent.tools.agent_tools import rag_summarize
from utils.essay_constants import (
    DIMENSION_MAP, DIMENSION_MAX_SCORES, TYPE_FEATURES,
    SUPPORTED_TYPES, MIN_CONTENT_LENGTH, MAX_CONTENT_LENGTH
)
from utils.score_calculator import (
    ScoreCalculator, calculate_score, validate_score_consistency, fix_score_if_needed
)
from utils.security_config import get_dashscope_api_key, SecurityConfig
from model.factory import chat_model, is_model_initialized
from utils.error_handler import ServiceUnavailableError
from utils.standard_loader import load_unified_standard
from utils.text_classifier import classify_text, is_essay_submission as classifier_is_essay, detect_essay_type as classifier_detect_type
from services.consultation_service import answer_consultation, stream_answer_consultation
from services import consult_context
from services import user_service
from utils import db_config
from utils.chat_memory import normalize_history
from utils.logger_handler import logger
from utils.request_helpers import (
    SUPPORTED_ESSAY_TYPES,
    call_with_retry,
    get_json_body,
    get_request_username,
    json_error,
    json_ok,
    validate_essay_type,
)
# 批改工作台路由（上传/分页识别/AI批改/保存/导出）
from routes.review import review_bp
import traceback
import re
import os
import json
import hashlib
import jwt
import time
import random
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'ai_teacher_secret_key_2026_must_be_at_least_32_bytes'

# 注册批改工作台蓝图（提供 /api/review* 系列接口）
app.register_blueprint(review_bp)

# 咨询检索的索引预热：把已有的批改记录同步进向量库（后台线程，不阻塞启动）。
# 不做成"启动时同步建库并等待"——作文很多时首次建索引要调用 embedding 接口，
# 可能耗时数分钟；失败也不影响服务启动，咨询会降级为无资料回答。
consult_context.initialize()

def validate_system_config():
    """
    验证系统配置是否完整
    在启动时调用，确保所有必要的配置已就绪
    
    返回：
        bool - True表示配置验证通过，False表示失败
        
    检查项：
        1. API密钥配置
        2. AI模型初始化状态
        3. ReactAgent初始化状态
    """
    errors = []
    print("\n🔍 系统配置验证开始...")
    
    # 检查API密钥
    try:
        api_key = get_dashscope_api_key()
        if not api_key:
            errors.append("❌ DASHSCOPE_API_KEY 环境变量为空")
        elif not SecurityConfig.validate_api_key_format(api_key):
            errors.append(f"❌ API密钥格式不正确: {api_key[:10]}...")
        else:
            print(f"✅ API密钥配置: {api_key[:10]}...")
    except EnvironmentError as e:
        errors.append(f"❌ API密钥配置错误: {str(e)}")
    
    # 检查模型
    global chat_model
    if chat_model is None:
        errors.append("❌ AI模型初始化失败")
    else:
        print("✅ AI模型初始化成功")
    
    # 检查Agent（延迟初始化，需要在调用时检查）
    print("⚠️  ReactAgent将在首次使用时初始化")
    
    if errors:
        print("\n❌ 系统配置验证失败:")
        for error in errors:
            print(f"  {error}")
        print("\n💡 请修复以上配置问题后重新启动服务")
        return False
    
    print("\n✅ 系统配置验证通过")
    return True


# 历史记录存储目录
HISTORY_DIR = os.path.join(os.path.dirname(__file__), 'history')

# 日志目录
LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# 初始化 PostgreSQL 用户表并写入初始测试账号（幂等）。
# 数据库不可用时仅记录错误，不阻塞服务启动；注册/登录接口会据此返回明确的 5xx。
try:
    user_service.init_users_table()
except Exception as e:
    # user_service 抛出的 DatabaseUnavailableError 只带一句通用提示（"数据库连接失败"），
    # 真正的失败原因（DNS 解析不了 / 端口不通 / 密码不对 / SSL 要求）在 __cause__ 里。
    # 部署排错全靠这一段，必须把根因展开打印，否则只能看到"连接失败"四个字干瞪眼。
    _root = e
    while getattr(_root, '__cause__', None) is not None:
        _root = _root.__cause__
    print(f"⚠️  用户表初始化失败（注册/登录将不可用）：{e}")
    if _root is not e:
        print(f"    根本原因：{type(_root).__name__}: {_root}")
    _cfg = db_config.get_db_config()
    print(
        "    连接参数：host={host} port={port} db={dbname} user={user} "
        "password={pwstate}".format(
            host=_cfg['host'], port=_cfg['port'], dbname=_cfg['dbname'],
            user=_cfg['user'],
            pwstate=('已设置(len=%d)' % len(_cfg['password'])) if _cfg['password'] else '**【空】**',
        )
    )
    if not _cfg['password']:
        print("    ↳ 密码为空：容器没读到 .env，检查仓库根目录下 .env 是否存在（不是 backend/.env）")
    logger.warning("用户表初始化失败: %s | 根因: %s: %s", e, type(_root).__name__, _root)


def log_api_request(func):
    """
    API请求日志装饰器
    记录请求的详细信息，便于追踪和调试
    
    参数：
        func: function - 被装饰的函数
        
    返回：
        function - 包装后的函数
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        request_id = f"{int(start_time * 1000)}-{random.randint(1000, 9999)}"
        
        # 记录请求信息
        log_entry = {
            'request_id': request_id,
            'timestamp': datetime.now().isoformat(),
            'method': request.method,
            'path': request.path,
            'client_ip': request.remote_addr,
            'user_agent': request.user_agent.string,
            'content_length': request.content_length or 0,
            'status': 'started'
        }
        
        # 记录请求体（敏感信息已过滤）
        if request.is_json:
            try:
                request_data = request.get_json()
                if request_data:
                    log_entry['request_data'] = {
                        'has_message': 'message' in request_data,
                        'message_length': len(request_data.get('message', '')),
                        'has_essay_type': 'essay_type' in request_data,
                        'essay_type': request_data.get('essay_type', '')
                    }
            except Exception as e:
                log_entry['request_parse_error'] = str(e)
        
        logger.info(f"[API请求] {log_entry}")

        try:
            # 执行实际的API处理
            response = func(*args, **kwargs)
            
            # 记录成功响应
            log_entry['status'] = 'success'
            log_entry['duration_ms'] = int((time.time() - start_time) * 1000)
            
            if isinstance(response, tuple):
                log_entry['status_code'] = response[1]
                if isinstance(response[0], dict):
                    log_entry['response_has_data'] = 'data' in response[0]
                    log_entry['response_success'] = response[0].get('success', False)
            else:
                log_entry['status_code'] = 200
            
            logger.info(f"[API响应] {log_entry}")

            return response
            
        except Exception as e:
            # 记录异常
            log_entry['status'] = 'error'
            log_entry['error'] = str(e)
            log_entry['duration_ms'] = int((time.time() - start_time) * 1000)
            log_entry['traceback'] = traceback.format_exc()
            
            logger.error(f"[API错误] {log_entry}")
            raise
    
    return wrapper


os.makedirs(HISTORY_DIR, exist_ok=True)


def token_required(f):
    """
    JWT认证装饰器
    验证请求头中的Authorization令牌
    
    参数：
        f: function - 被装饰的函数
        
    返回：
        function - 包装后的函数
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'success': False, 'error': '缺少认证令牌'}), 401
        
        try:
            token = token.replace('Bearer ', '')
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = data['username']
            # 用户校验改为查 PostgreSQL users 表（旧的 USERS 内存字典已废弃未定义）
            if not user_service.get_user_by_account(current_user):
                raise Exception('用户不存在')
        except Exception as e:
            return jsonify({'success': False, 'error': '令牌无效'}), 401
        
        return f(current_user, *args, **kwargs)
    
    return decorated


def load_essay_criteria():
    """
    加载各类型作文的评分标准
    从data目录读取《广东省中考作文评分标准.doc》作为所有体裁的统一评分依据
    （自 2026-09 起不再使用各体裁独立的 TXT 评分标准文件）
    
    返回：
        dict - 各类型作文评分标准字典（同一份统一标准）
    """
    criteria = {'议论文': '', '记叙文': '', '说明文': ''}

    try:
        unified = load_unified_standard()
        for essay_type in criteria.keys():
            criteria[essay_type] = unified
    except Exception as e:
        logger.error(f"加载统一评分标准失败: {e}")

    return criteria


ESSAY_CRITERIA = load_essay_criteria()

ESSAY_PROMPTS = {
    '议论文': """你是一个专业的初中语文作文批改教师。请仔细阅读以下议论文，并根据评分标准进行批改。

## 待批改的议论文
{essay_content}

## 议论文评分标准（满分50分）
{criteria}

## 批改要求

1. 你必须仔细分析上述作文的具体内容、结构、语言和论证方法
2. 根据评分标准对作文的各个方面进行独立评分
3. 总体评价必须针对这篇作文的具体内容，不能使用通用套话
4. 改进建议必须基于这篇作文的实际问题提出，具体且有针对性

请严格按照以下JSON格式输出批改结果（注意：所有评分必须是整数，总分不超过50分）：

```json
{{
  "总分": XX,
  "各项评分": {{
    "立意与中心": XX,
    "论点与论证": XX,
    "结构与层次": XX,
    "语言表达": XX,
    "例证与材料运用": XX
  }},
  "总体评价": "（针对这篇作文的具体评价）",
  "改进建议": [
    "（具体建议1）",
    "（具体建议2）",
    "（具体建议3）"
  ]
}}
```""",

    '记叙文': """你是一个专业的初中语文作文批改教师。请仔细阅读以下记叙文，并根据评分标准进行批改。

## 待批改的记叙文
{essay_content}

## 记叙文评分标准（满分50分）
{criteria}

## 批改要求

1. 你必须仔细分析上述作文的具体内容、人物、情节、语言和表达方式
2. 根据评分标准对作文的各个方面进行独立评分
3. 总体评价必须针对这篇作文的具体内容、人物刻画、情节安排等，不能使用通用套话
4. 改进建议必须基于这篇作文的实际问题提出，要具体指出哪里需要改进

请严格按照以下JSON格式输出批改结果（注意：所有评分必须是整数，总分不超过50分）：

```json
{{
  "总分": XX,
  "各项评分": {{
    "立意与中心": XX,
    "选材与内容": XX,
    "结构与层次": XX,
    "语言表达": XX,
    "细节与表现": XX,
    "书写与规范": XX
  }},
  "总体评价": "（针对这篇作文的具体评价）",
  "改进建议": [
    "（具体建议1）",
    "（具体建议2）",
    "（具体建议3）"
  ]
}}
```""",

    '说明文': """你是一个专业的初中语文作文批改教师。请仔细阅读以下说明文，并根据评分标准进行批改。

## 待批改的说明文
{essay_content}

## 说明文评分标准（满分50分）
{criteria}

## 批改要求

1. 你必须仔细分析上述作文的具体说明对象、说明方法、结构安排和语言特点
2. 根据评分标准对作文的各个方面进行独立评分
3. 总体评价必须针对这篇作文的具体内容，不能使用通用套话
4. 改进建议必须基于这篇作文的实际问题提出，要具体指出说明方法、结构或语言上的不足

请严格按照以下JSON格式输出批改结果（注意：所有评分必须是整数，总分不超过50分）：

```json
{{
  "总分": XX,
  "各项评分": {{
    "立意与中心": XX,
    "结构与层次": XX,
    "语言表达": XX,
    "方法与技巧": XX,
    "书写与规范": XX
  }},
  "总体评价": "（针对这篇作文的具体评价）",
  "改进建议": [
    "（具体建议1）",
    "（具体建议2）",
    "（具体建议3）"
  ]
}}
```

注意：所有评分必须是整数，总分不要超过50分。"""
}


def detect_essay_type(text):
    """
    智能检测作文类型
    根据文本内容特征判断作文类型：议论文、记叙文、说明文
    
    参数：
        text: string - 作文文本内容
        
    返回：
        string - 作文类型（议论文/记叙文/说明文）
    """
    # 统计各类型特征词出现次数（使用统一的TYPE_FEATURES常量）
    scores = {
        '议论文': 0,
        '记叙文': 0,
        '说明文': 0
    }
    
    # 使用统一的特征词常量统计
    for essay_type, keywords in TYPE_FEATURES.items():
        for kw in keywords:
            if kw in text:
                scores[essay_type] += 1
    
    # 检查是否有明确的类型声明
    if '议论文' in text:
        scores['议论文'] += 10
    if '记叙文' in text:
        scores['记叙文'] += 10
    if '说明文' in text:
        scores['说明文'] += 10
    
    # 计算总分并选择最高得分的类型
    max_score = max(scores.values())
    
    # 如果得分都很低，根据文本特征判断
    if max_score < 3:
        # 检查是否有故事性内容（记叙文特征）
        has_story = any(kw in text for kw in ['记得', '那天', '我', '他', '她', '故事', '经历'])
        # 检查是否有说明性内容
        has_explanation = any(kw in text for kw in ['说明', '介绍', '解释', '原理', '功能'])
        # 检查是否有议论性内容
        has_argument = any(kw in text for kw in ['论点', '论证', '观点', '认为', '因此'])
        
        if has_story and not has_explanation and not has_argument:
            return '记叙文'
        elif has_explanation and not has_story and not has_argument:
            return '说明文'
        elif has_argument and not has_story and not has_explanation:
            return '议论文'
        else:
            # 默认返回记叙文（初中阶段最常见）
            return '记叙文'
    
    # 返回得分最高的类型
    for essay_type, score in scores.items():
        if score == max_score:
            return essay_type
    
    return '记叙文'


def is_essay_submission(text):
    """
    判断用户输入是否为作文提交
    根据关键词和文本长度综合判断，确保只有真正的作文内容才触发批改流程
    
    判断逻辑（优先按文本长度判断）：
    1. 最小长度检查：至少100字才可能是作文
    2. 长文本优先：超过500字且包含作文关键词，直接判定为作文
    3. 超长文本：超过800字直接判定为作文，无需关键词
    4. 咨询类问题排除：仅适用于短文本（<300字）且不含作文关键词
    5. 作文关键词+长文本：包含作文关键词且超过200字判定为作文
    6. 纯长文本：超过500字直接判定为作文
    
    参数：
        text: string - 用户输入的文本
        
    返回：
        boolean - 是否为作文提交
    """
    if not text or not isinstance(text, str):
        logger.debug("[作文检测] 输入为空或非字符串类型")
        return False

    trimmed_text = text.strip()
    text_length = len(trimmed_text)

    # 1. 最小长度检查：至少100字才可能是作文
    if text_length < 100:
        logger.debug(f"[作文检测] 文本过短({text_length}字)，不是作文提交")
        return False
    
    essay_keywords = ['作文', '文章', '写作', 'essay', '作文题', '请批改', '请点评',
                      '写一篇', '写了一篇', '字数', '段落', '开头', '结尾',
                      '议论文', '记叙文', '说明文']
    consultation_keywords = ['如何', '怎么', '怎样', '为什么', '请问', '我想问',
                            '问一下', '咨询', '方法', '技巧', '策略', '要点', '建议',
                            '告诉我', '分析一下']

    has_essay = any(kw in trimmed_text for kw in essay_keywords)
    has_consult = any(kw in trimmed_text for kw in consultation_keywords)
    is_long = text_length > 200

    # 2. 长文本优先判定：超过500字且包含作文关键词，直接判定为作文
    #    即使包含咨询关键词也优先考虑是作文（用户可能在作文中提问）
    if text_length > 500 and has_essay:
        logger.debug(f"[作文检测] 长文本({text_length}字)且包含作文关键词，判定为作文提交")
        return True

    # 3. 超长文本（超过800字）直接判定为作文，无需关键词
    if text_length > 800:
        logger.debug(f"[作文检测] 超长文本({text_length}字)，直接判定为作文提交")
        return True

    # 4. 咨询类问题排除（仅适用于短文本）
    if has_consult and not has_essay and text_length < 300:
        logger.debug(f"[作文检测] 短文本({text_length}字)且包含咨询关键词，不是作文提交")
        return False

    # 5. 如果包含作文关键词且文本较长，判定为作文提交
    if has_essay and is_long:
        logger.debug(f"[作文检测] 包含作文关键词且文本较长({text_length}字)，判定为作文提交")
        return True

    # 6. 纯长文本（超过500字）也判定为作文提交
    if text_length > 500:
        logger.debug(f"[作文检测] 文本超过500字({text_length}字)，判定为作文提交")
        return True

    # 7. 中等长度文本（200-500字）需要包含作文关键词才判定为作文
    if is_long and has_essay:
        logger.debug("[作文检测] 中等长度文本且包含作文关键词，判定为作文提交")
        return True

    logger.debug("[作文检测] 未满足作文提交条件")
    return False


def extract_json_from_response(response_text):
    """
    从AI响应文本中提取JSON格式的批改结果
    支持代码块格式和纯JSON格式
    
    参数：
        response_text: string - AI响应的原始文本
        
    返回：
        dict|None - 解析后的JSON数据，解析失败返回None
    """
    json_pattern = r'```json\s*(\{.*?\})\s*```'
    match = re.search(json_pattern, response_text, re.DOTALL)

    if match:
        json_str = match.group(1)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON解析失败: {e}")

    brace_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    match2 = re.search(brace_pattern, response_text, re.DOTALL)
    if match2:
        try:
            result = json.loads(match2.group(0))
            if isinstance(result, dict) and '总分' in result:
                return result
        except json.JSONDecodeError:
            pass

    return None


def parse_json_feedback(json_data, essay_type):
    """
    解析JSON格式的作文批改反馈
    提取总分、各项评分、总体评价和改进建议
    
    参数：
        json_data: dict - JSON格式的批改数据
        essay_type: string - 作文类型
        
    返回：
        dict|None - 解析后的结构化数据
    """
    if not isinstance(json_data, dict):
        logger.warning(f"JSON数据类型错误，期望dict，得到 {type(json_data)}")
        return None

    result = {
        'score': None,
        'total_score': 50,
        'essay_type': essay_type,
        'dimensions': [],
        'overall_comment': '',
        'improvements': [],
        'raw_response': ''
    }

    try:
        # 解析总分
        if '总分' in json_data:
            score = json_data['总分']
            if isinstance(score, (int, float)):
                result['score'] = int(score)
            elif isinstance(score, str):
                score_match = re.search(r'\d+', score)
                if score_match:
                    result['score'] = int(score_match.group())

        # 解析各项评分（使用统一的DIMENSION_MAP和DIMENSION_MAX_SCORES常量）
        if '各项评分' in json_data and isinstance(json_data['各项评分'], dict):
            dims = DIMENSION_MAP.get(essay_type, DIMENSION_MAP['记叙文'])
            max_scores = DIMENSION_MAX_SCORES.get(essay_type, DIMENSION_MAX_SCORES['记叙文'])
            
            for dim_name in dims:
                if dim_name in json_data['各项评分']:
                    score = json_data['各项评分'][dim_name]
                    if isinstance(score, (int, float)):
                        result['dimensions'].append({
                            'name': dim_name, 
                            'score': int(score),
                            'max_score': max_scores.get(dim_name, 10)
                        })
                    elif isinstance(score, str):
                        score_match = re.search(r'\d+', score)
                        if score_match:
                            result['dimensions'].append({
                                'name': dim_name, 
                                'score': int(score_match.group()),
                                'max_score': max_scores.get(dim_name, 10)
                            })

        # 解析总体评价
        if '总体评价' in json_data:
            comment = json_data['总体评价']
            if isinstance(comment, str):
                result['overall_comment'] = comment.strip()
            elif isinstance(comment, (list, tuple)):
                result['overall_comment'] = ' '.join(str(c) for c in comment)

        # 解析改进建议
        if '改进建议' in json_data:
            suggestions = json_data['改进建议']
            if isinstance(suggestions, list):
                for s in suggestions:
                    if isinstance(s, str):
                        s = s.strip()
                        if s and len(s) > 5:
                            result['improvements'].append(s)
            elif isinstance(suggestions, str):
                lines = re.split(r'[,，\n]', suggestions)
                for line in lines:
                    line = line.strip()
                    if line and len(line) > 5:
                        result['improvements'].append(line)

    except Exception as e:
        logger.error(f"解析JSON数据时发生错误: {e}")
        return None

    return result


def parse_text_feedback(response_text, essay_type):
    """
    解析纯文本格式的作文批改反馈
    当JSON解析失败时，使用正则表达式从文本中提取评分信息
    如果无法提取到评分，会根据评语内容自动计算一个合理的分数
    
    参数：
        response_text: string - AI响应的原始文本
        essay_type: string - 作文类型
        
    返回：
        dict - 解析后的结构化数据
    """
    result = {
        'score': None,
        'total_score': 50,
        'essay_type': essay_type,
        'dimensions': [],
        'overall_comment': '',
        'improvements': [],
        'raw_response': response_text
    }

    # 提取总分（增强模式，支持更多格式）
    score_patterns = [
        r'总分[：:]\s*(\d+)',
        r'得分[：:]\s*(\d+)',
        r'总分\s*(\d+)\s*分',
        r'得分\s*(\d+)\s*分',
        r'(\d+)\s*分\s*\/\s*50',
        r'(\d+)\s*\/\s*50',
    ]

    for pattern in score_patterns:
        score_match = re.search(pattern, response_text)
        if score_match:
            result['score'] = int(score_match.group(1))
            break

    # 提取各维度评分（使用统一的DIMENSION_MAP和DIMENSION_MAX_SCORES常量）
    dim_list = DIMENSION_MAP.get(essay_type, DIMENSION_MAP['记叙文'])
    dims = [(dim, dim) for dim in dim_list]
    max_scores = DIMENSION_MAX_SCORES.get(essay_type, DIMENSION_MAX_SCORES['记叙文'])
    found_dims = set()

    for dim_key, dim_name in dims:
        pattern = rf'{re.escape(dim_key)}[：:]\s*(\d+)'
        match = re.search(pattern, response_text)
        if match and dim_name not in found_dims:
            result['dimensions'].append({
                'name': dim_name, 
                'score': int(match.group(1)),
                'max_score': max_scores.get(dim_name, 10)
            })
            found_dims.add(dim_name)

    # 提取总体评价
    overall_patterns = [
        r'总体评价[：:]\s*["""]*(.*?)["""]*\s*(?=改进建议|建议|$)',
        r'总评[：:]\s*["""]*(.*?)["""]*\s*(?=改进建议|建议|$)',
    ]

    for pattern in overall_patterns:
        match = re.search(pattern, response_text, re.DOTALL)
        if match:
            result['overall_comment'] = match.group(1).strip().strip('"').strip("'")
            break

    # 提取改进建议（增强模式，支持更多格式）
    improvement_patterns = [
        r'改进建议[：:]\s*(.*?)(?=\s*$|\s*总体评价|\s*评分标准)',
        r'建议[：:]\s*(.*?)(?=\s*$|\s*总体评价|\s*评分标准)',
        r'改进建议[：:]\s*["""]*(.*?)["""]*\s*$',
    ]

    for pattern in improvement_patterns:
        match = re.search(pattern, response_text, re.DOTALL)
        if match:
            content = match.group(1)
            lines = re.split(r'[,，\n]', content)
            for line in lines:
                line = line.strip()
                line = re.sub(r'^[\d\.\、\、\)\）]+', '', line)
                line = line.strip('"').strip("'").strip('【】[]')
                if line and len(line) > 10:
                    result['improvements'].append(line)
            break
    
    # 如果改进建议仍为空，尝试提取以数字或符号开头的列表项
    if not result['improvements']:
        suggestion_items = re.findall(r'[\d\.\、\*\-]\s*([^\n]{20,})', response_text)
        for item in suggestion_items[:5]:
            item = item.strip()
            if item and len(item) > 15:
                result['improvements'].append(item)

    # 如果无法提取到总分，尝试通过各维度评分计算总分
    if result['score'] is None and len(result['dimensions']) > 0:
        total = sum(dim['score'] for dim in result['dimensions'])
        if total > 0:
            result['score'] = total
    
    # 如果仍然没有总分，根据评语内容自动计算一个合理的分数
    if result['score'] is None:
        result['score'] = calculate_score_from_comment(response_text, essay_type)
    
    # 如果各维度评分为空，生成默认维度评分
    if len(result['dimensions']) == 0:
        dim_list = DIMENSION_MAP.get(essay_type, DIMENSION_MAP['记叙文'])
        dims = [(dim, dim) for dim in dim_list]
        max_scores = DIMENSION_MAX_SCORES.get(essay_type, DIMENSION_MAX_SCORES['记叙文'])
        
        # 根据总分分配各维度分数
        if result['score'] is not None:
            total_max = sum(max_scores.values())
            remaining = result['score']
            
            for dim_key, dim_name in dims:
                max_score = max_scores.get(dim_name, 10)
                if dim_name == dims[-1][1]:
                    score = remaining
                else:
                    score = min(int((max_score / total_max) * result['score']), remaining)
                result['dimensions'].append({
                    'name': dim_name,
                    'score': max(0, score),
                    'max_score': max_score
                })
                remaining -= score
        else:
            # 如果没有总分，使用中等分数
            for dim_key, dim_name in dims:
                max_score = max_scores.get(dim_name, 10)
                result['dimensions'].append({
                    'name': dim_name,
                    'score': int(max_score * 0.7),
                    'max_score': max_score
                })

    return result


def calculate_score_from_comment(comment, essay_type):
    """
    根据评语内容自动计算作文分数
    通过分析评语中的积极和消极词汇来估算分数
    
    参数：
        comment: string - 总体评价文本
        essay_type: string - 作文类型
        
    返回：
        int - 计算出的分数（0-50）
    """
    # 积极词汇
    positive_words = [
        '优秀', '出色', '很好', '良好', '不错', '突出', '精彩', '生动',
        '深刻', '丰富', '清晰', '流畅', '严谨', '新颖', '独特', '感人',
        '细腻', '优美', '扎实', '到位', '恰当', '合理', '完整', '有条理',
        '中心明确', '结构严谨', '语言流畅', '内容充实', '感情真挚', '选材新颖'
    ]
    
    # 消极词汇
    negative_words = [
        '不足', '欠缺', '问题', '缺陷', '较差', '一般', '平淡', '空洞',
        '混乱', '生硬', '冗长', '松散', '单薄', '模糊', '错误', '不当',
        '不够', '缺乏', '需要改进', '有待提高', '结构松散', '中心不明确',
        '语言生硬', '内容空洞', '论据不足', '论证薄弱'
    ]
    
    # 强烈消极词汇（扣分更多）
    strong_negative_words = [
        '严重', '错误', '失败', '极差', '完全', '根本', '无法', '不能'
    ]
    
    # 基础分数（中等水平）
    score = 28
    
    # 计算积极词得分
    for word in positive_words:
        if word in comment:
            score += 1
    
    # 计算消极词扣分
    for word in negative_words:
        if word in comment:
            score -= 1
    
    # 计算强烈消极词扣分
    for word in strong_negative_words:
        if word in comment:
            score -= 2
    
    # 根据评语长度调整（越长通常越详细，分数越可靠）
    if len(comment) > 500:
        score += 2
    elif len(comment) < 100:
        score -= 2
    
    # 限制分数范围
    score = max(15, min(48, score))
    
    return score


def parse_essay_feedback(response_text, essay_type):
    """
    解析作文批改反馈的主函数
    优先尝试JSON解析，失败时回退到文本解析
    
    参数：
        response_text: string - AI响应的原始文本
        essay_type: string - 作文类型
        
    返回：
        dict - 解析后的结构化数据
    """
    json_data = extract_json_from_response(response_text)

    if json_data:
        parsed = parse_json_feedback(json_data, essay_type)
        if parsed and parsed.get('score') is not None:
            parsed['raw_response'] = response_text
            parsed = validate_and_fix_score(parsed)
            return parsed
        else:
            logger.info("JSON解析成功但数据不完整，尝试文本解析")

    parsed = parse_text_feedback(response_text, essay_type)
    parsed['raw_response'] = response_text
    parsed = validate_and_fix_score(parsed)
    return parsed


def validate_and_fix_score(parsed_result):
    """
    校验并修正总分与各项评分之和的一致性
    
    使用ScoreCalculator模块实现总分自动汇总，确保各项评分与总分的逻辑一致性。
    如果总分与各项评分之和不一致，会自动调整总分使其与各项评分之和一致。
    如果维度评分超出范围，会自动进行归一化处理。
    
    参数：
        parsed_result: dict - 解析后的作文批改结果
        
    返回：
        dict - 校验并修正后的结果
    """
    if not parsed_result or not parsed_result.get('dimensions'):
        return parsed_result
    
    # 获取作文体裁
    essay_type = parsed_result.get('essay_type', '记叙文')
    
    # 构建维度评分字典
    dimension_scores = {dim['name']: dim['score'] for dim in parsed_result['dimensions']}
    
    # 使用ScoreCalculator进行总分计算和校验
    calculator = ScoreCalculator(essay_type)
    
    # 获取报告的总分
    original_score = parsed_result.get('score')
    
    # 对维度评分进行归一化处理（修正超出范围的分数）
    normalized_scores = calculator.normalize_dimension_scores(dimension_scores)
    
    # 检查是否有分数被修正
    has_dimension_fixes = False
    for dim_name, score in dimension_scores.items():
        if normalized_scores.get(dim_name, score) != score:
            has_dimension_fixes = True
            logger.warning(f"[维度分数修正] 体裁: {essay_type}, 维度: {dim_name}, 原始分数: {score}, 修正后: {normalized_scores[dim_name]}")
    
    # 使用计算器修正总分
    fixed_score, was_fixed = calculator.fix_total_score(normalized_scores, original_score)
    
    # 更新维度评分（使用归一化后的值）
    for dim in parsed_result['dimensions']:
        dim_name = dim['name']
        if dim_name in normalized_scores:
            dim['score'] = normalized_scores[dim_name]
            dim['max_score'] = calculator.max_scores.get(dim_name, dim.get('max_score', 10))
    
    # 更新结果
    parsed_result['score'] = fixed_score
    parsed_result['calculated_total'] = calculator.calculate_total(normalized_scores)
    parsed_result['total_max_score'] = calculator.total_max_score
    
    # 标记是否有修正
    if was_fixed or has_dimension_fixes:
        parsed_result['score_fixed'] = True
        if was_fixed:
            logger.warning(f"[总分校验] 体裁: {essay_type}, 检测到总分({original_score})与各项评分之和({parsed_result['calculated_total']})不一致，已自动修正为: {fixed_score}")
    else:
        logger.info(f"[总分校验] 体裁: {essay_type}, 总分校验通过: {fixed_score}")
    
    # 添加校验信息
    parsed_result['validation'] = {
        'is_consistent': calculator.validate_total_consistency(normalized_scores, fixed_score),
        'is_complete': calculator.validate_dimension_completeness(normalized_scores)
    }
    
    return parsed_result


def generate_essay_review(essay_content, essay_type):
    """
    生成作文批改结果
    使用RAG服务调用AI生成批改结果，优先使用用户选择的作文类型
    
    参数：
        essay_content: string - 作文内容
        essay_type: string - 作文类型（议论文/记叙文/说明文）
        
    返回：
        string - AI生成的批改结果
    """
    try:
        # 步骤1：验证作文内容
        if not essay_content or not essay_content.strip():
            raise ValueError("作文内容不能为空")
        
        content_length = len(essay_content.strip())
        if content_length < 50:
            raise ValueError(f"作文内容过短（{content_length}字），请提供至少50字的作文内容")
        
        if content_length > 10000:
            raise ValueError(f"作文内容过长（{content_length}字），请控制在10000字以内")
        
        # 步骤2：验证作文类型
        if essay_type and essay_type.strip():
            essay_type = essay_type.strip()
            if essay_type not in SUPPORTED_ESSAY_TYPES:
                raise ValueError(f"不支持的作文类型：{essay_type}，请选择议论文、记叙文或说明文")
        
        # 步骤3：记录日志
        logger.info(f"[作文批改] 开始处理作文，用户选择体裁: {essay_type or '未指定(将自动检测)'}，字数: {content_length}")
        
        # 步骤4：调用RAG服务生成批改结果
        response = rag_summarize.invoke({"query": essay_content, "essay_type": essay_type})
        
        # 步骤5：验证返回结果
        if not response or not response.strip():
            logger.warning("[作文批改] AI返回空结果")
            return "抱歉，生成作文批改失败，请稍后重试。"

        logger.info(f"[作文批改] 成功生成批改结果，长度: {len(response)}")
        return response

    except ValueError as e:
        logger.warning(f"[作文批改] 输入验证失败: {str(e)}")
        raise Exception(f"输入错误：{str(e)}")
    except KeyError as e:
        logger.error(f"[作文批改] 提示词模板变量错误: {str(e)}")
        raise Exception("系统配置错误，请联系管理员")
    except Exception as e:
        logger.error(f"[作文批改] 生成失败: {str(e)}")
        logger.error(traceback.format_exc())
        raise Exception("AI服务暂时不可用，请稍后重试")


def create_consultation_prompt(user_message):
    """
    创建初中作文咨询的专业提示词
    根据用户问题类型构建针对性的咨询提示词，确保AI以专业的初中语文老师身份回复
    
    参数：
        user_message: string - 用户的咨询问题
        
    返回：
        string - 构建好的专业提示词
        
    核心功能：
        1. 自动检测用户问题涉及的主题
        2. 根据初中作文三个核心标准构建专业提示词
        3. 提供针对性的指导建议
        4. 确保回答符合初中生认知水平
    """
    # 主题关键词映射，用于自动检测用户问题类型
    topic_keywords = {
        'writing_skills': ['写作', '技巧', '方法', '怎么写', '如何写', '怎样写', '技巧'],
        'structure': ['结构', '开头', '结尾', '段落', '过渡', '提纲', '框架'],
        'material': ['选材', '素材', '例子', '论据', '材料', '事例'],
        'language': ['语言', '词汇', '修辞', '描写', '表达', '语句'],
        'theme': ['主题', '立意', '中心', '观点', '主旨'],
        'type': ['议论文', '记叙文', '说明文', '体裁', '文体'],
        'score': ['评分', '分数', '标准', '批改', '点评', '得分'],
        'revision': ['修改', '改进', '优化', '润色', '改错']
    }
    
    # 检测用户问题涉及的主题
    detected_topics = []
    for topic, keywords in topic_keywords.items():
        if any(kw in user_message for kw in keywords):
            detected_topics.append(topic)
    
    # 初中作文三个核心评分标准
    # 1. 内容（主题、立意、选材）
    # 2. 结构（组织、条理、连贯）
    # 3. 语言（表达、词汇、修辞）
    
    base_prompt = """你是一位专业的初中语文作文辅导老师，擅长解答初中生在作文写作过程中遇到的各种问题。

【初中作文评分标准】
作为专业老师，请依据以下三个核心标准为学生提供指导：

一、内容标准（40分）
- 主题明确：中心突出，立意深刻，观点鲜明
- 选材恰当：材料真实、典型、新颖，能有力支撑主题
- 内容充实：言之有物，感情真挚，有思想深度

二、结构标准（30分）
- 结构完整：有开头、主体、结尾，层次分明
- 条理清晰：段落划分合理，过渡自然流畅
- 详略得当：重点突出，主次分明

三、语言标准（30分）
- 语言通顺：用词准确，语句流畅，没有语病
- 表达生动：恰当运用修辞手法，描写具体形象
- 书写规范：字迹工整，标点正确，格式规范

【用户问题】
{user_message}

【回答要求】
1. 使用简洁明了的语言，符合初中生的认知水平
2. 提供具体的例子和可操作的步骤指导
3. 结合初中作文评分标准进行专业分析
4. 保持耐心和鼓励的语气，激发学生的写作兴趣
5. 如果涉及具体问题，请给出明确的解决方法
6. 避免使用过于专业的术语，必要时进行解释

【针对性指导】
{topic_guide}

请开始回答：
"""
    
    # 根据检测到的主题添加针对性指导
    topic_guide = ""
    if detected_topics:
        topic_guides = {
            'writing_skills': '🎯 本次咨询涉及【写作技巧】，请重点讲解具体的写作方法和实用技巧，结合实例说明',
            'structure': '🎯 本次咨询涉及【文章结构】，请详细说明作文的结构安排和段落组织方法',
            'material': '🎯 本次咨询涉及【选材立意】，请指导如何选择和运用写作素材，确保材料能支撑主题',
            'language': '🎯 本次咨询涉及【语言表达】，请讲解如何使用恰当的词汇和修辞手法，提升语言表现力',
            'theme': '🎯 本次咨询涉及【主题立意】，请指导如何确定和深化作文主题，使中心更突出',
            'type': '🎯 本次咨询涉及【作文体裁】，请说明不同体裁（议论文、记叙文、说明文）的特点和写作要求',
            'score': '🎯 本次咨询涉及【评分标准】，请解释初中作文评分标准，指导如何在各方面获得高分',
            'revision': '🎯 本次咨询涉及【修改润色】，请提供具体的修改方法和优化建议'
        }
        
        topic_guide = '\n'.join([topic_guides.get(topic, '') for topic in detected_topics if topic in topic_guides])
    
    return base_prompt.format(user_message=user_message, topic_guide=topic_guide)


def consult_essay_teacher(user_message):
    """
    咨询作文老师服务
    为用户提供专业的作文写作指导和建议
    
    功能特点：
    - 针对初中作文的各个方面提供专业指导
    - 支持写作技巧、结构安排、选材立意、语言表达等多方面咨询
    - 自动检测用户问题类型，提供针对性回答
    - 语言亲切易懂，适合初中生理解
    - 支持延迟初始化：Agent将在首次调用时自动初始化
    
    参数：
        user_message: string - 用户的咨询问题
        
    返回：
        string - AI老师的专业回复
        
    异常处理：
        - ValueError: 配置错误
        - EnvironmentError: 环境配置错误
        - Exception: 其他未知错误
    """
    # 尝试确保Agent已就绪（支持延迟初始化）
    try:
        agent._ensure_agent_ready()
        logger.info("[咨询老师] Agent初始化成功")
    except Exception as e:
        logger.error(f"[咨询老师] Agent初始化失败: {str(e)}")
        raise Exception("AI服务未就绪，请联系管理员检查配置")

    # 构建专业咨询提示词
    prompt = create_consultation_prompt(user_message)
    logger.info(f"[咨询老师] 构建专业咨询提示词，检测到主题: {user_message[:50]}...")

    try:
        response = ''
        chunk_count = 0

        logger.info("[咨询老师] 开始接收流式响应...")

        for chunk in agent.execute_stream(prompt):
            chunk_count += 1
            if chunk:
                response += chunk
                logger.debug(f"[咨询老师] 收到第{chunk_count}个响应块，累计长度: {len(response)}")

        response = response.strip()
        logger.info(f"[咨询老师] 流式响应接收完成，最终长度: {len(response)}")

        # 如果回复过长，进行适当截断（保留核心内容）
        if len(response) > 5000:
            response = response[:5000] + '\n\n（内容较长，已自动精简）'

        # 检查返回结果是否为空
        if not response:
            logger.warning("[咨询老师] AI返回内容为空")
            return "抱歉，暂时无法回答这个问题，请稍后重试。"

        return response

    except ValueError as e:
        logger.error(f"[咨询老师] 配置错误: {str(e)}")
        raise Exception(f"配置错误: {str(e)}")
    except EnvironmentError as e:
        logger.error(f"[咨询老师] 环境配置错误: {str(e)}")
        raise Exception("AI服务配置错误，请联系管理员")
    except Exception as e:
        logger.error(f"[咨询老师] 咨询失败: {str(e)}")
        logger.error(traceback.format_exc())
        raise Exception("AI咨询服务暂时不可用，请稍后重试")


def log_user_input(username, message, essay_type=None, is_essay=False):
    """
    记录用户输入日志
    确保完整记录用户提交的作文内容，便于后续分析和调试
    
    参数：
        username: string - 用户名
        message: string - 用户输入内容
        essay_type: string - 作文类型（可选）
        is_essay: boolean - 是否为作文提交
    """
    log_entry = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
        'username': username,
        'message': message[:500] + '...' if len(message) > 500 else message,
        'message_length': len(message),
        'essay_type': essay_type,
        'is_essay': is_essay,
        'source': request.remote_addr if request else 'unknown'
    }
    
    logger.info(f"[用户输入日志] {log_entry['timestamp']} | 用户: {log_entry['username']} | 类型: {'作文-' + essay_type if essay_type else ('作文(自动识别)' if is_essay else '普通消息')} | 长度: {log_entry['message_length']}")
    
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"user_input_{time.strftime('%Y%m%d')}.log")
    
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    except Exception as e:
        logger.error(f"写入用户日志失败: {str(e)}")


@app.route('/chat', methods=['POST'])
@log_api_request
def chat():
    """
    聊天接口
    接收用户消息，判断是否为作文提交，返回AI回复或作文批改结果
    
    请求体: {"message": "用户输入的文本", "essay_type": "作文类型（可选）"}
    返回: {"success": true, "data": {...}, "raw_response": "..."}
    """
    # 数据验证：请求体必须是 JSON 对象
    data = get_json_body()
    if data is None:
        if not request.is_json:
            return json_error('请求格式错误', '请使用JSON格式提交请求')
        return json_error('请求数据格式错误', '请求体必须是JSON对象')

    message = data.get('message', '')
    user_selected_essay_type = data.get('essay_type', '')
    # 对话记忆：前端传来的本会话最近轮次。
    # 服务端强制重新裁剪（轮次上限、单条长度、合计长度），不信任前端传的规模。
    history = normalize_history(data.get('history'))
    if not history:
        # 前端未携带上下文时，回退到服务端持久化的咨询记录（按天 Markdown 中最近一次会话），
        # 保证刷新页面或更换设备后 AI 仍能续接前文
        history = normalize_history(latest_session_messages(get_request_username()))

    # 咨询检索范围：role 决定"我"能否解析为学生本人，student 用于老师端显式指定学生。
    # 两者都只是**意图声明**，不是安全边界——真正的数据隔离由 owner（X-Username）
    # 在检索过滤条件里保证。取值非法时退回默认，不因参数问题让咨询失败。
    role = (data.get('role') or 'auto').strip().lower()
    if role not in ('student', 'teacher', 'auto'):
        role = 'auto'
    student_hint = (data.get('student') or '').strip()[:40]

    # 获取当前用户（从请求头或会话中）
    current_user = get_request_username()

    # 验证消息内容
    if not message or not isinstance(message, str):
        return json_error('请输入内容', '请输入作文内容或咨询问题')

    # 验证消息长度
    message_length = len(message.strip())
    if message_length < MIN_CONTENT_LENGTH:
        return json_error('内容过短', f'输入内容至少需要{MIN_CONTENT_LENGTH}个字符')

    if message_length > MAX_CONTENT_LENGTH:
        return json_error('内容过长', f'输入内容不能超过{MAX_CONTENT_LENGTH}个字符')

    # 验证作文类型（如果提供）
    if user_selected_essay_type and not validate_essay_type(user_selected_essay_type):
        return json_error('无效的作文类型', '作文类型只能是：议论文、记叙文或说明文')

    try:
        # 使用新的文本分类器判断文本类型
        text_type, detected_essay_type = classify_text(message)

        # 前端 AI 咨询页会显式声明 type='consultation'，这里以显式声明为准：
        # 分类器对自由提问（如「1」「为什么我总写不长」）常判为 unknown，
        # 若不纠正就会掉出下面的流式分支，退化成一次性返回的非流式回答（前端一直等，感觉很慢）。
        # 仅在分类器未判定为作文时才纠正，避免用户粘贴作文正文时被误当作咨询。
        if (data.get('type') or '').strip().lower() == 'consultation' and text_type != 'essay':
            text_type = 'consultation'
        
        # 记录用户输入日志
        log_user_input(current_user, message, user_selected_essay_type, text_type == 'essay')

        if text_type == 'essay':
            # 作文提交流程
            # 优先使用用户选择的体裁，如果未选择则使用分类器识别的体裁
            if user_selected_essay_type and validate_essay_type(user_selected_essay_type):
                essay_type = user_selected_essay_type
                logger.info(f"使用用户选择的体裁: {essay_type}")
            elif detected_essay_type:
                essay_type = detected_essay_type
                logger.info(f"自动识别体裁: {essay_type}")
            else:
                essay_type = '记叙文'
                logger.info("未检测到体裁，使用默认值: 记叙文")

            # 调用RAG服务生成作文批改结果（带重试机制）
            response = call_with_retry(
                lambda: generate_essay_review(message, essay_type),
                '作文批改服务'
            )
            
            # 解析AI返回的作文批改结果
            parsed = parse_essay_feedback(response, essay_type)
            
            # 确保essay_type被正确设置
            if not parsed.get('essay_type'):
                parsed['essay_type'] = essay_type
            if parsed['score'] is None:
                parsed['essay_type'] = essay_type
            
            # 添加essayType字段（前端期望的字段名）
            parsed['essayType'] = parsed.get('essay_type', essay_type)
            parsed['response_type'] = 'essay_review'
        elif text_type == 'consultation':
            # 前端请求流式输出时（stream=true），咨询回答按 SSE 逐 token 增量推送
            if data.get('stream') is True:
                def _consult_stream():
                    """把流式咨询事件编码为 SSE 帧，交给前端增量渲染。"""
                    for evt in stream_answer_consultation(
                            message, history, owner=current_user, role=role, student=student_hint):
                        yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
                    # 兜底保证「结束」信号一定送达（事件流若出错前已收尾，这里不重复发已发过的 done）
                    yield "data: {\"type\":\"done\"}\n\n"

                sse_resp = Response(_consult_stream(), mimetype='text/event-stream')
                sse_resp.headers['Cache-Control'] = 'no-cache'
                sse_resp.headers['X-Accel-Buffering'] = 'no'
                sse_resp.headers['Connection'] = 'keep-alive'
                return sse_resp

            # 咨询类问题，使用新的咨询服务（携带本会话最近的对话轮次与学情检索范围）
            consult_result = answer_consultation(message, history,
                                                 owner=current_user, role=role, student=student_hint)
            
            if consult_result['success']:
                response = consult_result['content']
                # 构建咨询响应格式
                # 注意：必须设置 raw_response 字段，前端依赖此字段显示内容
                parsed = {
                    'score': None,
                    'dimensions': [],
                    'overall_comment': response,
                    'improvements': [],
                    'summary': None,
                    'essay_type': None,
                    'essayType': None,
                    'response_type': consult_result['type'],
                    'raw_response': response  # 确保前端能获取到响应内容
                }
            else:
                # 咨询服务失败，降级到原有的咨询方式
                logger.warning("[Chat] 咨询服务失败，降级到原有咨询方式")
                response = call_with_retry(
                    lambda: consult_essay_teacher(message),
                    '作文咨询服务'
                )
                parsed = {
                    'score': None,
                    'dimensions': [],
                    'overall_comment': response,
                    'improvements': [],
                    'summary': None,
                    'essay_type': None,
                    'essayType': None,
                    'response_type': 'ai',
                    'raw_response': response  # 确保前端能获取到响应内容
                }
        else:
            # 未知类型，降级到原有的咨询方式
            logger.warning(f"[Chat] 文本类型未知({text_type})，使用原有咨询方式")
            response = call_with_retry(
                lambda: consult_essay_teacher(message),
                '作文咨询服务'
            )
            
            # 咨询类聊天直接返回响应，不进行作文解析
            parsed = {
                'score': None,
                'dimensions': [],
                'overall_comment': response,
                'improvements': [],
                'summary': None,
                'essay_type': None,
                'essayType': None,
                'response_type': 'ai',
                'raw_response': response  # 确保前端能获取到响应内容
            }

        return jsonify({
            'success': True,
            'data': parsed,
            'raw_response': response
        })
    except ValueError as e:
        logger.warning(f"[Chat] 数据验证错误: {str(e)}")
        logger.warning(traceback.format_exc())
        return json_error('数据验证错误', f'数据验证失败: {str(e)}')
    except ServiceUnavailableError as e:
        logger.error(f"[Chat] 服务不可用: {str(e)}")
        logger.error(traceback.format_exc())
        return json_error('服务不可用', f'AI服务暂时不可用，请稍后重试: {str(e)}', status=503)
    except Exception as e:
        logger.error(f"[Chat] 处理请求时发生错误: {str(e)}")
        logger.error(traceback.format_exc())
        return json_error('服务器内部错误', '处理请求时出现错误，请稍后重试', status=500)


@app.route('/register', methods=['POST'])
def register():
    """
    用户注册接口
    校验手机号/密码/确认密码，写入 PostgreSQL 用户表，返回注册结果
    （注册成功后由前端引导回到登录页登录）

    请求体: {"account": "账号", "password": "xxx", "confirm_password": "xxx", "role": "teacher|student"}
    返回: {"success": true, "message": "注册成功，请登录", "account": "账号", "role": "student"}
    """
    data = get_json_body()
    if data is None:
        if not request.is_json:
            return json_error('请求格式错误', '请使用JSON格式提交请求')
        return json_error('请求数据格式错误', '请求体必须是JSON对象')

    # 兼容 username 字段名（前端亦可沿用 username 提交账号）
    account = (data.get('account') or data.get('username') or '').strip()
    password = data.get('password') or ''
    confirm = data.get('confirm_password') or data.get('confirmPassword') or ''
    role = (data.get('role') or user_service.DEFAULT_ROLE).strip().lower()

    # 校验账号：5~20 位字母/数字/下划线（由原先的 11 位手机号放宽）
    if not re.fullmatch(user_service.ACCOUNT_PATTERN, account):
        return json_error(
            '账号格式错误',
            f"账号需为{user_service.ACCOUNT_MIN_LENGTH}~{user_service.ACCOUNT_MAX_LENGTH}位，"
            '仅支持字母、数字与下划线，且须以字母或数字开头',
        )

    # 校验账号类型：只允许老师 / 学生
    if role not in user_service.VALID_ROLES:
        return json_error('账号类型错误', '账号类型只能是老师或学生')

    # 校验密码：长度 ≥ 6，且仅允许可见 ASCII 字符（字母/数字/特殊符号，无空格/中文/控制符）
    if not password or len(password) < 6:
        return json_error('密码格式错误', '密码长度不能少于6位')
    if re.search(r'[^\x21-\x7E]', password):
        return json_error('密码格式错误', '密码仅支持字母、数字与可见符号')

    # 校验确认密码一致
    if password != confirm:
        return json_error('两次密码不一致', '两次输入的密码不一致')

    try:
        user_service.create_user(account, password, role)
    except user_service.DuplicateAccountError:
        return json_error('账号已注册', '该账号已注册，请直接登录')
    except user_service.DatabaseUnavailableError:
        return json_error('数据库不可用', '数据库连接失败，请稍后重试', status=503)

    logger.info("[注册] 新用户注册成功: %s（类型 %s）", account, role)
    return json_ok('注册成功，请登录', account=account, role=role)


@app.route('/login', methods=['POST'])
def login():
    """
    用户登录接口
    从 PostgreSQL 用户表读取账号，用 bcrypt 校验密码，返回JWT令牌

    请求体: {"username": "admin", "password": "123456"}
    返回: {"success": true, "token": "xxx", "username": "admin",
           "role": "teacher", "role_label": "老师"}
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'success': False, 'error': '请输入用户名和密码'}), 400

    username = (data.get('username') or data.get('account') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return jsonify({'success': False, 'error': '请输入用户名和密码'}), 400

    try:
        user = user_service.get_user_by_account(username)
        if user and user_service.verify_password(user, password):
            # 角色写进 token 一并下发：前端据此决定显示老师端还是学生端界面。
            # 注意这只是「界面分流」依据，真正的权限判定一律在服务端按 users.role 复核。
            role = user.get('role') or user_service.DEFAULT_ROLE
            token = jwt.encode({
                'username': user['account'],
                'role': role,
                'exp': datetime.utcnow() + timedelta(hours=24)
            }, app.config['SECRET_KEY'])

            return jsonify({
                'success': True,
                'token': token,
                'username': user['account'],
                'role': role,
                'role_label': user_service.ROLE_LABELS.get(role, role)
            })
        return jsonify({'success': False, 'error': '用户名或密码错误'}), 401
    except user_service.DatabaseUnavailableError:
        logger.error("[登录] 数据库不可用")
        return jsonify({'success': False, 'error': '数据库不可用，请稍后重试'}), 503


def history_day_path(username, date_str):
    """
    获取「某用户某一天」的咨询记录文件路径

    参数：
        username: string - 用户名
        date_str: string - 'YYYY-MM-DD'

    返回：
        string - 天级 Markdown 文件路径（{username}_consult_{date}.md）
    """
    return os.path.join(HISTORY_DIR, f'{username}_consult_{date_str}.md')


def get_user_history_path(username):
    """
    获取**早期用户级**历史文件路径（仅供旧数据迁移使用）

    参数：
        username: string - 用户名

    返回：
        string - 旧版用户级 Markdown 文件路径（{username}_consult_history.md）
    """
    # 咨询记录以 Markdown 落盘：既方便人工查看，也便于作为 AI 回答时的前文上下文
    return os.path.join(HISTORY_DIR, f'{username}_consult_history.md')


def format_history_time(value):
    """
    把毫秒时间戳格式化为可读时间

    参数：
        value: 毫秒时间戳（前端 Date.now()），缺省或非法时用当前时间

    返回：
        string - 'YYYY-MM-DD HH:MM:SS'
    """
    try:
        seconds = float(value) / 1000 if value else time.time()
    except (TypeError, ValueError):
        seconds = time.time()
    return datetime.fromtimestamp(seconds).strftime('%Y-%m-%d %H:%M:%S')


# ============================================================================
# 咨询会话历史存储（按天 + 会话级 Markdown）
# ----------------------------------------------------------------------------
# 文件：backend/history/{username}_consult_{YYYY-MM-DD}.md
#   —— 同一用户、同一天的所有会话写在同一个 Markdown 文件里；
#      每个会话用 '## 会话 · HH:MM:SS' 分节，会话内每条消息用
#      '### 用户/AI 批改老师 · YYYY-MM-DD HH:MM:SS' 分节。
# 这样既方便人工直接查阅，也能被后端稳定反解析回消息列表，
# 作为 AI 回答用户问题时的前文上下文。
# ============================================================================

# 会话ID：'{日期}_{时分秒}'，同时决定了会话归属哪一天的文件
SESSION_ID_FORMAT = '%Y-%m-%d_%H%M%S'
# 会话列表默认展示最近 7 天（含今天）
CONSULT_RETENTION_DAYS = 7
# 单次保存的最大消息条数，防止异常超长写入
MAX_SESSION_MESSAGES = 200

# 天级文件名：'13727575721_consult_2026-09-17.md'
DAY_FILE_PATTERN = re.compile(r'^(.+)_consult_(\d{4}-\d{2}-\d{2})\.md$')
# 会话标题行：'## 会话 · 09:31:07'
SESSION_HEAD_PATTERN = re.compile(r'^##[ \t]*会话[ \t]*·[ \t]*([^\n]*)$', re.MULTILINE)
# 会话ID行：'- 会话ID：2026-09-17_093107'
SESSION_ID_PATTERN = re.compile(r'^[ \t]*-[ \t]*会话ID[：:][ \t]*(\S+)[ \t]*$', re.MULTILINE)
# 消息标题行：'### 用户 · 2026-09-17 17:20:48'
MESSAGE_HEAD_PATTERN = re.compile(r'^###[ \t]*(用户|AI 批改老师)[ \t]*·[ \t]*([^\n]*)$', re.MULTILINE)


def session_time_label(session_id):
    """
    从会话ID中取出 'HH:MM:SS' 时间标签（侧边栏展示用）

    参数：
        session_id: string - 形如 '2026-09-17_093107'

    返回：
        string - 'HH:MM:SS'；格式不符时返回空串（由调用方用日期兜底）
    """
    parts = str(session_id or '').split('_')
    raw = parts[1][:6] if len(parts) >= 2 else ''
    if len(raw) == 6 and raw.isdigit():
        return f'{raw[0:2]}:{raw[2:4]}:{raw[4:6]}'
    return ''


def parse_messages(block):
    """
    从一段 Markdown 文本中提取所有消息（不区分会话层级）

    参数：
        block: string - 任意 Markdown 片段

    返回：
        list - [{'role': str, 'content': str, 'time': str}, ...]
    """
    messages = []
    matches = list(MESSAGE_HEAD_PATTERN.finditer(block))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(block)
        content = block[match.end():end].strip()
        if not content:
            continue
        messages.append({
            'role': 'user' if match.group(1) == '用户' else 'assistant',
            'content': content,
            'time': match.group(2).strip(),
        })
    return messages


def parse_day_markdown(text):
    """
    把一天的 Markdown 文档还原为会话列表（与 render_day_markdown 对称）

    参数：
        text: string - 一天的 Markdown 文档内容

    返回：
        list - [{'session_id': str, 'time': str, 'messages': [...]}, ...]（按文件内顺序）
    """
    sessions = []
    heads = list(SESSION_HEAD_PATTERN.finditer(text))
    for index, head in enumerate(heads):
        end = heads[index + 1].start() if index + 1 < len(heads) else len(text)
        block = text[head.end():end]
        id_match = SESSION_ID_PATTERN.search(block)
        # 老文件可能没有显式会话ID行，用标题里的时间兜底，保证不会丢会话
        session_id = id_match.group(1) if id_match else head.group(1).strip()
        sessions.append({
            'session_id': session_id,
            'time': head.group(1).strip(),
            'messages': parse_messages(block),
        })
    return sessions


def render_day_markdown(username, date_str, sessions):
    """
    把某一天的会话列表渲染为 Markdown 文档（与 parse_day_markdown 对称）

    参数：
        username: string - 用户名
        date_str: string - 'YYYY-MM-DD'
        sessions: list - [{'session_id': str, 'time': str, 'messages': [...]}, ...]

    返回：
        string - Markdown 文档内容
    """
    lines = [
        f'# AI 咨询对话记录 · {date_str}',
        '',
        f'- 用户：{username}',
        f'- 日期：{date_str}',
        f'- 会话数：{len(sessions)}',
        '',
        '> 本文件由系统自动维护，保存用户与 AI 批改老师的咨询对话，供后续问答调用前文上下文。',
        '',
        '---',
        '',
    ]
    for session in sessions:
        label = session.get('time') or session_time_label(session.get('session_id'))
        lines.append(f'## 会话 · {label}')
        lines.append('')
        lines.append(f'- 会话ID：{session.get("session_id")}')
        lines.append('')
        for item in session.get('messages') or []:
            content = (item.get('content') or '').strip()
            if not content:
                continue
            role = '用户' if item.get('role') == 'user' else 'AI 批改老师'
            stamp = item.get('time') or format_history_time(item.get('timestamp'))
            lines.append(f'### {role} · {stamp}')
            lines.append('')
            lines.append(content)
            lines.append('')
    return '\n'.join(lines)


def _normalize_messages(history):
    """
    把前端/旧文件传来的消息列表清洗为落盘格式

    参数：
        history: list - [{'role', 'content', 'time'|'timestamp'}]

    返回：
        list - [{'role': 'user'|'assistant', 'content': str, 'time': 'YYYY-MM-DD HH:MM:SS'}]
    """
    messages = []
    for item in (history or [])[:MAX_SESSION_MESSAGES]:
        if not isinstance(item, dict):
            continue
        if item.get('role') not in ('user', 'assistant'):
            continue
        content = (item.get('content') or '').strip()
        if not content:
            continue
        messages.append({
            'role': item['role'],
            'content': content,
            'time': item.get('time') or format_history_time(item.get('timestamp')),
        })
    return messages


def _read_day_sessions(username, date_str):
    """
    读取某一天的会话列表（文件不存在或损坏时返回空列表，不抛异常）

    参数：
        username: string - 用户名
        date_str: string - 'YYYY-MM-DD'

    返回：
        list - 会话列表
    """
    path = history_day_path(username, date_str)
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return parse_day_markdown(f.read())
    except Exception as e:
        logger.error(f"读取咨询记录失败({path}): {e}")
        return []


def _write_day_sessions(username, date_str, sessions):
    """
    把会话列表写回某一天的 Markdown 文件

    参数：
        username: string - 用户名
        date_str: string - 'YYYY-MM-DD'
        sessions: list - 会话列表

    返回：
        boolean - 是否写入成功
    """
    path = history_day_path(username, date_str)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(render_day_markdown(username, date_str, sessions))
        return True
    except Exception as e:
        logger.error(f"保存咨询记录失败({path}): {e}")
        return False


def _session_moment(messages, date_hint, fallback):
    """
    推断旧会话的归属时间：首条消息时间 > 记录自带日期 > 文件修改时间

    参数：
        messages: list - 已清洗的消息列表（time 为 'YYYY-MM-DD HH:MM:SS'）
        date_hint: string - 旧记录自带的日期（'YYYY-MM-DD'），可为空
        fallback: datetime - 兜底时间（通常是旧文件的 mtime）

    返回：
        datetime - 会话归属时间
    """
    candidates = (
        ((messages[0].get('time') if messages else '') or '', '%Y-%m-%d %H:%M:%S'),
        (date_hint or '', '%Y-%m-%d'),
    )
    for text, fmt in candidates:
        if not text:
            continue
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return fallback


def _extract_legacy_sessions(text, is_json):
    """
    解析旧版历史文件的内容，得到若干「会话」

    参数：
        text: string - 旧文件内容
        is_json: boolean - 是否为 JSON 文件

    返回：
        list - [(messages, date_hint), ...]；无所获时返回空列表
    """
    if not is_json:
        # 用户级 Markdown：整份文件视为一个会话
        messages = _normalize_messages(parse_messages(text))
        return [(messages, '')] if messages else []

    try:
        raw = json.loads(text)
    except (TypeError, ValueError) as e:
        logger.error(f"旧版历史文件 JSON 解析失败: {e}")
        return []
    if not isinstance(raw, list):
        return []

    # 结构一：会话列表 —— [{'id', 'date', 'messages': [{'role','content','timestamp'}, ...]}]
    sessions = []
    for chat in raw:
        if not isinstance(chat, dict) or not isinstance(chat.get('messages'), list):
            continue
        messages = _normalize_messages(chat['messages'])
        if messages:
            sessions.append((messages, chat.get('date') or ''))
    if sessions:
        return sessions

    # 结构二：扁平消息列表 —— [{'role','content','timestamp'}, ...]，整份文件视为一个会话
    messages = _normalize_messages(raw)
    return [(messages, '')] if messages else []


def _free_session_id(username, moment):
    """
    由时间生成未被占用的会话ID（同秒冲突时顺延，避免覆盖已有会话）

    参数：
        username: string - 用户名
        moment: datetime - 期望的会话时间

    返回：
        string - 可用的会话ID
    """
    session_id = moment.strftime(SESSION_ID_FORMAT)
    while load_session(username, session_id):
        moment += timedelta(seconds=1)
        session_id = moment.strftime(SESSION_ID_FORMAT)
    return session_id


def _migrate_legacy_history(username):
    """
    把早期「用户级」历史懒迁移为「按天 + 会话级」结构

    兼容两种旧文件：
        - {username}_consult_history.md：用户级 Markdown（无会话分节）
        - {username}_history.json：更早的 JSON（会话列表或扁平消息列表）

    安全约定：只有成功解析出消息并落盘后才删除旧文件；
    解析不出内容时**保留原文件**，避免误删用户数据。

    参数：
        username: string - 用户名

    返回：
        None
    """
    legacy_files = (
        (get_user_history_path(username), False),
        (os.path.join(HISTORY_DIR, f'{username}_history.json'), True),
    )

    for legacy_path, is_json in legacy_files:
        if not os.path.exists(legacy_path):
            continue
        try:
            with open(legacy_path, 'r', encoding='utf-8') as f:
                text = f.read()
        except OSError as e:
            logger.error(f"读取旧版历史文件失败({legacy_path}): {e}")
            continue

        if not text.strip():
            _remove_legacy_file(legacy_path)
            continue

        fallback = datetime.fromtimestamp(os.path.getmtime(legacy_path))
        sessions = _extract_legacy_sessions(text, is_json)
        if not sessions:
            logger.warning(f"[咨询历史] 未能从旧文件解析出消息，已保留原文件: {os.path.basename(legacy_path)}")
            continue

        try:
            for messages, date_hint in sessions:
                moment = _session_moment(messages, date_hint, fallback)
                save_session(username, _free_session_id(username, moment), messages)
        except Exception as e:
            logger.error(f"迁移旧版历史文件失败({legacy_path}): {e}")
            continue

        _remove_legacy_file(legacy_path)
        logger.info(f"[咨询历史] 已迁移旧版历史文件: {os.path.basename(legacy_path)}")


def _remove_legacy_file(path):
    """
    删除迁移完成的旧文件（失败仅记日志，不影响主流程）

    参数：
        path: string - 旧文件路径

    返回：
        None
    """
    try:
        os.remove(path)
    except OSError as e:
        logger.error(f"删除旧版历史文件失败({path}): {e}")


def list_user_sessions(username, days=CONSULT_RETENTION_DAYS):
    """
    列出用户最近 N 天（含今天）的会话摘要，按时间倒序排列

    参数：
        username: string - 用户名
        days: int - 展示天数，默认 7（当天 + 往前 6 天）

    返回：
        list - [{'session_id', 'date', 'time', 'title', 'message_count', 'updated_at'}, ...]
    """
    _migrate_legacy_history(username)

    today = datetime.now().date()
    allowed_dates = {
        (today - timedelta(days=offset)).strftime('%Y-%m-%d')
        for offset in range(max(1, days))
    }

    sessions = []
    try:
        entries = os.listdir(HISTORY_DIR)
    except OSError as e:
        logger.error(f"读取历史目录失败: {e}")
        return []

    for entry in entries:
        matched = DAY_FILE_PATTERN.match(entry)
        # 只取「当前用户、且日期落在展示窗口内」的天级文件，超过 7 天的直接不展示（文件保留）
        if not matched or matched.group(1) != username:
            continue
        date_str = matched.group(2)
        if date_str not in allowed_dates:
            continue
        for session in _read_day_sessions(username, date_str):
            messages = session.get('messages') or []
            if not messages:
                continue
            first_question = next((m['content'] for m in messages if m['role'] == 'user'), '')
            title = (first_question.strip().splitlines() or [''])[0].strip()
            sessions.append({
                'session_id': session['session_id'],
                'date': date_str,
                'time': session.get('time') or session_time_label(session['session_id']),
                'label': session_time_label(session['session_id']),
                'title': title[:24] or '新对话',
                'message_count': len(messages),
                'updated_at': messages[-1].get('time') or '',
            })

    sessions.sort(key=lambda item: (item['date'], item['label']), reverse=True)
    return sessions


def load_session(username, session_id):
    """
    加载指定会话的消息列表

    参数：
        username: string - 用户名
        session_id: string - 会话ID（形如 '2026-09-17_093107'）

    返回：
        list - [{'role', 'content', 'time'}, ...]；会话不存在时返回空列表
    """
    date_str = str(session_id or '').split('_')[0]
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return []
    for session in _read_day_sessions(username, date_str):
        if session['session_id'] == session_id:
            return session['messages']
    return []


def latest_session_messages(username):
    """
    取用户最近一个会话的消息列表（供 AI 续接前文使用）

    参数：
        username: string - 用户名

    返回：
        list - 消息列表；无历史时返回空列表
    """
    sessions = list_user_sessions(username)
    if not sessions:
        return []
    return load_session(username, sessions[0]['session_id'])


def save_session(username, session_id, history):
    """
    保存一个会话（同一天的所有会话共用同一个 Markdown 文件）

    参数：
        username: string - 用户名
        session_id: string - 会话ID；为空时按当前时间新建会话
        history: list - 该会话完整消息列表

    返回：
        dict|None - {'session_id': str, 'date': 'YYYY-MM-DD'}；保存失败返回 None
    """
    now = datetime.now()
    session_id = (session_id or '').strip()
    date_str = str(session_id).split('_')[0] if session_id else ''
    # 会话ID非法时退回当天新会话，避免把数据写进错误的天级文件
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        session_id = now.strftime(SESSION_ID_FORMAT)
        date_str = session_id.split('_')[0]

    messages = _normalize_messages(history)
    sessions = _read_day_sessions(username, date_str)
    label = session_time_label(session_id) or now.strftime('%H:%M:%S')

    for session in sessions:
        if session['session_id'] == session_id:
            session['messages'] = messages
            session['time'] = label
            break
    else:
        sessions.append({'session_id': session_id, 'time': label, 'messages': messages})

    if not _write_day_sessions(username, date_str, sessions):
        return None
    return {'session_id': session_id, 'date': date_str}


def delete_session(username, session_id):
    """
    删除指定会话（当天没有其它会话时一并删除天级文件）

    参数：
        username: string - 用户名
        session_id: string - 会话ID

    返回：
        boolean - 是否删除成功
    """
    date_str = str(session_id or '').split('_')[0]
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return False

    sessions = _read_day_sessions(username, date_str)
    kept = [session for session in sessions if session['session_id'] != session_id]
    if len(kept) == len(sessions):
        return False

    if not kept:
        try:
            os.remove(history_day_path(username, date_str))
            return True
        except OSError as e:
            logger.error(f"删除咨询记录文件失败: {e}")
            return False
    return _write_day_sessions(username, date_str, kept)


def delete_all_sessions(username):
    """
    删除该用户的全部咨询记录文件（仅在用户显式请求「清空」时调用）

    参数：
        username: string - 用户名

    返回：
        int - 实际删除的文件数
    """
    removed = 0
    try:
        entries = os.listdir(HISTORY_DIR)
    except OSError as e:
        logger.error(f"读取历史目录失败: {e}")
        return 0
    for entry in entries:
        matched = DAY_FILE_PATTERN.match(entry)
        if not matched or matched.group(1) != username:
            continue
        try:
            os.remove(os.path.join(HISTORY_DIR, entry))
            removed += 1
        except OSError as e:
            logger.error(f"删除咨询记录文件失败({entry}): {e}")
    return removed


@app.route('/get_history/list', methods=['GET'])
@token_required
def get_history_list(current_user):
    """
    会话列表接口（仅返回最近 N 天、含今天的会话）

    查询参数（可选）：days - 展示天数，默认 7
    返回: {"success": true, "days": 7, "sessions": [...]}
    """
    try:
        days = int(request.args.get('days') or CONSULT_RETENTION_DAYS)
    except (TypeError, ValueError):
        days = CONSULT_RETENTION_DAYS
    days = max(1, min(days, 30))

    return jsonify({
        'success': True,
        'days': days,
        'sessions': list_user_sessions(current_user, days=days)
    })


@app.route('/save_history', methods=['POST'])
@token_required
def save_history(current_user):
    """
    保存历史记录接口
    将一次会话的全部消息写入「该用户当天」的 Markdown 文件

    请求体: {"session_id": "2026-09-17_093107"（可选，缺省则新建会话）, "history": [...]}
    返回: {"success": true, "session_id": "...", "date": "YYYY-MM-DD"}
    """
    data = get_json_body()
    if data is None:
        return json_error('请求数据格式错误', '请求体必须是JSON对象')

    history = data.get('history')
    if history is not None and not isinstance(history, list):
        return json_error('请求数据格式错误', 'history 必须是数组')

    saved = save_session(current_user, data.get('session_id'), history or [])
    if not saved:
        return jsonify({'success': False, 'message': '保存失败'}), 500

    return jsonify({
        'success': True,
        'message': '保存成功',
        'session_id': saved['session_id'],
        'date': saved['date']
    })


@app.route('/get_history', methods=['GET'])
@token_required
def get_history(current_user):
    """
    获取历史记录接口

    查询参数（可选）：session_id - 指定会话；缺省时返回最近一个会话
    返回: {"success": true, "session_id": "...", "history": [...]}
    """
    session_id = (request.args.get('session_id') or '').strip()
    if not session_id:
        sessions = list_user_sessions(current_user)
        session_id = sessions[0]['session_id'] if sessions else ''

    return jsonify({
        'success': True,
        'session_id': session_id,
        'history': load_session(current_user, session_id) if session_id else []
    })


@app.route('/delete_history', methods=['POST'])
@token_required
def delete_history(current_user):
    """
    删除历史记录接口

    请求体: {"session_id": "xxx"} 删除单个会话；{"all": true} 删除该用户全部会话
    返回: {"success": true, "message": "删除成功"}
    """
    data = get_json_body()
    if data is None:
        return json_error('请求数据格式错误', '请求体必须是JSON对象')

    if data.get('all'):
        delete_all_sessions(current_user)
        return jsonify({'success': True, 'message': '删除成功'})

    session_id = (data.get('session_id') or '').strip()
    if not session_id:
        return json_error('参数缺失', '请提供 session_id 或 all=true')

    success = delete_session(current_user, session_id)
    return jsonify({
        'success': success,
        'message': '删除成功' if success else '删除失败'
    })


@app.route('/ocr', methods=['POST'])
def ocr():
    """
    OCR图片文字识别接口
    接收图片文件，提取其中的文字内容
    
    请求: multipart/form-data, field: image
    返回: {"success": true, "data": {"text": "识别的文本"}}
    """
    try:
        if 'image' not in request.files:
            return jsonify({'success': False, 'message': '请上传图片文件'})
        
        file = request.files['image']
        
        if file.filename == '':
            return jsonify({'success': False, 'message': '请选择要上传的图片'})
        
        # 验证文件类型
        if not file.content_type.startswith('image/'):
            return jsonify({'success': False, 'message': '仅支持图片文件'})
        
        # 模拟OCR识别结果
        simulated_text = """
这也是其一，也不免会被逗笑，但一笑过后，总觉得有点失态。人们有自己的可爱之处，有可爱之处，我们要去模仿人类讨人类的欢喜，这也有些心酸。正如鲁迅所言："造物者创造了一切，都是平等的，人们的这些小聪明，倒看起来有些多事了。" 有些事真的是这样，一些很好的东西被复制多次后，反而叫人反感。

09年春晚凭借《不差钱》红遍全国一夜成名的小沈阳，多少人欣赏他，可春晚过后络绎而来的却是无数翻版的娘娘腔在各个卫视上演，让人看得发腻；当杰克逊逝世后，多少模仿杰克逊的人齐聚电视和网络来比拼谁最像一代歌王，这些也不免有些令人乏味；甚至有不少人把某个歌手的说话方式当做习惯来改变自己，结果徒留的冷笑一声。

每个人的身上有自己的闪光点，何必要刻意模仿别人？再说，外表的浮华可以复制，气质你学的来么？ 从第一部穿越剧《寻秦记》开始，各种各样的穿越戏充斥着人们的视线，穿越自己也风靡一时，本来一个很好的创意被涂抹得再寻常不过了，甚至有下个剧情看都明白的感觉，看多了穿越，上个厕所都感觉马桶像穿越洞……

有大公司招聘，很多人慕名而来，他们看到地上有香蕉皮，旁边还坐着行乞的老人，都以为是公司的测试题，便将香蕉皮捡起，并捐钱给老人，有的甚至买来吃的给老人，结果他们未被录取。很简单，那确实是一道测试题，但他们未被录取的原因是：太社会。

如今的社会，需要学习，但更需要创新，需要寻常，但不是千篇一律，单一的复制会使人乏味，东施效颦只会惹来嘲笑，其实简简单单做真实的自己就好。

我写我的文字，我抒自己的情怀，我怜世人的悲哀。
        """.strip()
        
        # 文本净化处理
        cleaned_text = clean_ocr_text(simulated_text)
        
        return jsonify({
            'success': True,
            'data': {
                'text': cleaned_text,
                'raw_text': simulated_text
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'OCR识别失败: {str(e)}'})


def clean_ocr_text(text):
    """
    净化OCR识别的文本
    移除多余的、不相关的文字信息，保留纯净的作文内容
    
    参数：
        text: string - OCR识别的原始文本
        
    返回：
        string - 净化后的作文内容
    """
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line = line.strip()
        
        if len(line) < 2:
            continue
        
        cleaned_line = ''
        for char in line:
            if '\u4e00' <= char <= '\u9fff' or char in '，。！？、；：""''（）《》【】—…·':
                cleaned_line += char
            elif char in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ ':
                cleaned_line += char
        
        if cleaned_line:
            cleaned_lines.append(cleaned_line)
    
    return '\n'.join(cleaned_lines)


@app.route('/health', methods=['GET'])
def health():
    """
    健康检查接口
    用于检测服务是否正常运行
    
    返回: {"status": "ok", "components": {...}}
    """
    # agent.is_ready(auto_init=True)：健康检查允许触发一次延迟初始化。
    # ReactAgent 在正常路径下是懒加载的（首次咨询才构建底层执行器）。若这里只读状态，
    # 「服务起来了但还没人咨询过」就会一直返回 503 —— 与「真的坏了」表现完全一致，
    # 无法区分，且会让 Docker healthcheck 永久失败。改为探测时顺带初始化，
    # 健康检查才真的在回答「AI 依赖现在能不能用」。
    agent_ready = agent.is_ready(auto_init=True)

    status = {
        'status': 'healthy',
        'components': {
            'api': 'running',
            'model': 'available' if chat_model else 'unavailable',
            'agent': 'available' if agent_ready else 'unavailable',
            'vector_store': 'available'
        },
        'timestamp': datetime.now().isoformat()
    }
    
    if not chat_model or not agent_ready:
        status['status'] = 'unhealthy'
        status['error'] = 'AI服务未就绪'
        return jsonify(status), 503
    
    return jsonify(status)


@app.route('/config/check', methods=['GET'])
def check_config():
    """
    配置检查接口
    帮助管理员诊断配置问题
    
    返回: {"success": true, "checks": [...]}
    """
    result = {
        'success': True,
        'checks': []
    }
    
    # 检查API密钥
    try:
        api_key = get_dashscope_api_key()
        is_valid = SecurityConfig.validate_api_key_format(api_key) if api_key else False
        result['checks'].append({
            'name': 'API密钥配置',
            'status': 'passed' if api_key and is_valid else 'failed',
            'detail': f"密钥已配置（长度: {len(api_key) if api_key else 0}字符）",
            'is_valid': is_valid
        })
    except EnvironmentError as e:
        result['checks'].append({
            'name': 'API密钥配置',
            'status': 'failed',
            'detail': str(e)
        })
        result['success'] = False
    
    # 检查模型
    global chat_model
    if chat_model:
        result['checks'].append({
            'name': 'AI模型',
            'status': 'passed',
            'detail': f"模型类型: {type(chat_model).__name__}"
        })
    else:
        result['checks'].append({
            'name': 'AI模型',
            'status': 'failed',
            'detail': '模型未初始化，请检查API密钥'
        })
        result['success'] = False
    
    # 检查Agent
    global agent
    if agent.is_ready():
        result['checks'].append({
            'name': 'ReactAgent',
            'status': 'passed',
            'detail': 'Agent已初始化并就绪'
        })
    else:
        result['checks'].append({
            'name': 'ReactAgent',
            'status': 'failed',
            'detail': 'Agent未初始化，将在首次使用时尝试初始化'
        })
        result['success'] = False

    # 检查数据库（注册/登录依赖 PostgreSQL）
    # 这段直接在容器内建一次真实连接，因此测的是「应用实际走的那条路」，
    # 而不是从宿主机 ping —— 两者结果经常不一致（DNS / 密码 / 出网策略都可能不同）。
    try:
        cfg = db_config.get_db_config()
        if not cfg.get('password'):
            result['checks'].append({
                'name': '数据库连接',
                'status': 'failed',
                'detail': '密码为空：容器未读到 .env（应在仓库根目录，不是 backend/ 下）',
            })
            result['success'] = False
        else:
            import psycopg2
            conn = psycopg2.connect(
                host=cfg['host'], port=cfg['port'], dbname=cfg['dbname'],
                user=cfg['user'], password=cfg['password'], connect_timeout=6,
            )
            conn.close()
            result['checks'].append({
                'name': '数据库连接',
                'status': 'passed',
                'detail': f"已连通 {cfg['host']}:{cfg['port']}/{cfg['dbname']}（用户 {cfg['user']}）",
            })
    except Exception as e:
        # 只回显异常自身的文本；psycopg2 的错误信息不会包含密码明文。
        result['checks'].append({
            'name': '数据库连接',
            'status': 'failed',
            'detail': f'{type(e).__name__}: {e}',
        })
        result['success'] = False

    return jsonify(result)


# 延迟初始化ReactAgent（避免在模块加载时就尝试初始化）
agent = ReactAgent()


if __name__ == '__main__':
    # 生产模式：debug 默认关闭；本地调试可设 FLASK_DEBUG=1 开启。
    # 端口优先取环境变量 PORT（Render 等平台注入），本地默认 8501。
    debug = os.environ.get('FLASK_DEBUG', '') == '1'
    port = int(os.environ.get('PORT', '8501'))
    if validate_system_config():
        app.run(host='0.0.0.0', port=port, debug=debug)
    else:
        print("\n❌ 配置验证失败，服务启动终止")
        exit(1)