"""
作文图片水印识别与清洗模块

背景：
    学生作文图片常来自社交媒体（抖音、小红书等），图片带有平台水印
    （如「抖音号：45137753049」「小红书号：26992932348」）。水印会：
    1. 混入 OCR 识别文本，污染批改输入，甚至被 AI 当成作文内容点评；
    2. 属于可溯源的身份信息，与评分标准中「出现暴露身份的真实信息扣分」相关。

职责（OCR 之后、进入批改之前调用）：
    1. 行级剔除：整行基本就是水印（页边空白处的独立水印行）→ 整行删除；
    2. 行内清洗：水印与正文识别在同一行（重叠水印）→ 仅删除水印子串，保留正文；
    3. 输出检测结果 findings，供批改引擎提示 AI「作文可能来自网络」。

技术边界（诚实声明）：
    与手写笔迹像素重叠的水印无法在图像层面安全去除（修复算法无法区分
    水印与笔迹，强行 inpainting 会破坏正文），因此本模块只做文本级清洗。
"""

import re
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# 水印特征模式（刻意保持高特异性，避免误伤正文）
# ---------------------------------------------------------------------------

# P1 显式账号模式：平台名 + (号/ID) + 冒号 + 账号
# 例：抖音号：45137753049 / 小红书号: 26992932348 / 快手ID: abc-123
_ACCOUNT_EXPLICIT_RE = re.compile(
    r'(抖音|小红书|快手|哔哩哔哩|bilibili|B站|微博|视频号|微信|公众号|头条号|百家号)'
    r'\s*(?:号|ID|Id|id)?\s*[:：]\s*[\w@.\-]+',
    re.IGNORECASE,
)

# P2 紧凑数字模式：平台名 + (号) + 长数字（无冒号也可能被 OCR 漏掉冒号）
# 例：抖音号45137753049 / 小红书26992932348
_ACCOUNT_COMPACT_RE = re.compile(
    r'(抖音|小红书|快手|哔哩哔哩|B站|微博|视频号|头条号|百家号)\s*号?\s*(\d{6,20})'
)

# P3 整行仅水印：平台名 + 可选(号/ID/冒号/账号)，行内去掉水印后几乎没有正文
_SOLO_LINE_RE = re.compile(
    r'^\s*(?:抖音|小红书|快手|哔哩哔哩|bilibili|B站|微博|视频号|微信|公众号|头条号|百家号)'
    r'\s*(?:号|ID|Id|id)?\s*[:：]?\s*[\w@.\-]*\s*$',
    re.IGNORECASE,
)

# P4 行尾 @用户名 水印（部分平台水印形态）
# 仅匹配行尾，且用户名长度受限，避免误伤正文
_TRAILING_AT_RE = re.compile(r'[@＠]\s*[\w\u4e00-\u9fa5\-]{2,20}\s*$')

# 整行仅平台名（无账号）时，要求该行位于页面边缘区域才剔除（水印常在角落，
# 正文整行只有「小红书」三个字的概率极低，但仍加位置约束防误删）
_EDGE_Y_TOP = 0.10     # 页面顶部 10%
_EDGE_Y_BOTTOM = 0.85  # 页面底部 15% 起视为边缘
_PLATFORM_NAME_ONLY_RE = re.compile(
    r'^\s*(抖音|小红书|快手|哔哩哔哩|bilibili|B站|微博|视频号)\s*$'
)


def _line_in_edge(line: Dict) -> bool:
    """判断一行（含 box 坐标）是否位于页面边缘区域。"""
    box = line.get('box') or []
    if len(box) != 4:
        return False
    y_center = box[1] + box[3] / 2
    return y_center <= _EDGE_Y_TOP or y_center >= _EDGE_Y_BOTTOM


def clean_watermarks(text: str, lines: Optional[List[Dict]] = None) -> Dict:
    """
    清洗 OCR 文本与行列表中的平台水印。

    参数：
        text:  整页 OCR 文本（段落级，行以 \n 分隔）
        lines: 行列表 [{'text': str, 'box': [x, y, w, h]}, ...]（可选）

    返回：
        {
            'text': str,            # 清洗后的整页文本
            'lines': list,          # 清洗后的行列表（入参原样返回类型与结构）
            'findings': [           # 检测到的水印（供批改可解释性使用）
                {'platform': '抖音', 'id': '45137753049', 'raw': '抖音号：45137753049'},
                ...
            ],
        }
    """
    findings: List[Dict] = []
    lines = [dict(line) for line in (lines or [])]

    def _record(raw: str, platform: str, watermark_id: str = ''):
        raw = (raw or '').strip()
        if raw and all(f['raw'] != raw for f in findings):
            findings.append({'platform': platform, 'id': watermark_id, 'raw': raw})

    def _strip(text_part: str) -> str:
        """对一段文本做行内水印子串剔除，并记录命中。"""
        for match in _ACCOUNT_EXPLICIT_RE.finditer(text_part):
            _record(match.group(0).strip(), match.group(1), match.group(0).split(':')[-1].split('：')[-1].strip())
        cleaned = _ACCOUNT_EXPLICIT_RE.sub('', text_part)
        for match in _ACCOUNT_COMPACT_RE.finditer(cleaned):
            _record(match.group(0).strip(), match.group(1), match.group(2))
        cleaned = _ACCOUNT_COMPACT_RE.sub('', cleaned)
        # 行尾 @用户名：仅当后面没有其他正文残留时才删（避免删掉正文里的 @）
        trailing = _TRAILING_AT_RE.search(cleaned)
        if trailing and not cleaned[trailing.end():].strip():
            _record(trailing.group(0).strip(), '@', '')
            cleaned = cleaned[:trailing.start()]
        return cleaned

    # ---- 行级处理：整行水印 → 删行；行内水印 → 删子串 ----
    kept_lines = []
    for line in lines:
        raw_text = line.get('text') or ''
        stripped = _strip(raw_text)
        is_solo = bool(_SOLO_LINE_RE.match(raw_text)) and not stripped.strip()
        is_name_only = bool(_PLATFORM_NAME_ONLY_RE.match(raw_text)) and _line_in_edge(line)
        if is_solo or is_name_only:
            _record(raw_text.strip(), raw_text.strip()[:3], '')
            continue  # 整行剔除
        if stripped != raw_text:
            line['text'] = stripped
        kept_lines.append(line)

    # ---- 整页文本：同样做子串剔除（text 与 lines 行不必一一对应）----
    cleaned_text = _strip(text or '')
    # 残余的「仅平台名」独立行（text 中可能单独成行）也剔除
    cleaned_text = '\n'.join(
        part for part in cleaned_text.splitlines()
        if not (_SOLO_LINE_RE.match(part) or (_PLATFORM_NAME_ONLY_RE.match(part) and not part.strip()))
    )

    # 去重相邻空行
    cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text).strip()
    return {'text': cleaned_text, 'lines': kept_lines, 'findings': findings}


def summarize_watermarks(pages: List[Dict]) -> List[Dict]:
    """
    汇总多页中的水印检测结果（批改引擎用于生成来源提示）。

    参数：
        pages: 分页列表（每页可含 'watermarks' 字段）

    返回：
        list: 去重后的水印列表
    """
    seen, result = set(), []
    for page in pages:
        for item in page.get('watermarks') or []:
            key = (item.get('platform'), item.get('id'), item.get('raw'))
            if key not in seen:
                seen.add(key)
                result.append(item)
    return result
