"""
安全配置管理模块
负责安全敏感配置（如API密钥）的统一管理
遵循安全最佳实践，确保密钥不在代码中硬编码
"""

import os
from typing import Optional


class SecurityConfig:
    """
    安全配置管理类
    负责从环境变量中读取敏感配置信息
    
    安全设计原则：
    1. 敏感配置仅从环境变量读取，不在代码或配置文件中硬编码
    2. 密钥仅在内存中临时存储，不写入日志或持久化存储
    3. 提供统一的配置获取接口，便于安全审计
    4. 实现优雅的错误处理，提供明确的配置指引
    """
    
    @staticmethod
    def get_dashscope_api_key() -> str:
        """
        获取Dashscope API密钥
        
        读取优先级：
        1. 系统环境变量 DASHSCOPE_API_KEY
        2. 如果环境变量不存在，抛出明确的错误提示
        
        返回：
            str: Dashscope API密钥
            
        异常：
            EnvironmentError: 当环境变量未配置时抛出，包含详细的配置指引
        """
        api_key = os.environ.get("DASHSCOPE_API_KEY")
        
        if not api_key or api_key.strip() == "":
            error_msg = (
                "配置错误：未找到DASHSCOPE_API_KEY环境变量\n\n"
                "请按照以下步骤配置API密钥：\n\n"
                "【Windows系统】\n"
                "方法1（临时生效，仅当前终端会话）：\n"
                "  set DASHSCOPE_API_KEY=your_api_key_here\n\n"
                "方法2（永久生效）：\n"
                "  1. 右键\"此电脑\" -> 属性 -> 高级系统设置 -> 环境变量\n"
                "  2. 在\"系统变量\"中点击\"新建\"\n"
                "  3. 变量名: DASHSCOPE_API_KEY\n"
                "  4. 变量值: 你的API密钥\n"
                "  5. 点击\"确定\"并重启终端\n\n"
                "【Linux/macOS系统】\n"
                "方法1（临时生效，仅当前终端会话）：\n"
                "  export DASHSCOPE_API_KEY=your_api_key_here\n\n"
                "方法2（永久生效）：\n"
                "  在 ~/.bashrc 或 ~/.zshrc 文件末尾添加：\n"
                "  export DASHSCOPE_API_KEY=your_api_key_here\n"
                "  然后执行: source ~/.bashrc 或 source ~/.zshrc\n\n"
                "【密钥格式要求】\n"
                "  - 长度：32个字符\n"
                "  - 类型：十六进制字符串（0-9, a-f）\n"
                "  - 示例格式：sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n\n"
                "【安全注意事项】\n"
                "  ⚠️ 请勿将API密钥提交到版本控制系统\n"
                "  ⚠️ 请勿在代码中硬编码密钥\n"
                "  ⚠️ 定期轮换API密钥以确保安全"
            )
            raise EnvironmentError(error_msg)
        
        return api_key.strip()
    
    @staticmethod
    def validate_api_key_format(api_key: str) -> bool:
        """
        验证API密钥格式是否正确
        
        Dashscope API密钥格式要求：
        - 必须以 'sk-' 前缀开头
        - 前缀后必须是32个字符
        - 必须是十六进制字符串（0-9, a-f, A-F）
        - 总长度：35个字符（'sk-' + 32个十六进制字符）
        
        参数：
            api_key: 待验证的API密钥
            
        返回：
            bool: 格式是否有效
        """
        # 检查长度和前缀
        if len(api_key) != 35 or not api_key.startswith('sk-'):
            return False
        
        # 提取密钥主体部分（去除 'sk-' 前缀）
        key_body = api_key[3:]
        
        try:
            # 尝试将字符串解析为十六进制
            int(key_body, 16)
            return True
        except ValueError:
            return False
    
    @staticmethod
    def get_dashscope_api_key_with_validation() -> str:
        """
        获取并验证Dashscope API密钥
        
        先获取密钥，然后验证格式是否正确
        如果格式不正确，抛出详细的错误提示
        
        返回：
            str: 验证通过的API密钥
            
        异常：
            EnvironmentError: 密钥未配置或格式不正确
        """
        api_key = SecurityConfig.get_dashscope_api_key()
        
        if not SecurityConfig.validate_api_key_format(api_key):
            error_msg = (
                f"配置错误：DASHSCOPE_API_KEY格式不正确\n\n"
                f"当前密钥：{api_key}\n\n"
                f"格式要求：\n"
                f"  - 长度必须为32个字符（当前长度：{len(api_key)}）\n"
                f"  - 必须是十六进制字符串（仅包含0-9, a-f, A-F）\n"
                f"  - 示例格式：sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n\n"
                f"请检查您的API密钥是否正确。"
            )
            raise EnvironmentError(error_msg)
        
        return api_key


# 模块级别函数，提供便捷访问接口
def get_dashscope_api_key() -> str:
    """
    获取Dashscope API密钥（便捷函数）
    
    调用SecurityConfig.get_dashscope_api_key()获取密钥
    确保API密钥从环境变量安全读取
    
    返回：
        str: Dashscope API密钥
    """
    return SecurityConfig.get_dashscope_api_key()


def get_dashscope_api_key_with_validation() -> str:
    """
    获取并验证Dashscope API密钥（便捷函数）
    
    返回：
        str: 验证通过的Dashscope API密钥
    """
    return SecurityConfig.get_dashscope_api_key_with_validation()
