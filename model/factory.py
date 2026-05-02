from abc import ABC, abstractmethod
from typing import Optional
from langchain_core.embeddings import Embeddings
from langchain_community.chat_models.tongyi import BaseChatModel
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.chat_models.tongyi import ChatTongyi
from utils.config_handler import rag_conf

# 抽象模型类
class BaseModelFactory(ABC):
    @abstractmethod
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        pass

# 实现聊天模型
class ChatModelFactory(BaseModelFactory):
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        api_key = rag_conf.get("dashscope_api_key")
        if api_key and api_key != "your_api_key_here":
            return ChatTongyi(model=rag_conf["chat_model_name"], dashscope_api_key=api_key)
        else:
            # 如果没有配置API密钥，尝试使用环境变量
            import os
            env_api_key = os.environ.get("DASHSCOPE_API_KEY")
            if env_api_key:
                return ChatTongyi(model=rag_conf["chat_model_name"], dashscope_api_key=env_api_key)
            else:
                raise ValueError("请在config/rag.yaml中配置dashscope_api_key或设置环境变量DASHSCOPE_API_KEY")

# 实现文本模型
class EmbeddingFactory(BaseModelFactory):
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        api_key = rag_conf.get("dashscope_api_key")
        if api_key and api_key != "your_api_key_here":
            return DashScopeEmbeddings(model=rag_conf["embedding_model_name"], dashscope_api_key=api_key)
        else:
            import os
            env_api_key = os.environ.get("DASHSCOPE_API_KEY")
            if env_api_key:
                return DashScopeEmbeddings(model=rag_conf["embedding_model_name"], dashscope_api_key=env_api_key)
            else:
                raise ValueError("请在config/rag.yaml中配置dashscope_api_key或设置环境变量DASHSCOPE_API_KEY")

chat_model = ChatModelFactory().generator()
embed_model = EmbeddingFactory().generator()