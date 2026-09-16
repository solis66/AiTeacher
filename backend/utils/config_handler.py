"""
配置处理模块
负责加载和管理非敏感配置项

安全注意事项：
- 本模块仅处理非敏感配置（如模型名称、路径等）
- 敏感配置（如API密钥）通过专门的安全配置模块处理
- 敏感信息不应存储在YAML配置文件中
"""

import yaml
from utils.path_tool import get_abs_path


def load_rag_config(config_path: str = get_abs_path('config/rag.yaml'), encoding: str = 'utf-8') -> dict:
    """
    加载RAG相关配置
    
    参数：
        config_path: 配置文件路径，默认使用config/rag.yaml
        encoding: 文件编码，默认UTF-8
        
    返回：
        dict: RAG配置字典，包含模型名称等非敏感配置
        
    安全说明：
        此配置文件不应包含API密钥等敏感信息
        敏感信息应通过环境变量或安全配置模块管理
    """
    with open(config_path, 'r', encoding=encoding) as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
    
    # 安全检查：确保配置文件中不包含敏感信息
    sensitive_keys = ['api_key', 'api-key', 'dashscope_api_key', 'secret', 'password', 'key']
    for key in sensitive_keys:
        if key in config or any(k.lower() == key for k in config.keys()):
            import warnings
            warnings.warn(
                f"安全警告：配置文件中包含敏感配置项 '{key}'。"
                "建议将敏感信息移至环境变量中管理。"
            )
    
    return config


def load_chroma_config(config_path: str = get_abs_path('config/chroma.yaml'), encoding: str = 'utf-8') -> dict:
    """
    加载Chroma向量数据库配置
    
    参数：
        config_path: 配置文件路径，默认使用config/chroma.yaml
        encoding: 文件编码，默认UTF-8
        
    返回：
        dict: Chroma配置字典
    """
    with open(config_path, 'r', encoding=encoding) as f:
        return yaml.load(f, Loader=yaml.FullLoader)


def load_prompts_config(config_path: str = get_abs_path('config/prompts.yaml'), encoding: str = 'utf-8') -> dict:
    """
    加载提示词模板配置
    
    参数：
        config_path: 配置文件路径，默认使用config/prompts.yaml
        encoding: 文件编码，默认UTF-8
        
    返回：
        dict: 提示词配置字典
    """
    with open(config_path, 'r', encoding=encoding) as f:
        return yaml.load(f, Loader=yaml.FullLoader)


def load_agent_config(config_path: str = get_abs_path('config/agent.yaml'), encoding: str = 'utf-8') -> dict:
    """
    加载Agent配置
    
    参数：
        config_path: 配置文件路径，默认使用config/agent.yaml
        encoding: 文件编码，默认UTF-8
        
    返回：
        dict: Agent配置字典
    """
    with open(config_path, 'r', encoding=encoding) as f:
        return yaml.load(f, Loader=yaml.FullLoader)


# 全局配置实例
# 这些配置仅包含非敏感信息
rag_conf = load_rag_config()
chroma_conf = load_chroma_config()
prompts_conf = load_prompts_config()
agent_conf = load_agent_config()
