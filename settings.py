"""
配置管理模块

负责统一加载和管理项目中的所有配置项，包括：
- YAML配置文件加载
- 环境变量读取
- 默认值管理
- 配置验证

设计原则：
- 集中管理：所有配置通过此模块访问
- 分层加载：环境变量 > 配置文件 > 默认值
- 类型安全：确保配置值类型正确
- 敏感信息：敏感配置通过环境变量管理
"""

import os
import yaml
from typing import Optional, Dict, Any
from utils.error_handler import ConfigurationError
import logging

# 配置日志
logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_CONFIG = {
    # 应用配置
    'app': {
        'debug': False,
        'host': '0.0.0.0',
        'port': 5000,
        'secret_key': 'your-secret-key-here'
    },
    
    # RAG配置
    'rag': {
        'chat_model_name': 'qwen-plus',
        'embedding_model_name': 'text-embedding-v1',
        'prompt_path': 'prompts/rag_summarize.txt',
        'chunk_size': 500,
        'chunk_overlap': 50,
        'top_k': 3
    },
    
    # API配置
    'api': {
        'timeout': 120,
        'max_content_length': 10 * 1024 * 1024  # 10MB
    },
    
    # 缓存配置
    'cache': {
        'enabled': True,
        'ttl': 3600,  # 1小时
        'max_size': 1000
    }
}


class Settings:
    """
    配置管理类
    
    提供统一的配置访问接口，支持：
    - 从YAML文件加载配置
    - 从环境变量覆盖配置
    - 类型安全的配置访问
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """
        初始化配置
        """
        if self._initialized:
            return
        
        self._config = DEFAULT_CONFIG.copy()
        self._load_from_file()
        self._load_from_env()
        self._validate_config()
        
        self._initialized = True
    
    def _load_from_file(self):
        """
        从YAML配置文件加载配置
        """
        config_files = [
            'config/config.yaml',
            'config/config.local.yaml',
            'config.yaml',
            'config.local.yaml'
        ]
        
        for config_file in config_files:
            if os.path.exists(config_file):
                try:
                    with open(config_file, 'r', encoding='utf-8') as f:
                        file_config = yaml.safe_load(f)
                        if file_config:
                            self._deep_merge(self._config, file_config)
                            logger.info(f"已加载配置文件: {config_file}")
                except Exception as e:
                    logger.warning(f"加载配置文件失败 {config_file}: {str(e)}")
    
    def _load_from_env(self):
        """
        从环境变量加载配置
        
        环境变量格式：APP_DEBUG, RAG_CHAT_MODEL_NAME, API_TIMEOUT等
        使用下划线分隔层级
        """
        env_mappings = {
            # 应用配置
            'APP_DEBUG': ('app', 'debug', bool),
            'APP_HOST': ('app', 'host', str),
            'APP_PORT': ('app', 'port', int),
            'APP_SECRET_KEY': ('app', 'secret_key', str),
            
            # RAG配置
            'RAG_CHAT_MODEL_NAME': ('rag', 'chat_model_name', str),
            'RAG_EMBEDDING_MODEL_NAME': ('rag', 'embedding_model_name', str),
            'RAG_PROMPT_PATH': ('rag', 'prompt_path', str),
            'RAG_CHUNK_SIZE': ('rag', 'chunk_size', int),
            'RAG_CHUNK_OVERLAP': ('rag', 'chunk_overlap', int),
            'RAG_TOP_K': ('rag', 'top_k', int),
            
            # API配置
            'API_TIMEOUT': ('api', 'timeout', int),
            'API_MAX_CONTENT_LENGTH': ('api', 'max_content_length', int),
            
            # 缓存配置
            'CACHE_ENABLED': ('cache', 'enabled', bool),
            'CACHE_TTL': ('cache', 'ttl', int),
            'CACHE_MAX_SIZE': ('cache', 'max_size', int)
        }
        
        for env_key, (section, key, type_converter) in env_mappings.items():
            env_value = os.environ.get(env_key)
            if env_value is not None:
                try:
                    # 转换类型
                    if type_converter == bool:
                        value = env_value.lower() in ('true', '1', 'yes')
                    else:
                        value = type_converter(env_value)
                    
                    # 设置配置
                    if section not in self._config:
                        self._config[section] = {}
                    self._config[section][key] = value
                    
                    logger.debug(f"环境变量覆盖配置: {env_key} = {value}")
                except ValueError:
                    logger.warning(f"环境变量 {env_key} 转换失败: {env_value}")
    
    def _validate_config(self):
        """
        验证配置的有效性
        """
        # 验证端口范围
        port = self._config['app']['port']
        if not (1 <= port <= 65535):
            raise ConfigurationError(f"无效的端口号: {port}，必须在1-65535范围内")
        
        # 验证缓存配置
        if self._config['cache']['ttl'] < 0:
            raise ConfigurationError("缓存TTL不能为负数")
        
        if self._config['cache']['max_size'] < 0:
            raise ConfigurationError("缓存最大容量不能为负数")
        
        logger.info("配置验证通过")
    
    def _deep_merge(self, base: Dict, update: Dict):
        """
        深度合并字典
        
        参数：
            base: 基础字典
            update: 更新字典
        """
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
    
    def get(self, path: str, default: Any = None) -> Any:
        """
        获取配置值
        
        参数：
            path: 配置路径，使用点分隔，如 'app.debug'
            default: 默认值
            
        返回：
            Any: 配置值
        """
        keys = path.split('.')
        value = self._config
        
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
    
    def get_app_config(self) -> Dict[str, Any]:
        """
        获取应用配置
        
        返回：
            Dict: 应用配置字典
        """
        return self._config.get('app', {})
    
    def get_rag_config(self) -> Dict[str, Any]:
        """
        获取RAG配置
        
        返回：
            Dict: RAG配置字典
        """
        return self._config.get('rag', {})
    
    def get_api_config(self) -> Dict[str, Any]:
        """
        获取API配置
        
        返回：
            Dict: API配置字典
        """
        return self._config.get('api', {})
    
    def get_cache_config(self) -> Dict[str, Any]:
        """
        获取缓存配置
        
        返回：
            Dict: 缓存配置字典
        """
        return self._config.get('cache', {})
    
    def __getitem__(self, key: str) -> Any:
        """
        通过索引访问配置
        
        参数：
            key: 配置键
            
        返回：
            Any: 配置值
        """
        return self._config.get(key)
    
    def __contains__(self, key: str) -> bool:
        """
        检查配置是否存在
        
        参数：
            key: 配置键
            
        返回：
            bool: 是否存在
        """
        return key in self._config


# 创建全局配置实例
settings = Settings()


def get_settings() -> Settings:
    """
    获取配置实例（便捷函数）
    
    返回：
        Settings: 配置实例
    """
    return settings


# 为了保持向后兼容，提供旧的配置访问方式
def get_rag_config() -> Dict[str, Any]:
    """
    获取RAG配置（向后兼容）
    
    返回：
        Dict: RAG配置字典
    """
    return settings.get_rag_config()
