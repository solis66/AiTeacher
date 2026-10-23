from langchain.agents import AgentState
from langchain.agents.middleware import wrap_tool_call, wrap_model_call, before_model
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from typing import Callable
from utils.logger_handler import logger
from langgraph.types import Command
from langgraph.runtime import Runtime
from utils.config_handler import agent_conf

# 单次问答允许执行的工具调用次数。
# 计数来源是本轮 Agent 状态里已有的 ToolMessage：每执行一次工具就多一条，
# 天然按「本轮」隔离——不需要 contextvars 或实例变量，多线程并发也不会串味。
MAX_TOOL_CALLS = max(1, int((agent_conf or {}).get('agent_max_tool_calls', 2)))
TOOL_LIMIT_MESSAGE = (
    f'本轮已执行 {MAX_TOOL_CALLS} 次工具调用，达到上限。'
    '不要再调用工具，请基于已获得的资料和通用教学常识直接作答。'
)


def _tool_result_count(state):
    """统计本轮已产生的工具结果条数（Agent 状态里的 ToolMessage）。"""
    messages = state.get('messages') if isinstance(state, dict) else getattr(state, 'messages', None)
    return sum(1 for message in (messages or []) if isinstance(message, ToolMessage))


@wrap_tool_call
def monitor_tool(
        # 请求的数据封装
        request: ToolCallRequest,
        # 执行的函数本身
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
) -> ToolMessage | Command:      # 工具执行的监控
    logger.info(f"[tool monitor]执行工具{request.tool_call['name']}")
    logger.info(f"[tool monitor]传入参数{request.tool_call['args']}")

    # 超限时不执行工具，直接把「已达上限」作为工具结果回给模型，
    # 让模型基于已有资料收尾作答，而不是反复检索拖到图步数超限。
    if _tool_result_count(request.state) >= MAX_TOOL_CALLS:
        logger.warning(
            '[tool monitor] 工具调用已达上限(%s)，跳过执行 %s',
            MAX_TOOL_CALLS, request.tool_call['name'])
        return ToolMessage(
            content=TOOL_LIMIT_MESSAGE,
            tool_call_id=request.tool_call.get('id') or '',
            name=request.tool_call.get('name'),
        )

    try:
        result = handler(request)
        logger.info(f"[tool monitor]工具{request.tool_call['name']}调用成功")
        return result
    except Exception as e:
        logger.error(f"工具{request.tool_call['name']}调用失败，原因：{str(e)}")
        raise e


@wrap_model_call
def limit_tools_after_budget(request, handler):
    """
    工具预算用完后，把工具定义从模型请求里摘掉。

    为什么仅靠 monitor_tool 不够：返回「已达上限」的提示后，模型经常不服，
    下一轮仍继续发起检索，每轮消耗 2 个图步数，最终撞上 recursion_limit，
    把已经写好的回答截断在中间。移除工具定义后模型没有任何可调用的工具，
    只能直接作答——这是终止工具循环的确定性手段，而不是"劝"模型停下来。
    """
    if _tool_result_count(request.state) >= MAX_TOOL_CALLS and request.tools:
        logger.info('[model guard] 本轮工具预算已用完，移除工具定义后强制作答')
        return handler(request.override(tools=[]))
    return handler(request)

@before_model
def log_before_model(
        state: AgentState,   # 整个Agent智能体中的状态记录
        runtime: Runtime,    # 记录了整个执行过程中的上下文信息
):     # 在模型执行前输出日志
    logger.info(f"[log_before_model]即将调用模型，带有{len(state['messages'])}条消息")

    logger.debug(f"[log_before_model]{type(state['messages'][-1]).__name__} | {state['messages'][-1].content.strip()}")
    return None


# def report_prompt_switch():
#     pass
