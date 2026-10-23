"""
降级调用所需的提示词装配

背景：
    咨询链路有多级降级：Agent（带工具与图编排）→ 直接调用模型 → 简化提示词。
    此前的降级直接 `model.invoke(prompt)`，system prompt 完全丢失——角色设定、
    "学情数字不得自行推算"、"不要编造片段出处"等硬约束在降级后全部失效，
    同一个知识库会给出两套口径不同的回答；Agent 内部兜底甚至连历史轮次也丢了。

原则：
    降级可以降"能力"（没有工具、没有图编排），但不能降"约束"。
    这里把「系统提示词 + 消息序列」的组装收敛到一处，避免多条降级路径各写一遍。
"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from utils.logger_handler import logger
from utils.prompt_loader import load_system_prompts


def system_message():
    """
    读取系统提示词并包装成 SystemMessage。

    返回：
        SystemMessage|None - 提示词为空或读取失败时返回 None——
        降级调用不应因为提示词文件问题而整体失败，宁可少一条约束也要给出回答。
    """
    try:
        text = load_system_prompts()
    except Exception as exc:
        logger.error('[降级调用] 系统提示词加载失败，本次调用将不带系统提示: %s', exc)
        return None
    text = (text or '').strip()
    return SystemMessage(content=text) if text else None


def to_chat_messages(turns):
    """
    把 [{'role': 'user'|'assistant', 'content': str}] 转成 LangChain 消息列表。

    跳过空正文；非 assistant 的角色一律按用户消息处理（宁可多带一条，
    也不要在降级时把上下文丢掉）。
    """
    messages = []
    for turn in turns or []:
        if not isinstance(turn, dict):
            continue
        content = (turn.get('content') or '').strip()
        if not content:
            continue
        if turn.get('role') == 'assistant':
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    return messages
