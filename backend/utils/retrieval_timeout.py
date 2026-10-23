"""
检索超时控制

为什么需要：
    config/chroma.yaml 里的 consult.timeout 一直没有被任何代码读取——Chroma 检索
    一旦卡住，咨询请求会一直挂着，只能等 embedding 层自身的超时。这里给检索调用
    加上真正的时限：超时即返回降级值，让咨询按"没有参考资料"继续往下走。

为什么用线程池而不是 signal：
    Flask 多线程 + gunicorn gthread 部署下，signal 只能在主线程注册；线程池跨平台可用。
    超时的任务不会被强制杀死，它会在自己的线程里跑完（embedding 层自带 15s 超时），
    线程随后归还池子——调用方拿到的只是降级值，不会泄漏。

使用方式：
    raw = run_with_timeout(lambda: store.similarity_search(...), 8, default=[])
    超时返回 default；其它异常原样抛给调用方（由调用方按原有逻辑兜底）。
"""

import concurrent.futures

from utils.logger_handler import logger

# 检索专用线程池。检索是咨询链路的前置步骤，宁可拿到空结果也不能拖死请求；
# 8 个线程足以覆盖并发咨询，超时任务跑完后线程自动回收。
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=8, thread_name_prefix='retrieval')


def run_with_timeout(func, timeout, default=None):
    """
    在受控线程里执行检索，超时返回 default。

    参数：
        func: callable - 实际检索调用（无参，用 lambda 包一层）
        timeout: float - 超时秒数
        default: Any - 超时后的降级返回值

    返回：
        Any - func 的返回值，或超时时的 default
    """
    try:
        return _EXECUTOR.submit(func).result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        logger.warning('[检索] 超过 %.1fs 未返回，降级为无检索结果', timeout)
        return default
