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

错误处理：
- 启动时验证API密钥配置
- 运行时检查模型有效性
- 提供统一的错误提示和诊断信息
"""

from abc import ABC, abstractmethod
from typing import Optional, Type, Dict, Any
from langchain_core.embeddings import Embeddings
from langchain_community.chat_models.tongyi import BaseChatModel
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.chat_models.tongyi import ChatTongyi
from utils.config_handler import rag_conf
from utils.security_config import get_dashscope_api_key, SecurityConfig


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
    5. 错误处理：完善的API密钥验证和模型状态检查
    """
    
    def __init__(self):
        """
        初始化工厂
        
        设置：
            _models: 模型缓存字典
            _api_key: API密钥（懒加载）
            _initialized: 标记是否已成功初始化
        """
        self._models: Dict[str, Any] = {}
        self._api_key: Optional[str] = None
        self._initialized: bool = False  # 新增：标记是否已成功初始化
    
    def _get_api_key(self) -> str:
        """
        获取API密钥（懒加载）
        
        返回：
            str: Dashscope API密钥
        
        异常：
            EnvironmentError: 当API密钥未配置时抛出，包含详细的配置指引
        """
        if not self._api_key:
            self._api_key = get_dashscope_api_key()
        return self._api_key
    
    def _validate_api_key(self) -> bool:
        """
        验证API密钥格式是否正确
        
        返回：
            bool: API密钥格式是否有效
        
        说明：
            调用SecurityConfig.validate_api_key_format()进行格式验证
            Dashscope API密钥要求：
            - 必须以 'sk-' 前缀开头
            - 前缀后必须是32个十六进制字符
            - 总长度：35个字符
        """
        api_key = self._get_api_key()
        return SecurityConfig.validate_api_key_format(api_key)
    
    def create_model(self, model_type: str) -> Optional[Embeddings | BaseChatModel]:
        """
        创建指定类型的模型实例
        
        参数：
            model_type: 模型类型，支持 'chat' 和 'embedding'
            
        返回：
            Optional[Embeddings | BaseChatModel]: 模型实例
            
        异常：
            ValueError: 当模型类型不支持时抛出
            EnvironmentError: 当API密钥未配置或格式不正确时抛出
        
        处理流程：
            1. 检查缓存，若已存在则直接返回
            2. 获取并验证API密钥
            3. 根据类型创建模型实例
            4. 缓存模型实例
            5. 标记初始化成功
        """
        # 检查缓存
        if model_type in self._models:
            return self._models[model_type]
        
        # 获取并验证API密钥
        api_key = self._get_api_key()
        
        # 验证API密钥格式
        if not self._validate_api_key():
            raise EnvironmentError(
                f"API密钥格式不正确: {api_key[:10]}...\n"
                "格式要求：必须以'sk-'开头，后跟32个十六进制字符，总长度35个字符"
            )
        
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
        try:
            model = model_class(model=model_name, dashscope_api_key=api_key)
            self._models[model_type] = model
            self._initialized = True  # 标记初始化成功
            print(f"[OK] 模型创建成功: {model_type} ({model_name})")
            return model
        except Exception as e:
            raise EnvironmentError(f"创建{model_type}模型失败: {str(e)}")
    
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
        
        说明：
            清除缓存后，下次调用get_chat_model()或get_embedding_model()
            将重新创建模型实例，可用于密钥更换后的模型重新初始化
        """
        self._models.clear()
        self._api_key = None
        self._initialized = False
    
    def is_initialized(self) -> bool:
        """
        检查模型是否已成功初始化
        
        返回：
            bool: True表示至少有一个模型已成功创建，False表示未初始化
            
        使用场景：
            在调用AI服务前检查模型状态，避免使用None模型导致错误
        """
        return self._initialized and 'chat' in self._models and self._models['chat'] is not None


# 创建全局工厂实例
_factory = UnifiedModelFactory()


def get_chat_model() -> BaseChatModel:
    """
    获取聊天模型（模块级便捷函数）
    
    返回：
        BaseChatModel: ChatTongyi模型实例
        
    异常：
        EnvironmentError: 当API密钥未配置或模型创建失败时抛出
    """
    return _factory.get_chat_model()


def get_embedding_model() -> Embeddings:
    """
    获取嵌入模型（模块级便捷函数）
    
    返回：
        Embeddings: DashScopeEmbeddings模型实例
        
    异常：
        EnvironmentError: 当API密钥未配置或模型创建失败时抛出
    """
    return _factory.get_embedding_model()


def is_model_initialized() -> bool:
    """
    检查模型是否已成功初始化（模块级便捷函数）
    
    返回：
        bool: True表示模型已成功初始化，False表示未初始化
        
    使用场景：
        在启动时检查配置是否完整，或在运行时检查服务状态
    """
    return _factory.is_initialized()


# 全局模型实例（保持向后兼容）
chat_model = None
embed_model = None

try:
    chat_model = get_chat_model()
    embed_model = get_embedding_model()
    print("[OK] AI模型初始化成功")
except EnvironmentError as e:
    # 如果密钥配置失败，记录错误并设置模型为None
    print(f"[ERR] 模型初始化失败: {str(e)}")
    print("[INFO] 提示：请配置环境变量 DASHSCOPE_API_KEY")