"""
对话记忆（P0）

把最近若干轮问答裁剪成可安全注入提示词的形态，让咨询链路具备上下文衔接能力。
此前 ConsultationService.answer_question 只接收单个问题字符串，ReactAgent 也只构造
{"messages": [{"role": "user", "content": query}]}，历史对话从不进入模型——
用户问「那我上一条说的那个问题呢」时，模型完全不知道在指什么。

设计约束：
- 只做短期上下文衔接，不做长期画像（画像属 P1，另建 memory_profile 表）
- 全部上限在服务端强制：前端传来的轮次与长度只作参考，一律重新裁剪
- 只保留有正文的有效轮次，批改卡片 / 加载占位消息一律丢弃
- 单条正文截断，避免整篇作文把上下文撑爆（一篇作文 800 字 ≈ 全预算的一半）
- 任何非法输入都退化成空列表，绝不抛异常——记忆缺失不该让对话失败
"""

# 最多保留的消息条数（约 3 轮问答）
MAX_MESSAGES = 6
# 单条正文最大字符数
MAX_CHARS_PER_MESSAGE = 500
# 全部记忆正文合计上限
MAX_TOTAL_CHARS = 2000

ROLE_LABELS = {'user': '学生', 'assistant': '老师'}
VALID_ROLES = ('user', 'assistant')


def _clip(text, limit):
    """按字符数截断，并留下明确的省略标记（不静默丢内容）。"""
    text = (text or '').strip()
    if len(text) <= limit:
        return text
    return text[:limit] + '……（后略）'


def normalize_history(raw):
    """
    把前端传来的历史裁剪成规范形态。

    参数：
        raw: 任意输入，期望为 [{'role': 'user'|'assistant', 'content': str}, ...]

    返回：
        list[dict]: [{'role': str, 'content': str}, ...]，按时间正序（最旧在前）

    裁剪顺序：
        1. 丢弃 role 非法、content 为空、非 dict 的条目
        2. 单条正文按 MAX_CHARS_PER_MESSAGE 截断
        3. 只取最近 MAX_MESSAGES 条
        4. 从最旧一侧收敛，直到总长度不超 MAX_TOTAL_CHARS
    """
    if not isinstance(raw, list):
        return []

    cleaned = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = item.get('role')
        if role not in VALID_ROLES:
            continue
        content = _clip(item.get('content'), MAX_CHARS_PER_MESSAGE)
        if not content:
            continue
        cleaned.append({'role': role, 'content': content})

    # 只保留最近若干条
    cleaned = cleaned[-MAX_MESSAGES:]

    # 总长度收敛：从最新一条往回累积，超预算就丢掉更早的
    total = 0
    kept = []
    for turn in reversed(cleaned):
        total += len(turn['content'])
        if total > MAX_TOTAL_CHARS:
            break
        kept.append(turn)
    return list(reversed(kept))


def build_history_block(history):
    """
    渲染成提示词里的文本块。

    仅供「无法传递 messages 数组」的直接调用模型路径使用
    （consultation_service._generate_ai_response 的方式 2 / 3 降级分支）。
    走 ReactAgent 的主路径应改用 execute_stream(query, history)，
    把历史作为真实消息前置，让模型能区分学生发言与既往回答。

    没有可用轮次时返回空串，调用方无需额外分支。
    """
    if not history:
        return ''
    lines = [f"{ROLE_LABELS[turn['role']]}：{turn['content']}" for turn in history]
    return (
        '【本会话此前的对话】以下内容仅用于衔接上下文，不是新的提问，'
        '不要重复回答其中的问题：\n' + '\n'.join(lines) + '\n\n'
    )
