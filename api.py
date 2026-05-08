from flask import Flask, request, jsonify
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

agent = ReactAgent()

# 用户数据（模拟数据库）
USERS = {
    'admin': hashlib.sha256('123456'.encode()).hexdigest()
}

# 历史记录存储目录
HISTORY_DIR = os.path.join(os.path.dirname(__file__), 'history')

# 日志目录
LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)


def retry_on_failure(max_retries=3, delay=1.0, backoff=2.0):
    """
    重试装饰器：在函数失败时自动重试
    适用于网络请求、外部API调用等可能临时失败的场景
    
    @param {int} max_retries - 最大重试次数
    @param {float} delay - 初始重试延迟（秒）
    @param {float} backoff - 延迟倍增因子
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            current_delay = delay
            
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    retries += 1
                    error_msg = str(e)
                    print(f"[重试机制] 第 {retries}/{max_retries} 次尝试失败: {error_msg}")
                    
                    if retries < max_retries:
                        # 添加随机抖动，避免重试风暴
                        jitter = random.uniform(0, current_delay * 0.1)
                        sleep_time = current_delay + jitter
                        print(f"[重试机制] 等待 {sleep_time:.2f} 秒后重试...")
                        time.sleep(sleep_time)
                        current_delay *= backoff
                    else:
                        print(f"[重试机制] 已达到最大重试次数 {max_retries}，放弃重试")
                        raise
        
            return func(*args, **kwargs)
        return wrapper
    return decorator


def log_api_request(func):
    """
    API请求日志装饰器
    记录请求的详细信息，便于追踪和调试
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
        
        print(f"[API请求] {log_entry}")
        
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
            
            print(f"[API响应] {log_entry}")
            
            return response
            
        except Exception as e:
            # 记录异常
            log_entry['status'] = 'error'
            log_entry['error'] = str(e)
            log_entry['duration_ms'] = int((time.time() - start_time) * 1000)
            log_entry['traceback'] = traceback.format_exc()
            
            print(f"[API错误] {log_entry}")
            raise
    
    return wrapper
os.makedirs(HISTORY_DIR, exist_ok=True)


def token_required(f):
    """
    JWT认证装饰器
    验证请求头中的Authorization令牌
    
    @param {function} f - 被装饰的函数
    @returns {function} - 包装后的函数
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
            if current_user not in USERS:
                raise Exception('用户不存在')
        except Exception as e:
            return jsonify({'success': False, 'error': '令牌无效'}), 401
        
        return f(current_user, *args, **kwargs)
    
    return decorated


def load_essay_criteria():
    """
    加载各类型作文的评分标准
    从data目录读取议论文、记叙文、说明文的评分标准文件
    
    @returns {dict} - 各类型作文评分标准字典
    """
    criteria = {
        '议论文': '',
        '记叙文': '',
        '说明文': ''
    }

    data_dir = os.path.join(os.path.dirname(__file__), 'data')

    for essay_type in criteria.keys():
        file_path = os.path.join(data_dir, f'{essay_type}（初中）评分标准.txt')
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    criteria[essay_type] = f.read()
        except Exception as e:
            print(f"加载{essay_type}评分标准失败: {e}")

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
    
    @param {string} text - 作文文本内容
    @returns {string} - 作文类型（议论文/记叙文/说明文）
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
    
    @param {string} text - 用户输入的文本
    @returns {boolean} - 是否为作文提交
    """
    if not text or not isinstance(text, str):
        print("[作文检测] 输入为空或非字符串类型")
        return False
    
    trimmed_text = text.strip()
    text_length = len(trimmed_text)
    
    # 1. 最小长度检查：至少100字才可能是作文
    if text_length < 100:
        print(f"[作文检测] 文本过短({text_length}字)，不是作文提交")
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
        print(f"[作文检测] 长文本({text_length}字)且包含作文关键词，判定为作文提交")
        return True
    
    # 3. 超长文本（超过800字）直接判定为作文，无需关键词
    if text_length > 800:
        print(f"[作文检测] 超长文本({text_length}字)，直接判定为作文提交")
        return True
    
    # 4. 咨询类问题排除（仅适用于短文本）
    if has_consult and not has_essay and text_length < 300:
        print(f"[作文检测] 短文本({text_length}字)且包含咨询关键词，不是作文提交")
        return False

    # 5. 如果包含作文关键词且文本较长，判定为作文提交
    if has_essay and is_long:
        print(f"[作文检测] 包含作文关键词且文本较长({text_length}字)，判定为作文提交")
        return True

    # 6. 纯长文本（超过500字）也判定为作文提交
    if text_length > 500:
        print(f"[作文检测] 文本超过500字({text_length}字)，判定为作文提交")
        return True

    # 5. 中等长度文本（200-500字）需要包含作文关键词才判定为作文
    if is_long and has_essay:
        print("[作文检测] 中等长度文本且包含作文关键词，判定为作文提交")
        return True

    print("[作文检测] 未满足作文提交条件")
    return False


def extract_json_from_response(response_text):
    """
    从AI响应文本中提取JSON格式的批改结果
    支持代码块格式和纯JSON格式
    
    @param {string} response_text - AI响应的原始文本
    @returns {dict|None} - 解析后的JSON数据，解析失败返回None
    """
    json_pattern = r'```json\s*(\{.*?\})\s*```'
    match = re.search(json_pattern, response_text, re.DOTALL)

    if match:
        json_str = match.group(1)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"JSON解析失败: {e}")

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
    
    @param {dict} json_data - JSON格式的批改数据
    @param {string} essay_type - 作文类型
    @returns {dict|None} - 解析后的结构化数据
    """
    if not isinstance(json_data, dict):
        print(f"JSON数据类型错误，期望dict，得到 {type(json_data)}")
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
        print(f"解析JSON数据时发生错误: {e}")
        return None

    return result


def parse_text_feedback(response_text, essay_type):
    """
    解析纯文本格式的作文批改反馈
    当JSON解析失败时，使用正则表达式从文本中提取评分信息
    如果无法提取到评分，会根据评语内容自动计算一个合理的分数
    
    @param {string} response_text - AI响应的原始文本
    @param {string} essay_type - 作文类型
    @returns {dict} - 解析后的结构化数据
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
    # 将DIMENSION_MAP转换为需要的(key, name)元组格式
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
        dims = DIMENSION_MAP.get(essay_type, DIMENSION_MAP['记叙文'])
        max_scores = DIMENSION_MAX_SCORES.get(essay_type, DIMENSION_MAX_SCORES['记叙文'])
        
        # 根据总分分配各维度分数
        if result['score'] is not None:
            # 按比例分配到各维度
            total_max = sum(max_scores.values())
            remaining = result['score']
            
            for dim_key, dim_name in dims:
                max_score = max_scores.get(dim_name, 10)
                # 按比例分配，最后一项取剩余值
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
    
    @param {string} comment - 总体评价文本
    @param {string} essay_type - 作文类型
    @returns {int} - 计算出的分数（0-50）
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
    
    @param {string} response_text - AI响应的原始文本
    @param {string} essay_type - 作文类型
    @returns {dict} - 解析后的结构化数据
    """
    json_data = extract_json_from_response(response_text)

    if json_data:
        parsed = parse_json_feedback(json_data, essay_type)
        if parsed and parsed.get('score') is not None:
            parsed['raw_response'] = response_text
            # 校验总分与各项评分之和是否一致
            parsed = validate_and_fix_score(parsed)
            return parsed
        else:
            print("JSON解析成功但数据不完整，尝试文本解析")

    parsed = parse_text_feedback(response_text, essay_type)
    parsed['raw_response'] = response_text
    # 校验总分与各项评分之和是否一致
    parsed = validate_and_fix_score(parsed)
    return parsed


def validate_and_fix_score(parsed_result):
    """
    校验并修正总分与各项评分之和的一致性
    
    使用ScoreCalculator模块实现总分自动汇总，确保各项评分与总分的逻辑一致性。
    如果总分与各项评分之和不一致，会自动调整总分使其与各项评分之和一致。
    如果维度评分超出范围，会自动进行归一化处理。
    这是为了解决AI可能返回不准确的总分或超出范围分数的问题。
    
    @param {dict} parsed_result - 解析后的作文批改结果
    @returns {dict} - 校验并修正后的结果
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
            print(f"[维度分数修正] 体裁: {essay_type}, 维度: {dim_name}, 原始分数: {score}, 修正后: {normalized_scores[dim_name]}")
    
    # 使用计算器修正总分
    fixed_score, was_fixed = calculator.fix_total_score(normalized_scores, original_score)
    
    # 更新维度评分（使用归一化后的值）
    for dim in parsed_result['dimensions']:
        dim_name = dim['name']
        if dim_name in normalized_scores:
            dim['score'] = normalized_scores[dim_name]
            # 更新维度满分配置
            dim['max_score'] = calculator.max_scores.get(dim_name, dim.get('max_score', 10))
    
    # 更新结果
    parsed_result['score'] = fixed_score
    parsed_result['calculated_total'] = calculator.calculate_total(normalized_scores)
    parsed_result['total_max_score'] = calculator.total_max_score
    
    # 标记是否有修正
    if was_fixed or has_dimension_fixes:
        parsed_result['score_fixed'] = True
        if was_fixed:
            print(f"[总分校验] 体裁: {essay_type}, 检测到总分({original_score})与各项评分之和({parsed_result['calculated_total']})不一致，已自动修正为: {fixed_score}")
    else:
        print(f"[总分校验] 体裁: {essay_type}, 总分校验通过: {fixed_score}")
    
    # 添加校验信息
    parsed_result['validation'] = {
        'is_consistent': calculator.validate_total_consistency(normalized_scores, fixed_score),
        'is_complete': calculator.validate_dimension_completeness(normalized_scores)
    }
    
    return parsed_result


def generate_essay_review(essay_content, essay_type):
    """
    生成作文批改结果
    使用RAG服务调用AI生成批改结果，支持自动检测作文类型和加载评分标准
    
    @param {string} essay_content - 作文内容
    @param {string} essay_type - 作文类型（议论文/记叙文/说明文）
    @returns {string} - AI生成的批改结果
    """
    try:
        # 调用RAG服务生成批改结果
        # RAG服务会自动检测作文类型、加载评分标准、检索参考资料
        response = rag_summarize.invoke(essay_content)
        return response if response else "抱歉，生成作文批改失败，请稍后重试。"
    except Exception as e:
        print(f"生成作文批改失败: {str(e)}")
        print(traceback.format_exc())
        raise Exception(f"生成作文批改失败: {str(e)}")


def chat_with_agent(message):
    """
    与AI助手进行普通对话
    用于非作文批改的咨询类问题
    
    @param {string} message - 用户输入的消息
    @returns {string} - AI的回复
    """
    try:
        response = ''
        for chunk in agent.execute_stream(message):
            if chunk:
                response += chunk
        return response if response else "抱歉，生成回复失败，请稍后重试。"
    except ValueError as e:
        # 捕获配置错误（如缺少API密钥）
        print(f"配置错误: {str(e)}")
        raise Exception(f"配置错误: {str(e)}")
    except Exception as e:
        print(f"对话失败: {str(e)}")
        print(traceback.format_exc())
        # 隐藏内部错误，向用户返回友好提示
        raise Exception("AI服务暂时不可用，请稍后重试")


@retry_on_failure(max_retries=3, delay=2.0, backoff=2.0)
def generate_essay_review_with_retry(essay_content, essay_type):
    """
    带重试机制的作文批改生成函数
    当AI服务临时不可用时自动重试
    
    @param {string} essay_content - 作文内容
    @param {string} essay_type - 作文类型
    @returns {string} - AI生成的批改结果
    """
    print(f"[重试机制] 调用作文批改服务，体裁: {essay_type}")
    return generate_essay_review(essay_content, essay_type)


@retry_on_failure(max_retries=3, delay=2.0, backoff=2.0)
def chat_with_agent_with_retry(message):
    """
    带重试机制的对话函数
    当AI服务临时不可用时自动重试
    
    @param {string} message - 用户消息
    @returns {string} - AI回复
    """
    print("[重试机制] 调用对话服务")
    return chat_with_agent(message)


def log_user_input(username, message, essay_type=None, is_essay=False):
    """
    记录用户输入日志
    确保完整记录用户提交的作文内容，便于后续分析和调试
    
    @param {string} username - 用户名
    @param {string} message - 用户输入内容
    @param {string} essay_type - 作文类型（可选）
    @param {boolean} is_essay - 是否为作文提交
    """
    import time
    log_entry = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
        'username': username,
        'message': message[:500] + '...' if len(message) > 500 else message,
        'message_length': len(message),
        'essay_type': essay_type,
        'is_essay': is_essay,
        'source': request.remote_addr if request else 'unknown'
    }
    
    # 打印日志到控制台
    print(f"[用户输入日志] {log_entry['timestamp']} | 用户: {log_entry['username']} | 类型: {'作文-' + essay_type if essay_type else ('作文(自动识别)' if is_essay else '普通消息')} | 长度: {log_entry['message_length']}")
    
    # 写入日志文件
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"user_input_{time.strftime('%Y%m%d')}.log")
    
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    except Exception as e:
        print(f"写入用户日志失败: {str(e)}")


@app.route('/chat', methods=['POST'])
@log_api_request
def chat():
    """
    聊天接口
    接收用户消息，判断是否为作文提交，返回AI回复或作文批改结果
    
    请求体: {"message": "用户输入的文本", "essay_type": "作文类型（可选）"}
    返回: {"success": true, "data": {...}, "raw_response": "..."}
    """
    # 数据验证
    if not request.is_json:
        return jsonify({
            'success': False,
            'error': '请求格式错误',
            'message': '请使用JSON格式提交请求'
        }), 400
    
    data = request.json
    
    # 验证请求数据结构
    if not isinstance(data, dict):
        return jsonify({
            'success': False,
            'error': '请求数据格式错误',
            'message': '请求体必须是JSON对象'
        }), 400
    
    message = data.get('message', '')
    # 优先使用前端传递的体裁参数，其次使用自动识别
    user_selected_essay_type = data.get('essay_type', '')
    
    # 获取当前用户（从请求头或会话中）
    current_user = request.headers.get('X-Username', 'anonymous')

    # 验证消息内容
    if not message or not isinstance(message, str):
        return jsonify({
            'success': False,
            'error': '请输入内容',
            'message': '请输入作文内容或咨询问题'
        }), 400
    
    # 验证消息长度
    message_length = len(message.strip())
    if message_length < MIN_CONTENT_LENGTH:
        return jsonify({
            'success': False,
            'error': '内容过短',
            'message': f'输入内容至少需要{MIN_CONTENT_LENGTH}个字符'
        }), 400
    
    if message_length > MAX_CONTENT_LENGTH:
        return jsonify({
            'success': False,
            'error': '内容过长',
            'message': f'输入内容不能超过{MAX_CONTENT_LENGTH}个字符'
        }), 400
    
    # 验证作文类型（如果提供）
    if user_selected_essay_type and user_selected_essay_type not in ['议论文', '记叙文', '说明文']:
        return jsonify({
            'success': False,
            'error': '无效的作文类型',
            'message': '作文类型只能是：议论文、记叙文或说明文'
        }), 400

    try:
        # 判断是否为作文提交
        is_essay = is_essay_submission(message)
        
        # 记录用户输入日志
        log_user_input(current_user, message, user_selected_essay_type, is_essay)

        if is_essay:
            # 优先使用用户选择的体裁，如果未选择则自动识别
            if user_selected_essay_type and user_selected_essay_type in ['议论文', '记叙文', '说明文']:
                essay_type = user_selected_essay_type
                print(f"使用用户选择的体裁: {essay_type}")
            else:
                essay_type = detect_essay_type(message)
                print(f"自动识别体裁: {essay_type}")
            # 调用RAG服务生成作文批改结果（带重试机制）
            response = generate_essay_review_with_retry(message, essay_type)
        else:
            # 普通对话，调用ReactAgent（带重试机制）
            response = chat_with_agent_with_retry(message)

        # 解析AI返回的批改结果
        parsed = parse_essay_feedback(response, essay_type if is_essay else '记叙文')

        if is_essay:
            # 确保essay_type被正确设置（后端字段名）
            if not parsed.get('essay_type'):
                parsed['essay_type'] = essay_type
            # 如果score为None，说明AI没有按JSON格式返回，使用评语计算
            if parsed['score'] is None:
                parsed['essay_type'] = essay_type
            
            # 添加essayType字段（前端期望的字段名），确保前后端字段统一
            # 同时保留essay_type以保持向后兼容性
            parsed['essayType'] = parsed.get('essay_type', essay_type)

        return jsonify({
            'success': True,
            'data': parsed,
            'raw_response': response
        })
    except Exception as e:
        print(f"处理请求时发生错误: {str(e)}")
        print(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e),
            'message': f'处理请求时出现错误: {str(e)}'
        }), 500


@app.route('/login', methods=['POST'])
def login():
    """
    用户登录接口
    验证用户名密码，返回JWT令牌
    
    请求体: {"username": "admin", "password": "123456"}
    返回: {"success": true, "token": "xxx", "username": "admin"}
    """
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'success': False, 'error': '请输入用户名和密码'}), 400
    
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    
    if username in USERS and USERS[username] == hashed_password:
        token = jwt.encode({
            'username': username,
            'exp': datetime.utcnow() + timedelta(hours=24)
        }, app.config['SECRET_KEY'])
        
        return jsonify({
            'success': True,
            'token': token,
            'username': username
        })
    
    return jsonify({'success': False, 'error': '用户名或密码错误'}), 401


def get_user_history_path(username):
    """
    获取用户历史记录文件路径
    
    @param {string} username - 用户名
    @returns {string} - 历史记录文件路径
    """
    return os.path.join(HISTORY_DIR, f'{username}_history.json')


def load_user_history(username):
    """
    加载用户历史记录
    
    @param {string} username - 用户名
    @returns {list} - 用户历史记录列表
    """
    history_path = get_user_history_path(username)
    if os.path.exists(history_path):
        try:
            with open(history_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载用户历史记录失败: {e}")
    return []


def save_user_history(username, history):
    """
    保存用户历史记录
    
    @param {string} username - 用户名
    @param {list} history - 历史记录列表
    @returns {boolean} - 保存是否成功
    """
    history_path = get_user_history_path(username)
    try:
        with open(history_path, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存用户历史记录失败: {e}")
        return False


@app.route('/save_history', methods=['POST'])
@token_required
def save_history(current_user):
    """
    保存历史记录接口
    将用户的聊天历史保存到服务器
    
    请求体: {"history": [...]}
    返回: {"success": true, "message": "保存成功"}
    """
    data = request.json
    history = data.get('history', [])
    
    # 限制最多100条记录
    history = history[:100]
    
    success = save_user_history(current_user, history)
    
    return jsonify({
        'success': success,
        'message': '保存成功' if success else '保存失败'
    })


@app.route('/get_history', methods=['GET'])
@token_required
def get_history(current_user):
    """
    获取历史记录接口
    返回用户的聊天历史
    
    返回: {"success": true, "history": [...]}
    """
    history = load_user_history(current_user)
    return jsonify({
        'success': True,
        'history': history
    })


@app.route('/delete_history', methods=['POST'])
@token_required
def delete_history(current_user):
    """
    删除历史记录接口
    删除指定聊天记录或全部记录
    
    请求体: {"chat_id": "xxx"} 或 {"all": true}
    返回: {"success": true, "message": "删除成功"}
    """
    data = request.json
    chat_id = data.get('chat_id')
    delete_all = data.get('all', False)
    
    history = load_user_history(current_user)
    
    if delete_all:
        history = []
    elif chat_id:
        history = [chat for chat in history if chat.get('id') != chat_id]
    
    success = save_user_history(current_user, history)
    
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
        
        # 模拟OCR识别结果（实际应用中应调用阿里云OCR API）
        # 这里使用一段示例作文作为模拟识别结果
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
    
    @param {string} text - OCR识别的原始文本
    @returns {string} - 净化后的作文内容
    """
    # 移除多余的空白字符和换行
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        # 移除首尾空白
        line = line.strip()
        
        # 跳过空行和过短的行（可能是噪音）
        if len(line) < 2:
            continue
        
        # 移除特殊字符和数字（保留中文、英文、标点）
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
    
    返回: {"status": "ok"}
    """
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8501, debug=True)
