"""
RAG（检索增强生成）总结服务类
功能说明：
1. 用户提交作文内容，系统自动检测作文类型
2. 根据作文类型加载对应的评分标准
3. 如果没有评分标准文件，使用向量检索获取参考资料
4. 将作文内容、评分标准和参考资料一起提交给AI模型
5. AI模型根据这些信息生成结构化的作文批改结果
"""
from langchain_core.output_parsers import StrOutputParser
from rag.vector_store import VectorStoreService
from utils.prompt_loader import load_rag_prompts
from langchain_core.prompts import PromptTemplate
from model.factory import chat_model
from langchain_core.documents import Document
import os


def print_prompt(prompt):
    """
    打印提示词模板内容（用于调试）
    
    @param {PromptTemplate} prompt - LangChain提示词模板对象
    @returns {PromptTemplate} - 返回原始提示词对象
    """
    print("="*20)
    print(prompt.to_string())
    print("="*20)
    return prompt


def detect_essay_type(text):
    """
    智能检测作文类型
    根据文本内容特征判断作文类型：议论文、记叙文、说明文
    
    @param {string} text - 作文文本内容
    @returns {string} - 作文类型（议论文/记叙文/说明文）
    """
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
        '一般', '通常', '主要', '基本', '大约', '大约', '左右', '之间'
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
    
    @param {string} essay_type - 作文类型（议论文/记叙文/说明文）
    @returns {string} - 评分标准内容，如果文件不存在则返回空字符串
    """
    # 构建评分标准文件路径
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    file_path = os.path.join(data_dir, f'{essay_type}（初中）评分标准.txt')
    
    # 如果文件存在，读取并返回内容
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    else:
        # 文件不存在，返回空字符串
        return ""


class RagSummarizeService(object):
    """
    RAG总结服务类
    负责作文批改的核心逻辑，包括类型检测、评分标准加载、向量检索和AI批改生成
    """
    
    def __init__(self):
        """
        初始化RAG服务
        - 创建向量存储服务实例
        - 初始化检索器
        - 加载提示词模板
        - 创建AI模型链
        """
        # 初始化向量存储服务
        self.vector_store = VectorStoreService()
        self.retriever = self.vector_store.get_retriever()
        
        # 加载RAG提示词模板
        self.prompt_text = load_rag_prompts()
        self.prompt_template = PromptTemplate.from_template(self.prompt_text)
        
        # 初始化AI模型
        self.model = chat_model
        
        # 创建处理链：提示词 -> 打印（调试）-> 模型 -> 字符串解析器
        self.chain = self._init_chain()

    def _init_chain(self):
        """
        初始化LangChain处理链
        将提示词、模型和输出解析器串联起来
        
        @returns {Chain} - LangChain处理链对象
        """
        chain = self.prompt_template | print_prompt | self.model | StrOutputParser()
        return chain

    def retriever_docs(self, query: str) -> list[Document]:
        """
        使用向量检索器搜索相关文档
        
        @param {string} query - 查询文本（通常是作文内容）
        @returns {list[Document]} - 检索到的相关文档列表
        """
        return self.retriever.invoke(query)

    def filter_relevant_docs(self, docs: list[Document], query: str) -> list[Document]:
        """
        过滤检索到的文档，确保仅使用与用户作文相关的参考资料
        过滤规则：
        1. 过滤掉与作文内容无关的文档（相似度低于阈值）
        2. 过滤掉文档内容过短的条目
        3. 过滤掉可能是系统提示词或配置文件的内容
        
        @param {list[Document]} docs - 检索到的文档列表
        @param {string} query - 用户输入的作文内容
        @returns {list[Document]} - 过滤后的相关文档列表
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

    def rag_summarize(self, query: str) -> str:
        """
        执行RAG总结，生成作文批改结果
        执行流程：
        1. 检测作文类型
        2. 根据类型加载评分标准（优先使用）
        3. 如果没有评分标准，使用向量检索获取参考资料并过滤
        4. 构建上下文（评分标准 + 过滤后的参考资料）
        5. 调用AI模型生成批改结果
        
        @param {string} query - 用户输入的作文内容
        @returns {string} - AI生成的批改结果
        """
        # 步骤1：检测作文类型
        essay_type = detect_essay_type(query)
        
        # 步骤2：根据作文类型加载评分标准
        criteria = ""
        if essay_type:
            criteria = load_criteria_by_type(essay_type)
            print(f"[RAG服务] 检测到作文类型: {essay_type}")
            print(f"[RAG服务] 评分标准加载: {'成功' if criteria else '失败'}")
        
        # 步骤3：如果没有从文件加载到评分标准，使用向量检索并过滤
        context_docs = []
        if not criteria:
            raw_docs = self.retriever_docs(query)
            # 过滤无关文档，确保仅使用与用户作文相关的参考资料
            context_docs = self.filter_relevant_docs(raw_docs, query)

        # 步骤4：构建上下文
        context = ""
        
        # 添加评分标准到上下文（优先使用）
        if criteria:
            context += f"【评分标准】：{criteria}\n"
        
        # 添加过滤后的参考资料（最多3条）
        counter = 0
        for doc in context_docs[:3]:
            counter += 1
            # 仅提取文档内容，避免传入元数据中的非用户内容
            context += f"【参考资料{counter}】：{doc.page_content.strip()[:1000]}\n"

        # 如果没有任何上下文，使用默认提示
        if not context:
            context = "暂无参考资料，请根据专业知识进行批改。"

        # 步骤5：调用AI模型生成批改结果
        # 传入参数：input（作文内容）、context（评分标准和参考资料）
        return self.chain.invoke(
            {
                "input": query,
                "context": context,
            }
        )
