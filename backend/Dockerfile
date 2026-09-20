# AiTeachers 后端镜像（Render / Docker 平台通用）
# 说明：pywin32 在 requirements.txt 中标了 sys_platform=="win32"，Linux 下自动跳过，
#       评分标准自动落到 data/ 下的 .txt（已随代码打包），无需 Word。

# 基础镜像可覆盖：国内节点直连 docker.io 常超时，或被失效镜像源返回 not found。
# 默认用官方名（由 /etc/docker/daemon.json 的 registry-mirrors 加速）；
# 若加速器不可用，可直接指向可用仓库，不必改本文件：
#   BASE_IMAGE=docker.m.daocloud.io/library/python:3.11-slim
ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}

# 避免 Python 产生 pyc / 控制台输出缓冲
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# 国内服务器构建必换镜像源：本项目依赖解压后约 550MB，直连 pypi.org 会慢到超时。
# 以下默认值用公网源（任何环境可达）；云厂商内网源更快，由 compose 的 build.args 覆盖：
#   阿里云 ECS ：http://mirrors.cloud.aliyuncs.com/pypi/simple
#   腾讯云 CVM ：http://mirrors.cloud.tencent.com/pypi/simple
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple
ARG APT_MIRROR=mirrors.aliyun.com

# chromadb / onnxruntime 需要的运行库
#   libgomp1        —— chromadb / onnxruntime 的 OpenMP 运行时
#   fonts-wqy-zenhei —— 中文字体。纯文字正文批改（无附件）要把正文渲染成 page-N.jpg，
#                       PIL 取不到中文字体会直接抛「缺少中文字体」，整次批改 failed。
#                       该包在 Debian 下的路径是 /usr/share/fonts/truetype/wqy/wqy-zenhei.ttc，
#                       正是 review_documents.font() 探测的 Linux 路径，勿改名或换包。
RUN sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖（利用层缓存）
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} -r requirements.txt

# 拷贝后端代码与运行数据（含 data/ 评分标准 .txt、knowledge）
COPY backend/ ./

# 对外端口：api.py 会读取环境变量 PORT（Render 注入），Dockerfile 暴露默认端口便于本地
EXPOSE 8501

# 生产模式：Gunicorn（gthread worker）替代 Flask 内置的 Werkzeug 开发服务器。
#
# 为什么必须换：api.py 结尾是 app.run()，那是开发服务器 —— 每来一个请求就
# 新起一个线程、没有上限，多人同时用（尤其 AI 咨询的 SSE 长连接各占一个线程
# 数十秒）时线程数会失控。gthread 换成固定大小的线程池，超出即排队，这才有背压。
#
# 参数取舍（改之前请读完）：
#   -w 1        单 worker 是硬约束，不能改成 2 或更多。两个原因：
#               ① services/review_workbench.py 的 _GRADE_SEM 是**进程内**信号量，
#                  多 worker 会让批改并发闸翻倍（N×2），直接打爆下游 AI 接口限流；
#               ② chromadb 多进程并发写同一目录有数据风险。
#               要真正多进程，先按 docs/DEPLOY_VERCEL_DOCKER.md 把批改任务拆到
#               独立 worker 容器（web 层无状态后才能加副本）。
#   -k gthread  不能用默认的 sync：sync worker 一个进程同时只处理一个请求，
#               一条 SSE 长连接就会把它锁死，并且会触发 worker timeout 被强杀。
#   --threads   16 就是真正的并发上限。26.x 的 gthread 是「事件循环 + 线程池」结构：
#               连接由 worker_connections（默认 1000）兜住，但同一时刻只有 threads
#               个请求能被真正执行，其余排队 —— 这正是我们要的背压。
#               I/O 密集（线程大多在等 AI 响应，不占 CPU），故可远多于核数。
#               2 核 4G 取 16：留出「十几人同时咨询」的余量，再多堆线程收益递减。
#   --timeout   300。gthread 主循环每秒上报一次心跳（见 workers/gthread.py 的 run()），
#               正常情况根本不会触发超时；这个值的真实意义是「容忍偶发的 GIL 长时间
#               阻塞」—— 批改里的 PIL 图片渲染、PDF 导出是 C 扩展长调用，会让主循环
#               短暂上报不及时。默认 30s 对含图像处理的应用偏紧，一旦误判就会杀掉
#               worker，连带正在跑的批改线程（那次批改直接变 failed）。
#   --graceful-timeout 收到重启信号后，等待 in-flight 连接收尾的时间。
#               ⚠️ 注意它只等 HTTP 连接：后台批改线程不在其中，所以「重启会丢掉
#               正在跑的批改」这件事无法靠参数解决，要靠拆独立 worker 容器。
#   ${PORT:-8501} 保留 Render 等平台动态注入端口的兼容性。
#   用 sh -c + exec：让 gunicorn 成为 PID 1，否则 SIGTERM 收不到、无法优雅重启。
CMD ["sh", "-c", "exec gunicorn -w 1 -k gthread --threads 16 --timeout 300 --graceful-timeout 60 --access-logfile - --error-logfile - -b 0.0.0.0:${PORT:-8501} api:app"]