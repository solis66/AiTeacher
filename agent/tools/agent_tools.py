import random
from langchain_core.tools import tool
from rag.rag_service import RagSummarizeService

rag = RagSummarizeService()

user_id = ["1001", "1002", "1003", "1004", "1005", "1006", "1007", "1008", "1009", "1010"]

@tool(description="从向量存储中检索参考资料，支持作文批改")
def rag_summarize(query: str, essay_type: str = None) -> str:
    """
    RAG检索工具函数
    根据用户输入的作文内容，结合评分标准和参考资料生成批改结果
    
    @param {string} query - 用户输入的作文内容
    @param {string} essay_type - 作文类型（可选，值为"议论文"/"记叙文"/"说明文"）
                               如果未提供或为空，将自动检测作文类型
    @returns {string} - AI生成的作文批改结果
    """
    return rag.rag_summarize(query, essay_type)

@tool(description="获取用户的ID, 以纯字符串形式返回")
def get_user_id() -> str:
    return random.choice(user_id)

# @tool(description="从外部系统中获取用户在指定月份的使用记录，以纯字符串形式返回，如果未检索")
# def fetch_external_data(user_id: str, month: str) -> str:
#     pass
#
# def generate_external_data(user_id: str, month: str) -> str:
#     pass




