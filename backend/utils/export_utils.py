"""
导出工具

提供批改结果的 Markdown / PDF 导出（需求 D4：两者仅在「批改结果页」提供）。

实现说明（同源、零漂移）：
- 先构造一份**结构化报告对象** `_report(record)`，
  Markdown 与 PDF 都只从这一份对象渲染，保证两套导出内容完全一致。
- PDF 使用 reportlab + 内置中文字体 STSong-Light（CID 字体，无需外部字体文件），
  避免服务器缺少字体文件导致的导出乱码/失败。
- 导出以**已保存版本**（record['result']）为准，未保存的临时编辑不参与导出。
- 导出文件名来自作文原题，做路径/非法字符安全处理，中文用 UTF-8。
"""

import io
import re
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def safe_filename(title: str) -> str:
    """
    把作文原题转成安全的导出文件名。

    - 去掉 Windows/Unix 非法字符（\\ / : * ? " < > |）与换行
    - 压缩连续空白、限制长度，避免超长/含空格导致下载异常
    """
    text = re.sub(r'[\\/:*?"<>|\r\n\t]+', '_', (title or '').strip())
    text = re.sub(r'\s+', ' ', text).strip('. ')
    text = text[:60]
    return text or '作文批改报告'


def _report(record):
    """
    构造「结构化报告对象」——MD 与 PDF 的唯一数据源。

    导出以已保存版本（result）为准，un-saved 编辑不参与。
    """
    inp = record.get('input', {})
    result = record.get('result') or {}
    return {
        'owner': record.get('owner') or '',
        'title': inp.get('title') or '未命名作文',
        'grade': inp.get('grade', ''),
        'essay_type': inp.get('essay_type', ''),
        'word_count': result.get('word_count', 0),
        'score': result.get('score'),
        'total_score': result.get('total_score', 50),
        'rating': result.get('rating', ''),
        'dimensions': result.get('dimensions', []),
        'overall': result.get('overall_comment', ''),
        'suggestions': result.get('suggestions', []),
        'highlights': result.get('highlights', []),
        'corrections': result.get('corrections', []),
        'rewrites': result.get('rewrites', {}),
        'polished_title': result.get('polished_title', ''),
        'polished_text': result.get('polished_text', ''),
    }


def export_markdown(record):
    """
    按需求文档第五节的 MD 模板生成 Markdown 报告。

    返回：
        (str, str): (markdown 文本, 建议文件名)
    """
    data = _report(record)
    lines = [
        f"# {data['owner'] or '用户'}《{data['title']}》 得分 {data['score']}/{data['total_score']}"
        f"（{data['rating']}）",
        f"年级：{data['grade']}　体裁：{data['essay_type'] or '未限定'}　字数：{data['word_count']}",
        '',
        '## 总评',
        data['overall'] or '暂无',
        '',
        '## 建议',
    ]
    lines.extend((f'- {s}' for s in data['suggestions'])) if data['suggestions'] else lines.append('暂无')
    lines.append('')
    lines.append('## 详细评分')
    for dim in data['dimensions']:
        name = dim.get('name', '')
        lines.append(f"- {name}方面：{dim.get('score', '')}/{dim.get('max_score', '')}")
    if not data['dimensions']:
        lines.append('暂无')
    lines.append('')
    lines.append('## 好词好句')
    lines.extend((f'- {h}' for h in data['highlights'])) if data['highlights'] else lines.append('暂无')
    lines.append('')
    lines.append('## 错词错句')
    if data['corrections']:
        for item in data['corrections']:
            lines.append(f"- 原句：{item.get('quote', '')}；建议：{item.get('suggestion', '')}")
    else:
        lines.append('无确定错别字/语病（以图片识别为准）')
    lines.append('')
    lines.append('## 改写开头与结尾')
    rw = data['rewrites'] or {}
    if rw.get('title'):
        lines.append(f"- 候选标题：{rw['title']}")
    op = rw.get('opening') or []
    lines.append('- 三个开头候选：')
    lines.extend((f'  1. {c}' for c in op)) if op else lines.append('  N/A（未生成）')
    en = rw.get('ending') or []
    lines.append('- 三个结尾候选：')
    lines.extend((f'  1. {c}' for c in en)) if en else lines.append('  N/A（未生成）')
    # 润色纳入报告，保持与 PDF 同源
    if data['polished_text']:
        lines.extend(['', '## 作文润色'])
        if data['polished_title']:
            lines.extend(['', f'**{data["polished_title"]}**', ''])
        lines.extend(p for p in str(data['polished_text']).splitlines() if p.strip())
    lines.extend(['', f'导出时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}'])
    return '\n'.join(lines), f"{safe_filename(data['title'])}.md"


def _md_inline(text):
    """把 Markdown 行转成 reportlab 可渲染的内联文本。

    - 先转义 & < >，再识别 **加粗** 为 <b>…</b>，避免转义破坏加粗标签。
    """
    s = str(text or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
    return s


def export_pdf(record):
    """
    把同一份 Markdown 报告转换为排版后的 PDF（MD → PDF 真正同源，零漂移）。

    先调用 export_markdown 得到结构化 MD 文本，再用 reportlab 按行解析渲染，
    只关心我们生成报告中出现的语法（# 标题 / ## 分节 / - 列表 / 数字列表 / 加粗）。
    """
    md_text, _ = export_markdown(record)
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))

    margin = 18 * mm
    title_style = ParagraphStyle('t', fontName='STSong-Light', fontSize=16, leading=24,
                                 spaceAfter=10, alignment=1)  # 居中
    meta_style = ParagraphStyle('m', fontName='STSong-Light', fontSize=9, leading=14,
                                textColor='#5f6368', spaceAfter=6, alignment=1)
    h_style = ParagraphStyle('h', fontName='STSong-Light', fontSize=12.5, leading=19,
                             spaceBefore=12, spaceAfter=6, textColor='#1a73e8')
    body_style = ParagraphStyle('b', fontName='STSong-Light', fontSize=10, leading=17, spaceAfter=3)
    item_style = ParagraphStyle('i', parent=body_style, leftIndent=10)
    num_style = ParagraphStyle('n', parent=body_style, leftIndent=20)

    story = []
    heading_count = 0
    for raw in md_text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            story.append(Spacer(1, 4))
            continue
        if line.startswith('# '):
            story.append(Paragraph(_md_inline(line[2:]), title_style))
        elif line.startswith('## '):
            heading_count += 1
            story.append(Paragraph(f'<font color="#1a73e8"><b>{_md_inline(line[3:])}</b></font>', h_style))
        elif line.startswith('#') and line.lstrip('#').strip():
            # 其他 # 级别标题兜底，按一级节标题渲染
            story.append(Paragraph(f'<font color="#1a73e8"><b>{_md_inline(line.lstrip("#").strip())}</b></font>', h_style))
        elif line.lstrip().startswith('- '):
            story.append(Paragraph('•&nbsp; ' + _md_inline(line.lstrip('- ').strip()), item_style))
        elif re.match(r'^\s*\d+\.\s+', line):
            story.append(Paragraph(_md_inline(line.strip()), num_style))
        else:
            story.append(Paragraph(_md_inline(line), body_style))

    # 若完全没有分节则给个占位，避免导出空白 PDF（正常报告不会走到）
    if heading_count == 0:
        story.append(Paragraph('（该报告未生成分节内容）', body_style))

    story.append(Spacer(1, 8))
    story.append(Paragraph(f'导出时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}',
                           ParagraphStyle('ft', parent=meta_style, alignment=1)))

    buffer = io.BytesIO()
    SimpleDocTemplate(buffer, pagesize=A4,
                      leftMargin=margin, rightMargin=margin,
                      topMargin=16 * mm, bottomMargin=16 * mm).build(story)
    return buffer.getvalue()