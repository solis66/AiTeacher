"""
咨询服务模块

负责处理用户的非作文类咨询问题，提供专业的初中语文教育相关回答。

核心功能：
1. 输入验证与内容相关性检测：确保用户输入有效且与初中作文相关
2. 问候语响应：处理用户问候和自我介绍请求
3. 作文知识咨询：回答关于作文写作技巧、评分标准等问题
4. 天气查询响应：处理天气相关查询
5. 通用问题回答：使用AI模型回答各类问题

设计特点：
- 基于规则和AI模型的混合响应机制
- 支持初中教育场景的专业知识
- 友好的语言风格，适合初中生理解
- 完善的错误处理和回退机制
- 严格的内容相关性检测，屏蔽无关消息
"""

from typing import Optional, Dict, Any, Tuple
from model.factory import get_chat_model, is_model_initialized
from agent.tools.react_agent import ReactAgent
from services import consult_context
from utils.standard_loader import load_unified_standard
from utils.chat_memory import build_history_block
import logging
import re

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ConsultationService:
    """
    咨询服务类
    
    提供专业的初中作文咨询服务，支持：
    1. 输入验证与内容相关性检测
    2. 问候语处理
    3. 作文知识问答
    4. 通用问题回答
    5. 特殊问题处理（如天气查询）
    
    响应类型说明：
        - greeting: 问候语响应
        - weather: 天气查询响应  
        - knowledge: 知识库响应
        - ai: AI生成响应
        - irrelevant: 无关内容响应
        - error: 错误响应
    """
    
    # 无关内容提示语（符合用户要求的标准格式）
    IRRELEVANT_CONTENT_MESSAGE = "这里是AI智能批改教师，请问有什么需要帮助的吗？"
    
    # 最小输入长度限制（允许1个及以上字符）
    MIN_INPUT_LENGTH = 1
    
    def __init__(self):
        """
        初始化咨询服务
        
        加载预设的问候语响应、作文知识库和相关关键词列表
        """
        self._chat_model = None
        self._agent = ReactAgent()
        
        # 预设问候语响应
        self._greeting_responses = {
            'hello': [
                '你好！我是你的初中AI语文老师，很高兴为你服务！',
                '你好呀！请问有什么可以帮助你的吗？',
                '嗨！我是专门帮助初中生学习作文的AI老师，有问题尽管问我吧！'
            ],
            'introduce': [
                '我是你的初中AI语文老师，主要可以帮你：\n\n'
                '📝 作文批改：提交你的作文，我会为你提供专业的批改和建议\n'
                '💡 写作指导：解答你关于作文写作的各种问题\n'
                '📚 知识问答：解释作文评分标准、写作技巧等知识\n'
                '🎯 学习建议：根据你的需求提供针对性的学习建议',
                '你好！我是专为初中生设计的作文辅导AI。我可以帮你批改作文、解答写作疑问，'
                '还能教你各种写作技巧。有什么需要帮助的吗？'
            ]
        }
        
        # 预设作文知识问答（基于统一评分标准文档《广东省中考作文评分标准.doc》）
        self._essay_knowledge = {
            '议论文标准': self._build_unified_standard_knowledge('议论文'),
            '记叙文标准': self._build_unified_standard_knowledge('记叙文'),
            '说明文标准': self._build_unified_standard_knowledge('说明文'),

            '写作技巧': """初中作文写作技巧：

📌 审题立意
- 仔细阅读题目，理解题目的要求
- 确定文章的中心思想，做到立意深刻

📌 结构安排
- 开头：开门见山或设置悬念
- 主体：分段论述，层次清晰
- 结尾：总结全文或升华主题

📌 选材技巧
- 选择真实、典型、新颖的材料
- 材料要能有力支撑主题

📌 语言表达
- 使用准确、生动的词语
- 恰当运用比喻、拟人等修辞手法
- 语句通顺，避免语病

📌 修改润色
- 检查错别字和标点错误
- 优化语句表达
- 调整文章结构""",

            '如何写好开头': """写好作文开头的方法：

1. **开门见山法**：直接点明主题，简洁明了
   例："诚信是做人的根本，也是我一直坚守的原则。"

2. **设置悬念法**：引起读者兴趣
   例："那一天，我终于明白了什么叫做真正的勇气。"

3. **引用名言法**：增加文采和说服力
   例："古人云：'书犹药也，善读之可以医愚。'读书伴我成长。"

4. **景物描写法**：渲染气氛，烘托心情
   例："夕阳的余晖洒落在校园的操场上，一群孩子正在快乐地奔跑。"

5. **故事引入法**：用小故事开头
   例："记得小时候，妈妈给我讲过一个故事..."

选择适合文章主题的开头方式，让你的作文一开始就抓住读者！""",

            '如何写好结尾': """写好作文结尾的方法：

1. **总结全文法**：概括文章主要内容，点明中心
   例："通过这件事，我懂得了坚持就是胜利的道理。"

2. **升华主题法**：从具体事例上升到人生哲理
   例："那一刻，我明白了：关爱他人，就是关爱自己。"

3. **首尾呼应法**：与开头相呼应，结构完整
   例：（开头）"春天来了..."（结尾）"春天，真是一个美好的季节！"

4. **留下悬念法**：让读者回味无穷
   例："这件事虽然过去了很久，但它带给我的启示却永远铭记在心..."

5. **引用名言法**：增强文章的感染力
   例："正如鲁迅先生所说：'时间就像海绵里的水，只要愿挤，总还是有的。'"

一个好的结尾能让文章更加完整，给读者留下深刻印象！""",

            '如何提高作文水平': """提高作文水平的方法：

📝 多读优秀范文
- 阅读课本中的课文
- 阅读课外优秀作文选
- 分析别人的写作技巧

✍️ 坚持每天练习
- 写日记或周记
- 尝试不同体裁的写作
- 注重积累好词好句

🔍 认真修改作文
- 检查错别字和标点
- 优化语句表达
- 调整文章结构

💬 请教老师和同学
- 听取别人的建议
- 接受老师的批改意见
- 学习他人的优点

🎯 积累生活素材
- 观察生活中的点点滴滴
- 记录自己的感受和想法
- 丰富自己的人生体验

坚持下去，你的作文水平一定会不断提高！"""
        }
        
        # 问题类型关键词映射
        self._question_type_mapping = {
            '议论文': ['议论文', '议论', '论点', '论证', '论据'],
            '记叙文': ['记叙文', '记叙', '故事', '经历', '回忆'],
            '说明文': ['说明文', '说明', '介绍', '解释', '原理'],
            '开头': ['开头', '开篇', '开头怎么写', '如何开头'],
            '结尾': ['结尾', '收尾', '结尾怎么写', '如何结尾'],
            '技巧': ['技巧', '方法', '如何写', '怎样写', '提高'],
            '标准': ['标准', '评分', '分数', '满分', '要求'],
        }
        
        # 初中作文相关关键词（用于内容相关性检测）
        self._relevant_keywords = [
            # 作文体裁
            '作文', '议论文', '记叙文', '说明文', '散文', '文章', '习作',
            
            # 作文结构
            '开头', '结尾', '段落', '结构', '提纲', '草稿', '层次',
            
            # 写作技巧
            '写作', '技巧', '方法', '如何', '怎样', '怎么写', '写法',
            
            # 评分相关
            '评分', '标准', '分数', '满分', '要求', '批改', '点评',
            
            # 学习相关
            '学习', '练习', '作业', '题目', '主题', '立意', '选材',
            
            # 语言表达
            '语言', '表达', '词汇', '句子', '描写', '修辞',
            
            # 问候与帮助
            '你好', '您好', '嗨', '帮助', '介绍', '功能', '请教',
        ]
        
        # 排除类关键词（根据边界判定标准文档）
        # 注意：避免使用单字关键词，防止误判正常的作文相关问题
        self._excluded_keywords = [
            # 天气相关（使用完整词语，避免单字"天"造成误判）
            '天气', '温度', '气温', '晴', '雨', '雪', '风', '预报',
            '今天天气', '明天天气', '天气预报',
            
            # 学科知识
            '数学', '物理', '化学', '英语', '历史', '地理', '生物',
            '公式', '定理', '方程', '光合作用',
            
            # 作业代写
            '帮我写', '代写', '写一篇', '帮我修改',
            
            # 闲聊聊天
            '在吗', '无聊', '随便聊聊', '聊天',
            
            # 其他无关内容
            '电影', '音乐', '游戏', '新闻', '体育', '明星', '八卦',
        ]

    def _build_unified_standard_knowledge(self, genre: str) -> str:
        """
        构建统一评分标准知识条目（依据《广东省中考作文评分标准.doc》）

        参数：
            genre: str - 作文体裁（议论文/记叙文/说明文）

        返回：
            str: 知识库回答文本
        """
        genre_guide = {
            '议论文': '写简单的议论文，做到有理有据',
            '记叙文': '写记叙文，做到内容具体充实',
            '说明文': '写简单的说明文，做到明白清楚',
        }.get(genre, '')
        try:
            standard = load_unified_standard()
        except Exception as e:
            logger.error(f"[知识库] 加载统一评分标准失败: {str(e)}")
            standard = ''
        return f"""初中作文统一评分标准（满分50分，依据《广东省中考作文评分标准.doc》）：

{standard}

本题材要点：{genre_guide}

评分优先级：题目与题干要求优先于评分标准文件；评分标准文件仅作为辅助参考依据。"""

    @property
    def chat_model(self):
        """
        获取聊天模型（懒加载）
        
        返回：
            聊天模型实例，如果初始化失败则返回None
            
        异常：
            初始化失败时不抛出异常，返回None，允许降级到其他方式
        """
        if not self._chat_model:
            try:
                logger.info("[咨询服务] 正在初始化聊天模型...")
                self._chat_model = get_chat_model()
                logger.info("[咨询服务] 聊天模型初始化成功")
            except Exception as e:
                logger.error(f"[咨询服务] 初始化聊天模型失败: {str(e)}")
                # 不抛出异常，允许降级到Agent方式
        return self._chat_model
    
    def _validate_input(self, question: str) -> Tuple[bool, str, str]:
        """
        验证用户输入的有效性
        
        参数：
            question: 用户输入的文本内容
            
        返回：
            Tuple[bool, str, str]: (是否有效, 清理后的内容, 错误信息)
            - 第一个元素：True表示输入有效，False表示无效
            - 第二个元素：清理后的输入内容
            - 第三个元素：错误信息（如果有效则为空字符串）
            
        验证规则：
            1. 必须为字符串类型
            2. 长度至少为1个字符
            3. 不能仅包含空白字符
        """
        # 检查类型
        if not isinstance(question, str):
            logger.error("[输入验证] 输入类型错误，期望字符串类型")
            return (False, "", "输入必须为文本类型")
        
        # 清理空白字符
        cleaned_question = question.strip()
        
        # 检查长度
        if len(cleaned_question) < self.MIN_INPUT_LENGTH:
            logger.error("[输入验证] 输入内容为空或过短")
            return (False, "", "请输入有效的问题")
        
        logger.info(f"[输入验证] 输入验证通过，内容长度: {len(cleaned_question)}")
        return (True, cleaned_question, "")
    
    def _is_content_relevant(self, question: str) -> bool:
        """
        检测用户输入内容是否与初中作文相关
        
        根据边界判定标准文档，实现内容相关性检测：
        - 可接受的咨询内容：作文构思、结构优化、语言表达、体裁知识、修改润色、学习方法
        - 排除的咨询范畴：学科知识讲解、作业代写、非作文类问题、聊天闲聊、恶意内容
        
        参数：
            question: 用户输入的文本内容（已通过输入验证）
            
        返回：
            bool: True表示内容相关，False表示内容无关
            
        检测逻辑（按优先级顺序）：
            1. 检查是否为空或非字符串 → 无关
            2. 检查是否为纯数字（如"111"、"12345"等）→ 无关
            3. 检查是否为单字符无效输入（如"x"、"a"等）→ 无关
            4. 检查是否为无意义纯字母（如"ahdkah"等乱码）→ 无关
            5. 检查是否包含排除类关键词（天气、学科、代写、闲聊等）→ 无关
            6. 检查是否包含初中作文相关关键词 → 相关
            7. 检查是否为问候语 → 相关
            8. 检查是否包含疑问词或请求帮助模式 → 相关
            9. 检查是否为自我介绍请求 → 相关
            10. 检查文本长度和复杂度（长文本或包含中文）→ 相关
            11. 默认判定为无关
        """
        if not question or not isinstance(question, str):
            return False
        
        text = question.strip()
        logger.debug(f"[内容检测] 开始检测内容相关性: {text[:30]}...")
        
        # 1. 检查是否为空
        if not text:
            logger.warning("[内容检测] 空内容被判定为无关")
            return False
        
        # 2. 检查是否为纯数字（如"111"、"12345"等）→ 无关
        if text.isdigit():
            logger.warning(f"[内容检测] 纯数字内容 '{text}' 被判定为无关")
            return False
        
        # 3. 检查是否为单字符无效输入（如"x"、"a"等单个字母或符号）→ 无关
        if len(text) == 1:
            # 单个中文汉字视为可能相关（如"写"、"作"等）
            if text >= '\u4e00' and text <= '\u9fff':
                logger.info(f"[内容检测] 单个中文字符 '{text}'，判定为相关")
                return True
            # 单个英文字母或符号视为无关
            logger.warning(f"[内容检测] 单字符无效输入 '{text}' 被判定为无关")
            return False
        
        # 4. 检查是否为纯字母且无意义（如"ahdkah"等乱码）→ 无关
        # 注意：已移除元音检查功能，避免误判技术术语（如SQL、HTML、CSS等）和专有名词
        if text.isalpha() and len(text) <= 15:
            text_lower = text.lower()
            
            # 常见英文单词列表（视为相关）
            common_words = {
                'hello', 'hi', 'help', 'good', 'yes', 'no', 'please', 'thank', 'you',
                'what', 'how', 'why', 'who', 'when', 'where', 'which'
            }
            
            if text_lower not in common_words:
                # 检查是否为乱码（超过50%的字符相同）
                unique_chars = len(set(text))
                if unique_chars / len(text) < 0.4:
                    logger.warning(f"[内容检测] 重复字符乱码 '{text}' 被判定为无关")
                    return False
        
        # 5. 检查是否包含排除类关键词（根据边界判定标准文档）→ 无关
        for keyword in self._excluded_keywords:
            if keyword in text:
                logger.warning(f"[内容检测] 包含排除关键词 '{keyword}'，被判定为无关")
                return False
        
        # 6. 检查是否包含初中作文相关关键词（优先级最高）→ 相关
        for keyword in self._relevant_keywords:
            if keyword in text:
                logger.info(f"[内容检测] 包含相关关键词 '{keyword}'，判定为相关")
                return True
        
        # 7. 检查是否包含问候语模式 → 相关
        greeting_patterns = ['你好', '您好', 'hi', 'hello', '嗨', '您好呀', '你好啊']
        for pattern in greeting_patterns:
            if pattern in text:
                logger.info(f"[内容检测] 包含问候语 '{pattern}'，判定为相关")
                return True
        
        # 8. 检查是否包含疑问词（通常表示有意义的问题）→ 相关
        question_words = ['什么', '怎么', '如何', '为什么', '哪里', '哪个', '谁', '几', '多少']
        has_question = any(qw in text for qw in question_words)
        
        # 9. 检查是否包含请求帮助的模式 → 相关
        help_patterns = ['帮我', '请教', '咨询', '问题', '解答', '指导', '讲解', '告诉我']
        has_help = any(hp in text for hp in help_patterns)
        
        if has_question or has_help:
            logger.info(f"[内容检测] 包含疑问词或请求帮助模式，判定为相关")
            return True
        
        # 10. 检查是否为自我介绍请求 → 相关
        intro_patterns = ['你是谁', '你叫什么', '你能做什么', '介绍一下', '你是做什么的']
        if any(ip in text for ip in intro_patterns):
            logger.info(f"[内容检测] 包含自我介绍请求，判定为相关")
            return True
        
        # 11. 检查文本长度和复杂度（较长或包含中文的内容更可能相关）→ 相关
        has_chinese = any('\u4e00' <= c <= '\u9fff' for c in text)
        if len(text) > 20 or has_chinese:
            logger.info(f"[内容检测] 文本较长({len(text)}字)或包含中文，判定为相关")
            return True
        
        # 默认判定为无关
        logger.warning(f"[内容检测] 无法判定相关性，内容 '{text}' 被判定为无关")
        return False
    
    def _get_knowledge_response(self, question: str) -> Optional[str]:
        """
        从预设知识库中获取回答
        
        参数：
            question: 用户问题（已通过输入验证和相关性检测）
            
        返回：
            Optional[str]: 如果匹配到知识库内容则返回回答字符串，否则返回None
            
        匹配逻辑（按优先级从高到低）：
            1. 精确匹配体裁+类型的组合（如"记叙文标准"）
            2. 单一体裁匹配（如"记叙文"→"记叙文标准"）
            3. 单一类型匹配（如"开头"→"如何写好开头"）
            4. 包含疑问词的匹配（如"如何"、"怎么"配合类型关键词）
            5. 模糊匹配（检查问题是否包含知识库键名）
        """
        # 体裁关键词
        genre_keywords = ['议论文', '记叙文', '说明文']
        # 类型关键词（扩展以支持更多表达方式）
        type_keywords = ['标准', '技巧', '开头', '结尾', '提高', '如何', '怎样', '怎么', '方法']
        
        # 找到问题中包含的体裁和类型
        found_genres = [g for g in genre_keywords if g in question]
        found_types = [t for t in type_keywords if t in question]
        
        logger.debug(f"[知识库匹配] 问题: {question}")
        logger.debug(f"[知识库匹配] 匹配到的体裁: {found_genres}")
        logger.debug(f"[知识库匹配] 匹配到的类型: {found_types}")
        
        # 1. 尝试体裁+类型组合匹配（优先级最高）
        for genre in found_genres:
            for type_kw in found_types:
                combined_key = f"{genre}{type_kw}"
                if combined_key in self._essay_knowledge:
                    logger.info(f"[知识库匹配] 匹配到组合关键词: {combined_key}")
                    return self._essay_knowledge[combined_key]
        
        # 2. 尝试单一体裁匹配（默认返回该体裁的标准）
        for genre in found_genres:
            genre_key = f"{genre}标准"
            if genre_key in self._essay_knowledge:
                logger.info(f"[知识库匹配] 匹配到体裁标准: {genre_key}")
                return self._essay_knowledge[genre_key]
        
        # 3. 尝试单一类型匹配（写作技巧相关）
        if '技巧' in found_types or '提高' in found_types or '方法' in found_types:
            if '写作技巧' in self._essay_knowledge:
                logger.info(f"[知识库匹配] 匹配到写作技巧")
                return self._essay_knowledge['写作技巧']
            elif '如何提高作文水平' in self._essay_knowledge:
                logger.info(f"[知识库匹配] 匹配到提高作文水平")
                return self._essay_knowledge['如何提高作文水平']
        
        # 4. 尝试开头/结尾相关匹配（支持多种表达方式）
        if '开头' in found_types or ('如何' in found_types and '开头' in question):
            if '如何写好开头' in self._essay_knowledge:
                logger.info(f"[知识库匹配] 匹配到如何写好开头")
                return self._essay_knowledge['如何写好开头']
        
        if '结尾' in found_types or ('如何' in found_types and '结尾' in question):
            if '如何写好结尾' in self._essay_knowledge:
                logger.info(f"[知识库匹配] 匹配到如何写好结尾")
                return self._essay_knowledge['如何写好结尾']
        
        # 5. 尝试模糊匹配（检查问题是否包含知识库键名）
        for key in self._essay_knowledge.keys():
            if key in question or question in key:
                logger.info(f"[知识库匹配] 模糊匹配到: {key}")
                return self._essay_knowledge[key]
        
        # 6. 最后尝试：如果问题包含体裁且有相关知识，返回通用写作技巧
        if found_genres and '写作技巧' in self._essay_knowledge:
            logger.info(f"[知识库匹配] 未找到精确匹配，返回写作技巧")
            return self._essay_knowledge['写作技巧']
        
        logger.info(f"[知识库匹配] 未找到匹配的知识库内容")
        return None
    
    def _generate_greeting_response(self, question: str) -> Optional[str]:
        """
        生成问候语响应
        
        参数：
            question: 用户输入（已通过输入验证和相关性检测）
            
        返回：
            Optional[str]: 问候语响应字符串，如果未匹配到则返回None
            
        处理逻辑：
            1. 优先检查是否包含自我介绍请求（你是谁、你能做什么等）
            2. 其次检查是否包含问候语（你好、您好等）
            3. 如果同时包含问候语和自我介绍请求，优先返回自我介绍响应
        """
        greeting_patterns = ['你好', '您好', 'hi', 'hello', '嗨', '您好呀', '你好啊']
        intro_patterns = ['你是谁', '你叫什么', '你能做什么', '介绍一下', '功能', '帮助', 
                         '可以帮我', '能干什么', '什么用', '有什么用', '你是做什么的']
        
        has_greeting = any(p in question for p in greeting_patterns)
        has_intro = any(p in question for p in intro_patterns)
        
        # 如果包含自我介绍请求，优先返回自我介绍
        if has_intro:
            logger.info("[问候语检测] 检测到自我介绍请求")
            return self._greeting_responses['introduce'][0]
        
        # 如果包含问候语，返回问候响应
        if has_greeting:
            logger.info("[问候语检测] 检测到问候语")
            return self._greeting_responses['hello'][0]
        
        return None
    
    def _generate_weather_response(self, question: str) -> str:
        """
        生成天气查询响应（无法实时查询，返回提示）
        
        参数：
            question: 用户问题（已通过输入验证和相关性检测）
            
        返回：
            str: 天气查询响应字符串
            
        说明：
            由于系统不支持实时天气查询，返回友好的提示信息，
            引导用户通过其他方式获取天气信息。
        """
        return """抱歉，我目前无法查询实时天气信息。如果你想了解天气，可以通过以下方式：

1. 打开手机上的天气APP
2. 查看电视或广播的天气预报
3. 询问身边的家人或老师

如果有其他关于作文写作的问题，我很乐意为你解答！"""
    
    def _generate_ai_response(self, question: str, history=None, owner: str = '',
                              role: str = 'auto', student: str = '') -> str:
        """
        使用AI模型生成回答

        参数：
            question: 用户问题（已通过输入验证和相关性检测）
            history:  本会话此前的对话轮次
            owner:    当前账号（数据隔离键，用于检索该账号下的批改记录）
            role:     'student' / 'teacher' / 'auto'，决定"我"能否解析为学生本人
            student:  显式指定的学生名（老师端选择学生时传入）

        返回：
            str: AI生成的回答字符串

        处理流程（多重降级机制）：
            1. 首先尝试使用ReactAgent（支持工具调用）
            2. 如果Agent失败或返回空，尝试直接调用聊天模型（使用完整提示词）
            3. 如果仍失败，尝试使用简化提示词调用聊天模型
            4. 如果所有方式都失败，返回友好的错误提示

        提示词有三种形态，区分逻辑与「对话记忆」的注入方式直接相关：
            - prompt_core：Agent 主路径使用。**参考资料必须留在这里**——消息数组
              没有承载参考资料的通道；历史则由 execute_stream 的 history 参数作为
              真实多轮消息传入，因此不渲染进文本，避免同一段上下文进两遍。
            - prompt_full：两条降级路径使用。没有消息数组可用，
              历史与参考资料都只能渲染进文本。
            - prompt_simple：最后的兜底，保持极简，不带任何资料。

        这与上一轮做对话记忆时的处理**正好相反**：历史有 messages 通道所以要剥离，
        参考资料没有通道所以必须留在 prompt 里。

        错误处理：
            - 捕获所有异常，记录日志后继续尝试下一种方式
            - 所有方式失败时返回标准错误提示
        """
        # 参考资料装配（学情数据 + 历史批改片段 + 教研资料）。
        # 装配失败不阻断咨询：降级为"无资料回答"，而不是返回错误。
        context = None
        try:
            context = consult_context.build_context(question, owner, role=role, student_hint=student)
            logger.info(
                "[AI响应生成] 参考资料：范围=%s 学生=%s 批改片段=%s条",
                context.get('scope'), context.get('student') or '-', context.get('n_cases'),
            )
        except Exception as exc:
            logger.error(f"[AI响应生成] 参考资料装配失败，降级为无资料回答: {exc}")

        prompt_core = self._build_consultation_prompt(question, context=context)
        prompt_full = self._build_consultation_prompt(question, history, context=context)
        logger.info(
            f"[AI响应生成] 提示词长度: 主路径 {len(prompt_core)} / 含记忆 {len(prompt_full)}"
        )
        
        # 方式1：尝试使用ReactAgent（支持工具调用）
        try:
            response = ""
            chunk_count = 0
            logger.info("[AI响应生成] 尝试使用ReactAgent获取响应...")
            
            # 检查agent是否为None
            if self._agent is None:
                logger.warning("[AI响应生成] ReactAgent为None，跳过此方式")
            else:
                for chunk in self._agent.execute_stream(prompt_core, history):
                    chunk_count += 1
                    if chunk:
                        response += chunk
                        logger.debug(f"[AI响应生成] 收到第{chunk_count}个响应块，累计长度: {len(response)}")
            
            response = response.strip()
            
            if response:
                logger.info(f"[AI响应生成] ReactAgent响应成功，长度: {len(response)}")
                return response
            else:
                logger.warning("[AI响应生成] ReactAgent返回空响应，尝试备用方式")
                
        except Exception as e:
            logger.error(f"[AI响应生成] 使用ReactAgent失败: {str(e)}")
        
        # 方式2：尝试直接调用聊天模型（完整提示词）
        try:
            chat_model_instance = self.chat_model
            if chat_model_instance:
                logger.info("[AI响应生成] 尝试直接调用聊天模型...")
                model_response = chat_model_instance.invoke(prompt_full)
                content = model_response.content if hasattr(model_response, 'content') else str(model_response)
                
                if content and content.strip():
                    logger.info(f"[AI响应生成] 直接调用模型成功，长度: {len(content)}")
                    return content.strip()
                else:
                    logger.warning("[AI响应生成] 直接调用模型返回空响应")
            else:
                logger.warning("[AI响应生成] 聊天模型未初始化，跳过直接调用")
                
        except Exception as e:
            logger.error(f"[AI响应生成] 直接调用聊天模型失败: {str(e)}")
        
        # 方式3：尝试简化提示词（不使用复杂包装）
        try:
            chat_model_instance = self.chat_model
            if chat_model_instance:
                logger.info("[AI响应生成] 尝试使用简化提示词直接调用模型...")
                simple_prompt = f"作为初中语文老师，请回答问题：{question}"
                model_response = chat_model_instance.invoke(simple_prompt)
                content = model_response.content if hasattr(model_response, 'content') else str(model_response)
                
                if content and content.strip():
                    logger.info(f"[AI响应生成] 简化提示词调用成功，长度: {len(content)}")
                    return content.strip()
                    
        except Exception as e:
            logger.error(f"[AI响应生成] 简化提示词调用失败: {str(e)}")
        
        # 所有方式都失败，返回友好提示
        logger.error("[AI响应生成] 所有AI调用方式均失败")
        return "抱歉，我暂时无法回答这个问题，请稍后重试。"
    
    def _build_consultation_prompt(self, question: str, history=None, context: dict = None) -> str:
        """
        构建专业咨询提示词

        参数：
            question: 用户问题
            history:  本会话此前的对话轮次（仅在无消息数组的降级路径下渲染进文本）
            context:  consult_context.build_context() 的结果，
                      含学情数据、历史批改片段、教研资料

        返回：
            str: 完整的提示词字符串

        提示词设计原则：
            1. 明确角色定位，并按读者身份切换表述方式（学生 / 教师）
            2. 明确任务：针对问题提供专业回答
            3. 明确要求：语言简洁、提供例子、结合评分标准、鼓励语气
            4. 确保回答符合初中生认知水平
            5. **事实约束**：学情数字必须与系统统计一致，不得自行推算或编造出处。
               这是接入检索后新增的最重要一条——模型看到一堆数据后最危险的倾向
               就是"顺手算一下平均分"和"给这段评语编个来源"。
        """
        history_block = build_history_block(history)

        context_block = ''
        if context:
            rendered = consult_context.render_context_block(context)
            if rendered:
                context_block = f'{rendered}\n\n'

        scope = (context or {}).get('scope') or 'none'
        student = (context or {}).get('student') or ''
        if scope == 'student':
            # 老师问某个学生：读者是教师，表述要能直接用于教学
            persona = (
                f'你正在向一位初中语文老师汇报学生「{student}」的学情与写作指导建议。'
                '读者是教师，请给出可直接用于课堂或个别辅导的具体动作；'
                '不要用哄小孩的语气，也不要用"多读多写"这类没有操作性的套话。'
            )
        elif scope == 'self':
            persona = (
                '你正在为一位初中生解答他本人的作文问题。'
                '语气耐心鼓励，语言符合初中生认知水平。'
                f'提到他自己的情况时，只使用下方学情数据里的真实统计，'
                '既不夸大进步，也不打击信心。'
            )
        else:
            persona = '你正在为一位初中生或初中语文老师解答作文写作与教学问题。'

        prompt = f"""你是一位专业的初中语文作文辅导老师，擅长解答初中生在作文写作过程中遇到的各种问题，并熟悉广东省中考作文评分标准。

{persona}

{history_block}{context_block}请针对以下问题提供专业、详细且适合理解对象水平的回答：

问题：{question}

回答要求：
1. 使用简洁明了的语言，符合初中生的认知水平（若读者是教师，则按教师视角表述）
2. 提供具体的例子和可操作的步骤指导
3. 结合初中作文评分标准进行专业分析
4. 保持耐心和鼓励的语气，激发学生的写作兴趣
5. 如果涉及具体问题，请给出明确的解决方法
6. 避免使用过于专业的术语，必要时进行解释
7. 若上面的学情数据与历史批改片段与本次问题无关，忽略它们，不要强行引用
8. 涉及该学生的分数、篇数、维度得分率等事实时，必须与「学情数据」完全一致，
   不得自行推算、四舍五入或编造（例如不要自己计算平均分）
9. 引用历史批改片段时说明出自哪一篇（使用片段自带的日期与题目），不要编造出处
10. 若确实没有相关资料支撑，就基于通用教学常识回答，并说明这是通用建议

请开始回答："""

        return prompt
    
    def answer_question(self, question: str, history=None, owner: str = '',
                        role: str = 'auto', student: str = '') -> Dict[str, Any]:
        """
        回答用户咨询问题（核心入口方法）

        参数：
            question: 用户问题（字符串类型，至少1个字符）
            history:  本会话此前的对话轮次
            owner:    当前账号（数据隔离键，用于检索该账号下的批改记录）
            role:     'student' / 'teacher' / 'auto'，决定"我"能否解析为学生本人
            student:  显式指定的学生名（老师端选择学生时传入）

        返回：
            Dict[str, Any]: 包含回答内容和类型的字典
            结构：{
                'success': bool,      # 是否成功
                'type': str,          # 响应类型
                'content': str,       # 响应内容
                'raw_response': str   # 原始响应（可选）
            }
            type取值说明：
                - 'greeting': 问候语响应
                - 'knowledge': 知识库响应
                - 'ai': AI生成响应
                - 'error': 错误响应

        处理流程：
            1. 输入验证（类型检查、长度检查）
            2. 问候语检测与响应（优先级最高，保留原有功能）
            3. 知识库匹配与响应（**仅对通用问题**，见下）
            4. AI模型调用与响应（带学情数据与历史批改片段）

        关于第 3 步的适用条件（接入检索后新增）：
            预设知识库 `_essay_knowledge` 里只有通用评分标准与写作技巧。
            若提问针对某个具体的人（如"我记叙文标准掌握得怎么样"），
            命中知识库会把问题当成"标准是什么"来回答，完全答非所问，
            而且会绕过学情数据。因此**只在范围解析为"不涉及具体人"时才走知识库**，
            涉及具体人的提问一律走模型并带真实数据。
        """
        logger.info(f"[咨询服务] 收到咨询请求，内容长度: {len(question) if question else 0}")

        # 1. 输入验证：检查是否为有效字符串
        is_valid, cleaned_question, error_msg = self._validate_input(question)
        if not is_valid:
            logger.error(f"[咨询服务] 输入验证失败: {error_msg}")
            return {
                'success': False,
                'type': 'error',
                'content': error_msg
            }

        # 2. 尝试生成问候语响应（优先级最高，保留原有功能）
        greeting_response = self._generate_greeting_response(cleaned_question)
        if greeting_response:
            logger.info("[咨询服务] 返回问候语响应")
            return {
                'success': True,
                'type': 'greeting',
                'content': greeting_response
            }

        # 3. 范围解析：这条提问是否针对某个具体的人（本人 / 某位学生）
        scope_info = consult_context.resolve(cleaned_question, owner, role, student)
        personal = scope_info.get('scope') != 'none'
        if personal:
            logger.info("[咨询服务] 识别为个人学情提问（范围=%s 学生=%s），跳过预设知识库",
                        scope_info.get('scope'), scope_info.get('student'))

        # 4. 尝试从预设知识库获取回答（仅限通用问题，避免答非所问）
        if not personal:
            knowledge_response = self._get_knowledge_response(cleaned_question)
            if knowledge_response:
                logger.info("[咨询服务] 返回知识库响应")
                return {
                    'success': True,
                    'type': 'knowledge',
                    'content': knowledge_response
                }

        # 5. 使用AI模型生成回答（携带学情数据与历史批改片段）
        logger.info("[咨询服务] 使用AI模型生成回答")
        ai_response = self._generate_ai_response(cleaned_question, history,
                                                 owner=owner, role=role, student=student)

        return {
            'success': True,
            'type': 'ai',
            'content': ai_response
        }
    
    def is_ready(self) -> bool:
        """
        检查服务是否就绪
        
        返回：
            bool: True表示服务已就绪，False表示未就绪
            
        检查内容：
            - 检查全局模型是否已初始化
            - 检查ReactAgent是否就绪
        """
        is_model_ready = is_model_initialized()
        is_agent_ready = self._agent.is_ready(auto_init=False)
        
        logger.info(f"[服务状态] 模型状态: {is_model_ready}, Agent状态: {is_agent_ready}")
        return is_model_ready or is_agent_ready


# 创建全局服务实例
consultation_service = ConsultationService()


def answer_consultation(question: str, history=None, owner: str = '',
                        role: str = 'auto', student: str = '') -> Dict[str, Any]:
    """
    咨询服务便捷函数（对外暴露的接口）

    参数：
        question: 用户问题（字符串类型，至少1个字符）

        history:  可选，本会话此前的对话轮次
                  （[{'role': 'user'|'assistant', 'content': str}, ...]）。
                  调用方应先用 utils.chat_memory.normalize_history 裁剪，
                  本函数不再重复校验长度。传 None 时行为与改造前完全一致。

        owner:    当前账号（X-Username）。用于检索该账号名下的批改记录，
                  也是学情数据的数据隔离键。为空时不注入个人学情。

        role:     'student' / 'teacher' / 'auto'（默认 auto）。
                  决定提问中的"我"能否被解析为学生本人：
                  教师账号下有多名学生时，"我"不会指向任何学生。

        student:  可选，显式指定的学生名。老师端在界面上选定学生后传入，
                  此时不做自动识别，直接用该学生作为检索范围。

    返回：
        Dict[str, Any]: 回答结果，包含以下字段：
            - success: bool - 是否成功
            - type: str - 响应类型（greeting/knowledge/ai/error）
            - content: str - 响应内容文本

    调用示例：
        result = answer_consultation("你好，你是谁？")
        result = answer_consultation("李明的学情怎么样", owner="李老师", role="teacher")
    """
    return consultation_service.answer_question(question, history,
                                                owner=owner, role=role, student=student)