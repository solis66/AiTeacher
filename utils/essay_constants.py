"""
作文评分常量配置模块

集中管理作文批改相关的常量配置，避免重复定义。

包含：
- 各体裁的评分维度映射
- 各维度的满分值配置
- 体裁特征词配置
- 评分等级阈值配置
"""

from typing import Dict, List, Tuple

# 各体裁的评分维度映射
# 维度顺序按照评分标准文件中的权重从高到低排列
DIMENSION_MAP: Dict[str, List[str]] = {
    '议论文': ['立意与中心', '论点与论证', '结构与层次', '语言表达', '例证与材料运用'],
    '记叙文': ['立意与中心', '选材与内容', '结构与层次', '语言表达', '细节与表现', '书写与规范'],
    '说明文': ['立意与中心', '结构与层次', '语言表达', '方法与技巧', '书写与规范']
}

# 各体裁的维度满分值映射
# 注意：所有体裁的维度满分之和必须等于 TOTAL_SCORE (50分)
# 各维度权重根据评分标准文件制定：
# 议论文：立意与中心(20%) + 论点与论证(36%) + 结构与层次(16%) + 语言表达(20%) + 例证与材料运用(8%) = 100%
# 记叙文：立意与中心(20%) + 选材与内容(30%) + 结构与层次(16%) + 语言表达(20%) + 细节与表现(10%) + 书写与规范(4%) = 100%
# 说明文：立意与中心(34%) + 结构与层次(34%) + 语言表达(26%) + 方法与技巧(4%) + 书写与规范(2%) = 100%
DIMENSION_MAX_SCORES: Dict[str, Dict[str, int]] = {
    '议论文': {
        '立意与中心': 10,
        '论点与论证': 18,
        '结构与层次': 8,
        '语言表达': 10,
        '例证与材料运用': 4
    },
    '记叙文': {
        '立意与中心': 10,
        '选材与内容': 15,
        '结构与层次': 8,
        '语言表达': 10,
        '细节与表现': 5,
        '书写与规范': 2
    },
    '说明文': {
        '立意与中心': 17,
        '结构与层次': 17,
        '语言表达': 13,
        '方法与技巧': 2,
        '书写与规范': 1
    }
}

# 体裁特征词（用于自动检测）
TYPE_FEATURES: Dict[str, List[str]] = {
    '议论文': ['论点', '论证', '论据', '观点', '反驳', '证明', '认为', '因此', '所以', '然而', '但是',
              '一方面', '另一方面', '首先', '其次', '最后', '综上所述', '理由', '道理'],
    '记叙文': ['记得', '回忆', '那天', '时候', '突然', '忽然', '然后', '接着', '终于', '开始', '结束',
              '看见', '听到', '想到', '感到', '觉得', '我', '他', '她', '他们', '故事', '经历', '经过'],
    '说明文': ['介绍', '说明', '原理', '方法', '步骤', '特点', '功能', '结构', '作用', '定义',
              '分类', '比较', '对比', '举例', '数据', '分析', '发现', '结论', '例如', '比如']
}

# 评分等级阈值
SCORE_LEVELS: Dict[str, Tuple[int, int]] = {
    'high': (80, 100),    # 高分段：80%-100%
    'medium': (60, 79),   # 中等分数：60%-79%
    'low': (0, 59)        # 低分段：0%-59%
}

# 支持的体裁列表
SUPPORTED_TYPES: List[Dict[str, str]] = [
    {'value': '议论文', 'label': '议论文', 'icon': '💬', 'description': '以议论为主，表达观点和论证'},
    {'value': '记叙文', 'label': '记叙文', 'icon': '📖', 'description': '以叙述为主，讲述故事和经历'},
    {'value': '说明文', 'label': '说明文', 'icon': '📝', 'description': '以说明为主，解释事物和原理'}
]

# 总分满分值
TOTAL_SCORE: int = 50

# 作文内容长度限制
MIN_CONTENT_LENGTH: int = 10
MAX_CONTENT_LENGTH: int = 10000


def get_dimensions(essay_type: str) -> List[str]:
    """
    获取指定体裁的评分维度列表
    
    参数：
        essay_type: 作文体裁
        
    返回：
        List[str]: 维度名称列表
    """
    return DIMENSION_MAP.get(essay_type, DIMENSION_MAP['记叙文'])


def get_dimension_max_score(dimension_name: str, essay_type: str) -> int:
    """
    获取指定维度的满分值
    
    参数：
        dimension_name: 维度名称
        essay_type: 作文体裁
        
    返回：
        int: 满分值
    """
    return DIMENSION_MAX_SCORES.get(essay_type, {}).get(dimension_name, 10)


def get_total_max_score(essay_type: str) -> int:
    """
    获取总分满分值
    
    参数：
        essay_type: 作文体裁
        
    返回：
        int: 总分满分值
    """
    return sum(DIMENSION_MAX_SCORES.get(essay_type, {}).values()) or TOTAL_SCORE


def get_score_level(percentage: float) -> str:
    """
    根据百分比获取评分等级
    
    参数：
        percentage: 分数百分比（0-100）
        
    返回：
        str: 等级（high/medium/low）
    """
    if percentage >= SCORE_LEVELS['high'][0]:
        return 'high'
    elif percentage >= SCORE_LEVELS['medium'][0]:
        return 'medium'
    else:
        return 'low'


def validate_dimension_scores(essay_type: str, dimension_scores: Dict[str, int]) -> bool:
    """
    校验各维度评分是否符合评分标准
    
    参数：
        essay_type: 作文体裁
        dimension_scores: 各维度评分字典
        
    返回：
        bool: 是否校验通过
    """
    max_scores = DIMENSION_MAX_SCORES.get(essay_type, {})
    
    for dim_name, score in dimension_scores.items():
        # 检查维度是否存在
        if dim_name not in max_scores:
            print(f"[维度校验] 未知维度: {dim_name}")
            return False
        
        # 检查分数是否在有效范围内
        max_score = max_scores[dim_name]
        if score < 0 or score > max_score:
            print(f"[维度校验] 维度 {dim_name} 分数 {score} 超出范围 [0, {max_score}]")
            return False
    
    return True


def calculate_total_score(essay_type: str, dimension_scores: Dict[str, int]) -> int:
    """
    根据各维度评分计算总分
    
    参数：
        essay_type: 作文体裁
        dimension_scores: 各维度评分字典
        
    返回：
        int: 总分
    """
    if not validate_dimension_scores(essay_type, dimension_scores):
        return 0
    
    return sum(dimension_scores.values())


def get_dimension_weight(essay_type: str, dimension_name: str) -> float:
    """
    获取指定维度的权重比例（0-1）
    
    参数：
        essay_type: 作文体裁
        dimension_name: 维度名称
        
    返回：
        float: 权重比例
    """
    max_scores = DIMENSION_MAX_SCORES.get(essay_type, {})
    
    if dimension_name not in max_scores:
        return 0.0
    
    total = sum(max_scores.values())
    if total == 0:
        return 0.0
    
    return max_scores[dimension_name] / total
