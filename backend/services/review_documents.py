"""
作文材料处理模块

职责：
1. 上传文件真实性校验（图片仅 JPG、PDF 必须未加密且页数受限）
2. 分页渲染：把 PDF / 图片 / 纯文字统一转成带真实文字行坐标的页面
3. OCR：调用阿里云文字识别（手写体识别）获取文字与行位置
4. 定位：把 AI 引用的原句映射回页面坐标（仅接受唯一匹配，绝不伪造位置）

设计约束（对应需求）：
- 坐标一律保存为相对值（0~1），这样前端缩放、旋转后仍能保持对齐。
- OCR 失败必须抛出可读的中文原因，由上层展示错误状态，不得返回编造文本。
"""

import io
import json
import os
import re
from pathlib import Path

# PyMuPDF：新版包名 pymupdf，旧版为 fitz，做兼容导入
try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover - 兼容旧安装
    import fitz

from PIL import Image, ImageOps, ImageDraw, ImageFont

from utils.watermark_cleaner import clean_watermarks

# Windows 上若宿主未继承系统级环境变量，这里补齐 OCR 凭据，避免误报“未配置凭据”
from utils.win_env import load as _load_win_env

# 限制：一次上传的图片/PDF 属于同一篇作文，单篇最多 3 张/页、单个附件最大 20MB
# （一次请求的全部附件合并为一条批改记录，为后续“批量批改”按作文分组扩展预留）
MAX_PAGES = 3
MAX_BYTES = 20 * 1024 * 1024
# 纯文字排版参数（用于把无附件的正文生成可批注页面）
TEXT_PAGE_W, TEXT_PAGE_H = 1000, 1400
TEXT_LINE_CHARS = 32
TEXT_LINES_PER_PAGE = 26


def font(size=28):
    """
    加载可显示中文的字体，用于把纯文字正文渲染成图片页面。

    背景（这是一个真实事故的修复）：
        纯文字正文（无附件）批改时必须把正文渲染成 page-N.jpg 才能进中栏画布，
        这一步依赖中文字体。部署用的 python:3.11-slim 镜像本身不含任何中文字体，
        Dockerfile 又没装 —— 结果是「粘贴正文点批改」100% 失败，报「缺少中文字体」；
        而图片批改走 OCR 不需要字体，所以一直是好的，很容易误判成"批改功能偶尔坏"。
        修复分两处：Dockerfile 安装 fonts-wqy-zenhei（见该文件注释），以及本函数增强探测。

    探测顺序：环境变量 → Windows 字体 → Linux 常见中文字体 → 扫描字体目录兜底。
    """
    candidates = [
        os.getenv('REVIEW_FONT_PATH', ''),
        'C:/Windows/Fonts/msyh.ttc',
        'C:/Windows/Fonts/msyhbd.ttc',
        'C:/Windows/Fonts/simhei.ttf',
        'C:/Windows/Fonts/simsun.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc',
        '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/arphic/uming.ttc',
        '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
    ]
    for path in candidates:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size)

    # 兜底：有些基础镜像把字体装在别处，按文件名特征扫一遍常见目录，
    # 避免因为路径不同就报"缺字体"。
    import glob
    keywords = ('cjk', 'wqy', 'zenhei', 'microhei', 'uming', 'ukai', 'droidsansfallback')
    for pattern in ('/usr/share/fonts/**/*.ttc',
                    '/usr/share/fonts/**/*.otf',
                    '/usr/share/fonts/**/*.ttf'):
        for path in sorted(glob.glob(pattern, recursive=True)):
            if any(k in os.path.basename(path).lower() for k in keywords):
                try:
                    return ImageFont.truetype(path, size)
                except OSError:
                    continue

    raise ValueError(
        '服务器缺少中文字体，无法生成作文正文页面。'
        '请在部署镜像中安装中文字体（Debian/Ubuntu：apt-get install -y fonts-wqy-zenhei），'
        '或用 REVIEW_FONT_PATH 环境变量指定字体文件路径后重启服务。'
    )


def validate_upload(name, raw):
    """
    校验上传文件的真实格式（不信任扩展名与前端声明）。

    参数：
        name: 原始文件名
        raw:  文件二进制内容

    返回：
        str: 规范化后的后缀（.jpg / .pdf）

    异常：
        ValueError: 校验不通过，消息为面向用户的中文提示
    """
    suffix = Path(name).suffix.lower()
    if len(raw) > MAX_BYTES:
        raise ValueError('单个文件不能超过20MB')

    if suffix == '.pdf':
        try:
            with fitz.open(stream=raw, filetype='pdf') as pdf:
                if pdf.is_encrypted or not 0 < len(pdf) <= MAX_PAGES:
                    raise ValueError()
        except Exception as exc:
            raise ValueError(f'请上传未加密的有效PDF，最多{MAX_PAGES}页') from exc
    else:
        try:
            # 需求：图片只允许 JPG，其他格式统一提示
            if suffix != '.jpg':
                raise ValueError()
            with Image.open(io.BytesIO(raw)) as img:
                # 必须真实解码为 JPEG，避免改扩展名的绕过
                if img.format != 'JPEG' or img.width * img.height > 25_000_000:
                    raise ValueError()
                img.verify()
        except Exception as exc:
            raise ValueError('请重新输入jpg格式的图片') from exc
    return suffix


def recognize(path):
    """
    调用阿里云 OCR（手写体识别）识别单张图片。

    说明：
        - 使用 RecognizeHandwriting，禁用自动旋转以保留原图坐标体系。
        - 只把返回的坐标做归一化，不做任何猜测性补全。

    返回：
        (str, list[dict]): (整篇文本, 行列表[{text, box:[x,y,w,h]}])

    异常：
        ValueError: 凭据缺失或调用失败，消息为可直接展示给用户的中文说明
    """
    from alibabacloud_ocr_api20210707.client import Client
    from alibabacloud_ocr_api20210707.models import RecognizeHandwritingRequest
    from alibabacloud_tea_openapi.models import Config
    from alibabacloud_tea_util.models import RuntimeOptions

    _load_win_env(['ALIBABA_CLOUD_ACCESS_KEY_ID', 'ALIBABA_CLOUD_ACCESS_KEY_SECRET'])
    key = os.getenv('ALIBABA_CLOUD_ACCESS_KEY_ID')
    secret = os.getenv('ALIBABA_CLOUD_ACCESS_KEY_SECRET')
    if not key or not secret:
        raise ValueError('阿里云OCR尚未配置凭据（ALIBABA_CLOUD_ACCESS_KEY_ID / ACCESS_KEY_SECRET），配置后可重试。')

    client = Client(Config(access_key_id=key, access_key_secret=secret,
                           endpoint='ocr-api.cn-hangzhou.aliyuncs.com'))
    try:
        with open(path, 'rb') as stream:
            response = client.recognize_handwriting_with_options(
                RecognizeHandwritingRequest(body=stream, need_rotate=False, paragraph=True),
                RuntimeOptions(read_timeout=60000, connect_timeout=10000))
    except Exception as exc:
        # 把阿里云的错误码翻译成用户能看懂、能行动的提示，避免把原始堆栈抛给前端
        message = str(exc)
        if 'ocrServiceNotOpen' in message:
            raise ValueError('阿里云账号尚未开通“文字识别 OCR”服务，开通后可重试。') from exc
        if 'noPermission' in message:
            raise ValueError('当前 AccessKey 没有调用 OCR 的权限，请为该 RAM 用户授予 AliyunOCRFullAccess 策略后重试。') from exc
        if 'InvalidAccessKeyId' in message or 'SignatureDoesNotMatch' in message:
            raise ValueError('阿里云 AccessKey 无效或密钥不匹配，请检查环境变量后重试。') from exc
        raise ValueError(f'OCR识别失败：{message[:200]}') from exc

    data = json.loads(response.body.data)
    width, height = float(data['width']), float(data['height'])
    lines = []
    for item in data.get('prism_wordsInfo', []):
        points = item.get('pos', [])
        if not points or not item.get('word'):
            continue
        xs, ys = [p['x'] / width for p in points], [p['y'] / height for p in points]
        lines.append({'text': item['word'],
                      'box': [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]})
    text = '\n'.join(p['word'] for p in data.get('prism_paragraphsInfo', []) if p.get('word'))
    return text or data.get('content', '') or '\n'.join(line['text'] for line in lines), lines


def text_pages(text, directory):
    """
    纯文字正文：渲染成固定尺寸页面，同时记录每行真实绘制位置。

    这样即使没有附件，中栏也能展示“原文 + 批注”并有准确的批注坐标。
    """
    lines = []
    for paragraph in text.splitlines():
        paragraph = paragraph.strip()
        if paragraph:
            lines.extend([paragraph[i:i + TEXT_LINE_CHARS] for i in range(0, len(paragraph), TEXT_LINE_CHARS)])
        lines.append('')

    pages = []
    for start in range(0, len(lines), TEXT_LINES_PER_PAGE):
        image = Image.new('RGB', (TEXT_PAGE_W, TEXT_PAGE_H), 'white')
        draw = ImageDraw.Draw(image)
        line_font = font(28)
        boxes = []
        for n, line in enumerate(lines[start:start + TEXT_LINES_PER_PAGE]):
            y = 70 + n * 48
            draw.text((52, y), line, font=line_font, fill='#20252b')
            if line:
                boxes.append({
                    'text': line,
                    'box': [0.052, y / TEXT_PAGE_H,
                            min(0.90, draw.textlength(line, font=line_font) / TEXT_PAGE_W),
                            34 / TEXT_PAGE_H],
                })
        name = f'page-{len(pages) + 1}.jpg'
        image.save(directory / name, quality=94)
        pages.append({'file': name, 'width': TEXT_PAGE_W, 'height': TEXT_PAGE_H,
                      'text': '\n'.join(lines[start:start + TEXT_LINES_PER_PAGE]), 'lines': boxes})
    return pages


def prepare_pages(record, directory):
    """
    把记录中的附件统一转成“页面”列表。

    处理策略：
        - PDF：优先取自带文字层（矢量 PDF 精度最高）；无文字层才走 OCR
        - JPG：一律走 OCR（手写作文图片）
        - 无附件：把正文渲染成分页图片
    """
    if not record['attachments']:
        return text_pages(record['input']['body'], directory)

    pages = []
    for attachment in record['attachments']:
        path = directory / attachment['file']
        if path.suffix == '.pdf':
            with fitz.open(path) as pdf:
                for page in pdf:
                    if len(pages) >= MAX_PAGES:
                        raise ValueError(f'一篇作文最多{MAX_PAGES}张图片/页')
                    name = f'page-{len(pages) + 1}.jpg'
                    pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                    pix.save(directory / name)
                    # 抽取文字层行坐标
                    lines = []
                    for block in page.get_text('dict')['blocks']:
                        for line in block.get('lines', []):
                            text = ''.join(s['text'] for s in line['spans'])
                            x0, y0, x1, y1 = line['bbox']
                            lines.append({'text': text, 'box': [x0 / page.rect.width, y0 / page.rect.height,
                                                                (x1 - x0) / page.rect.width,
                                                                (y1 - y0) / page.rect.height]})
                    text = page.get_text()
                    if not text.strip():
                        # 扫描版 PDF 没有文字层，降级到 OCR
                        text, lines = recognize(directory / name)
                    # 平台水印清洗：OCR/文字层文本都过一遍，防止水印混入批改输入
                    cleaned = clean_watermarks(text, lines)
                    text, lines = cleaned['text'], cleaned['lines']
                    pages.append({'file': name, 'width': pix.width, 'height': pix.height,
                                  'text': text, 'lines': lines, 'watermarks': cleaned['findings']})
        else:
            if len(pages) >= MAX_PAGES:
                raise ValueError(f'一篇作文最多{MAX_PAGES}张图片/页')
            name = f'page-{len(pages) + 1}.jpg'
            with Image.open(path) as image:
                # 按 EXIF 纠正方向后再保存，确保坐标与展示一致
                image = ImageOps.exif_transpose(image).convert('RGB')
                image.save(directory / name, quality=95)
                width, height = image.size
            text, lines = recognize(directory / name)
            # 平台水印清洗（JPG 手写作文图片的主要入口）
            cleaned = clean_watermarks(text, lines)
            text, lines = cleaned['text'], cleaned['lines']
            pages.append({'file': name, 'width': width, 'height': height, 'text': text,
                          'lines': lines, 'watermarks': cleaned['findings']})
    return pages


def locate(quote, pages, page_number=None):
    """
    把 AI 引用的原句定位到页面坐标。

    规则（对应需求“缺失的分析显示明确状态，不以示例内容代替”）：
        - 只在页面行文本拼接后做匹配
        - 仅接受“唯一命中”，歧义（多页/多处命中）与未命中都返回空坐标
        - 指定页码时只在该页查找

    返回：
        (int|None, list): (页码, 该句覆盖到的行坐标列表)
    """
    normalize = lambda text: re.sub(r'\s+', '', text)
    query = normalize(quote)
    if not query:
        return None, []

    matches = []
    for index, page in enumerate(pages):
        if page_number and index + 1 != page_number:
            continue
        text = ''.join(normalize(line['text']) for line in page['lines'])
        start = text.find(query)
        # 出现两次及以上视为歧义，放弃定位
        if start < 0 or text.find(query, start + 1) >= 0:
            continue
        offset, boxes = 0, []
        for line in page['lines']:
            end = offset + len(normalize(line['text']))
            if end > start and offset < start + len(query):
                boxes.append(line['box'])
            offset = end
        matches.append((index + 1, boxes))

    return matches[0] if len(matches) == 1 else (None, [])


def locate_origin(quote, pages, page_number=None):
    """
    定位 AI 引用的原句，返回命中的「真实 OCR 行文本」（与图片原文一致）。

    与 locate 共享同一套唯一命中规则（消除空白后全文匹配、仅接受唯一命中），
    区别在于：locate 只返回坐标（用于图上画框），本函数返回被该句覆盖到的
    OCR 行的原始文本拼接——供「原文纠正」以图片中的原文为准来展示。

    返回：
        (int|None, str): (页码, 覆盖到该句的 OCR 行文本；未命中时字符串为空)
    """
    normalize = lambda text: re.sub(r'\s+', '', text)
    query = normalize(quote)
    if not query:
        return None, ''

    matches = []
    for index, page in enumerate(pages):
        if page_number and index + 1 != page_number:
            continue
        joined = ''.join(normalize(line['text']) for line in page['lines'])
        start = joined.find(query)
        # 出现两次及以上视为歧义，放弃定位
        if start < 0 or joined.find(query, start + 1) >= 0:
            continue
        # 收集被该句覆盖到的行（保留 OCR 原始文本，跨多行用换行连接）
        offset, lines_hit = 0, []
        for line in page['lines']:
            end = offset + len(normalize(line['text']))
            if end > start and offset < start + len(query):
                lines_hit.append(line['text'])
            offset = end
        matches.append((index + 1, '\n'.join(lines_hit)))

    return matches[0] if len(matches) == 1 else (None, '')
