import random
from langchain_core.tools import tool
from rag.rag_service import RagSummarizeService

rag = RagSummarizeService()

user_id = ["1001", "1002", "1003", "1004", "1005", "1006", "1007", "1008", "1009", "1010"]

@tool(description="从向量存储中检索参考资料")
def rag_summarize(query: str) -> str:
    return rag.rag_summarize(query)

@tool(description="获取用户的ID, 以纯字符串形式返回")
def get_user_id() -> str:
    return random.choice(user_id)

# @tool(description="从外部系统中获取用户在指定月份的使用记录，以纯字符串形式返回，如果未检索")
# def fetch_external_data(user_id: str, month: str) -> str:
#     pass
#
# def generate_external_data(user_id: str, month: str) -> str:
#     pass




