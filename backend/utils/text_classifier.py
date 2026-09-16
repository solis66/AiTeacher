"""
文本内容分类模块

负责识别用户输入的文本类型，准确区分作文内容和咨询问题。

核心功能：
1. 作文内容识别：判断用户输入是否为作文提交
2. 咨询问题识别：判断用户输入是否为咨询类问题
3. 作文体裁检测：识别作文类型（议论文/记叙文/说明文）

设计特点：
- 基于规则的分类器，结合关键词匹配和文本特征分析
- 支持初中教育场景的专业术语和表达方式
- 可配置的关键词列表，便于扩展和维护
- 完善的日志记录，便于调试和优化
"""

import re
from typing import Optional, Tuple, Dict, List

# 作文相关关键词
ESSAY_KEYWORDS = [
    # 直接作文标识
    '作文', '文章', 'essay', '作文题', '请批改', '请点评', '批改', '点评',
    '写一篇', '写了一篇', '我的作文', '这是我的',
    
    # 作文结构相关
    '字数', '段落', '开头', '结尾', '提纲', '草稿',
    
    # 作文体裁
    '议论文', '记叙文', '说明文', '散文', '诗歌', '小说',
    
    # 作文写作相关
    '写作', '习作', '练习', '作业', '题目', '主题', '立意',
]

# 咨询类问题关键词
CONSULTATION_KEYWORDS = [
    # 疑问词
    '如何', '怎么', '怎样', '为什么', '什么', '哪个', '哪种',
    '请问', '我想问', '问一下', '咨询', '请教', '解惑',
    
    # 请求类
    '方法', '技巧', '策略', '要点', '建议', '指导', '教程',
    '告诉我', '分析一下', '解释一下', '说明一下', '举例',
    
    # 教育相关咨询
    '标准', '评分', '分数', '满分', '及格', '优秀',
    '要求', '规则', '格式', '模板', '范例', '例子',
    
    # 闲聊类
    '你好', '你是谁', '你能做什么', '自我介绍', '功能', '帮助',
]

# 作文体裁特征词
TYPE_FEATURES = {
    '议论文': ['论点', '论证', '论据', '观点', '反驳', '证明', '认为', '因此', 
              '所以', '然而', '但是', '一方面', '另一方面', '首先', '其次', 
              '最后', '综上所述', '理由', '道理', '结论', '主张'],
    '记叙文': ['记得', '回忆', '那天', '时候', '突然', '忽然', '然后', '接着', 
              '终于', '开始', '结束', '看见', '听到', '想到', '感到', '觉得', 
              '我', '他', '她', '他们', '故事', '经历', '经过', '那年', '小时候'],
    '说明文': ['介绍', '说明', '原理', '方法', '步骤', '特点', '功能', '结构', 
              '作用', '定义', '分类', '比较', '对比', '举例', '数据', '分析', 
              '发现', '结论', '例如', '比如', '组成', '构成']
}

# 天气相关关键词（用于识别天气查询）
# 注意：使用完整短语而非单字，避免误判正常作文咨询问题
WEATHER_KEYWORDS = [
    '天气', '天气预报', '今天天气', '明天天气', '后天天气',
    '温度', '气温', '湿度', '晴', '下雨', '下雪', '刮风',
    '雾霾', '大风', '暴雨', '暴雪', '高温', '低温'
]


class TextClassifier:
    """
    文本分类器类
    
    提供文本类型识别的核心功能，支持：
    1. 作文提交检测
    2. 咨询问题检测
    3. 作文体裁识别
    """
    
    def __init__(self):
        """
        初始化分类器
        """
        self.essay_keywords = ESSAY_KEYWORDS
        self.consultation_keywords = CONSULTATION_KEYWORDS
        self.type_features = TYPE_FEATURES
        self.weather_keywords = WEATHER_KEYWORDS
    
    def _contains_any(self, text: str, keywords: List[str]) -> bool:
        """
        检查文本是否包含任何关键词
        
        参数：
            text: 待检测文本
            keywords: 关键词列表
            
        返回：
            bool: 是否包含任一关键词
        """
        for kw in keywords:
            if kw in text:
                return True
        return False
    
    def _count_keywords(self, text: str, keywords: List[str]) -> int:
        """
        统计文本中关键词出现的次数
        
        参数：
            text: 待检测文本
            keywords: 关键词列表
            
        返回：
            int: 关键词出现次数
        """
        count = 0
        for kw in keywords:
            count += text.count(kw)
        return count
    
    def is_weather_query(self, text: str) -> bool:
        """
        判断是否为天气查询
        
        参数：
            text: 用户输入文本
            
        返回：
            bool: 是否为天气查询
        """
        if not text or not isinstance(text, str):
            return False
        
        trimmed_text = text.strip()
        text_length = len(trimmed_text)
        
        # 天气查询通常较短（少于50字）
        if text_length > 50:
            return False
        
        # 检查是否包含天气关键词
        has_weather = self._contains_any(trimmed_text, self.weather_keywords)
        
        if has_weather:
            print(f"[文本分类] 检测到天气查询: {trimmed_text[:30]}...")
            return True
        
        return False
    
    def is_consultation(self, text: str) -> bool:
        """
        判断是否为咨询类问题
        
        咨询类问题特点：
        1. 文本较短（通常少于300字）
        2. 包含疑问词或请求词
        3. 不包含作文相关关键词
        
        参数：
            text: 用户输入文本
            
        返回：
            bool: 是否为咨询类问题
        """
        if not text or not isinstance(text, str):
            print("[文本分类] 输入为空或非字符串类型")
            return False
        
        trimmed_text = text.strip()
        text_length = len(trimmed_text)
        
        # 短文本优先判断为咨询
        if text_length < 100:
            # 检查是否包含咨询关键词
            has_consult = self._contains_any(trimmed_text, self.consultation_keywords)
            
            if has_consult:
                print(f"[文本分类] 短文本({text_length}字)包含咨询关键词，判定为咨询问题")
                return True
            
            # 检查是否为问候语
            greetings = ['你好', '您好', 'hi', 'hello', '嗨']
            if any(g in trimmed_text for g in greetings):
                print(f"[文本分类] 检测到问候语，判定为咨询问题")
                return True
            
            # 检查是否为自我介绍请求
            intro_patterns = ['你是谁', '你叫什么', '你能做什么', '介绍一下', '功能', '帮助']
            if any(p in trimmed_text for p in intro_patterns):
                print(f"[文本分类] 检测到自我介绍请求，判定为咨询问题")
                return True
        
        # 中等长度文本（100-300字）：需要明确的咨询关键词
        elif 100 <= text_length < 300:
            has_consult = self._contains_any(trimmed_text, self.consultation_keywords)
            has_essay = self._contains_any(trimmed_text, self.essay_keywords)
            
            # 如果只有咨询关键词，没有作文关键词，判定为咨询
            if has_consult and not has_essay:
                print(f"[文本分类] 中等长度文本({text_length}字)仅包含咨询关键词，判定为咨询问题")
                return True
        
        # 检查是否为天气查询
        if self.is_weather_query(trimmed_text):
            return True
        
        print(f"[文本分类] 未判定为咨询问题，文本长度: {text_length}")
        return False
    
    def is_essay(self, text: str) -> bool:
        """
        判断是否为作文提交
        
        作文判定逻辑：
        1. 最小长度检查：至少150字才可能是作文
        2. 作文关键词检查：包含作文相关关键词
        3. 文本长度加权：越长越可能是作文
        4. 排除明确的咨询问题
        
        参数：
            text: 用户输入文本
            
        返回：
            bool: 是否为作文提交
        """
        if not text or not isinstance(text, str):
            print("[文本分类] 输入为空或非字符串类型")
            return False
        
        trimmed_text = text.strip()
        text_length = len(trimmed_text)
        
        # 1. 最小长度检查：至少150字才可能是作文
        if text_length < 150:
            print(f"[文本分类] 文本过短({text_length}字)，不是作文提交")
            return False
        
        # 2. 检查是否为明确的咨询问题（短文本）
        if text_length < 300:
            has_consult = self._contains_any(trimmed_text, self.consultation_keywords)
            has_essay = self._contains_any(trimmed_text, self.essay_keywords)
            
            # 如果只有咨询关键词，没有作文关键词，排除作文
            if has_consult and not has_essay:
                print(f"[文本分类] 短文本({text_length}字)仅包含咨询关键词，不是作文提交")
                return False
        
        # 3. 超长文本（超过500字）直接判定为作文
        if text_length > 500:
            print(f"[文本分类] 超长文本({text_length}字)，直接判定为作文提交")
            return True
        
        # 4. 检查作文关键词
        has_essay = self._contains_any(trimmed_text, self.essay_keywords)
        
        # 5. 检查体裁特征词（作为辅助判断）
        type_feature_count = 0
        for features in self.type_features.values():
            type_feature_count += self._count_keywords(trimmed_text, features)
        
        # 6. 综合判定
        if text_length >= 300:
            # 中长文本：有作文关键词或体裁特征词较多则判定为作文
            if has_essay or type_feature_count >= 3:
                print(f"[文本分类] 中长文本({text_length}字)包含作文关键词或体裁特征，判定为作文提交")
                return True
        
        # 7. 检查是否包含明确的作文标识
        explicit_essay_markers = ['作文', '请批改', '请点评', '写一篇', '我的作文']
        if any(marker in trimmed_text for marker in explicit_essay_markers):
            print(f"[文本分类] 包含明确作文标识，判定为作文提交")
            return True
        
        print(f"[文本分类] 未满足作文提交条件，长度: {text_length}, 作文关键词: {has_essay}, 体裁特征: {type_feature_count}")
        return False
    
    def detect_essay_type(self, text: str) -> str:
        """
        检测作文体裁
        
        参数：
            text: 作文文本内容
            
        返回：
            str: 作文体裁（议论文/记叙文/说明文）
        """
        content_lower = text.lower()
        scores = {}
        
        # 使用体裁特征词统计
        for essay_type, features in self.type_features.items():
            score = sum(1 for feature in features if feature in content_lower)
            scores[essay_type] = score
        
        # 检查明确的体裁声明
        if '议论文' in text:
            scores['议论文'] += 10
        if '记叙文' in text:
            scores['记叙文'] += 10
        if '说明文' in text:
            scores['说明文'] += 10
        
        # 返回得分最高的体裁
        max_score = max(scores.values())
        
        # 如果得分都很低，根据文本特征判断
        if max_score < 3:
            # 检查故事性内容（记叙文特征）
            has_story = any(kw in text for kw in ['记得', '那天', '我', '他', '她', '故事', '经历'])
            # 检查说明性内容
            has_explanation = any(kw in text for kw in ['说明', '介绍', '解释', '原理', '功能'])
            # 检查议论性内容
            has_argument = any(kw in text for kw in ['论点', '论证', '观点', '认为', '因此'])
            
            if has_story and not has_explanation and not has_argument:
                return '记叙文'
            elif has_explanation and not has_story and not has_argument:
                return '说明文'
            elif has_argument and not has_story and not has_explanation:
                return '议论文'
            else:
                # 默认返回记叙文（初中阶段最常见）
                return '记叙文'
        
        # 返回得分最高的类型
        for essay_type, score in scores.items():
            if score == max_score:
                return essay_type
        
        return '记叙文'
    
    def classify(self, text: str) -> Tuple[str, Optional[str]]:
        """
        综合分类：判断文本类型
        
        参数：
            text: 用户输入文本
            
        返回：
            Tuple[str, Optional[str]]: (类型, 体裁)
            类型取值：'essay' | 'consultation' | 'unknown'
            体裁取值：'议论文' | '记叙文' | '说明文' | None
        """
        if not text or not isinstance(text, str):
            return ('unknown', None)
        
        # 优先判断是否为咨询问题
        if self.is_consultation(text):
            return ('consultation', None)
        
        # 判断是否为作文
        if self.is_essay(text):
            essay_type = self.detect_essay_type(text)
            return ('essay', essay_type)
        
        return ('unknown', None)


# 创建全局分类器实例
classifier = TextClassifier()


def classify_text(text: str) -> Tuple[str, Optional[str]]:
    """
    文本分类便捷函数
    
    参数：
        text: 用户输入文本
        
    返回：
        Tuple[str, Optional[str]]: (类型, 体裁)
    """
    return classifier.classify(text)


def is_essay_submission(text: str) -> bool:
    """
    判断是否为作文提交（保持向后兼容）
    
    参数：
        text: 用户输入文本
        
    返回：
        bool: 是否为作文提交
    """
    return classifier.is_essay(text)


def is_consultation(text: str) -> bool:
    """
    判断是否为咨询问题（保持向后兼容）
    
    参数：
        text: 用户输入文本
        
    返回：
        bool: 是否为咨询问题
    """
    return classifier.is_consultation(text)


def detect_essay_type(text: str) -> str:
    """
    检测作文体裁（保持向后兼容）
    
    参数：
        text: 作文文本内容
        
    返回：
        str: 作文体裁
    """
    return classifier.detect_essay_type(text)