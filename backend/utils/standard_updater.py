"""
评分标准自动更新工具（手动运行）

把「更新的评分标准 Word 文档」喂给 AI，AI 按约束的 JSON schema 返回结构化内容，
再还原为与 standard_loader 兼容的 .txt 评分标准文本并写回 data 目录。

为什么做这一步：
    评分标准是批改的“统一依据”。原流程需要人工整理 .doc 内容、手写 .txt。
    本工具把「任意格式的 .doc → 结构化标准」交给 AI 完成，人工只需审阅 AI
    生成的 JSON 与最终 txt，减少手工排版。

用法（需在 Windows + 已装 Word + 配置好 DASHSCOPE_API_KEY 的开发机运行）：
    python -m utils.standard_updater "新评分标准.doc"
    可选：--dry-run 只打印 AI 返回的 JSON 与将写入的 txt，不落盘。

注意：
    - 写入 .txt 后，其 mtime 更新为当前时间（晚于 .doc），standard_loader
      会优先用新 .txt（Windows 与 Linux 一致生效）。
    - 本工具只改 .txt，不改 .doc；.doc 仅作为输入源。
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

from openai import OpenAI

# 保证可直接运行：python -m utils.standard_updater
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.security_config import get_dashscope_api_key
from utils.standard_loader import STANDARD_TXT

# 与 config/rag.yaml 保持一致（若文件存在则取其值，否则用默认）
BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
CHAT_MODEL = 'qwen3.8-max-0902'


def _load_model_config():
    """从 config/rag.yaml 读取 base_url 与 chat_model_name，缺省用默认值。"""
    global BASE_URL, CHAT_MODEL
    try:
        import yaml
        cfg_path = Path(__file__).resolve().parent.parent / 'config' / 'rag.yaml'
        if cfg_path.exists():
            cfg = yaml.safe_load(cfg_path.read_text(encoding='utf-8')) or {}
            BASE_URL = cfg.get('base_url') or BASE_URL
            CHAT_MODEL = cfg.get('chat_model_name') or CHAT_MODEL
    except Exception as exc:  # 读失败不阻断，用默认值
        print(f'[评分标准更新] 读取 rag.yaml 失败，沿用默认模型配置: {exc}')


# 约束的 JSON schema（AI 必须原样返回，键名固定）
SCHEMA = {
    '考纲要求': ['考纲要求的逐条文本'],
    '满分': 50,
    '作文等级': [
        {
            '等级': '一类卷',
            '分数范围': '50~45',
            '要求': ['该等级逐条要求文本'],
        }
    ],
    '加分': ['加分项逐条文本（不含“加1~3分”总述，总述见 prompt）'],
    '扣分': ['扣分项逐条文本'],
}


def _extract_doc_text(doc_path: Path) -> str:
    """通过 Word COM 提取 .doc 纯文本（仅 Windows + 已装 Word 可用）。"""
    try:
        import win32com.client
    except ImportError as exc:
        raise SystemExit(
            f'提取 .doc 需要 Windows 且已安装 Word（pywin32）。当前环境：{exc}'
        ) from exc
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


def build_prompt(doc_text: str) -> str:
    """构造要求 AI 返回固定 JSON 的提示词。"""
    return f'''请把下面这份“中考作文评分标准”文档整理成结构化 JSON。要求：
- 只输出一个 JSON 对象，不要任何解释、不要代码围栏（```）、不要多余文字。
- JSON 的键必须严格使用以下结构（键名与小节对应）：

{json.dumps(SCHEMA, ensure_ascii=False, indent=2)}

其中：
- 考纲要求：文档开头“考纲要求”下的逐条要求文本数组。
- 满分：满分分值（整数，通常 50）。
- 作文等级：按“一类卷/二类卷/.../五类卷”逐级列出，等级名去掉括号分数，分数放进“分数范围”，
  每条分档要求放进“要求”数组，原文编号（1. 2. 3.）保留在文本里。
- 加分：只列加分项条目本身（如“立意深刻”），不要包含“符合如下条件之一...加1~3分”这段总述。
- 扣分：扣分项逐条文本，保留原文编号（1. 2. ...）。
- 内容忠于原文，不要增删改评分规则；标点保持原文档写法。

待整理文档原文：
=====
{doc_text}
=====
'''


def call_ai(prompt: str) -> str:
    """调用兼容模式对话模型，返回其回复文本。期望为纯净 JSON。"""
    api_key = get_dashscope_api_key()
    if not api_key:
        raise SystemExit('未配置 DASHSCOPE_API_KEY，请先配置环境变量后再运行。')
    client = OpenAI(api_key=api_key, base_url=BASE_URL)
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{'role': 'user', 'content': prompt}],
        response_format={'type': 'json_object'},
        temperature=0.0,
    )
    return resp.choices[0].message.content


def parse_json(text: str) -> dict:
    """从模型输出中稳健提取 JSON 对象。"""
    if not text:
        raise ValueError('AI 返回为空，无法解析 JSON')
    # 去代码围栏
    text = re.sub(r'```(?:json)?', '', text).strip()
    start, end = text.find('{'), text.rfind('}')
    if start == -1 or end == -1 or end <= start:
        raise ValueError('模型输出中未找到可解析的 JSON 对象')
    return json.loads(text[start:end + 1])


def json_to_txt(data: dict) -> str:
    """把结构化的标准 JSON 还原为 standard_loader 兼容的 .txt 明文。"""
    lines = []
    lines.append('中考作文考纲要求及评分标准')
    lines.append('考纲要求')
    # 考纲要求条目
    for item in data.get('考纲要求', []):
        lines.append(str(item).strip())
    # 评分标准等级
    lines.append('作文等级')
    lines.append('评分标准')
    for level in data.get('作文等级', []):
        lines.append(str(level.get('等级', '')).strip())
        lines.append(f'（{level.get("分数范围", "")}）')
        for req in level.get('要求', []):
            lines.append(str(req).strip())
    # 加分
    lines.append('加分')
    lines.append('符合如下条件之一，可酌情加1~3分(加至本题满分为止)')
    for item in data.get('加分', []):
        lines.append(str(item).strip())
    # 扣分
    lines.append('扣分')
    for item in data.get('扣分', []):
        lines.append(str(item).strip())
    return '\n'.join(lines)


def update_standard_from_doc(doc_path: str, dry_run: bool = False) -> str:
    """
    一键流程：提取 .doc → AI 生成约束 JSON → 还原 txt → 写回（或 dry-run 打印）。
    返回生成的 .txt 全文。
    """
    dp = Path(doc_path)
    if not dp.exists():
        raise SystemExit(f'文档不存在: {dp}')
    _load_model_config()

    print(f'[步骤 1/4] 从 Word 提取文本: {dp}')
    doc_text = _extract_doc_text(dp)
    if not doc_text.strip():
        raise SystemExit('Word 文档内容为空，无法解析')

    print(f'[步骤 2/4] 调用 AI（{CHAT_MODEL}）生成约束 JSON…')
    prompt = build_prompt(doc_text)
    raw = call_ai(prompt)
    data = parse_json(raw)
    print(f'[步骤 3/4] 解析 JSON 成功，等级数: {len(data.get("作文等级", []))}')

    txt = json_to_txt(data)
    if dry_run:
        print('[--dry-run--] 不会写盘。AI JSON 如下：')
        print(json.dumps(data, ensure_ascii=False, indent=2))
        print('[--dry-run--] 将写入的 .txt 如下：')
        print(txt)
        return txt

    STANDARD_TXT.parent.mkdir(parents=True, exist_ok=True)
    STANDARD_TXT.write_text(txt, encoding='utf-8')
    print(f'[步骤 4/4] 已写入 {STANDARD_TXT}（{len(txt.encode("utf-8"))} 字节）')
    return txt


def main():
    parser = argparse.ArgumentParser(description='AI 辅助更新评分标准 .txt')
    parser.add_argument('doc', help='更新的评分标准 .doc 文件路径')
    parser.add_argument('--dry-run', action='store_true', help='只打印结果，不写盘')
    args = parser.parse_args()
    update_standard_from_doc(args.doc, dry_run=args.dry_run)


if __name__ == '__main__':
    main()