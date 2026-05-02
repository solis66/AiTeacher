from flask import Flask, request, jsonify
from flask_cors import CORS
from agent.tools.react_agent import ReactAgent
import traceback
import re
import os
import json
import hashlib
import jwt
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
os.makedirs(HISTORY_DIR, exist_ok=True)

# JWT装饰器
def token_required(f):
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

## 议论文评分标准（满分60分）
{criteria}

## 批改要求

1. 你必须仔细分析上述作文的具体内容、结构、语言和论证方法
2. 根据评分标准对作文的各个方面进行独立评分
3. 总体评价必须针对这篇作文的具体内容，不能使用通用套话
4. 改进建议必须基于这篇作文的实际问题提出，具体且有针对性

请严格按照以下JSON格式输出批改结果（注意：所有评分必须是整数，总分不超过60分）：

```json
{{
  "总分": XX,
  "各项评分": {{
    "立意与中心": XX,
    "论点与论证": XX,
    "结构与层次": XX,
    "语言表达": XX,
    "例证与材料运用": XX,
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

    '记叙文': """你是一个专业的初中语文作文批改教师。请仔细阅读以下记叙文，并根据评分标准进行批改。

## 待批改的记叙文
{essay_content}

## 记叙文评分标准（满分60分）
{criteria}

## 批改要求

1. 你必须仔细分析上述作文的具体内容、人物、情节、语言和表达方式
2. 根据评分标准对作文的各个方面进行独立评分
3. 总体评价必须针对这篇作文的具体内容、人物刻画、情节安排等，不能使用通用套话
4. 改进建议必须基于这篇作文的实际问题提出，要具体指出哪里需要改进

请严格按照以下JSON格式输出批改结果（注意：所有评分必须是整数，总分不超过60分）：

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

## 说明文评分标准（满分60分）
{criteria}

## 批改要求

1. 你必须仔细分析上述作文的具体说明对象、说明方法、结构安排和语言特点
2. 根据评分标准对作文的各个方面进行独立评分
3. 总体评价必须针对这篇作文的具体内容，不能使用通用套话
4. 改进建议必须基于这篇作文的实际问题提出，要具体指出说明方法、结构或语言上的不足

请严格按照以下JSON格式输出批改结果（注意：所有评分必须是整数，总分不超过60分）：

```json
{{
  "总分": XX,
  "各项评分": {{
    "立意与中心": XX,
    "内容与材料": XX,
    "结构与层次": XX,
    "语言表达": XX,
    "方法与技巧": 5,
    "书写与规范": 2
  }},
  "总体评价": "这篇说明文抓住了事物的特征进行介绍，条理较为清晰，能够运用适当的说明方法。但在内容的深度、广度以及说明方法的灵活运用上还有提升空间。",
  "改进建议": [
    "建议1：增加具体数据和实例，使说明更加准确有据",
    "建议2：运用多种说明方法，如作比较、列数字、举例子等",
    "建议3：优化文章结构，按照合理的逻辑顺序组织材料"
  ]
}}
```

注意：所有评分必须是整数，总分不要超过60分。"""
}

def detect_essay_type(text):
    if '议论文' in text or '论点' in text or '论证' in text or '论据' in text:
        return '议论文'
    if '记叙文' in text or '记叙' in text or '叙事' in text or '描写' in text:
        return '记叙文'
    if '说明文' in text or '说明' in text or '解释' in text or '介绍' in text:
        return '说明文'
    return '记叙文'

def is_essay_submission(text):
    essay_keywords = ['作文', '文章', '写作', 'essay', '作文题', '请批改', '请点评',
                      '写一篇', '写了一篇', '字数', '段落', '开头', '结尾',
                      '议论文', '记叙文', '说明文']
    consultation_keywords = ['如何', '怎么', '怎样', '为什么', '请问', '我想问',
                            '问一下', '咨询', '方法', '技巧', '策略', '要点', '建议',
                            '告诉我', '分析一下']

    has_essay = any(kw in text for kw in essay_keywords)
    has_consult = any(kw in text for kw in consultation_keywords)
    is_long = len(text) > 200

    # 如果文本很短（小于30字），即使包含作文关键词也不是作文提交
    if len(text) < 30:
        return False

    # 如果包含咨询关键词，优先判定为咨询
    if has_consult:
        return False

    # 如果包含作文关键词且文本较长，判定为作文提交
    if has_essay and is_long:
        return True

    # 纯长文本（超过500字）也判定为作文提交
    if len(text) > 500:
        return True

    return is_long

def extract_json_from_response(response_text):
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
    if not isinstance(json_data, dict):
        print(f"JSON数据类型错误，期望dict，得到 {type(json_data)}")
        return None

    dimension_map = {
        '议论文': ['立意与中心', '论点与论证', '结构与层次', '语言表达', '例证与材料运用', '书写与规范'],
        '记叙文': ['立意与中心', '选材与内容', '结构与层次', '语言表达', '细节与表现', '书写与规范'],
        '说明文': ['立意与中心', '内容与材料', '结构与层次', '语言表达', '方法与技巧', '书写与规范']
    }

    result = {
        'score': None,
        'total_score': 60,
        'essay_type': essay_type,
        'dimensions': [],
        'overall_comment': '',
        'improvements': [],
        'raw_response': ''
    }

    try:
        if '总分' in json_data:
            score = json_data['总分']
            if isinstance(score, (int, float)):
                result['score'] = int(score)
            elif isinstance(score, str):
                score_match = re.search(r'\d+', score)
                if score_match:
                    result['score'] = int(score_match.group())

        if '各项评分' in json_data and isinstance(json_data['各项评分'], dict):
            dims = dimension_map.get(essay_type, dimension_map['记叙文'])
            for dim_name in dims:
                if dim_name in json_data['各项评分']:
                    score = json_data['各项评分'][dim_name]
                    if isinstance(score, (int, float)):
                        result['dimensions'].append({'name': dim_name, 'score': int(score)})
                    elif isinstance(score, str):
                        score_match = re.search(r'\d+', score)
                        if score_match:
                            result['dimensions'].append({'name': dim_name, 'score': int(score_match.group())})

        if '总体评价' in json_data:
            comment = json_data['总体评价']
            if isinstance(comment, str):
                result['overall_comment'] = comment.strip()
            elif isinstance(comment, (list, tuple)):
                result['overall_comment'] = ' '.join(str(c) for c in comment)

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
    dimension_map = {
        '议论文': [
            ('立意与中心', '立意与中心'),
            ('论点与论证', '论点与论证'),
            ('结构与层次', '结构与层次'),
            ('语言表达', '语言表达'),
            ('例证与材料运用', '例证与材料运用'),
            ('书写与规范', '书写与规范')
        ],
        '记叙文': [
            ('立意与中心', '立意与中心'),
            ('选材与内容', '选材与内容'),
            ('结构与层次', '结构与层次'),
            ('语言表达', '语言表达'),
            ('细节与表现', '细节与表现'),
            ('书写与规范', '书写与规范')
        ],
        '说明文': [
            ('立意与中心', '立意与中心'),
            ('内容与材料', '内容与材料'),
            ('结构与层次', '结构与层次'),
            ('语言表达', '语言表达'),
            ('方法与技巧', '方法与技巧'),
            ('书写与规范', '书写与规范')
        ]
    }

    result = {
        'score': None,
        'total_score': 60,
        'essay_type': essay_type,
        'dimensions': [],
        'overall_comment': '',
        'improvements': [],
        'raw_response': response_text
    }

    score_patterns = [
        r'总分[：:]\s*(\d+)',
        r'得分[：:]\s*(\d+)',
    ]

    for pattern in score_patterns:
        score_match = re.search(pattern, response_text)
        if score_match:
            result['score'] = int(score_match.group(1))
            break

    dims = dimension_map.get(essay_type, dimension_map['记叙文'])
    found_dims = set()

    for dim_key, dim_name in dims:
        pattern = rf'{re.escape(dim_key)}[：:]\s*(\d+)'
        match = re.search(pattern, response_text)
        if match and dim_name not in found_dims:
            result['dimensions'].append({'name': dim_name, 'score': int(match.group(1))})
            found_dims.add(dim_name)

    overall_patterns = [
        r'总体评价[：:]\s*["""]?(.*?)["""]?\s*(?=改进建议|建议|$)',
        r'总评[：:]\s*["""]?(.*?)["""]?\s*(?=改进建议|建议|$)',
    ]

    for pattern in overall_patterns:
        match = re.search(pattern, response_text, re.DOTALL)
        if match:
            result['overall_comment'] = match.group(1).strip().strip('"').strip("'")
            break

    improvement_patterns = [
        r'改进建议[：:]\s*["""]?(.*?)["""]?\s*$',
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

    return result

def parse_essay_feedback(response_text, essay_type):
    json_data = extract_json_from_response(response_text)

    if json_data:
        parsed = parse_json_feedback(json_data, essay_type)
        if parsed and parsed.get('score') is not None:
            parsed['raw_response'] = response_text
            return parsed
        else:
            print("JSON解析成功但数据不完整，尝试文本解析")

    parsed = parse_text_feedback(response_text, essay_type)
    parsed['raw_response'] = response_text
    return parsed

def generate_essay_review(essay_content, essay_type):
    prompt_template = ESSAY_PROMPTS.get(essay_type, ESSAY_PROMPTS['记叙文'])
    criteria = ESSAY_CRITERIA.get(essay_type, '')

    # 完整的prompt已包含{essay_content}占位符
    full_prompt = prompt_template.format(
        essay_content=essay_content,
        criteria=criteria
    )

    try:
        response = ''
        for chunk in agent.execute_stream(full_prompt):
            if chunk:
                response += chunk
        return response if response else "抱歉，生成作文批改失败，请稍后重试。"
    except Exception as e:
        print(f"生成作文批改失败: {str(e)}")
        print(traceback.format_exc())
        raise Exception(f"生成作文批改失败: {str(e)}")

def chat_with_agent(message):
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

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    message = data.get('message', '')

    if not message:
        return jsonify({
            'success': False,
            'error': '请输入内容',
            'message': '请输入内容'
        }), 400

    try:
        is_essay = is_essay_submission(message)

        if is_essay:
            essay_type = detect_essay_type(message)
            response = generate_essay_review(message, essay_type)
        else:
            response = chat_with_agent(message)

        parsed = parse_essay_feedback(response, essay_type if is_essay else '记叙文')

        if is_essay and parsed['score'] is None:
            parsed['essay_type'] = detect_essay_type(message)

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
    请求体: {"username": "admin", "password": "123456"}
    返回: {"success": true, "token": "xxx"}
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
    """
    return os.path.join(HISTORY_DIR, f'{username}_history.json')

def load_user_history(username):
    """
    加载用户历史记录
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
    保存历史记录
    请求体: {"history": [...]}
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
    获取历史记录
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
    删除历史记录
    请求体: {"chat_id": "xxx"} 或 {"all": true}
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

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8501, debug=True)