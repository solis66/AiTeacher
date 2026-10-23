"""
跨进程文件锁

为什么需要它：
    咨询会话以「按天 Markdown」存储，一次写入是
    「读整天文件 → 改其中一个会话 → 整份写回」。
    这种读-改-写必须整体串行，否则两个写入方会各自基于同一份旧内容写回，
    后写的一方直接覆盖前一方（表现为"丢了一轮问答"）。
    进程内的 threading 锁只能管住同一个进程；一旦部署成多 worker / 多容器，
    就必须用操作系统持有的文件锁。

为什么不用第三方库：
    只需要「独占 + 阻塞等待 + 进程崩溃自动释放」这一种能力，
    POSIX 的 flock 与 Windows 的 msvcrt.locking 都满足，且没有陈旧锁问题
    （锁由内核挂在文件句柄上，进程退出即释放，不需要清理 .lock 文件内容）。

使用约定：
    with file_lock('/path/to/xxx.lock'):
        ...
    - 锁文件要与被保护的数据文件分开（删除数据文件时不会把锁一起删掉）；
    - 同一进程内不要对同一文件重复加锁（会自锁，与 flock 语义一致）。
"""

import os
from contextlib import contextmanager

if os.name == 'nt':
    import msvcrt
else:
    import fcntl


def _acquire(fd):
    """阻塞获取独占锁，直到成功为止。"""
    if os.name == 'nt':
        # LK_LOCK 是「重试若干次后抛 OSError」的阻塞模式；
        # 外面再套一层循环，就是真正的不限时等待。
        while True:
            try:
                msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
                return
            except OSError:
                continue
    fcntl.flock(fd, fcntl.LOCK_EX)


def _release(fd):
    """释放锁（Windows 要求从加锁时的同一位置解锁）。"""
    if os.name == 'nt':
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)


@contextmanager
def file_lock(path):
    """
    独占文件锁上下文管理器

    参数：
        path: string - 锁文件路径（不存在时自动创建，父目录也会自动创建）

    异常时同样会释放锁；进程异常退出由操作系统回收，不会留下死锁。
    """
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        _acquire(fd)
        yield
    finally:
        try:
            _release(fd)
        finally:
            os.close(fd)
