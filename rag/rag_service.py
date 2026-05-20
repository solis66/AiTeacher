"""
RAG（检索增强生成）总结服务类
功能说明：
1. 用户提交作文内容，系统自动检测作文类型
2. 根据作文类型加载对应的评分标准
3. 如果没有评分标准文件，使用向量检索获取参考资料
4. 将作文内容、评分标准和参考资料一起提交给AI模型
5. AI模型根据这些信息生成结构化的作文批改结果

错误处理：
- 支持延迟初始化，在首次使用时检查模型状态
- 模型不可用时提供明确的错误提示
- 完善的日志记录便于问题排查
"""
from langchain_core.output_parsers import StrOutputParser
from rag.vector_store import VectorStoreService
from utils.prompt_loader import load_rag_prompts
from langchain_core.prompts import PromptTemplate
from model.factory import chat_model, get_chat_model, is_model_initialized
from langchain_core.documents import Document
from utils.error_handler import ServiceUnavailableError
import os


def print_prompt(prompt):
    """
    打印提示词模板内容（用于调试）
    
    参数：
        prompt: PromptTemplate - LangChain提示词模板对象
        
    返回：
        PromptTemplate - 返回原始提示词对象
        
    使用场景：
        在开发和调试阶段，打印完整的提示词内容以便检查
    """
    print("="*20)
    print(prompt.to_string())
    print("="*20)
    return prompt


def detect_essay_type(text):
    """
    智能检测作文类型
    根据文本内容特征判断作文类型：议论文、记叙文、说明文
    
    参数：
        text: string - 作文文本内容
        
    返回：
        string | None - 作文类型（议论文/记叙文/说明文），无法检测时返回None
        
    检测逻辑：
        1. 使用特征词加权计分（议论文权重3，记叙文权重2，说明文权重3）
        2. 明确类型声明权重最高（+30分）
        3. 低分情况下进行二次分析，检查人称代词、时间标记等特征
        4. 多类型得分相同时根据文本长度判断
    """
    if not text or not isinstance(text, str):
        return None
        
    # 初始化各类型得分
    scores = {'议论文': 0, '记叙文': 0, '说明文': 0}
    
    # 议论文特征词（论证相关词汇）
    argument_keywords = [
        '论点', '论据', '论证', '议论', '观点', '道理', '理由', '反驳',
        '认为', '表明', '因此', '所以', '然而', '但是', '总之',
        '一方面', '另一方面', '首先', '其次', '最后', '综上所述',
        '证明', '阐述', '分析', '批判', '主张', '支持', '反对',
        '应该', '必须', '不能', '需要', '只有', '只要', '才能',
        '因为', '由此可见', '不难看出', '显而易见', '事实上', '实际上'
    ]
    
    # 记叙文特征词（叙事相关词汇）
    narrative_keywords = [
        '我', '他', '她', '他们', '记得', '回忆', '那天', '当时', '忽然',
        '突然', '然后', '接着', '终于', '开始', '结束', '看见', '听到',
        '想到', '感到', '觉得', '高兴', '难过', '生气', '开心', '伤心',
        '时间', '地点', '人物', '事情', '故事', '经历', '经过', '结果',
        '描写', '叙述', '记叙', '讲述', '发生', '来到', '走进', '望着',
        '跑着', '笑着', '哭着', '说着', '想着', '那一刻', '这件事'
    ]
    
    # 说明文特征词（说明相关词汇）
    expository_keywords = [
        '说明', '介绍', '解释', '定义', '特征', '原理', '方法', '步骤',
        '结构', '功能', '用途', '种类', '分类', '比较', '对比', '举例',
        '数据', '实验', '研究', '分析', '表明', '显示', '发现', '结论',
        '由...组成', '包括', '分为', '具有', '作用', '原理是', '过程是',
        '是', '叫做', '指的是', '含有', '属于', '用于', '可以', '能够',
        '一般', '通常', '主要', '基本', '大约', '左右', '之间'
    ]
    
    # 统计特征词出现次数，并加权计算得分
    for kw in argument_keywords:
        count = text.count(kw)
        scores['议论文'] += count * 3 if count > 0 else 0
    
    for kw in narrative_keywords:
        count = text.count(kw)
        scores['记叙文'] += count * 2 if count > 0 else 0
    
    for kw in expository_keywords:
        count = text.count(kw)
        scores['说明文'] += count * 3 if count > 0 else 0
    
    # 检查是否有明确的类型声明（权重非常高）
    if '议论文' in text:
        scores['议论文'] += 30
    if '记叙文' in text:
        scores['记叙文'] += 30
    if '说明文' in text:
        scores['说明文'] += 30
    
    # 计算最高分和第二高分
    max_score = max(scores.values())
    second_max = sorted(scores.values(), reverse=True)[1]
    top_types = [essay_type for essay_type, score in scores.items() if score == max_score]
    
    # 如果得分差距不大，需要进一步判断
    score_diff = max_score - second_max
    
    # 如果得分都很低，进行二次分析
    if max_score < 8:
        # 检查记叙文特征
        has_first_person = any(pronoun in text for pronoun in ['我', '我们'])
        has_third_person = any(pronoun in text for pronoun in ['他', '她', '他们', '它'])
        has_time_markers = any(marker in text for marker in ['今天', '昨天', '那天', '曾经', '记得', '小时候'])
        
        # 检查议论文特征
        has_viewpoint = any(vp in text for vp in ['我认为', '我觉得', '应该', '必须', '不能'])
        has_reasoning = any(r in text for r in ['因为', '所以', '因此', '然而', '但是'])
        
        # 检查说明文特征
        has_explanation = any(e in text for e in ['说明', '介绍', '解释', '是', '叫做', '指的是'])
        has_definition = any(d in text for d in ['定义', '特征', '原理', '功能', '用途', '结构'])
        
        # 统计各类型特征数量
        story_features = sum([has_first_person, has_third_person, has_time_markers])
        arg_features = sum([has_viewpoint, has_reasoning])
        exp_features = sum([has_explanation, has_definition])
        
        # 根据特征数量判断类型
        if story_features >= 2:
            return '记叙文'
        elif arg_features >= 2:
            return '议论文'
        elif exp_features >= 2:
            return '说明文'
        elif has_first_person and has_time_markers:
            return '记叙文'
        elif has_viewpoint and has_reasoning:
            return '议论文'
        elif has_explanation and has_definition:
            return '说明文'
        elif max_score > 0:
            return top_types[0]
        else:
            return None
    
    # 如果只有一个类型得分最高，直接返回
    if len(top_types) == 1:
        return top_types[0]
    
    # 如果有多个类型得分相同且差距很小，根据其他特征判断
    if len(top_types) >= 2 and score_diff < 5:
        if len(text) > 300:
            if scores['议论文'] >= scores['说明文']:
                return '议论文'
            else:
                return '说明文'
        else:
            return '记叙文'
    
    return top_types[0]


def load_criteria_by_type(essay_type):
    """
    根据作文类型加载相应的评分标准
    
    参数：
        essay_type: string - 作文类型（议论文/记叙文/说明文）
        
    返回：
        string - 评分标准内容，如果文件不存在则返回空字符串
        
    文件路径：
        data/{essay_type}（初中）评分标准.txt
    """
    # 构建评分标准文件路径
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    file_path = os.path.join(data_dir, f'{essay_type}（初中）评分标准.txt')
    
    # 如果文件存在，读取并返回内容
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"[评分标准加载] 读取文件失败: {str(e)}")
            return ""
    else:
        # 文件不存在，返回空字符串
        return ""


def extract_dimensions_from_criteria(criteria_text):
    """
    从评分标准文本中提取评分维度信息
    
    参数：
        criteria_text: string - 评分标准文本内容
        
    返回：
        string - 维度JSON Schema字符串，用于提示词模板
        
    支持的评分标准格式：
        1. 记叙文格式："一、立意与中心（10分，权重20%）"
        2. 议论文格式："- 立意与中心：10分  (权重20%)"
        3. 说明文格式：类似上述两种格式
        
    提取逻辑：
        1. 首先尝试匹配带中文数字序号的格式（如"一、"）
        2. 如果第一种格式没有匹配结果，尝试匹配带短横线的格式（如"- "）
        3. 如果都没有匹配，返回默认维度值
    """
    if not criteria_text:
        print("[维度提取] 评分标准为空，返回默认维度")
        return '{"维度1": "分值", "维度2": "分值", "维度3": "分值", "维度4": "分值", "维度5": "分值", "维度6": "分值"}'
    
    import re
    
    # 定义多种评分维度格式的正则表达式模式
    # 模式1：匹配中文数字序号格式（如"一、立意与中心（10分，权重20%）"）
    pattern1 = r'[一二三四五六七八九十]+、(.+?)（(\d+)分'
    # 模式2：匹配短横线格式（如"- 立意与中心：10分  (权重20%)"）
    pattern2 = r'-\s*([^：:]+?)[：:]\s*(\d+)分'
    
    # 尝试第一种模式（中文数字序号格式）
    matches = re.findall(pattern1, criteria_text)
    
    if not matches:
        # 如果第一种模式没有匹配，尝试第二种模式（短横线格式）
        print("[维度提取] 模式1未匹配，尝试模式2")
        matches = re.findall(pattern2, criteria_text)
    
    if matches:
        dimensions = {}
        for match in matches:
            dimension_name = match[0].strip()
            dimension_score = match[1].strip()
            dimensions[dimension_name] = f"{dimension_score}分"
        
        import json
        result = json.dumps(dimensions, ensure_ascii=False)
        print(f"[维度提取] 成功提取 {len(dimensions)} 个维度: {result}")
        return result
    else:
        # 如果无法提取维度，返回默认值
        print("[维度提取] 未找到匹配的评分维度格式，返回默认维度")
        return '{"维度1": "分值", "维度2": "分值", "维度3": "分值", "维度4": "分值", "维度5": "分值", "维度6": "分值"}'


class RagSummarizeService(object):
    """
    RAG总结服务类
    负责作文批改的核心逻辑，包括类型检测、评分标准加载、向量检索和AI批改生成
    
    功能特性：
        1. 支持延迟初始化，在首次使用时检查模型状态
        2. 模型不可用时提供明确的错误提示
        3. 完善的日志记录便于问题排查
        4. 支持自动检测和用户指定作文类型
    """
    
    def __init__(self):
        """
        初始化RAG服务
        
        设置：
            vector_store: 向量存储服务实例
            retriever: 检索器
            prompt_text: 提示词模板内容
            prompt_template: PromptTemplate对象
            model: AI聊天模型（延迟初始化）
            chain: LangChain处理链（延迟初始化）
        """
        # 初始化向量存储服务
        self.vector_store = VectorStoreService()
        self.retriever = self.vector_store.get_retriever()
        
        # 加载RAG提示词模板
        self.prompt_text = load_rag_prompts()
        self.prompt_template = PromptTemplate.from_template(self.prompt_text)
        
        # 延迟初始化AI模型和处理链
        self._model = None
        self._chain = None
    
    def _get_valid_model(self):
        """
        获取有效的AI模型，检查模型是否为None
        
        返回：
            BaseChatModel | None - 有效的模型实例或None
            
        处理流程：
            1. 检查全局chat_model是否有效
            2. 如果无效，尝试重新初始化
            3. 返回模型实例或None
        """
        global chat_model
        
        # 如果全局模型已有效，直接返回
        if chat_model is not None:
            return chat_model
        
        print("[RAG服务] 警告：chat_model为None，尝试重新初始化")
        try:
            chat_model = get_chat_model()
            print("[RAG服务] 模型重新初始化成功")
            return chat_model
        except Exception as e:
            print(f"[RAG服务] 模型重新初始化失败: {str(e)}")
            return None
    
    def _ensure_model_ready(self):
        """
        确保模型已准备好，如果未初始化则尝试初始化
        
        异常：
            ServiceUnavailableError - 当模型无法初始化时抛出
        """
        if self._model is None:
            self._model = self._get_valid_model()
            
        if self._model is None:
            raise ServiceUnavailableError("AI模型服务不可用，请检查API密钥配置")
    
    def _init_chain(self):
        """
        初始化LangChain处理链
        将提示词、模型和输出解析器串联起来
        
        返回：
            Chain - LangChain处理链对象
            
        处理流程：
            prompt_template -> print_prompt（调试）-> model -> StrOutputParser
        """
        self._ensure_model_ready()
        chain = self.prompt_template | print_prompt | self._model | StrOutputParser()
        return chain
    
    def _ensure_chain_ready(self):
        """
        确保处理链已准备好，如果未初始化则创建
        
        异常：
            ServiceUnavailableError - 当模型无法初始化时抛出
        """
        if self._chain is None:
            self._chain = self._init_chain()
    
    def retriever_docs(self, query: str) -> list[Document]:
        """
        使用向量检索器搜索相关文档
        
        参数：
            query: string - 查询文本（通常是作文内容）
            
        返回：
            list[Document] - 检索到的相关文档列表
        """
        return self.retriever.invoke(query)

    def filter_relevant_docs(self, docs: list[Document], query: str) -> list[Document]:
        """
        过滤检索到的文档，确保仅使用与用户作文相关的参考资料
        
        过滤规则：
            1. 过滤掉空文档或内容过短（<50字符）的条目
            2. 过滤掉可能是系统提示词或配置文件的内容
            3. 过滤掉不包含作文相关关键词的文档
            4. 检查文档与用户输入的词重叠率
            
        参数：
            docs: list[Document] - 检索到的文档列表
            query: string - 用户输入的作文内容
            
        返回：
            list[Document] - 过滤后的相关文档列表
        """
        filtered_docs = []
        
        for doc in docs:
            # 跳过空文档或内容过短的文档
            if not doc.page_content or len(doc.page_content.strip()) < 50:
                continue
            
            # 跳过可能是系统配置或提示词模板的文档
            content = doc.page_content.lower()
            if any(keyword in content for keyword in ['prompt', 'template', '系统提示', '指令', '请你']):
                continue
            
            # 跳过与作文体裁不相关的文档（检查是否包含作文相关词汇）
            essay_keywords = ['作文', '评分', '写作', '文章', '记叙文', '议论文', '说明文']
            has_essay_keyword = any(keyword in content for keyword in essay_keywords)
            if not has_essay_keyword:
                continue
            
            # 检查文档是否与用户输入内容有一定相关性
            # 计算简单的词重叠率
            query_words = set(query[:500].replace('，', '').replace('。', '').replace('\n', '')[:100])
            doc_words = set(content[:500].replace('，', '').replace('。', '').replace('\n', '')[:100])
            overlap = len(query_words & doc_words)
            
            # 如果没有任何词重叠且内容不包含作文相关关键词，跳过
            if overlap == 0 and not has_essay_keyword:
                continue
            
            filtered_docs.append(doc)
        
        print(f"[RAG服务] 文档过滤：原始 {len(docs)} 条，过滤后 {len(filtered_docs)} 条")
        return filtered_docs

    def rag_summarize(self, query: str, essay_type: str = None) -> str:
        """
        执行RAG总结，生成作文批改结果
        
        执行流程：
            1. 确保模型和处理链已准备好
            2. 获取作文类型（优先使用用户指定的类型，否则自动检测）
            3. 根据类型加载评分标准
            4. 如果没有评分标准，使用向量检索获取参考资料并过滤
            5. 构建上下文（评分标准 + 过滤后的参考资料）
            6. 从评分标准中提取维度信息
            7. 调用AI模型生成批改结果
            
        参数：
            query: string - 用户输入的作文内容
            essay_type: string - 用户选择的作文类型（可选）
                              值为"议论文"/"记叙文"/"说明文"，未提供时自动检测
            
        返回：
            string - AI生成的批改结果
            
        异常：
            ServiceUnavailableError - 当AI服务不可用时抛出
            ValueError - 当用户指定的体裁与自动检测结果不一致时抛出
        """
        # 确保模型和处理链已准备好
        self._ensure_chain_ready()
        
        try:
            # 步骤1：获取作文类型
            # 优先使用用户指定的体裁，否则自动检测
            detected_type = detect_essay_type(query)
            
            if essay_type and essay_type.strip():
                # 使用用户指定的体裁
                final_type = essay_type.strip()
                print(f"[RAG服务] 使用用户选择的体裁: {final_type}")
                
                # 如果用户指定了体裁且自动检测结果不同，记录警告日志
                if detected_type and detected_type != final_type:
                    print(f"[RAG服务] 警告：用户选择的体裁({final_type})与自动检测结果({detected_type})不一致")
            else:
                # 使用自动检测的体裁
                final_type = detected_type if detected_type else "记叙文"
                print(f"[RAG服务] 自动检测到作文类型: {final_type}")
            
            # 步骤2：根据作文类型加载评分标准
            criteria = load_criteria_by_type(final_type)
            print(f"[RAG服务] 评分标准加载: {'成功' if criteria else '失败'}")
            
            # 步骤3：如果没有从文件加载到评分标准，使用向量检索并过滤
            context_docs = []
            if not criteria:
                raw_docs = self.retriever_docs(query)
                # 过滤无关文档，确保仅使用与用户作文相关的参考资料
                context_docs = self.filter_relevant_docs(raw_docs, query)

            # 步骤4：构建上下文（评分标准 + 参考资料）
            scoring_criteria = ""
            
            # 添加评分标准到上下文（优先使用）
            if criteria:
                scoring_criteria = criteria
            elif context_docs:
                # 如果没有评分标准文件，使用检索到的参考资料
                counter = 0
                for doc in context_docs[:3]:
                    counter += 1
                    scoring_criteria += f"【参考资料{counter}】：{doc.page_content.strip()[:1000]}\n"
            else:
                # 如果没有任何参考资料，使用默认提示
                scoring_criteria = "暂无参考资料，请根据专业知识进行批改。"

            # 步骤5：从评分标准中提取维度信息
            dimension_json_schema = extract_dimensions_from_criteria(criteria)
            print(f"[RAG服务] 提取的评分维度: {dimension_json_schema}")

            # 步骤6：调用AI模型生成批改结果
            # 传入参数：essay_content, essay_type, scoring_criteria, dimension_json_schema
            result = self._chain.invoke(
                {
                    "essay_content": query,
                    "essay_type": final_type,
                    "scoring_criteria": scoring_criteria,
                    "dimension_json_schema": dimension_json_schema,
                }
            )
            
            # 检查返回结果是否为空
            if not result or not result.strip():
                print("[RAG服务] 警告：AI返回内容为空")
                return "抱歉，AI服务暂时无法提供批改结果，请稍后重试。"
            
            return result
            
        except ValueError as e:
            # 捕获值错误并重新抛出
            print(f"[RAG服务] 参数错误: {str(e)}")
            raise
        except ServiceUnavailableError as e:
            # 捕获服务不可用错误并重新抛出
            print(f"[RAG服务] 服务不可用: {str(e)}")
            raise
        except Exception as e:
            print(f"[RAG服务] 生成作文批改失败: {str(e)}")
            import traceback
            print(traceback.format_exc())
            raise ServiceUnavailableError("AI服务暂时不可用，请稍后重试")