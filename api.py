from flask import Flask, request, jsonify
from flask_cors import CORS
from agent.tools.react_agent import ReactAgent
import traceback
import re
import os
import json

app = Flask(__name__)
CORS(app)

agent = ReactAgent()

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
    '议论文': """你是一个专业的初中语文作文批改教师。请根据以下议论文评分标准，对用户提交的议论文进行批改并给出评分。

## 议论文评分标准（满分60分）
{criteria}

## 批改要求

请对议论文进行专业批改。批改完成后，你必须严格按照以下JSON格式输出，不要输出任何其他内容：

```json
{{
  "总分": 50,
  "各项评分": {{
    "立意与中心": 10,
    "论点与论证": 15,
    "结构与层次": 8,
    "语言表达": 10,
    "例证与材料运用": 5,
    "书写与规范": 2
  }},
  "总体评价": "这篇议论文立论明确，论点清晰，论证过程较为完整。开头提出中心论点，中段运用例证进行论证，结尾总结升华。文章结构层次分明，但在论据的丰富性和语言的精炼度上还有提升空间。",
  "改进建议": [
    "建议1：增加更多典型事例作为论据，使论证更加充分有力",
    "建议2：优化段落之间的过渡，使文章结构更流畅",
    "建议3：加强对关键论点的深入分析，避免浅尝辄止"
  ]
}}
```

注意：所有评分必须是整数，总分不要超过60分。""",

    '记叙文': """你是一个专业的初中语文作文批改教师。请根据以下记叙文评分标准，对用户提交的记叙文进行批改并给出评分。

## 记叙文评分标准（满分60分）
{criteria}

## 批改要求

请对记叙文进行专业批改。批改完成后，你必须严格按照以下JSON格式输出，不要输出任何其他内容：

```json
{{
  "总分": 50,
  "各项评分": {{
    "立意与中心": 10,
    "选材与内容": 15,
    "结构与层次": 8,
    "语言表达": 10,
    "细节与表现": 5,
    "书写与规范": 2
  }},
  "总体评价": "这篇记叙文选材贴近生活，叙事较为清晰，能够围绕中心事件展开描写。人物形象有一定特色，语言表达较为流畅。但在细节描写、情感深度和结构布局上还有提升空间，结尾的升华略显不足。",
  "改进建议": [
    "建议1：增加人物心理活动的描写，使情感更加细腻动人",
    "建议2：精选1-2个重点场景进行详细刻画，避免平铺直叙",
    "建议3：优化文章结构，可以采用倒叙或插叙等手法增加吸引力"
  ]
}}
```

注意：所有评分必须是整数，总分不要超过60分。""",

    '说明文': """你是一个专业的初中语文作文批改教师。请根据以下说明文评分标准，对用户提交的说明文进行批改并给出评分。

## 说明文评分标准（满分60分）
{criteria}

## 批改要求

请对说明文进行专业批改。批改完成后，你必须严格按照以下JSON格式输出，不要输出任何其他内容：

```json
{{
  "总分": 50,
  "各项评分": {{
    "立意与中心": 10,
    "内容与材料": 15,
    "结构与层次": 8,
    "语言表达": 10,
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
                            '问一下', '咨询', '方法', '技巧', '策略', '要点', '建议']

    has_essay = any(kw in text for kw in essay_keywords)
    has_consult = any(kw in text for kw in consultation_keywords)
    is_long = len(text) > 200

    if has_essay and not has_consult:
        return True
    if has_consult and not has_essay:
        return False
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

    full_prompt = f"""{prompt_template.format(criteria=criteria)}

## 待批改作文

{essay_content}

请对以上作文进行批改，直接输出JSON结果，不要输出其他内容。"""

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
    except Exception as e:
        print(f"对话失败: {str(e)}")
        print(traceback.format_exc())
        raise Exception(f"对话失败: {str(e)}")

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

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8501, debug=True)