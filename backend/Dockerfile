# AiTeachers 后端镜像（Render / Docker 平台通用）
# 说明：pywin32 在 requirements.txt 中标了 sys_platform=="win32"，Linux 下自动跳过，
#       评分标准自动落到 data/ 下的 .txt（已随代码打包），无需 Word。

FROM python:3.11-slim

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
RUN sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
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