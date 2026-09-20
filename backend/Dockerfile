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

# 生产模式：debug=false，端口取 $PORT 或 8501
CMD ["python", "api.py"]