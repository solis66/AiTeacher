"""
统一评分标准加载模块

职责：
1. 以 data/广东省中考作文评分标准.doc 作为所有作文体裁共用的默认评分依据。
   加载优先级：模块级缓存 → .txt 缓存（.doc 未更新时）→ 实时从 .doc 提取（本机装有 Word）→ 内置兜底文本。
2. 从题目 / 题干中提取具体要求，作为评分决策系统中的“主依据”，
   与“辅依据”（评分标准文件）共同构成可解释的评分决策系统。

设计原则：
- .doc 是唯一权威来源；.txt 缓存只是其提取产物，.doc 被更新后会自动重新提取。
- 加载结果做进程内缓存，避免每次批改重复读取文件 / 启动 Word。
- 提取文本做轻度清洗（去除 Word 控制字符、压缩多余空行），不做内容改写。
"""

import re
from pathlib import Path
from typing import Dict, List, Optional

# data 目录与评分标准文件
DATA_DIR = Path(__file__).resolve().parents[1] / 'data'
STANDARD_DOC = DATA_DIR / '广东省中考作文评分标准.doc'
STANDARD_TXT = DATA_DIR / '广东省中考作文评分标准.txt'
STANDARD_NAME = '《广东省中考作文评分标准.doc》'

# 内置兜底文本（与 .doc 提取内容一致；当本机无 Word 且无缓存时使用，
# 保证服务在任意环境下都能给出统一的评分依据）
BUILTIN_STANDARD = '''中考作文考纲要求及评分标准
考纲要求
评分标准（满分50分）
1.中心明确,内容具体，感情真挚
2.结构完整，条理清楚
3.写记叙文,做到内容具体充实
4.写简单的议论文，做到有理有据
5.写简单的说明文,做到明白清楚
6.语言通顺,不写错别字
7.正确使用标点符号
8.书写规范、整洁
作文等级 评分标准
一类卷（50~45）
1.立意明确，中心突出,材料具体生动，有真情实感
2.结构严谨，注意照应，详略得当
3.语言得体、流畅
二类卷(44～40）
1.立意明确,中心突出，材料具体
2.结构完整，条理清楚
3.语言规范、通顺
三类卷(39～30）
1.立意明确,材料能表现中心
2.结构基本完整，有条理
3.语言基本通顺,有少数错别字
四类卷（29~15）
1.立意不明确,材料难以表现中心
2.结构不完整,条理不清楚
3.语言不通顺，错别字较多
五类卷（14～0）
1.没有中心,空洞无物，严重离题
2.结构残缺，不成篇章
3.文理不通,错别字较多
加分
符合如下条件之一，可酌情加1~3分(加至本题满分为止)
1.立意深刻
2.构思独特
3.语言优美
4.富有个性
5.文面整洁，书写优美
扣分
1.要求自拟标题或补充作文题目时，作文无标题或题目不完整扣2分
2.不足500字者,每少50字扣1分
3.错别字每3个扣1分（重复的错别字不计），最多扣3分
4.不能正确使用标点符号扣1~3分
5.文面脏乱,字迹潦草、难以辨认的扣1～3分
6.出现暴露身份的真实校名、地名、人名的扣1~3分'''

_cached_standard: Optional[str] = None


def _clean_standard_text(text: str) -> str:
    """轻度清洗 Word 提取文本：去控制字符、压缩多余空行，保留原文内容与标点。"""
    lines = []
    for line in (text or '').splitlines():
        line = ''.join(ch for ch in line if ch not in '\x07\x0b\x0c' and not (ch < ' ' and ch not in '\t'))
        line = line.strip()
        if line:
            lines.append(line)
    # 去重连续空行（已在上面按非空行收集），直接拼接
    return '\n'.join(lines)


def _extract_doc_text(doc_path: Path) -> str:
    """通过 Word COM 从 .doc 提取纯文本（仅 Windows 且已安装 Word 时可用）。"""
    import win32com.client
    word = win32com.client.Dispatch('Word.Application')
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        doc = word.Documents.Open(str(doc_path), ReadOnly=True)
        try:
            return doc.Content.Text
        finally:
            doc.Close(False)
    finally:
        word.Quit()


def load_unified_standard() -> str:
    """
    加载统一评分标准全文（所有作文体裁共用）。

    加载顺序：
      1. 模块级缓存（进程内只读一次）
      2. .txt 缓存存在且不比 .doc 旧 → 直接读取
      3. .doc 存在 → 实时提取并刷新 .txt 缓存
      4. 内置兜底文本

    返回：
        str: 评分标准全文
    """
    global _cached_standard
    if _cached_standard:
        return _cached_standard

    try:
        if STANDARD_DOC.exists():
            doc_mtime = STANDARD_DOC.stat().st_mtime
            if STANDARD_TXT.exists() and STANDARD_TXT.stat().st_mtime >= doc_mtime:
                _cached_standard = _clean_standard_text(STANDARD_TXT.read_text(encoding='utf-8'))
                return _cached_standard
            # .doc 比缓存新（或被替换过）→ 重新提取并刷新缓存
            text = _extract_doc_text(STANDARD_DOC)
            text = _clean_standard_text(text)
            if text:
                STANDARD_TXT.write_text(text, encoding='utf-8')
                _cached_standard = text
                return text
    except Exception as exc:
        print(f'[评分标准加载] 从 .doc 提取失败，改用缓存/内置标准: {exc}')

    if STANDARD_TXT.exists():
        _cached_standard = _clean_standard_text(STANDARD_TXT.read_text(encoding='utf-8'))
        return _cached_standard

    _cached_standard = BUILTIN_STANDARD
    return _cached_standard


# ---------------------------------------------------------------------------
# 题目 / 题干要求提取（评分决策系统中的“主依据”）
# ---------------------------------------------------------------------------

# 字数约束正则（按优先级依次匹配：范围 → 最少 → 最多 → 左右 → 以上 → 以下）
_WORD_RANGE_RE = re.compile(r'(?P<min>\d{3,4})\s*[-～~至到]\s*(?P<max>\d{3,4})\s*字')
_MIN_WORD_RE = re.compile(r'(?:不少于|至少|不低于)\s*(?P<n>\d{3,4})\s*字')
_MAX_WORD_RE = re.compile(r'(?:不超过|至多|不多于)\s*(?P<n>\d{3,4})\s*字')
_AROUND_WORD_RE = re.compile(r'(?P<n>\d{3,4})\s*字\s*(?:左右|上下)')
_ABOVE_WORD_RE = re.compile(r'(?P<n>\d{3,4})\s*字\s*以上')
_BELOW_WORD_RE = re.compile(r'(?P<n>\d{3,4})\s*字\s*(?:以下|以内)')


def _detect_word_limit(title: str, requirements: str) -> Optional[Dict]:
    """从题目 / 题干原文中检测字数约束。"""
    full = f'{title or ""} {requirements or ""}'

    m = _WORD_RANGE_RE.search(full)
    if m:
        return {'text': m.group(0), 'min': int(m.group('min')), 'max': int(m.group('max')), 'mode': 'range'}
    m = _MIN_WORD_RE.search(full)
    if m:
        return {'text': m.group(0), 'min': int(m.group('n')), 'max': int(m.group('n')), 'mode': 'min'}
    m = _MAX_WORD_RE.search(full)
    if m:
        return {'text': m.group(0), 'min': int(m.group('n')), 'max': int(m.group('n')), 'mode': 'max'}
    m = _AROUND_WORD_RE.search(full)
    if m:
        return {'text': m.group(0), 'min': int(m.group('n')), 'max': int(m.group('n')), 'mode': 'around'}
    m = _ABOVE_WORD_RE.search(full)
    if m:
        return {'text': m.group(0), 'min': int(m.group('n')), 'max': int(m.group('n')), 'mode': 'min'}
    m = _BELOW_WORD_RE.search(full)
    if m:
        return {'text': m.group(0), 'min': int(m.group('n')), 'max': int(m.group('n')), 'mode': 'max'}
    return None


def _detect_genre(text: str) -> str:
    """检测题干中是否存在明确的体裁限制（与 review_grader.detect_essay_type 逻辑一致）。"""
    if not text:
        return ''
    if any(key in text for key in ('文体不限', '体裁不限', '不限文体', '不限体裁', '除诗歌外')):
        return ''
    for name in ('议论文', '记叙文', '说明文'):
        if name in text:
            return name
    if '议论' in text or '论说' in text or '驳' in text:
        return '议论文'
    if '记叙' in text or '叙述' in text:
        return '记叙文'
    return ''


def extract_topic_requirements(title: str, requirements: str) -> Dict:
    """
    从题目与题干中提取评分主依据（具体要求清单 + 结构化约束）。

    返回结构：
        {
            'title': str,
            'requirements': str,
            'has_title': bool,          # 是否提供了题目
            'has_requirements': bool,   # 是否提供了题干要求
            'has_topic': bool,          # 是否提供了题目或题干（决定主依据是否生效）
            'genre': str,               # 题干限定的体裁（'' 表示未限定）
            'word_limit': dict | None,  # 字数约束（text/min/max/mode）
            'items': [                  # 逐条具体要求（供提示词逐条核对）
                {'source': '题目' | '题干', 'text': str},
                ...
            ],
        }
    """
    title = (title or '').strip()
    requirements = (requirements or '').strip()

    items: List[Dict] = []
    if title:
        items.append({'source': '题目', 'text': f'题目《{title}》：作文必须切合题意、紧扣题目写作'})
    if requirements:
        # 按句读 + 逗号/顿号切分题干，每条非空子句视为一项具体要求（粒度更细，便于逐条核对）
        for part in re.split(r'[。；;！？\n，,、]+', requirements):
            part = part.strip()
            if part:
                items.append({'source': '题干', 'text': part})

    return {
        'title': title,
        'requirements': requirements,
        'has_title': bool(title),
        'has_requirements': bool(requirements),
        'has_topic': bool(title or requirements),
        'genre': _detect_genre(f'{title} {requirements}'),
        'word_limit': _detect_word_limit(title, requirements),
        'items': items,
    }


def build_primary_requirement_text(topic: Dict) -> str:
    """
    把提取到的题目/题干要求整理成提示词中的“主依据”文本。

    参数：
        topic: extract_topic_requirements 的返回结果

    返回：
        str: 供提示词使用的主依据描述
    """
    lines = []
    if topic['has_title']:
        lines.append(f'题目：{topic["title"]}')
    if topic['has_requirements']:
        lines.append(f'题干要求：{topic["requirements"]}')
    if not topic['has_topic']:
        return '未提供题目与题干要求。'

    if topic['items']:
        lines.append('已识别的具体要求清单（必须逐条核对）：')
        lines.extend(f'- [{item["source"]}] {item["text"]}' for item in topic['items'])
    if topic['word_limit']:
        wl = topic['word_limit']
        lines.append(f'字数要求：{wl["text"]}。作文字数须符合该要求，不足时按标准文件扣分细则处理。')
    return '\n'.join(lines)
