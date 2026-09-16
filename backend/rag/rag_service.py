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
from utils.essay_constants import DIMENSION_MAX_SCORES, UNIFIED_MAX_SCORES
from utils.standard_loader import STANDARD_NAME, load_unified_standard
import json
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
        essay_type: string - 作文类型（议论文/记叙文/说明文，保留参数以兼容调用方）

    返回：
        string - 评分标准内容

    说明（自 2026-09 起）：
        所有作文体裁统一以《广东省中考作文评分标准.doc》为默认评分依据，
        不再使用各体裁独立的 TXT 评分标准文件。
    """
    try:
        return load_unified_standard()
    except Exception as e:
        print(f"[评分标准加载] 读取失败: {str(e)}")
        return ""


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

        说明（本次修正）：
            改为走 `search_with_scores`，即**在检索阶段就用相似度阈值过滤**。
            此前用 `as_retriever().invoke()`，该方法不返回相似度分数，
            导致后面只能靠"字符重叠率"这种无效启发式去判断相关性（见
            filter_relevant_docs 的说明）。有了真实分数就不需要那些补丁。
        """
        try:
            return [doc for doc, _score in self.vector_store.search_with_scores(query)]
        except Exception as e:
            print(f"[RAG服务] 向量检索失败: {str(e)}")
            return []

    # 真正的提示词模板特征：占位符。
    # 此前用 '不过'、'请你' 这类日常词做黑名单，会把"请你分析下面的病句"
    # 这样的正常教学例句整条丢掉——黑名单必须针对模板的结构特征，而不是常用词。
    _TEMPLATE_MARKERS = ('{essay_content}', '{scoring_criteria}', '{essay_type}',
                         '{dimension_json_schema}')
    _MIN_DOC_CHARS = 50

    def filter_relevant_docs(self, docs: list[Document], query: str) -> list[Document]:
        """
        对检索结果做结构性清洗（相关性已由检索阶段的分数阈值保证）。

        过滤规则：
            1. 丢弃空内容或过短（<50字符）的片段——多半是标题行、页码残留
            2. 丢弃含提示词占位符的片段——这类内容属于模板而不是教学资料
            3. 按内容去重——同一段落可能因切片重叠而重复出现

        参数：
            docs: list[Document] - 检索到的文档列表
            query: string - 用户输入的作文内容（保留参数以兼容调用方）

        返回：
            list[Document] - 清洗后的文档列表
        """
        filtered = []
        seen = set()
        for doc in docs:
            content = (doc.page_content or '').strip()
            if len(content) < self._MIN_DOC_CHARS:
                continue
            if any(marker in content for marker in self._TEMPLATE_MARKERS):
                continue
            fingerprint = content[:200]
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            filtered.append(doc)

        print(f"[RAG服务] 文档清洗：原始 {len(docs)} 条，清洗后 {len(filtered)} 条")
        return filtered

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
                # 统一评分标准（所有体裁共用）作为辅助参考依据
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

            # 步骤5：构建维度 JSON schema（统一维度配置，所有体裁共用）
            dimension_json_schema = json.dumps(UNIFIED_MAX_SCORES, ensure_ascii=False)
            print(f"[RAG服务] 使用的评分维度: {dimension_json_schema}")

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