from langchain.agents import AgentState
from langchain.agents.middleware import wrap_tool_call, before_model
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from typing import Callable
from utils.logger_handler import logger
from langgraph.types import Command
from langgraph.runtime import Runtime


@wrap_tool_call
def monitor_tool(
        # 请求的数据封装
        request: ToolCallRequest,
        # 执行的函数本身
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
) -> ToolMessage | Command:      # 工具执行的监控
    logger.info(f"[tool monitor]执行工具{request.tool_call['name']}")
    logger.info(f"[tool monitor]传入参数{request.tool_call['args']}")

    try:
        result = handler(request)
        logger.info(f"[tool monitor]工具{request.tool_call['name']}调用成功")
        return result
    except Exception as e:
        logger.error(f"工具{request.tool_call['name']}调用成功，原因：{str(e)}")
        raise e

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
