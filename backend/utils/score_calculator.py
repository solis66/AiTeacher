"""
作文评分计算模块

提供评分计算、校验、转换等核心功能，确保各项评分与总分的逻辑一致性。

核心功能：
- 总分自动计算（由各项评分汇总生成）
- 评分维度校验
- 分数区间转换
- 四舍五入规则处理
- 评分标准一致性验证
"""

from typing import Dict, List, Tuple, Optional
from .essay_constants import (
    DIMENSION_MAP, DIMENSION_MAX_SCORES, TOTAL_SCORE,
    get_dimensions, get_dimension_max_score, validate_dimension_scores
)


class ScoreCalculator:
    """
    评分计算器类
    
    负责评分计算、校验和转换，确保各项评分与总分的逻辑一致性。
    """
    
    def __init__(self, essay_type: str):
        """
        初始化评分计算器
        
        参数：
            essay_type: 作文体裁（议论文/记叙文/说明文）
        """
        self.essay_type = essay_type
        self.dimensions = get_dimensions(essay_type)
        self.max_scores = DIMENSION_MAX_SCORES.get(essay_type, {})
        self.total_max_score = sum(self.max_scores.values()) if self.max_scores else TOTAL_SCORE
    
    def calculate_total(self, dimension_scores: Dict[str, int], auto_fix: bool = True) -> int:
        """
        根据各维度评分计算总分
        
        参数：
            dimension_scores: 各维度评分字典，key为维度名称，value为分数
            auto_fix: 是否自动修正超出范围的分数（默认True）
            
        返回：
            int: 总分（各项评分之和）
        """
        # 如果需要自动修正，先对分数进行归一化处理
        if auto_fix:
            dimension_scores = self.normalize_dimension_scores(dimension_scores)
        
        # 计算总分（各项评分之和）
        total = sum(dimension_scores.values())
        
        # 确保总分在有效范围内
        return max(0, min(total, self.total_max_score))
    
    def validate_total_consistency(self, dimension_scores: Dict[str, int], reported_total: int) -> bool:
        """
        校验报告的总分与计算总分是否一致
        
        参数：
            dimension_scores: 各维度评分字典
            reported_total: 报告的总分
            
        返回：
            bool: 是否一致（允许±1的误差）
        """
        calculated_total = self.calculate_total(dimension_scores)
        difference = abs(reported_total - calculated_total)
        
        return difference <= 1
    
    def fix_total_score(self, dimension_scores: Dict[str, int], reported_total: Optional[int] = None) -> Tuple[int, bool]:
        """
        修正总分使其与各项评分之和一致
        
        参数：
            dimension_scores: 各维度评分字典
            reported_total: 报告的总分（可选）
            
        返回：
            Tuple[int, bool]: (修正后的总分, 是否进行了修正)
        """
        # 使用自动修正功能计算总分
        calculated_total = self.calculate_total(dimension_scores, auto_fix=True)
        
        if reported_total is None:
            # 如果没有报告总分，直接使用计算值
            return calculated_total, False
        
        # 检查是否需要修正
        if abs(reported_total - calculated_total) > 1:
            # 差异超过1分，进行修正
            print(f"[总分修正] 体裁: {self.essay_type}, 报告总分: {reported_total}, 计算总分: {calculated_total}, 已修正")
            return calculated_total, True
        
        return reported_total, False
    
    def convert_to_percentage(self, dimension_scores: Dict[str, int]) -> Dict[str, float]:
        """
        将各维度分数转换为百分比
        
        参数：
            dimension_scores: 各维度评分字典
            
        返回：
            Dict[str, float]: 各维度百分比字典（保留两位小数）
        """
        percentages = {}
        
        for dim_name, score in dimension_scores.items():
            max_score = self.max_scores.get(dim_name, 10)
            if max_score == 0:
                percentage = 0.0
            else:
                percentage = round((score / max_score) * 100, 2)
            percentages[dim_name] = percentage
        
        return percentages
    
    def round_score(self, score: float, method: str = 'banker') -> int:
        """
        分数四舍五入
        
        参数：
            score: 待四舍五入的分数
            method: 四舍五入方法
                - 'banker': 银行家舍入法（四舍六入五取偶）
                - 'standard': 标准四舍五入
                
        返回：
            int: 四舍五入后的整数分数
        """
        if method == 'banker':
            # 银行家舍入法：四舍六入五取偶
            integer_part = int(score)
            decimal_part = score - integer_part
            
            if decimal_part < 0.5:
                return integer_part
            elif decimal_part > 0.5:
                return integer_part + 1
            else:
                # 0.5的情况，取偶数
                return integer_part if integer_part % 2 == 0 else integer_part + 1
        else:
            # 标准四舍五入
            return int(round(score))
    
    def distribute_score_to_dimensions(self, total_score: int) -> Dict[str, int]:
        """
        将总分按权重分配到各维度
        
        参数：
            total_score: 总分
            
        返回：
            Dict[str, int]: 各维度评分字典
        """
        # 计算各维度权重
        weights = {}
        total_max = sum(self.max_scores.values())
        
        for dim_name in self.dimensions:
            max_score = self.max_scores.get(dim_name, 10)
            weights[dim_name] = max_score / total_max if total_max > 0 else 0.0
        
        # 按权重分配分数
        dimension_scores = {}
        remaining = total_score
        
        for i, dim_name in enumerate(self.dimensions):
            if i == len(self.dimensions) - 1:
                # 最后一个维度取剩余值
                dimension_scores[dim_name] = max(0, remaining)
            else:
                # 按权重分配
                score = self.round_score(total_score * weights[dim_name])
                score = min(score, remaining)
                dimension_scores[dim_name] = max(0, score)
                remaining -= score
        
        return dimension_scores
    
    def normalize_dimension_scores(self, dimension_scores: Dict[str, int]) -> Dict[str, int]:
        """
        归一化维度评分，确保每个维度的分数在有效范围内
        
        参数：
            dimension_scores: 各维度评分字典
            
        返回：
            Dict[str, int]: 归一化后的维度评分字典
        """
        normalized = {}
        
        for dim_name, score in dimension_scores.items():
            max_score = self.max_scores.get(dim_name, 10)
            # 确保分数在[0, max_score]范围内
            normalized[dim_name] = max(0, min(score, max_score))
        
        return normalized
    
    def validate_dimension_completeness(self, dimension_scores: Dict[str, int]) -> bool:
        """
        校验维度评分是否完整（所有必需维度都有评分）
        
        参数：
            dimension_scores: 各维度评分字典
            
        返回：
            bool: 是否完整
        """
        for dim_name in self.dimensions:
            if dim_name not in dimension_scores:
                print(f"[维度完整性校验] 缺少维度: {dim_name}")
                return False
        
        return True
    
    def generate_score_report(self, dimension_scores: Dict[str, int], reported_total: Optional[int] = None) -> Dict:
        """
        生成完整的评分报告
        
        参数：
            dimension_scores: 各维度评分字典
            reported_total: 报告的总分（可选）
            
        返回：
            Dict: 包含总分、各维度评分、百分比、校验状态等信息的报告
        """
        # 归一化维度评分
        normalized_scores = self.normalize_dimension_scores(dimension_scores)
        
        # 计算总分
        calculated_total = self.calculate_total(normalized_scores)
        
        # 检查是否需要修正
        if reported_total is not None:
            fixed_total, was_fixed = self.fix_total_score(normalized_scores, reported_total)
        else:
            fixed_total, was_fixed = calculated_total, False
        
        # 计算各维度百分比
        percentages = self.convert_to_percentage(normalized_scores)
        
        # 构建报告
        report = {
            'essay_type': self.essay_type,
            'total_score': fixed_total,
            'total_max_score': self.total_max_score,
            'was_fixed': was_fixed,
            'original_total': reported_total,
            'calculated_total': calculated_total,
            'dimensions': [],
            'validation': {
                'is_complete': self.validate_dimension_completeness(dimension_scores),
                'is_consistent': self.validate_total_consistency(normalized_scores, fixed_total),
                'total_max_matches': self.total_max_score == TOTAL_SCORE
            }
        }
        
        # 添加各维度详细信息
        for dim_name in self.dimensions:
            score = normalized_scores.get(dim_name, 0)
            max_score = self.max_scores.get(dim_name, 0)
            percentage = percentages.get(dim_name, 0.0)
            
            report['dimensions'].append({
                'name': dim_name,
                'score': score,
                'max_score': max_score,
                'percentage': percentage,
                'weight': round((max_score / self.total_max_score) * 100, 1) if self.total_max_score > 0 else 0.0
            })
        
        return report


def calculate_score(dimension_scores: Dict[str, int], essay_type: str, reported_total: Optional[int] = None) -> Dict:
    """
    评分计算入口函数
    
    参数：
        dimension_scores: 各维度评分字典
        essay_type: 作文体裁
        reported_total: 报告的总分（可选）
        
    返回：
        Dict: 评分报告
    """
    calculator = ScoreCalculator(essay_type)
    return calculator.generate_score_report(dimension_scores, reported_total)


def validate_score_consistency(essay_type: str, dimension_scores: Dict[str, int], total_score: int) -> bool:
    """
    校验评分一致性的便捷函数
    
    参数：
        essay_type: 作文体裁
        dimension_scores: 各维度评分字典
        total_score: 总分
        
    返回：
        bool: 是否一致
    """
    calculator = ScoreCalculator(essay_type)
    return calculator.validate_total_consistency(dimension_scores, total_score)


def fix_score_if_needed(essay_type: str, dimension_scores: Dict[str, int], reported_total: int) -> int:
    """
    如果需要则修正总分的便捷函数
    
    参数：
        essay_type: 作文体裁
        dimension_scores: 各维度评分字典
        reported_total: 报告的总分
        
    返回：
        int: 修正后的总分
    """
    calculator = ScoreCalculator(essay_type)
    fixed_total, _ = calculator.fix_total_score(dimension_scores, reported_total)
    return fixed_total


def validate_all_criteria() -> List[Dict[str, bool]]:
    """
    验证所有评分标准配置的一致性
    
    返回：
        List[Dict]: 各体裁的校验结果列表
    """
    results = []
    
    for essay_type in ['议论文', '记叙文', '说明文']:
        calculator = ScoreCalculator(essay_type)
        
        # 检查维度满分之和是否等于总分
        sum_matches_total = calculator.total_max_score == TOTAL_SCORE
        
        # 检查维度映射与满分配置是否一致
        dimensions_match = set(calculator.dimensions) == set(calculator.max_scores.keys())
        
        results.append({
            'essay_type': essay_type,
            'sum_matches_total': sum_matches_total,
            'dimensions_match': dimensions_match,
            'total_max_score': calculator.total_max_score,
            'expected_total': TOTAL_SCORE,
            'dimensions_count': len(calculator.dimensions),
            'max_scores_count': len(calculator.max_scores)
        })
    
    return results


if __name__ == '__main__':
    # 测试评分计算器
    print("=== 评分计算器测试 ===")
    
    # 测试议论文评分计算
    print("\n1. 议论文测试：")
    dim_scores = {
        '立意与中心': 8,
        '论点与论证': 15,
        '结构与层次': 6,
        '语言表达': 8,
        '例证与材料运用': 3
    }
    report = calculate_score(dim_scores, '议论文', reported_total=40)
    print(f"   输入维度评分: {dim_scores}")
    print(f"   报告总分: {report['original_total']}, 计算总分: {report['calculated_total']}, 修正后总分: {report['total_score']}")
    print(f"   是否修正: {report['was_fixed']}")
    print(f"   校验结果: {report['validation']}")
    
    # 测试记叙文评分计算
    print("\n2. 记叙文测试：")
    dim_scores = {
        '立意与中心': 9,
        '选材与内容': 12,
        '结构与层次': 7,
        '语言表达': 8,
        '细节与表现': 4,
        '书写与规范': 2
    }
    report = calculate_score(dim_scores, '记叙文', reported_total=42)
    print(f"   输入维度评分: {dim_scores}")
    print(f"   报告总分: {report['original_total']}, 计算总分: {report['calculated_total']}, 修正后总分: {report['total_score']}")
    print(f"   是否修正: {report['was_fixed']}")
    
    # 测试说明文评分计算
    print("\n3. 说明文测试：")
    dim_scores = {
        '立意与中心': 14,
        '结构与层次': 14,
        '语言表达': 11,
        '方法与技巧': 2,
        '书写与规范': 1
    }
    report = calculate_score(dim_scores, '说明文', reported_total=45)
    print(f"   输入维度评分: {dim_scores}")
    print(f"   报告总分: {report['original_total']}, 计算总分: {report['calculated_total']}, 修正后总分: {report['total_score']}")
    print(f"   是否修正: {report['was_fixed']}")
    
    # 测试评分标准一致性验证
    print("\n4. 评分标准一致性验证：")
    criteria_results = validate_all_criteria()
    for result in criteria_results:
        print(f"   {result['essay_type']}: 总分匹配={result['sum_matches_total']}, 维度匹配={result['dimensions_match']}, 实际总分={result['total_max_score']}")
