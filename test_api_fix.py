"""
API修复验证测试脚本

验证修复后的评分计算逻辑能够正确处理：
1. 议论文维度评分超出范围的情况
2. 总分与各项评分一致性校验
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api import validate_and_fix_score


def test_argumentative_essay_with_exceeded_score():
    """测试议论文评分超出范围时的自动修正"""
    print("=== 测试议论文评分超出范围 ===")
    
    # 模拟AI返回的结果，其中"立意与中心"分数超出范围（满分10分，返回14分）
    parsed_result = {
        'essay_type': '议论文',
        'score': 40,
        'dimensions': [
            {'name': '立意与中心', 'score': 14},    # 超出范围
            {'name': '论点与论证', 'score': 15},
            {'name': '结构与层次', 'score': 6},
            {'name': '语言表达', 'score': 8},
            {'name': '例证与材料运用', 'score': 3}
        ],
        'overall_comment': '这是一篇不错的议论文',
        'suggestions': ['建议增加更多例证']
    }
    
    print(f"原始总分: {parsed_result['score']}")
    print("原始维度评分:")
    for dim in parsed_result['dimensions']:
        print(f"  - {dim['name']}: {dim['score']}")
    
    # 调用校验函数
    result = validate_and_fix_score(parsed_result)
    
    print(f"\n修正后总分: {result['score']}")
    print("修正后维度评分:")
    for dim in result['dimensions']:
        print(f"  - {dim['name']}: {dim['score']} (满分: {dim.get('max_score', '未知')})")
    
    print(f"\n校验状态:")
    print(f"  - 是否一致: {result['validation']['is_consistent']}")
    print(f"  - 是否完整: {result['validation']['is_complete']}")
    
    # 验证修正后总分是否正确
    expected_total = 10 + 15 + 6 + 8 + 3  # 立意与中心修正为10分
    assert result['score'] == expected_total, f"预期总分 {expected_total}，实际 {result['score']}"
    assert result['validation']['is_consistent'] == True
    assert result['validation']['is_complete'] == True
    
    print("\n[OK] 测试通过！")


def test_expository_essay_dimension_consistency():
    """测试说明文维度一致性"""
    print("\n=== 测试说明文维度一致性 ===")
    
    parsed_result = {
        'essay_type': '说明文',
        'score': 42,
        'dimensions': [
            {'name': '立意与中心', 'score': 14},
            {'name': '结构与层次', 'score': 14},
            {'name': '语言表达', 'score': 11},
            {'name': '方法与技巧', 'score': 2},
            {'name': '书写与规范', 'score': 1}
        ],
        'overall_comment': '这是一篇结构清晰的说明文',
        'suggestions': ['建议使用更多说明方法']
    }
    
    result = validate_and_fix_score(parsed_result)
    
    print(f"总分: {result['score']}")
    print("维度评分:")
    for dim in result['dimensions']:
        print(f"  - {dim['name']}: {dim['score']} (满分: {dim.get('max_score', '未知')})")
    
    assert result['validation']['is_consistent'] == True
    assert result['validation']['is_complete'] == True
    
    print("[OK] 测试通过！")


def test_narrative_essay_score_fix():
    """测试记叙文总分修正"""
    print("\n=== 测试记叙文总分修正 ===")
    
    # AI返回的总分与各项评分之和不一致
    parsed_result = {
        'essay_type': '记叙文',
        'score': 45,  # AI报告的总分
        'dimensions': [
            {'name': '立意与中心', 'score': 8},
            {'name': '选材与内容', 'score': 12},
            {'name': '结构与层次', 'score': 7},
            {'name': '语言表达', 'score': 8},
            {'name': '细节与表现', 'score': 4},
            {'name': '书写与规范', 'score': 2}
        ],
        'overall_comment': '这是一篇生动的记叙文',
        'suggestions': ['建议增加细节描写']
    }
    
    print(f"原始报告总分: {parsed_result['score']}")
    print(f"各项评分之和: {sum(dim['score'] for dim in parsed_result['dimensions'])}")
    
    result = validate_and_fix_score(parsed_result)
    
    print(f"修正后总分: {result['score']}")
    print(f"是否修正: {result.get('score_fixed', False)}")
    
    expected_total = 8 + 12 + 7 + 8 + 4 + 2
    assert result['score'] == expected_total, f"预期总分 {expected_total}，实际 {result['score']}"
    assert result['score_fixed'] == True
    
    print("[OK] 测试通过！")


if __name__ == '__main__':
    test_argumentative_essay_with_exceeded_score()
    test_expository_essay_dimension_consistency()
    test_narrative_essay_score_fix()
    print("\n=== 所有测试通过！ ===")
