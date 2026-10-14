# Iktsuarpok 后端（FastAPI）镜像
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 先装依赖，利用镜像层缓存（源码变动不会触发重装）
COPY requirements.txt ./
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 再拷贝源码；db_config.py / llm_config.py 被 .dockerignore 排除，
# 由 docker-entrypoint.sh 按环境变量在启动时生成
COPY . .

# Windows 下检出的脚本可能带 CRLF，统一转成 LF 再赋可执行权限
RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod +x docker-entrypoint.sh

EXPOSE 3000
CMD ["sh", "/app/docker-entrypoint.sh"]
