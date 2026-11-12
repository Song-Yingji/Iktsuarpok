# -*- coding: utf-8 -*-
"""大模型接入层：封装 OpenAI 兼容 API 的非流式与流式调用。

切换模型只需修改 llm_config.py / .env；提示词统一在 prompts.py 管理，
本模块只保留响应解析标记与调用逻辑。
"""
import json

import requests

# ====== 模型配置（从 llm_config.py 读取） ======
from llm_config import API_BASE_URL, API_KEY, MODEL_NAME

# qwen3 系列默认开启深度思考，拖慢响应；本平台只需直接回答，故关闭（DashScope 顶层 enable_thinking）
_IS_QWEN3 = 'qwen3' in MODEL_NAME.lower()

# ====== 响应解析标记 ======
# 策略 JSON 必须用 ===STRATEGY_JSON=== 和 ===END_STRATEGY=== 包裹，
# 以便后端解析时精确提取，避免与普通文本混淆。
STRATEGY_START = '===STRATEGY_JSON==='
STRATEGY_END = '===END_STRATEGY==='

# 荐股 JSON 用 ===RECOMMEND_JSON=== 和 ===END_RECOMMEND=== 包裹。
RECOMMEND_START = '===RECOMMEND_JSON==='
RECOMMEND_END = '===END_RECOMMEND==='


def chat(messages, system_prompt=None, temperature=0.3):
    """调用 OpenAI 兼容 API（非流式），一次性返回完整回答文本。

    system_prompt 传空或 None 时不注入系统消息（分析类提示词自带指令）。
    失败时返回空串，由调用方按保守策略兜底。
    """
    url = f'{API_BASE_URL}/chat/completions'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {API_KEY}',
    }
    msgs = [{'role': 'system', 'content': system_prompt}] + messages if system_prompt else messages
    payload = {
        'model': MODEL_NAME,
        'messages': msgs,
        'stream': False,
        'temperature': temperature,
        'top_p': 0.9,
    }
    if _IS_QWEN3:
        payload['enable_thinking'] = False
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return (data.get('choices') or [{}])[0].get('message', {}).get('content') or ''
    except Exception as e:
        print(f'[warn] 大模型非流式调用失败：{e}')
        return ''


def chat_stream(messages, system_prompt=None, temperature=0.3):
    """流式调用 OpenAI 兼容 API，逐段 yield 增量文本（SSE）。

    仅用于面向用户的最终自然语言回答；需要解析 JSON 的内部调用仍用 chat()。
    失败时打印告警并结束迭代（不 yield），由调用方按保守策略兜底。
    """
    url = f'{API_BASE_URL}/chat/completions'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {API_KEY}',
    }
    msgs = [{'role': 'system', 'content': system_prompt}] + messages if system_prompt else messages
    payload = {
        'model': MODEL_NAME,
        'messages': msgs,
        'stream': True,
        'temperature': temperature,
        'top_p': 0.9,
    }
    if _IS_QWEN3:
        payload['enable_thinking'] = False
    try:
        with requests.post(url, json=payload, headers=headers, timeout=120, stream=True) as resp:
            resp.raise_for_status()
            for raw in resp.iter_lines():
                if not raw:
                    continue
                line = raw.decode('utf-8', errors='replace').strip()
                if not line.startswith('data:'):
                    continue
                data = line[5:].strip()
                if data == '[DONE]':
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = (obj.get('choices') or [{}])[0].get('delta', {}).get('content')
                if delta:
                    yield delta
    except Exception as e:
        print(f'[warn] 大模型流式调用失败：{e}')
        return