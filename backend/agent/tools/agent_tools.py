"""
咨询侧可调用的 agent 工具

工具设计原则（这条是踩过坑才写下来的）：
    注册给**咨询** agent 的工具，语义必须与"咨询"一致——返回可直接用于回答的
    资料片段。此前这里把 `rag_summarize` 注册进了 agent 的工具列表，而它的返回值
    是**整份批改 JSON**（总分、各项评分、批注坐标）。学生问"议论文的论点怎么写"时，
    agent 判断"该查资料"就会调用它，把一句提问当成一篇作文去批改，返回一份
    "总分 XX / 各项评分"的假批改结果——答非所问，而且每次白烧一次 30~60 秒的
    大模型调用（历史日志 logs/agent_*.log 里能看到这些实际发生的调用）。

因此：
    - `rag_summarize` 保留原样，但**只给 api.py 的旧批改入口显式调用**，
      不再注册给 agent。
    - `get_user_id`（返回 random.choice 的假 ID）已删除：它不提供任何真实信息，
      却可能被模型当成"学生的真实编号"写进回答里。
    - 新增 `search_knowledge`：真正与咨询意图一致的检索工具。
"""

from langchain_core.tools import tool

from rag import knowledge_loader
from rag.rag_service import RagSummarizeService

rag = RagSummarizeService()


@tool(description=(
    "检索教研知识库，返回与问题相关的写作方法、体裁要求、评分标准解读等资料片段。"
    "当需要引用具体的教学方法或标准条文、而系统提供的参考资料不足以回答时使用。"
    "返回内容是资料原文片段，不是批改结果。"
))
def search_knowledge(query: str) -> str:
    """
    教研知识库检索工具。

    @param {string} query - 要检索的问题或关键词（如"记叙文怎么选材"）
    @returns {string} - 检索到的资料片段；未命中时明确说明未检索到
    """
    query = (query or '').strip()
    if not query:
        return '查询内容为空，请提供要检索的问题。'
    return knowledge_loader.search_text(query)


@tool(description="基于学生作文内容与评分标准生成结构化批改结果，返回批改 JSON")
def rag_summarize(query: str, essay_type: str = None) -> str:
    """
    作文批改工具（**不属于咨询链路**）。

    注意：本工具返回的是完整体检式批改结果，不是检索片段。它只应由
    api.py 的旧批改入口按作文内容显式调用；注册给咨询 agent 会导致
    "把提问当作文批改"的错误行为，因此未列入 ReactAgent 的工具列表。

    @param {string} query - 待批改的作文内容
    @param {string} essay_type - 作文体裁（可选）
    @returns {string} - AI生成的作文批改结果
    """
    return rag.rag_summarize(query, essay_type)
