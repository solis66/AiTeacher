from langchain.agents.middleware import wrap_tool_call


@wrap_tool_call
def monitor_tool(
        # 请求的数据封装
        request,
        # 执行的函数本身
        handler,
):      # 工具执行的监控
    pass

def log_before_model():
    pass

def report_prompt_switch():
    pass
