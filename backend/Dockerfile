# AiTeachers 后端镜像（Render / Docker 平台通用）
# 说明：pywin32 在 requirements.txt 中标了 sys_platform=="win32"，Linux 下自动跳过，
#       评分标准自动落到 data/ 下的 .txt（已随代码打包），无需 Word。

FROM python:3.11-slim

# 避免 Python 产生 pyc / 控制台输出缓冲
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# chromadb / onnxruntime 需要的运行库
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖（利用层缓存）
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝后端代码与运行数据（含 data/ 评分标准 .txt、knowledge）
COPY backend/ ./

# 对外端口：api.py 会读取环境变量 PORT（Render 注入），Dockerfile 暴露默认端口便于本地
EXPOSE 8501

# 生产模式：debug=false，端口取 $PORT 或 8501
CMD ["python", "api.py"]