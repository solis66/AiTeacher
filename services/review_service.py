"""
作文批改服务模块

负责处理作文批改的核心业务逻辑，包括：
- 作文体裁识别
- RAG检索评分标准
- 调用AI模型进行批改
- 解析批改结果（支持JSON格式）
- 管理批改历史记录

设计模式：
- 服务层封装：将业务逻辑与路由解耦
- 依赖注入：通过模型工厂获取AI模型实例
- 策略模式：根据体裁选择不同的评分标准

安全设计：
- 输入清洗：对用户输入进行安全处理
- 日志脱敏：不在日志中记录敏感信息
- 异常处理：统一的异常处理机制
"""

import json
import re
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any, List
from model.factory import get_chat_model, get_embedding_model
from utils.config_handler import rag_conf
from utils.error_handler import ServiceUnavailableError
from utils.essay_constants import (
    TYPE_FEATURES, SUPPORTED_TYPES, DIMENSION_MAP, DIMENSION_MAX_SCORES,
    TOTAL_SCORE, get_dimensions, get_dimension_max_score
)
import logging

# 配置日志
logger = logging.getLogger(__name__)


class EssayReviewService:
    """
    作文批改服务类
    
    提供作文批改的完整业务流程：
    1. 接收作文内容和体裁（可选）
    2. 识别/验证作文体裁
    3. 检索相应的评分标准
    4. 调用AI模型进行批改
    5. 解析和格式化结果（优先JSON格式）
    6. 保存历史记录
    """
    
    def __init__(self):
        """
        初始化服务
        """
        # 初始化模型（懒加载）
        self._chat_model = None
        self._embedding_model = None
    
    @property
    def chat_model(self):
        """
        获取聊天模型（懒加载）
        
        返回：
            聊天模型实例
        """
        if not self._chat_model:
            try:
                self._chat_model = get_chat_model()
            except Exception as e:
                logger.error(f"初始化聊天模型失败: {str(e)}")
                raise ServiceUnavailableError("AI服务")
        return self._chat_model
    
    @property
    def embedding_model(self):
        """
        获取嵌入模型（懒加载）
        
        返回：
            嵌入模型实例
        """
        if not self._embedding_model:
            try:
                self._embedding_model = get_embedding_model()
            except Exception as e:
                logger.error(f"初始化嵌入模型失败: {str(e)}")
                raise ServiceUnavailableError("AI服务")
        return self._embedding_model
    
    def detect_essay_type(self, content: str) -> str:
        """
        自动检测作文体裁
        
        参数：
            content: 作文内容
            
        返回：
            str: 检测到的体裁（议论文/记叙文/说明文）
            
        实现逻辑：
        1. 统计各体裁特征词在作文中的出现次数
        2. 返回特征词匹配最多的体裁
        3. 如果没有匹配，默认返回记叙文
        """
        content_lower = content.lower()
        scores = {}
        
        # 使用统一的体裁特征词常量
        for essay_type, features in TYPE_FEATURES.items():
            score = sum(1 for feature in features if feature in content_lower)
            scores[essay_type] = score
        
        # 返回得分最高的体裁，默认记叙文
        max_score = max(scores.values())
        if max_score == 0:
            return '记叙文'
        
        # 处理并列情况
        top_types = [t for t, s in scores.items() if s == max_score]
        
        # 如果议论文和记叙文得分相同，优先选择记叙文（更常见）
        if len(top_types) > 1:
            if '记叙文' in top_types:
                return '记叙文'
        
        return top_types[0]
    
    def _generate_prompt(self, content: str, essay_type: str) -> str:
        """
        生成AI提示词
        
        参数：
            content: 作文内容
            essay_type: 作文体裁
            
        返回：
            str: 完整的提示词
            
        实现逻辑：
        1. 读取提示词模板文件
        2. 动态生成评分标准（基于作文体裁）
        3. 动态生成JSON schema（仅包含当前体裁的维度）
        4. 替换模板中的占位符
        """
        # 读取提示词模板
        prompt_path = rag_conf.get('prompt_path', 'prompts/rag_summarize.txt')
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                prompt_template = f.read()
        except Exception as e:
            logger.error(f"读取提示词模板失败: {str(e)}")
            # 使用默认模板
            prompt_template = self._get_default_prompt()
        
        # 构建评分标准提示（动态生成）
        criteria_prompt = self._build_criteria_prompt(essay_type)
        
        # 构建维度JSON schema（动态生成）
        dimension_json_schema = self._build_dimension_json_schema(essay_type)
        
        # 构建完整提示词
        full_prompt = prompt_template.format(
            essay_content=content,
            essay_type=essay_type,
            scoring_criteria=criteria_prompt,
            dimension_json_schema=dimension_json_schema
        )
        
        logger.debug(f"生成的提示词长度: {len(full_prompt)}")
        return full_prompt
    
    def _get_default_prompt(self) -> str:
        """
        获取默认提示词模板（当模板文件读取失败时使用）
        
        返回：
            str: 默认提示词模板
        """
        return """
你是一位专业的初中语文作文批改老师，请按照以下要求对作文进行批改：

### 作文内容
{essay_content}

### 作文体裁
{essay_type}

### 评分标准
{scoring_criteria}

### 输出格式要求

请严格按照以下JSON格式输出批改结果（注意：所有评分必须是整数，总分不超过50分）：

```json
{{
  "总分": XX,
  "各项评分": {dimension_json_schema},
  "总体评价": "（针对这篇作文的具体评价）",
  "改进建议": ["（具体建议1）", "（具体建议2）", "（具体建议3）"],
  "亮点": ["亮点1", "亮点2"],
  "问题": ["问题1", "问题2"]
}}
```

### 约束条件
1. 内容必须基于作文内容和评分标准，不得编造信息
2. 语言简洁、准确，适合初中生理解
3. 评分必须客观公正，符合评分标准
4. 改进建议要具体可行，具有指导性
5. 输出格式必须符合上述要求，使用JSON格式回答
"""
    
    def _build_criteria_prompt(self, essay_type: str) -> str:
        """
        动态构建评分标准提示词
        
        参数：
            essay_type: 作文体裁
            
        返回：
            str: 评分标准描述
            
        设计说明：
        - 使用常量配置DIMENSION_MAP和DIMENSION_MAX_SCORES动态生成
        - 确保评分标准与配置严格一致
        - 维度顺序与配置保持一致
        """
        # 获取当前体裁的维度列表和满分配置
        dimensions = get_dimensions(essay_type)
        max_scores = DIMENSION_MAX_SCORES.get(essay_type, {})
        
        # 维度评分标准描述模板
        dimension_descriptions = {
            '立意与中心': '中心突出、立意新颖、思想深刻',
            '论点与论证': '论点明确、深刻；论证充分、逻辑严密',
            '选材与内容': '选材新颖、内容充实、感情真挚',
            '结构与层次': '结构完整、层次清晰、过渡自然',
            '语言表达': '语言流畅、准确生动、用词恰当',
            '例证与材料运用': '例证恰当、材料丰富、运用合理',
            '细节与表现': '细节描写生动、表现力强',
            '方法与技巧': '说明方法恰当、技巧运用熟练',
            '书写与规范': '书写工整、格式规范'
        }
        
        # 构建评分标准字符串
        criteria_lines = []
        criteria_lines.append(f"【{essay_type}评分标准（满分{TOTAL_SCORE}分）】")
        
        for i, dim_name in enumerate(dimensions, 1):
            max_score = max_scores.get(dim_name, 10)
            description = dimension_descriptions.get(dim_name, '评分维度')
            criteria_lines.append(f"{i}. {dim_name}（{max_score}分）：{description}")
        
        return '\n'.join(criteria_lines)
    
    def _build_dimension_json_schema(self, essay_type: str) -> str:
        """
        动态构建维度JSON schema
        
        参数：
            essay_type: 作文体裁
            
        返回：
            str: JSON格式的维度schema
            
        设计说明：
        - 根据作文体裁动态生成对应的评分维度
        - 确保JSON schema仅包含当前体裁的必要维度
        - 格式符合JSON规范，便于AI理解和输出
        """
        # 获取当前体裁的维度列表
        dimensions = get_dimensions(essay_type)
        
        # 构建维度schema（每个维度占一行，便于阅读）
        dim_lines = []
        for dim_name in dimensions:
            dim_lines.append(f'        "{dim_name}": XX')
        
        # 组合成完整的JSON对象字符串
        return '{\n' + ',\n'.join(dim_lines) + '\n      }'
    
    def _parse_response(self, response: str, essay_type: str) -> Dict[str, Any]:
        """
        解析AI响应（优先JSON格式，兼容旧格式）
        
        参数：
            response: AI返回的原始响应
            essay_type: 作文体裁
            
        返回：
            Dict: 解析后的批改结果
            
        实现逻辑：
        1. 首先尝试JSON格式解析（优先）
        2. 如果JSON解析失败，尝试正则表达式解析（兼容旧格式）
        3. 确保解析结果与常量配置一致
        """
        result = {
            'score': None,
            'total_score': TOTAL_SCORE,
            'essay_type': essay_type,
            'dimensions': [],
            'overall_comment': '',
            'improvements': [],
            'summary': {
                'highlights': [],
                'issues': []
            },
            'raw_response': response
        }
        
        # 尝试从响应中提取JSON内容（处理可能的markdown代码块）
        json_content = self._extract_json_from_response(response)
        
        if json_content:
            # 尝试JSON解析
            try:
                parsed = json.loads(json_content)
                result = self._parse_json_response(parsed, essay_type)
                logger.info("成功使用JSON格式解析响应")
                return result
            except json.JSONDecodeError as e:
                logger.warning(f"JSON解析失败，尝试正则解析: {str(e)}")
        
        # JSON解析失败，使用正则表达式解析（兼容旧格式）
        result = self._parse_regex_response(response, essay_type)
        logger.info("使用正则表达式解析响应")
        
        return result
    
    def _extract_json_from_response(self, response: str) -> Optional[str]:
        """
        从响应中提取JSON内容
        
        参数：
            response: AI返回的原始响应
            
        返回：
            Optional[str]: 提取的JSON字符串，失败返回None
            
        实现逻辑：
        1. 尝试匹配markdown代码块中的JSON
        2. 如果没有代码块，尝试直接查找JSON对象
        """
        # 尝试匹配markdown代码块
        code_block_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
        if code_block_match:
            return code_block_match.group(1)
        
        # 尝试匹配大括号包裹的JSON对象
        json_match = re.search(r'(\{[\s\S]*\})', response)
        if json_match:
            return json_match.group(1)
        
        return None
    
    def _parse_json_response(self, parsed: Dict[str, Any], essay_type: str) -> Dict[str, Any]:
        """
        解析JSON格式的响应
        
        参数：
            parsed: 已解析的JSON对象
            essay_type: 作文体裁
            
        返回：
            Dict: 格式化后的批改结果
            
        实现逻辑：
        1. 提取总分
        2. 提取各项评分（确保维度与配置一致）
        3. 提取总体评价和改进建议
        4. 提取亮点和问题
        """
        result = {
            'score': parsed.get('总分'),
            'total_score': TOTAL_SCORE,
            'essay_type': essay_type,
            'dimensions': [],
            'overall_comment': parsed.get('总体评价', ''),
            'improvements': parsed.get('改进建议', []),
            'summary': {
                'highlights': parsed.get('亮点', []),
                'issues': parsed.get('问题', [])
            },
            'raw_response': json.dumps(parsed, ensure_ascii=False)
        }
        
        # 提取各项评分并与配置匹配
        dimension_scores = parsed.get('各项评分', {})
        dimensions = get_dimensions(essay_type)
        max_scores = DIMENSION_MAX_SCORES.get(essay_type, {})
        
        for dim_name in dimensions:
            score = dimension_scores.get(dim_name)
            if score is not None:
                result['dimensions'].append({
                    'name': dim_name,
                    'score': int(score),
                    'max_score': max_scores.get(dim_name, 10)
                })
        
        # 如果没有总分，计算总分
        if result['score'] is None and result['dimensions']:
            result['score'] = sum(d['score'] for d in result['dimensions'])
        
        return result
    
    def _parse_regex_response(self, response: str, essay_type: str) -> Dict[str, Any]:
        """
        使用正则表达式解析响应（兼容旧格式）
        
        参数：
            response: AI返回的原始响应
            essay_type: 作文体裁
            
        返回：
            Dict: 解析后的批改结果
            
        实现逻辑：
        1. 使用正则表达式提取总分
        2. 根据体裁配置提取各维度评分
        3. 提取总体评价和改进建议
        """
        result = {
            'score': None,
            'total_score': TOTAL_SCORE,
            'essay_type': essay_type,
            'dimensions': [],
            'overall_comment': '',
            'improvements': [],
            'summary': {
                'highlights': [],
                'issues': []
            },
            'raw_response': response
        }
        
        try:
            # 解析总分（查找类似"总分：45分"或"得分：45"的模式）
            score_match = re.search(r'(总分|得分)[：:]?\s*(\d+)', response)
            if score_match:
                result['score'] = int(score_match.group(2))
            
            # 获取当前体裁的维度配置
            dimensions = get_dimensions(essay_type)
            max_scores = DIMENSION_MAX_SCORES.get(essay_type, {})
            
            # 解析各维度评分
            parsed_dimensions = []
            for dim_name in dimensions:
                # 构建正则模式匹配该维度
                pattern = re.escape(dim_name) + r'[：:]?\s*(\d+)'
                match = re.search(pattern, response)
                if match:
                    parsed_dimensions.append({
                        'name': dim_name,
                        'score': int(match.group(1)),
                        'max_score': max_scores.get(dim_name, 10)
                    })
            
            if parsed_dimensions:
                result['dimensions'] = parsed_dimensions
                # 如果没有解析到总分，计算总分
                if result['score'] is None:
                    result['score'] = sum(d['score'] for d in parsed_dimensions)
            
            # 解析总体评价
            comment_match = re.search(r'【总体评价】(.*?)(【|$)', response, re.DOTALL)
            if comment_match:
                result['overall_comment'] = comment_match.group(1).strip()
            
            # 解析改进建议
            improvements_match = re.search(r'【改进建议】(.*?)(【|$)', response, re.DOTALL)
            if improvements_match:
                improvements_text = improvements_match.group(1)
                improvements = re.findall(r'[\d一二三四五][、.．]?\s*(.*?)(?=\n|$)', improvements_text)
                result['improvements'] = [i.strip() for i in improvements if i.strip()]
            
            # 解析亮点
            highlights_match = re.search(r'亮点[：:]?\s*\[([^\]]+)\]', response)
            if highlights_match:
                highlights = [h.strip() for h in highlights_match.group(1).split(',')]
                result['summary']['highlights'] = highlights
            
            # 解析问题
            issues_match = re.search(r'问题[：:]?\s*\[([^\]]+)\]', response)
            if issues_match:
                issues = [i.strip() for i in issues_match.group(1).split(',')]
                result['summary']['issues'] = issues
        
        except Exception as e:
            logger.error(f"正则解析AI响应失败: {str(e)}")
        
        return result
    
    def _save_to_history(self, content: str, result: Dict, user_id: Optional[str]) -> str:
        """
        保存批改记录到历史
        
        参数：
            content: 作文内容
            result: 批改结果
            user_id: 用户ID
            
        返回：
            str: 记录ID
        """
        record = {
            'id': hashlib.md5(f"{datetime.now().timestamp()}{content[:100]}".encode()).hexdigest(),
            'content': content[:500],  # 保存摘要
            'result': result,
            'user_id': user_id,
            'created_at': datetime.now().isoformat(),
            'essay_type': result.get('essay_type')
        }
        
        # 保存到本地文件（实际项目中应使用数据库）
        history_file = 'data/history.json'
        try:
            import os
            os.makedirs('data', exist_ok=True)
            
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except FileNotFoundError:
                history = []
            
            history.insert(0, record)
            
            # 保留最近100条记录
            history = history[:100]
            
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
                
            logger.info(f"批改记录已保存，ID: {record['id']}")
        except Exception as e:
            logger.error(f"保存历史记录失败: {str(e)}")
            # 不影响主要流程
        
        return record['id']
    
    def review_essay(self, content: str, essay_type: str = '', user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        执行作文批改
        
        参数：
            content: 作文内容
            essay_type: 作文体裁（可选，不传则自动检测）
            user_id: 用户ID（可选）
            
        返回：
            Dict: 批改结果
            
        业务流程：
        1. 检测或验证体裁
        2. 生成提示词（动态维度配置）
        3. 调用AI模型
        4. 解析响应（优先JSON格式）
        5. 保存历史记录
        """
        logger.info(f"开始作文批改，体裁: {essay_type or '自动检测'}, 用户ID: {user_id}")
        
        # 1. 检测或验证体裁
        if not essay_type:
            essay_type = self.detect_essay_type(content)
            logger.info(f"自动检测体裁: {essay_type}")
        
        # 2. 生成提示词（包含动态评分标准和JSON schema）
        prompt = self._generate_prompt(content, essay_type)
        
        # 3. 调用AI模型
        try:
            logger.info("调用AI模型进行批改...")
            response = self.chat_model.invoke(prompt)
            raw_response = response.content if hasattr(response, 'content') else str(response)
            logger.debug(f"AI响应长度: {len(raw_response)}")
        except Exception as e:
            logger.error(f"调用AI模型失败: {str(e)}")
            raise ServiceUnavailableError("AI服务")
        
        # 4. 解析响应（优先JSON格式）
        result = self._parse_response(raw_response, essay_type)
        
        # 5. 保存历史记录
        self._save_to_history(content, result, user_id)
        
        logger.info(f"作文批改完成，得分: {result.get('score')}, 维度数量: {len(result.get('dimensions', []))}")
        
        return result
    
    def get_history(self, user_id: Optional[str] = None, page: int = 1, limit: int = 10) -> Dict[str, Any]:
        """
        获取批改历史
        
        参数：
            user_id: 用户ID（可选，不传则返回所有）
            page: 页码
            limit: 每页数量
            
        返回：
            Dict: 包含items、total、page、limit的字典
        """
        history_file = 'data/history.json'
        
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except FileNotFoundError:
            history = []
        
        # 过滤用户
        if user_id:
            history = [h for h in history if h.get('user_id') == user_id]
        
        total = len(history)
        start = (page - 1) * limit
        end = start + limit
        
        return {
            'items': history[start:end],
            'total': total,
            'page': page,
            'limit': limit
        }
    
    def get_history_detail(self, history_id: str) -> Optional[Dict]:
        """
        获取单条历史记录详情
        
        参数：
            history_id: 记录ID
            
        返回：
            Optional[Dict]: 记录详情或None
        """
        history_file = 'data/history.json'
        
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            
            for record in history:
                if record.get('id') == history_id:
                    return record
        except Exception as e:
            logger.error(f"查询历史记录失败: {str(e)}")
        
        return None
    
    def delete_history(self, history_id: str) -> bool:
        """
        删除历史记录
        
        参数：
            history_id: 记录ID
            
        返回：
            bool: 是否删除成功
        """
        history_file = 'data/history.json'
        
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            
            original_length = len(history)
            history = [h for h in history if h.get('id') != history_id]
            
            if len(history) < original_length:
                with open(history_file, 'w', encoding='utf-8') as f:
                    json.dump(history, f, ensure_ascii=False, indent=2)
                return True
        except Exception as e:
            logger.error(f"删除历史记录失败: {str(e)}")
        
        return False
    
    def get_supported_types(self) -> List[Dict]:
        """
        获取支持的作文体裁列表
        
        返回：
            List[Dict]: 体裁列表
        """
        # 使用统一的体裁列表常量
        return SUPPORTED_TYPES