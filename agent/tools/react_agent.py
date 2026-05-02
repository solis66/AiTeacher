from langchain.agents import create_agent
from model.factory import chat_model
from utils.prompt_loader import load_system_prompts
from agent.tools.agent_tools import rag_summarize, get_user_id
from agent.tools.middleware import monitor_tool, log_before_model

class ReactAgent:
    """
    AI对话代理类
    负责与AI模型交互，处理用户消息并返回流式响应
    """
    def __init__(self):
        self.agent = create_agent(
            model=chat_model,
            system_prompt=load_system_prompts(),
            tools=[rag_summarize, get_user_id],
            middleware=[monitor_tool, log_before_model],
        )

    def execute_stream(self, query: str):
        """
        流式执行查询，返回AI生成的增量内容
        @param {string} query - 用户输入的查询内容
        @yield {string} - AI生成的增量内容块
        """
        input_dict = {
            "messages": [
                {"role": "user", "content": query},
            ]
        }

        previous_content = ""
        for chunk in self.agent.stream(input_dict, stream_mode="messages"):
            # 方式0：chunk是元组，第一个元素是AIMessage
            if isinstance(chunk, tuple) and len(chunk) > 0:
                chunk = chunk[0]
            
            # 尝试多种方式获取内容
            new_content = ""
            
            # 方式1：chunk是字典
            if isinstance(chunk, dict):
                if "content" in chunk:
                    new_content = chunk["content"]
                elif "message" in chunk and isinstance(chunk["message"], dict):
                    new_content = chunk["message"].get("content", "")
            # 方式2：chunk是对象，有content属性
            elif hasattr(chunk, "content"):
                new_content = chunk.content
            # 方式3：chunk是BaseMessage对象
            elif hasattr(chunk, "dict"):
                chunk_dict = chunk.dict()
                new_content = chunk_dict.get("content", "")
            
            # 如果获取到内容且与之前不同，则yield增量
            if new_content and new_content != previous_content:
                # 计算增量（只返回新增的部分）
                delta = new_content[len(previous_content):]
                if delta:
                    yield delta
                previous_content = new_content

    def execute(self, query: str) -> str:
        """
        非流式执行查询，返回完整响应
        @param {string} query - 用户输入的查询内容
        @return {string} - AI生成的完整响应
        """
        response = ""
        for chunk in self.execute_stream(query):
            response += chunk
        return response