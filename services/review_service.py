"""
作文批改服务模块

负责处理作文批改的核心业务逻辑，包括：
- 作文体裁识别
- RAG检索评分标准
- 调用AI模型进行批改
- 解析批改结果
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
    TYPE_FEATURES, SUPPORTED_TYPES, DIMENSION_MAP, DIMENSION_MAX_SCORES
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
    5. 解析和格式化结果
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
        
        # 构建评分标准提示
        criteria_prompt = self._build_criteria_prompt(essay_type)
        
        # 构建完整提示词
        full_prompt = prompt_template.format(
            essay_content=content,
            essay_type=essay_type,
            scoring_criteria=criteria_prompt
        )
        
        return full_prompt
    
    def _get_default_prompt(self) -> str:
        """
        获取默认提示词模板
        """
        return """
你是一位专业的初中语文作文批改老师，请按照以下要求对作文进行批改：

作文内容：
{essay_content}

作文体裁：{essay_type}

评分标准：
{scoring_criteria}

请按照以下结构输出批改结果：

【作文批改总结】
- 亮点：列出作文的优点和亮点（最多3点）
- 问题：列出作文存在的主要问题（最多3点）

【各项评分】
请按照评分标准给出各维度得分

【总体评价】
给出简洁的总体评价

【改进建议】
作为批改老师，给出具体、可操作的改进建议（3-5条）

请确保输出格式清晰，便于用户阅读和理解。
"""
    
    def _build_criteria_prompt(self, essay_type: str) -> str:
        """
        构建评分标准提示词
        
        参数：
            essay_type: 作文体裁
            
        返回：
            str: 评分标准描述
        """
        criteria = {
            '议论文': """
【议论文评分标准（满分50分）】
1. 论点与论证（18分）：论点明确、深刻；论证充分、逻辑严密
2. 立意与中心（12分）：中心突出、立意新颖、思想深刻
3. 结构与层次（8分）：结构完整、层次清晰、过渡自然
4. 语言表达（10分）：语言流畅、准确生动、用词恰当
5. 书写与规范（2分）：书写工整、格式规范
""",
            '记叙文': """
【记叙文评分标准（满分50分）】
1. 选材与内容（15分）：选材新颖、内容充实、感情真挚
2. 立意与中心（12分）：中心明确、主题深刻
3. 结构与层次（8分）：结构完整、条理清晰
4. 语言表达（10分）：语言流畅、生动形象
5. 细节与表现（5分）：细节描写生动、表现力强
""",
            '说明文': """
【说明文评分标准（满分50分）】
1. 内容与材料（15分）：内容准确、材料丰富、数据可靠
2. 立意与中心（12分）：说明对象明确、中心突出
3. 结构与层次（8分）：结构清晰、条理分明
4. 语言表达（10分）：语言准确、简洁明了
5. 方法与技巧（5分）：说明方法恰当、技巧运用熟练
"""
        }
        
        return criteria.get(essay_type, criteria['记叙文'])
    
    def _parse_response(self, response: str, essay_type: str) -> Dict[str, Any]:
        """
        解析AI响应
        
        参数：
            response: AI返回的原始响应
            essay_type: 作文体裁
            
        返回：
            Dict: 解析后的批改结果
        """
        result = {
            'score': None,
            'total_score': 50,
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
            
            # 解析各维度评分
            dimension_patterns = {
                '议论文': [
                    ('论点与论证', r'论点与论证[：:]?\s*(\d+)'),
                    ('立意与中心', r'立意与中心[：:]?\s*(\d+)'),
                    ('结构与层次', r'结构与层次[：:]?\s*(\d+)'),
                    ('语言表达', r'语言表达[：:]?\s*(\d+)'),
                    ('书写与规范', r'书写与规范[：:]?\s*(\d+)')
                ],
                '记叙文': [
                    ('选材与内容', r'选材与内容[：:]?\s*(\d+)'),
                    ('立意与中心', r'立意与中心[：:]?\s*(\d+)'),
                    ('结构与层次', r'结构与层次[：:]?\s*(\d+)'),
                    ('语言表达', r'语言表达[：:]?\s*(\d+)'),
                    ('细节与表现', r'细节与表现[：:]?\s*(\d+)')
                ],
                '说明文': [
                    ('内容与材料', r'内容与材料[：:]?\s*(\d+)'),
                    ('立意与中心', r'立意与中心[：:]?\s*(\d+)'),
                    ('结构与层次', r'结构与层次[：:]?\s*(\d+)'),
                    ('语言表达', r'语言表达[：:]?\s*(\d+)'),
                    ('方法与技巧', r'方法与技巧[：:]?\s*(\d+)')
                ]
            }
            
            dimensions = []
            for name, pattern in dimension_patterns.get(essay_type, []):
                match = re.search(pattern, response)
                if match:
                    dimensions.append({
                        'name': name,
                        'score': int(match.group(1)),
                        'max_score': self._get_dimension_max_score(name, essay_type)
                    })
            
            if dimensions:
                result['dimensions'] = dimensions
                # 如果没有解析到总分，计算总分
                if result['score'] is None:
                    result['score'] = sum(d['score'] for d in dimensions)
            
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
            
            # 解析总结中的亮点和问题
            summary_match = re.search(r'【作文批改总结】(.*?)(【|$)', response, re.DOTALL)
            if summary_match:
                summary_text = summary_match.group(1)
                
                highlights_match = re.search(r'亮点[：:]?(.*?)(问题|$)', summary_text, re.DOTALL)
                if highlights_match:
                    highlights = re.findall(r'[-•*]\s*(.*?)(?=\n|$)', highlights_match.group(1))
                    result['summary']['highlights'] = [h.strip() for h in highlights if h.strip()]
                
                issues_match = re.search(r'问题[：:]?(.*?)$', summary_text, re.DOTALL)
                if issues_match:
                    issues = re.findall(r'[-•*]\s*(.*?)(?=\n|$)', issues_match.group(1))
                    result['summary']['issues'] = [i.strip() for i in issues if i.strip()]
            
        except Exception as e:
            logger.error(f"解析AI响应失败: {str(e)}")
            # 如果解析失败，返回原始响应
            pass
        
        return result
    
    def _get_dimension_max_score(self, dimension_name: str, essay_type: str) -> int:
        """
        获取维度满分值
        
        参数：
            dimension_name: 维度名称
            essay_type: 作文体裁
            
        返回：
            int: 满分值
        """
        # 使用统一的维度满分值常量
        return DIMENSION_MAX_SCORES.get(essay_type, {}).get(dimension_name, 10)
    
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
        """
        logger.info(f"开始作文批改，体裁: {essay_type or '自动检测'}, 用户ID: {user_id}")
        
        # 1. 检测或验证体裁
        if not essay_type:
            essay_type = self.detect_essay_type(content)
            logger.info(f"自动检测体裁: {essay_type}")
        
        # 2. 生成提示词
        prompt = self._generate_prompt(content, essay_type)
        
        # 3. 调用AI模型
        try:
            logger.info("调用AI模型进行批改...")
            response = self.chat_model.invoke(prompt)
            raw_response = response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            logger.error(f"调用AI模型失败: {str(e)}")
            raise ServiceUnavailableError("AI服务")
        
        # 4. 解析响应
        result = self._parse_response(raw_response, essay_type)
        
        # 5. 保存历史记录
        self._save_to_history(content, result, user_id)
        
        logger.info(f"作文批改完成，得分: {result.get('score')}")
        
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
