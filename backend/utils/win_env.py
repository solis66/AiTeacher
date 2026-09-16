"""
Windows 环境变量兜底加载

背景：
    本项目依赖的外部凭据（DashScope / 阿里云 OCR）以“系统级环境变量”形式配置。
    正常启动（资源管理器、cmd、PowerShell 派生进程）会自动继承；
    但部分受限宿主不会继承，例如 IDE 内置终端、计划任务、Windows 服务、
    以及各类沙箱 shell。表现就是 os.getenv 取不到值，OCR / 模型调用错误地
    报出“尚未配置凭据”，把真实问题（未授权 / 未开通）掩盖掉。

行为：
    仅在 Windows、且目标变量在进程内缺失时，从注册表的
    Machine 与 User 两个作用域读取“持久化环境变量”补齐。
    已存在的进程内取值一律保留，不覆盖。
"""

import os
import sys

__all__ = ['load']

# 常见凭据变量：这些变量不会随 k=v 展开（REG_SZ / REG_EXPAND_SZ 都做一次展开）
_DEFAULT_NAMES = (
    'DASHSCOPE_API_KEY',
    'ALIBABA_CLOUD_ACCESS_KEY_ID',
    'ALIBABA_CLOUD_ACCESS_KEY_SECRET',
)


def _read_scope(names):
    """从注册表读取指定作用域的持久化环境变量，返回 {name: value}。"""
    import winreg

    scopes = [
        (winreg.HKEY_LOCAL_MACHINE,
         r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment'),
        (winreg.HKEY_CURRENT_USER, r'Environment'),
    ]
    registry_types = (winreg.REG_SZ, winreg.REG_EXPAND_SZ)
    if hasattr(winreg, 'REG_MULTI_SZ'):
        registry_types = registry_types + (winreg.REG_MULTI_SZ,)

    found = {}
    for hive, path in scopes:
        try:
            with winreg.OpenKey(hive, path) as key:
                for name in names:
                    if name in found:
                        continue
                    try:
                        value, kind = winreg.QueryValueEx(key, name)
                    except OSError:
                        continue
                    if kind not in registry_types:
                        continue
                    if isinstance(value, (list, tuple)):
                        value = ';'.join(str(item) for item in value)
                    value = str(value)
                    # REG_EXPAND_SZ 允许引用其它变量，展开一次以匹配启动器行为
                    expanded = os.path.expandvars(value)
                    if expanded != value and '%' not in expanded:
                        value = expanded
                    if value:
                        found[name] = value
        except OSError:
            # 无权限读取某个作用域时跳过，不影响另一作用域
            continue
    return found


def load(names=None):
    """
    补齐缺失的环境变量，返回本次实际补齐的变量名列表。

    参数：
        names: 需要确保存在的变量名集合，缺省为项目常用凭据变量
    """
    if not sys.platform.startswith('win'):
        return []

    targets = tuple(names) if names else _DEFAULT_NAMES
    missing = [name for name in targets if not os.getenv(name)]
    if not missing:
        return []

    try:
        found = _read_scope(missing)
    except ImportError:  # 非 Windows 或 winreg 不可用
        return []

    filled = []
    for name in missing:
        value = found.get(name)
        if value:
            os.environ[name] = value
            filled.append(name)
    return filled
