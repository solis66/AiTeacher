"""
作文评分计算模块单元测试

测试覆盖：
1. 各体裁评分计算
2. 总分一致性校验
3. 分数归一化（超出范围自动修正）
4. 维度完整性校验
5. 边界条件测试
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from utils.score_calculator import ScoreCalculator


class TestScoreCalculator(unittest.TestCase):
    """评分计算器单元测试"""
    
    def test_argumentative_essay_score_calculation(self):
        """测试议论文评分计算"""
        calculator = ScoreCalculator('议论文')
        
        dim_scores = {
            '立意与中心': 8,
            '论点与论证': 15,
            '结构与层次': 6,
            '语言表达': 8,
            '例证与材料运用': 3
        }
        
        total = calculator.calculate_total(dim_scores)
        expected_total = sum(dim_scores.values())
        self.assertEqual(total, expected_total)
    
    def test_narrative_essay_score_calculation(self):
        """测试记叙文评分计算"""
        calculator = ScoreCalculator('记叙文')
        
        dim_scores = {
            '立意与中心': 9,
            '选材与内容': 12,
            '结构与层次': 7,
            '语言表达': 8,
            '细节与表现': 4,
            '书写与规范': 2
        }
        
        total = calculator.calculate_total(dim_scores)
        expected_total = sum(dim_scores.values())
        self.assertEqual(total, expected_total)
    
    def test_expository_essay_score_calculation(self):
        """测试说明文评分计算"""
        calculator = ScoreCalculator('说明文')
        
        dim_scores = {
            '立意与中心': 14,
            '结构与层次': 14,
            '语言表达': 11,
            '方法与技巧': 2,
            '书写与规范': 1
        }
        
        total = calculator.calculate_total(dim_scores)
        expected_total = sum(dim_scores.values())
        self.assertEqual(total, expected_total)
    
    def test_score_normalization_exceeding_max(self):
        """测试超出满分时的自动修正（归一化）"""
        calculator = ScoreCalculator('议论文')
        
        # 立意与中心满分10分，但AI返回14分
        dim_scores = {
            '立意与中心': 14,  # 超出范围
            '论点与论证': 15,
            '结构与层次': 6,
            '语言表达': 8,
            '例证与材料运用': 3
        }
        
        # 归一化后应将立意与中心修正为10分
        normalized = calculator.normalize_dimension_scores(dim_scores)
        self.assertEqual(normalized['立意与中心'], 10)
        
        # 计算总分使用归一化后的值
        total = calculator.calculate_total(dim_scores)
        self.assertEqual(total, 10 + 15 + 6 + 8 + 3)
    
    def test_score_normalization_negative(self):
        """测试负分的自动修正"""
        calculator = ScoreCalculator('记叙文')
        
        dim_scores = {
            '立意与中心': -2,  # 负数分数
            '选材与内容': 12,
            '结构与层次': 7,
            '语言表达': 8,
            '细节与表现': 4,
            '书写与规范': 2
        }
        
        normalized = calculator.normalize_dimension_scores(dim_scores)
        self.assertEqual(normalized['立意与中心'], 0)
    
    def test_score_fix_when_inconsistent(self):
        """测试不一致时的总分修正"""
        calculator = ScoreCalculator('记叙文')
        
        dim_scores = {
            '立意与中心': 8,
            '选材与内容': 12,
            '结构与层次': 7,
            '语言表达': 8,
            '细节与表现': 4,
            '书写与规范': 2
        }
        
        # 报告总分45与实际计算总分41不一致，应自动修正
        fixed_total, was_fixed = calculator.fix_total_score(dim_scores, 45)
        expected_total = sum(dim_scores.values())
        self.assertEqual(fixed_total, expected_total)
        self.assertTrue(was_fixed)
    
    def test_score_consistency_when_consistent(self):
        """测试一致时不进行修正"""
        calculator = ScoreCalculator('说明文')
        
        dim_scores = {
            '立意与中心': 14,
            '结构与层次': 14,
            '语言表达': 11,
            '方法与技巧': 2,
            '书写与规范': 1
        }
        
        expected_total = sum(dim_scores.values())
        fixed_total, was_fixed = calculator.fix_total_score(dim_scores, expected_total)
        self.assertEqual(fixed_total, expected_total)
        self.assertFalse(was_fixed)
    
    def test_dimension_validation(self):
        """测试维度校验"""
        calculator = ScoreCalculator('议论文')
        
        dim_scores = {
            '立意与中心': 8,
            '论点与论证': 15,
            '结构与层次': 6,
            '语言表达': 8,
            '例证与材料运用': 3
        }
        
        is_complete = calculator.validate_dimension_completeness(dim_scores)
        self.assertTrue(is_complete)
    
    def test_dimension_validation_missing(self):
        """测试缺少维度时的校验"""
        calculator = ScoreCalculator('议论文')
        
        # 缺少"例证与材料运用"维度
        dim_scores = {
            '立意与中心': 8,
            '论点与论证': 15,
            '结构与层次': 6,
            '语言表达': 8
        }
        
        is_complete = calculator.validate_dimension_completeness(dim_scores)
        self.assertFalse(is_complete)
    
    def test_max_score_validation(self):
        """测试各体裁满分值"""
        # 议论文满分应为50分
        arg_calc = ScoreCalculator('议论文')
        self.assertEqual(arg_calc.total_max_score, 50)
        
        # 记叙文满分应为50分
        nar_calc = ScoreCalculator('记叙文')
        self.assertEqual(nar_calc.total_max_score, 50)
        
        # 说明文满分应为50分
        exp_calc = ScoreCalculator('说明文')
        self.assertEqual(exp_calc.total_max_score, 50)
    
    def test_percentage_conversion(self):
        """测试百分比转换"""
        calculator = ScoreCalculator('议论文')
        
        dim_scores = {
            '立意与中心': 8,
            '论点与论证': 15,
            '结构与层次': 6,
            '语言表达': 8,
            '例证与材料运用': 3
        }
        
        percentages = calculator.convert_to_percentage(dim_scores)
        
        # 验证百分比计算正确
        self.assertEqual(percentages['立意与中心'], 80.0)  # 8/10 * 100
        self.assertEqual(percentages['论点与论证'], 83.33)  # 15/18 * 100
        
    def test_boundary_zero_score(self):
        """测试零分边界条件"""
        calculator = ScoreCalculator('议论文')
        
        dim_scores = {
            '立意与中心': 0,
            '论点与论证': 0,
            '结构与层次': 0,
            '语言表达': 0,
            '例证与材料运用': 0
        }
        
        total = calculator.calculate_total(dim_scores)
        self.assertEqual(total, 0)
    
    def test_boundary_full_score(self):
        """测试满分边界条件"""
        calculator = ScoreCalculator('议论文')
        
        dim_scores = {
            '立意与中心': 10,
            '论点与论证': 18,
            '结构与层次': 8,
            '语言表达': 10,
            '例证与材料运用': 4
        }
        
        total = calculator.calculate_total(dim_scores)
        self.assertEqual(total, 50)
    
    def test_score_rounding(self):
        """测试四舍五入功能"""
        calculator = ScoreCalculator('议论文')
        
        # 测试标准四舍五入
        rounded = calculator.round_score(8.6)
        self.assertEqual(rounded, 9)
        
        rounded = calculator.round_score(8.4)
        self.assertEqual(rounded, 8)


if __name__ == '__main__':
    unittest.main()
