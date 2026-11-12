# -*- coding: utf-8 -*-
"""大模型 / 向量化模型配置（可提交，不含任何密钥）。

私有地址与 API Key 放在项目根目录或后端目录的 `.env`（已 gitignore），
本模块导入时加载 `.env` 并读取环境变量；未提供时回退本地 Ollama 默认值。
环境变量名与 docker-compose.yml 一致，容器内由 compose 直接注入，无需生成文件。
"""
import os


def _load_dotenv():
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.join(here, '.env'), os.path.join(os.path.dirname(here), '.env')):
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    key, _, val = line.partition('=')
                    key, val = key.strip(), val.strip().strip('"\'')
                    if key and key not in os.environ:
                        os.environ[key] = val
        except OSError:
            pass


_load_dotenv()

# ====== 对话模型（策略生成 / 智能体 / 荐股） ======
API_BASE_URL = os.environ.get('LLM_API_BASE_URL', 'http://localhost:11434/v1')
API_KEY = os.environ.get('LLM_API_KEY', '') or 'ollama'
MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'qwen3:0.6b')

# ====== 向量化模型（RAG 知识库专用，与对话模型相互独立） ======
EMBED_BASE_URL = os.environ.get('EMBED_BASE_URL', 'http://localhost:11434/v1')
EMBED_API_KEY = os.environ.get('EMBED_API_KEY', '') or 'ollama'
EMBED_MODEL = os.environ.get('EMBED_MODEL', 'qwen3-embedding:0.6b')