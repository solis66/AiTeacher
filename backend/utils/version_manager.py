"""
评分标准版本管理模块

提供评分标准的版本控制、变更记录、审核流程管理功能。

核心功能：
- 版本信息查询
- 变更记录管理
- 审核流程追踪
- 版本验证
- 自动测试验证
"""

import json
import os
import time
from datetime import datetime
from typing import Dict, List, Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.score_calculator import validate_all_criteria


class VersionManager:
    """
    版本管理器类
    
    负责评分标准的版本控制和审核流程管理。
    """
    
    def __init__(self, data_dir: str = None):
        """
        初始化版本管理器
        
        参数：
            data_dir: 数据目录路径，默认为项目根目录下的data目录
        """
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
        self.data_dir = os.path.abspath(data_dir)
        self.version_file = os.path.join(self.data_dir, 'version_control.json')
        
        # 加载版本配置
        self.version_info = self._load_version_info()
    
    def _load_version_info(self) -> Dict:
        """
        加载版本配置信息
        
        返回：
            Dict: 版本配置信息
        """
        if os.path.exists(self.version_file):
            try:
                with open(self.version_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载版本配置失败: {e}")
                return self._create_default_version()
        
        return self._create_default_version()
    
    def _create_default_version(self) -> Dict:
        """
        创建默认版本配置
        
        返回：
            Dict: 默认版本配置
        """
        return {
            'version': '1.0.0',
            'release_date': datetime.now().strftime('%Y-%m-%d'),
            'description': '作文评分标准初始版本',
            'change_history': [],
            'approval_workflow': self._get_default_workflow(),
            'validation_rules': self._get_default_rules()
        }
    
    def _get_default_workflow(self) -> List:
        """
        获取默认审核流程
        
        返回：
            List: 审核流程步骤列表
        """
        return [
            {
                'step': 1,
                'name': '变更申请',
                'description': '提交评分标准变更申请',
                'responsible': '内容管理员'
            },
            {
                'step': 2,
                'name': '技术评审',
                'description': '技术团队评审变更',
                'responsible': '技术负责人'
            },
            {
                'step': 3,
                'name': '测试验证',
                'description': '运行测试验证变更',
                'responsible': '测试工程师'
            },
            {
                'step': 4,
                'name': '审批发布',
                'description': '最终审批发布',
                'responsible': '系统管理员'
            }
        ]
    
    def _get_default_rules(self) -> Dict:
        """
        获取默认验证规则
        
        返回：
            Dict: 验证规则字典
        """
        return {
            'total_score_must_be_50': True,
            'dimension_names_must_match_code': True,
            'weights_must_sum_to_100': True,
            'all_dimensions_must_have_scores': True,
            'scores_must_be_non_negative': True,
            'scores_must_not_exceed_max': True
        }
    
    def get_current_version(self) -> str:
        """
        获取当前版本号
        
        返回：
            str: 当前版本号
        """
        return self.version_info.get('version', '1.0.0')
    
    def get_version_info(self) -> Dict:
        """
        获取完整的版本信息
        
        返回：
            Dict: 版本信息字典
        """
        return self.version_info
    
    def create_change_request(self, changes: List[Dict], author: str, description: str = "") -> Dict:
        """
        创建变更申请
        
        参数：
            changes: 变更内容列表
            author: 申请人
            description: 变更描述
        
        返回：
            Dict: 变更申请信息
        """
        new_version = self._increment_version()
        
        change_record = {
            'version': new_version,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'author': author,
            'status': 'pending',
            'description': description,
            'changes': changes,
            'created_at': datetime.now().isoformat()
        }
        
        # 添加到变更历史
        self.version_info['change_history'].append(change_record)
        
        # 保存配置
        self._save_version_info()
        
        print(f"[版本管理] 创建变更申请: 版本 {new_version}, 申请人: {author}")
        
        return change_record
    
    def _increment_version(self) -> str:
        """
        生成下一个版本号
        
        返回：
            str: 新版本号
        """
        current_version = self.version_info.get('version', '1.0.0')
        parts = current_version.split('.')
        
        if len(parts) == 3:
            major, minor, patch = map(int, parts)
            patch += 1
            return f"{major}.{minor}.{patch}"
        
        return f"{current_version}.1"
    
    def approve_change(self, version: str, reviewer: str) -> bool:
        """
        审批变更申请
        
        参数：
            version: 版本号
            reviewer: 审批人
        
        返回：
            bool: 是否审批成功
        """
        for record in self.version_info['change_history']:
            if record['version'] == version and record['status'] == 'pending':
                # 先进行验证
                validation_result = self.validate_version()
                
                if not validation_result['all_passed']:
                    print(f"[版本管理] 版本 {version} 验证失败，无法审批")
                    record['status'] = 'rejected'
                    record['rejection_reason'] = validation_result['errors']
                    self._save_version_info()
                    return False
                
                # 运行测试
                test_result = self.run_tests()
                
                if not test_result['passed']:
                    print(f"[版本管理] 版本 {version} 测试失败，无法审批")
                    record['status'] = 'rejected'
                    record['rejection_reason'] = test_result['errors']
                    self._save_version_info()
                    return False
                
                # 审批通过
                record['status'] = 'approved'
                record['reviewer'] = reviewer
                record['review_date'] = datetime.now().strftime('%Y-%m-%d')
                record['test_results'] = test_result['message']
                
                # 更新当前版本
                self.version_info['version'] = version
                self.version_info['release_date'] = datetime.now().strftime('%Y-%m-%d')
                
                self._save_version_info()
                
                print(f"[版本管理] 版本 {version} 审批通过，审批人: {reviewer}")
                return True
        
        print(f"[版本管理] 未找到待审批的版本: {version}")
        return False
    
    def validate_version(self) -> Dict:
        """
        验证当前版本配置的正确性
        
        返回：
            Dict: 验证结果
        """
        results = validate_all_criteria()
        all_passed = True
        errors = []
        
        for result in results:
            essay_type = result['essay_type']
            
            if not result['sum_matches_total']:
                errors.append(f"{essay_type}维度满分之和不等于50分")
                all_passed = False
            
            if not result['dimensions_match']:
                errors.append(f"{essay_type}维度映射与满分配置不一致")
                all_passed = False
        
        return {
            'all_passed': all_passed,
            'errors': errors,
            'details': results
        }
    
    def run_tests(self) -> Dict:
        """
        运行版本测试
        
        返回：
            Dict: 测试结果
        """
        try:
            # 运行评分计算器测试
            import subprocess
            result = subprocess.run(
                ['python', '-m', 'pytest', 'tests/test_score_calculator.py', '-v'],
                capture_output=True,
                text=True,
                cwd=os.path.dirname(os.path.dirname(self.data_dir))
            )
            
            if result.returncode == 0:
                return {
                    'passed': True,
                    'message': '所有测试通过',
                    'output': result.stdout
                }
            else:
                return {
                    'passed': False,
                    'message': '测试失败',
                    'errors': result.stderr
                }
        except Exception as e:
            return {
                'passed': False,
                'message': f'测试执行失败: {str(e)}',
                'errors': str(e)
            }
    
    def _save_version_info(self):
        """
        保存版本配置信息
        """
        try:
            with open(self.version_file, 'w', encoding='utf-8') as f:
                json.dump(self.version_info, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存版本配置失败: {e}")
    
    def get_change_history(self) -> List[Dict]:
        """
        获取变更历史记录
        
        返回：
            List[Dict]: 变更历史列表
        """
        return self.version_info.get('change_history', [])
    
    def get_pending_changes(self) -> List[Dict]:
        """
        获取待审批的变更申请
        
        返回：
            List[Dict]: 待审批变更列表
        """
        return [
            record for record in self.version_info.get('change_history', [])
            if record['status'] == 'pending'
        ]
    
    def generate_version_report(self) -> str:
        """
        生成版本报告
        
        返回：
            str: 版本报告文本
        """
        report = []
        report.append("=" * 60)
        report.append("作文评分标准版本报告")
        report.append("=" * 60)
        report.append(f"当前版本: {self.get_current_version()}")
        report.append(f"发布日期: {self.version_info.get('release_date', '未知')}")
        report.append(f"描述: {self.version_info.get('description', '')}")
        report.append("")
        
        # 验证状态
        validation = self.validate_version()
        report.append("验证状态:")
        report.append(f"  全部通过: {'[OK]' if validation['all_passed'] else '[FAIL]'}")
        for error in validation['errors']:
            report.append(f"  - [FAIL] {error}")
        
        report.append("")
        
        # 变更历史
        history = self.get_change_history()
        report.append(f"变更记录 ({len(history)}条):")
        for record in reversed(history[:5]):  # 只显示最近5条
            status_icon = {
                'approved': '[OK]',
                'pending': '[PENDING]',
                'rejected': '[FAIL]'
            }.get(record['status'], '[UNKNOWN]')
            
            report.append(f"  {status_icon} {record['version']} ({record['date']})")
            report.append(f"     作者: {record['author']}")
            report.append(f"     状态: {record['status']}")
        
        report.append("=" * 60)
        
        return '\n'.join(report)


# 全局实例
version_manager = VersionManager()


def get_version_manager() -> VersionManager:
    """
    获取版本管理器实例
    
    返回：
        VersionManager: 版本管理器实例
    """
    return version_manager


if __name__ == '__main__':
    # 测试版本管理器
    manager = VersionManager()
    
    print("=== 版本管理器测试 ===")
    print(f"当前版本: {manager.get_current_version()}")
    
    # 验证当前版本
    validation = manager.validate_version()
    print(f"\n验证结果: {'通过' if validation['all_passed'] else '失败'}")
    
    # 生成版本报告
    print("\n版本报告:")
    print(manager.generate_version_report())
