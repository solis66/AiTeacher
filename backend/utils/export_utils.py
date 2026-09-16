"""
导出工具

提供批改结果的 PDF 导出。

实现说明：
- PDF：reportlab + 内置中文字体 STSong-Light（CID 字体，无需外部字体文件），
  避免服务器缺少字体文件导致的导出失败。
"""

import io
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def _payload(record):
    """
    把批改记录整理成“导出用的扁平结构”。

    注意：导出必须以**已保存版本**（record['result']）为准，未保存的临时编辑不参与导出。
    """
    inp = record.get('input', {})
    result = record.get('result') or {}
    return {
        'title': inp.get('title') or '未命名作文',
        'grade': inp.get('grade', ''),
        'essay_type': inp.get('essay_type', ''),
        'word_count': result.get('word_count', 0),
        'score': result.get('score'),
        'total_score': result.get('total_score', 50),
        'rating': result.get('rating', ''),
        'dimensions': result.get('dimensions', []),
        'overall': result.get('overall_comment', ''),
        'rewrites': result.get('rewrites', {}),
        'corrections': result.get('corrections', []),
        'analysis': result.get('analysis', {}),
        'highlights': result.get('highlights', []),
        'suggestions': result.get('suggestions', []),
        'polished_title': result.get('polished_title', ''),
        'polished_text': result.get('polished_text', ''),
    }


# 详细点评中 AI 分析的中文标签
ANALYSIS_LABELS = {
    'content': '内容', 'structure': '结构', 'language': '语言',
    'technique': '技巧', 'emotion': '情感',
}


def export_pdf(record):
    """生成 PDF 文档，返回 bytes。"""
    data = _payload(record)
    # 注册内置中文 CID 字体（无需字体文件，跨机器稳定）
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))

    title_style = ParagraphStyle('t', fontName='STSong-Light', fontSize=16, leading=22, spaceAfter=6)
    h_style = ParagraphStyle('h', fontName='STSong-Light', fontSize=12, leading=18,
                             spaceBefore=10, spaceAfter=4, textColor='#1a73e8')
    body_style = ParagraphStyle('b', fontName='STSong-Light', fontSize=10, leading=16, spaceAfter=2)

    def esc(text):
        # reportlab 使用类 HTML 标记，需转义特殊字符
        return (str(text or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))

    story = [
        Paragraph(f"{esc(data['title'])}｜作文批改报告", title_style),
        Paragraph(esc(f"年级：{data['grade']}　体裁：{data['essay_type']}　字数：{data['word_count']}　"
                      f"得分：{data['score']}/{data['total_score']}（{data['rating']}）"), body_style),
    ]

    story.append(Paragraph('一、总评', h_style))
    story.append(Paragraph(esc(data['overall']).replace('\n', '<br/>'), body_style))

    if data['dimensions']:
        story.append(Paragraph('二、各项评分', h_style))
        for dim in data['dimensions']:
            story.append(Paragraph(esc(f"· {dim.get('name', '')}：{dim.get('score', '')}/{dim.get('max_score', '')}"), body_style))

    rewrites = data['rewrites'] or {}
    if any(rewrites.values()):
        story.append(Paragraph('三、吸睛改写', h_style))
        for label, key in [('标题', 'title'), ('开头', 'opening'), ('结尾', 'ending')]:
            if rewrites.get(key):
                story.append(Paragraph(esc(f"【{label}】{rewrites[key]}").replace('\n', '<br/>'), body_style))

    if data['corrections']:
        story.append(Paragraph('四、原文纠正', h_style))
        for item in data['corrections']:
            story.append(Paragraph(esc(f"原句：{item.get('quote', '')}").replace('\n', '<br/>'), body_style))
            story.append(Paragraph(esc(f"建议：{item.get('suggestion', '')}").replace('\n', '<br/>'), body_style))

    analysis = data['analysis'] or {}
    if any(analysis.values()):
        story.append(Paragraph('五、AI 分析', h_style))
        for key, label in ANALYSIS_LABELS.items():
            if analysis.get(key):
                story.append(Paragraph(esc(f"【{label}】{analysis[key]}").replace('\n', '<br/>'), body_style))

    if data['highlights']:
        story.append(Paragraph('六、文章亮点', h_style))
        for item in data['highlights']:
            story.append(Paragraph(esc('· ' + item), body_style))

    if data['suggestions']:
        story.append(Paragraph('七、改进建议', h_style))
        for item in data['suggestions']:
            story.append(Paragraph(esc('· ' + item), body_style))

    if data['polished_text']:
        story.append(Paragraph('八、全文润色', h_style))
        if data['polished_title']:
            story.append(Paragraph(esc(data['polished_title']), body_style))
        for para in str(data['polished_text']).splitlines():
            if para.strip():
                story.append(Paragraph(esc(para), body_style))

    story.append(Spacer(1, 8))
    story.append(Paragraph(esc(f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"), body_style))

    buffer = io.BytesIO()
    SimpleDocTemplate(buffer, pagesize=A4,
                      leftMargin=18 * mm, rightMargin=18 * mm,
                      topMargin=16 * mm, bottomMargin=16 * mm).build(story)
    return buffer.getvalue()
