"""
评分工具模块

提供评分相关的工具函数，包括：
- 评分等级计算（高/中/低）
- 百分比计算
- 总分计算

设计原则：
1. 可复用：提供通用的评分计算逻辑
2. 可配置：支持自定义分数区间
3. 类型安全：确保输入输出类型正确
"""

from typing import Dict, Any, Optional


def calculate_percentage(score: float, max_score: float) -> float:
    """
    计算分数百分比
    
    参数：
        score: 当前分数
        max_score: 满分
        
    返回：
        float: 百分比（0-100）
        
    异常：
        ValueError: 当max_score为0时抛出
    """
    if max_score == 0:
        raise ValueError("满分不能为0")
    
    return (score / max_score) * 100


def get_score_level(score: float, max_score: float = None) -> str:
    """
    获取评分等级
    
    根据分数百分比返回等级：
    - high: 80%及以上
    - medium: 60%-79%
    - low: 低于60%
    
    参数：
        score: 当前分数，可以是数值或包含分数信息的字典
        max_score: 满分（可选，当score为数值时必须提供）
        
    返回：
        str: 等级（'high'、'medium'、'low'）
        
    示例：
        get_score_level(8, 10)  # 返回 'high'
        get_score_level(70)     # 返回 'high'（直接传入百分比）
        get_score_level({'score': 6, 'max_score': 10})  # 返回 'medium'
    """
    # 处理字典类型输入
    if isinstance(score, dict):
        if 'score' in score and 'max_score' in score:
            percentage = calculate_percentage(score['score'], score['max_score'])
        elif 'percentage' in score:
            percentage = score['percentage']
        else:
            raise ValueError("字典必须包含'score'和'max_score'键，或'percentage'键")
    elif max_score is not None:
        # 计算百分比
        percentage = calculate_percentage(score, max_score)
    else:
        # 假设直接传入百分比
        percentage = score
    
    # 判断等级
    if percentage >= 80:
        return 'high'
    elif percentage >= 60:
        return 'medium'
    else:
        return 'low'


def get_total_score_level(total_score: float, max_total_score: float = 50) -> str:
    """
    获取总分等级
    
    参数：
        total_score: 总分
        max_total_score: 满分（默认50分制）
        
    返回：
        str: 等级（'high'、'medium'、'low'）
    """
    return get_score_level(total_score, max_total_score)


def get_dimension_percent(dimension: Dict[str, Any]) -> float:
    """
    计算维度百分比
    
    参数：
        dimension: 维度字典，包含'score'和'max_score'
        
    返回：
        float: 百分比
    """
    if 'score' not in dimension or 'max_score' not in dimension:
        raise ValueError("维度字典必须包含'score'和'max_score'键")
    
    return calculate_percentage(dimension['score'], dimension['max_score'])


def format_score(score: float, max_score: float, show_percentage: bool = True) -> str:
    """
    格式化分数显示
    
    参数：
        score: 当前分数
        max_score: 满分
        show_percentage: 是否显示百分比
        
    返回：
        str: 格式化的分数字符串
        
    示例：
        format_score(8, 10)  # 返回 '8/10 (80%)'
        format_score(8, 10, False)  # 返回 '8/10'
    """
    result = f"{score}/{max_score}"
    
    if show_percentage:
        percentage = calculate_percentage(score, max_score)
        result += f" ({percentage:.1f}%)"
    
    return result


def get_level_color(level: str) -> str:
    """
    获取等级对应的颜色
    
    参数：
        level: 等级（'high'、'medium'、'low'）
        
    返回：
        str: 颜色名称或CSS类名
    """
    color_map = {
        'high': 'green',
        'medium': 'yellow',
        'low': 'red'
    }
    
    return color_map.get(level, 'gray')


def validate_score(score: float, max_score: float) -> bool:
    """
    验证分数是否有效
    
    参数：
        score: 当前分数
        max_score: 满分
        
    返回：
        bool: 是否有效
    """
    if max_score <= 0:
        return False
    
    if score < 0 or score > max_score:
        return False
    
    return True
