"""
模型工厂模块 - 优化版
负责创建和管理AI模型实例，采用单例模式和泛型工厂方法消除代码重复

设计模式：
- 单例模式：确保每个模型类型只创建一个实例
- 泛型工厂方法：通过参数化实现不同模型的统一创建逻辑
- 懒加载：仅在首次使用时创建实例，节省资源

安全设计：
- API密钥通过环境变量获取，不在代码中硬编码
- 使用统一的安全配置模块管理敏感信息
- 密钥仅在内存中临时使用，不进行持久化存储
"""

from abc import ABC, abstractmethod
from typing import Optional, Type, Dict, Any
from langchain_core.embeddings import Embeddings
from langchain_community.chat_models.tongyi import BaseChatModel
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.chat_models.tongyi import ChatTongyi
from utils.config_handler import rag_conf
from utils.security_config import get_dashscope_api_key


class BaseModelFactory(ABC):
    """
    模型工厂抽象基类
    定义模型生成器的统一接口
    """
    
    @abstractmethod
    def generator(self) -> Optional[Embeddings | BaseChatModel]:
        """
        生成模型实例
        
        返回：
            Optional[Embeddings | BaseChatModel]: 模型实例或None
        """
        pass


class SingletonMeta(type):
    """
    单例元类
    确保每个类只创建一个实例
    """
    
    _instances: Dict[Type, Any] = {}
    
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class UnifiedModelFactory(metaclass=SingletonMeta):
    """
    统一模型工厂类
    使用泛型方法创建不同类型的模型实例，消除代码重复
    
    功能特性：
    1. 单例模式：确保全局只有一个工厂实例
    2. 懒加载：模型实例仅在首次使用时创建
    3. 缓存机制：已创建的模型实例被缓存，避免重复初始化
    4. 统一接口：通过模型类型参数创建不同模型
    """
    
    def __init__(self):
        """
        初始化工厂
        """
        self._models: Dict[str, Any] = {}
        self._api_key: Optional[str] = None
    
    def _get_api_key(self) -> str:
        """
        获取API密钥（懒加载）
        
        返回：
            str: Dashscope API密钥
        """
        if not self._api_key:
            self._api_key = get_dashscope_api_key()
        return self._api_key
    
    def create_model(self, model_type: str) -> Optional[Embeddings | BaseChatModel]:
        """
        创建指定类型的模型实例
        
        参数：
            model_type: 模型类型，支持 'chat' 和 'embedding'
            
        返回：
            Optional[Embeddings | BaseChatModel]: 模型实例
            
        异常：
            ValueError: 当模型类型不支持时抛出
            EnvironmentError: 当API密钥未配置时抛出
        """
        # 检查缓存
        if model_type in self._models:
            return self._models[model_type]
        
        # 获取API密钥
        api_key = self._get_api_key()
        
        # 根据类型创建模型
        model_config = {
            'chat': {
                'class': ChatTongyi,
                'config_key': 'chat_model_name'
            },
            'embedding': {
                'class': DashScopeEmbeddings,
                'config_key': 'embedding_model_name'
            }
        }
        
        if model_type not in model_config:
            raise ValueError(f"不支持的模型类型: {model_type}")
        
        config = model_config[model_type]
        model_class = config['class']
        model_name = rag_conf[config['config_key']]
        
        # 创建并缓存模型实例
        model = model_class(model=model_name, dashscope_api_key=api_key)
        self._models[model_type] = model
        
        return model
    
    def get_chat_model(self) -> BaseChatModel:
        """
        获取聊天模型实例（便捷方法）
        
        返回：
            BaseChatModel: ChatTongyi模型实例
        """
        return self.create_model('chat')
    
    def get_embedding_model(self) -> Embeddings:
        """
        获取嵌入模型实例（便捷方法）
        
        返回：
            Embeddings: DashScopeEmbeddings模型实例
        """
        return self.create_model('embedding')
    
    def clear_cache(self):
        """
        清除模型缓存
        用于模型重新加载或密钥更换场景
        """
        self._models.clear()
        self._api_key = None


# 创建全局工厂实例
_factory = UnifiedModelFactory()


def get_chat_model() -> BaseChatModel:
    """
    获取聊天模型（模块级便捷函数）
    
    返回：
        BaseChatModel: ChatTongyi模型实例
    """
    return _factory.get_chat_model()


def get_embedding_model() -> Embeddings:
    """
    获取嵌入模型（模块级便捷函数）
    
    返回：
        Embeddings: DashScopeEmbeddings模型实例
    """
    return _factory.get_embedding_model()


# 全局模型实例（保持向后兼容）
try:
    chat_model = get_chat_model()
    embed_model = get_embedding_model()
except EnvironmentError as e:
    # 如果密钥配置失败，记录错误并设置模型为None
    print(f"模型初始化失败: {str(e)}")
    chat_model = None
    embed_model = None
