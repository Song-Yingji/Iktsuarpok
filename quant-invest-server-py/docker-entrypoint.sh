#!/bin/sh
# Iktsuarpok 后端容器入口脚本：
# 1) 按环境变量生成 db_config.py（仓库里该文件已 gitignore，镜像中不存在，
#    因此每个容器都会按当前环境变量重新生成）；若要自定义可挂载同名文件到 /app。
#    llm_config.py 已脱敏随镜像提交，直接读取 compose 注入的环境变量，无需生成。
# 2) 以 0.0.0.0 启动 uvicorn（容器内不能用 127.0.0.1 监听，否则宿主机无法访问）。
set -e

# ---------- 数据库配置 ----------
if [ ! -f /app/db_config.py ]; then
  cat > /app/db_config.py <<EOF
# -*- coding: utf-8 -*-
"""由 docker-entrypoint.sh 按环境变量生成（挂载同名文件可覆盖）。"""
DB_HOST = '${DB_HOST:-mysql}'
DB_PORT = ${DB_PORT:-3306}
DB_USER = '${DB_USER:-root}'
DB_PASSWORD = '${DB_PASSWORD:-123456}'
DB_NAME = '${DB_NAME:-xb_quant}'

# 账户凭证加密密钥（Fernet 对称加密）；未提供时临时生成，重启后旧密文将无法解密
CRED_SECRET_KEY = '${CRED_SECRET_KEY:-}'
EOF
fi

# ---------- 凭证密钥兜底 ----------
if [ -z "$CRED_SECRET_KEY" ]; then
  CRED_SECRET_KEY=$(python -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
  sed -i "s#^CRED_SECRET_KEY = .*#CRED_SECRET_KEY = '${CRED_SECRET_KEY}'#" /app/db_config.py
  echo "[warn] 未提供 CRED_SECRET_KEY，已临时生成。请写入 .env 后重建容器，否则重启后已加密的账户凭证无法解密。"
fi

echo "[Iktsuarpok] 后端启动中：uvicorn main:app --host 0.0.0.0 --port ${PORT:-3000}"
echo "[Iktsuarpok] 数据库 ${DB_USER:-root}@${DB_HOST:-mysql}:${DB_PORT:-3306}/${DB_NAME:-xb_quant}"

exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-3000}" --log-level info
