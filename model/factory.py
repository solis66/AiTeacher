"""
模型工厂模块 - 兼容模式版

负责创建和管理AI模型实例，采用单例模式和统一工厂方法消除代码重复。

【本次修改说明（重要）】
问题：原实现使用 langchain_community 的 ChatTongyi / DashScopeEmbeddings（底层为
      dashscope 原生 SDK）。本机安装的 dashscope 版本为 1.25.13，其内部按模型名前缀
      推断请求 URL，遇到较新的模型名（如 qwen3.8-max-0902）会直接报
      `InvalidParameter: url error, please check url`，导致批改链路完全不可用。
      实测：qwen3.8-max-0902 确实存在于账号可用模型列表中，是 SDK 版本问题，不是模型名问题。
方案：改用阿里云百炼（DashScope）提供的 **OpenAI 兼容模式** 端点
      https://dashscope.aliyuncs.com/compatible-mode/v1
      该端点对模型名不做前缀推断，实测 qwen3.8-max-0902 与 qwen3.7-text-embedding 均可正常调用。
      依赖 langchain_openai 已随项目环境安装，无需新增第三方包。

设计模式：
- 单例模式：确保每种模型只创建一个实例
- 懒加载：仅在首次使用时创建实例，节省资源
- 统一接口：通过模型类型参数创建不同模型

安全设计：
- API密钥通过环境变量获取，不在代码中硬编码
- 密钥仅在内存中临时使用，不进行持久化存储
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Type

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from utils.config_handler import rag_conf
from utils.security_config import get_dashscope_api_key, SecurityConfig

# 阿里云百炼 OpenAI 兼容模式端点（可在 config/rag.yaml 中用 base_url 覆盖）
DEFAULT_DASHSCOPE_BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1'


class BaseModelFactory(ABC):
    """模型工厂抽象基类：定义模型生成器的统一接口。"""

    @abstractmethod
    def generator(self) -> Optional[Any]:
        """生成模型实例。"""
        pass


class SingletonMeta(type):
    """单例元类：确保每个类只创建一个实例。"""

    _instances: Dict[Type, Any] = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class UnifiedModelFactory(metaclass=SingletonMeta):
    """
    统一模型工厂类

    功能特性：
    1. 单例模式：确保全局只有一个工厂实例
    2. 懒加载：模型实例仅在首次使用时创建
    3. 缓存机制：已创建的模型实例被缓存，避免重复初始化
    4. 统一接口：通过模型类型参数创建不同模型
    5. 错误处理：完善的API密钥验证和模型状态检查
    """

    def __init__(self):
        self._models: Dict[str, Any] = {}
        self._api_key: Optional[str] = None
        self._initialized: bool = False

    def _get_api_key(self) -> str:
        """获取API密钥（懒加载）。未配置时抛出带指引的 EnvironmentError。"""
        if not self._api_key:
            self._api_key = get_dashscope_api_key()
        return self._api_key

    def _validate_api_key(self) -> bool:
        """验证API密钥格式（sk- 前缀 + 32位十六进制，共35字符）。"""
        return SecurityConfig.validate_api_key_format(self._get_api_key())

    def create_model(self, model_type: str):
        """
        创建指定类型的模型实例

        参数：
            model_type: 模型类型，支持 'chat' 和 'embedding'

        返回：
            模型实例（BaseChatModel 或 Embeddings）

        处理流程：
            1. 命中缓存直接返回
            2. 获取并校验 API 密钥
            3. 走百炼 OpenAI 兼容模式创建实例
            4. 缓存并标记初始化成功
        """
        # 1. 缓存命中
        if model_type in self._models:
            return self._models[model_type]

        # 2. 密钥校验
        api_key = self._get_api_key()
        if not self._validate_api_key():
            raise EnvironmentError(
                f"API密钥格式不正确: {api_key[:10]}...\n"
                "格式要求：必须以'sk-'开头，后跟32个十六进制字符，总长度35个字符"
            )

        # 3. 读取模型名与端点（base_url 允许在 config/rag.yaml 覆盖）
        base_url = rag_conf.get('base_url') or DEFAULT_DASHSCOPE_BASE_URL
        model_config = {
            'chat': ('chat_model_name', '模型'),
            'embedding': ('embedding_model_name', '向量模型'),
        }
        if model_type not in model_config:
            raise ValueError(f"不支持的模型类型: {model_type}")

        config_key, label = model_config[model_type]
        model_name = rag_conf[config_key]

        # 4. 创建并缓存实例
        try:
            if model_type == 'chat':
                # 思考模式：qwen3.8-max 默认开启，token 先流进 reasoning 通道，
                # content 长时间为空，实测批改请求会直接超时。批改要的是稳定的
                # 结构化输出，不是推理过程，因此默认关闭（见 config/rag.yaml）。
                enable_thinking = bool(rag_conf.get('enable_thinking', False))
                timeout = int(rag_conf.get('chat_timeout') or 300)
                max_retries = int(rag_conf.get('chat_max_retries') if rag_conf.get('chat_max_retries') is not None else 1)
                model = ChatOpenAI(
                    model=model_name,
                    api_key=api_key,
                    base_url=base_url,
                    temperature=0.3,      # 批改场景需要稳定输出，温度取低值
                    max_retries=max_retries,
                    timeout=timeout,
                    extra_body={'enable_thinking': enable_thinking},
                )
                print(f"[OK] 思考模式: {'开启' if enable_thinking else '关闭'}, 超时 {timeout}s")
            else:
                model = OpenAIEmbeddings(
                    model=model_name,
                    api_key=api_key,
                    base_url=base_url,
                    check_embedding_ctx_length=False,  # 百炼兼容端点不支持按 token 切分，关闭以免报错
                )

            self._models[model_type] = model
            self._initialized = True
            print(f"[OK] 模型创建成功: {label} {model_name} @ 兼容模式")
            return model
        except Exception as e:
            raise EnvironmentError(f"创建{model_type}模型失败: {str(e)}")

    def get_chat_model(self) -> BaseChatModel:
        """获取聊天模型实例（便捷方法）。"""
        return self.create_model('chat')

    def get_embedding_model(self) -> Embeddings:
        """获取嵌入模型实例（便捷方法）。"""
        return self.create_model('embedding')

    def clear_cache(self):
        """清除模型缓存（用于密钥更换或模型切换后重新初始化）。"""
        self._models.clear()
        self._api_key = None
        self._initialized = False

    def is_initialized(self) -> bool:
        """检查聊天模型是否已成功初始化。"""
        return self._initialized and 'chat' in self._models and self._models['chat'] is not None


# 创建全局工厂实例
_factory = UnifiedModelFactory()


def get_chat_model() -> BaseChatModel:
    """获取聊天模型（模块级便捷函数）。"""
    return _factory.get_chat_model()


def get_embedding_model() -> Embeddings:
    """获取嵌入模型（模块级便捷函数）。"""
    return _factory.get_embedding_model()


def is_model_initialized() -> bool:
    """检查模型是否已成功初始化（模块级便捷函数）。"""
    return _factory.is_initialized()


# 全局模型实例（保持向后兼容，供 api.py 直接导入）
chat_model = None
embed_model = None

try:
    chat_model = get_chat_model()
    embed_model = get_embedding_model()
    print("[OK] AI模型初始化成功")
except EnvironmentError as e:
    # 密钥缺失或网络异常时不让整个应用崩溃，仅降级为 None，由健康检查接口暴露问题
    print(f"[ERR] 模型初始化失败: {str(e)}")
    print("[INFO] 提示：请配置环境变量 DASHSCOPE_API_KEY")
except Exception as e:
    print(f"[ERR] 模型初始化出现未预期错误: {str(e)}")
