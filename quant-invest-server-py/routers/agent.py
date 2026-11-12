# -*- coding: utf-8 -*-
"""AI 智能体：策略生成（Quant Buffett）与智能荐股（Recommend Buffett）。"""
import json
import re

from fastapi import APIRouter, Body, Depends
from fastapi.responses import StreamingResponse

import agent_core
import db
import llm
import prompts
from common import _clamp_int, get_current_user
from data import DEFAULT_PREFS, get_market
from routers.prefs import _row_to_prefset

router = APIRouter(prefix='/api/agent', tags=['agent'])


def _factor_line(s):
    """把一只标的的真实行情与技术因子整理成一行文本，供模型分析。

    因子全部由 Baostock 历史日 K 与实时快照推导，不引入任何模拟值。
    """
    closes = [c['close'] for c in (s.get('history') or [])]
    price = s.get('price') or 0
    prev = s.get('prevClose') or price
    chg = (price - prev) / prev * 100 if prev else 0.0

    def _ma(n):
        return sum(closes[-n:]) / n if len(closes) >= n else None

    def _chg(n):
        return (closes[-1] / closes[-n - 1] - 1) * 100 if len(closes) > n else None

    def _fmt(v, unit='', digits=2):
        return '--' if v is None else f'{v:.{digits}f}{unit}'

    vol20 = None
    if len(closes) > 21:
        rets = [closes[i] / closes[i - 1] - 1 for i in range(len(closes) - 20, len(closes))]
        mean = sum(rets) / len(rets)
        vol20 = (sum((r - mean) ** 2 for r in rets) / len(rets)) ** 0.5 * (252 ** 0.5) * 100

    pos60 = None
    if len(closes) >= 60:
        hi, lo = max(closes[-60:]), min(closes[-60:])
        pos60 = (closes[-1] - lo) / (hi - lo) * 100 if hi > lo else 50.0

    return (
        f'{s["code"]} {s["name"]}｜板块:{s["sector"]}｜现价:{_fmt(price)}｜今日:{chg:+.2f}%'
        f'｜PE:{s.get("pe", "--")}｜MA5:{_fmt(_ma(5))}｜MA20:{_fmt(_ma(20))}｜MA60:{_fmt(_ma(60))}'
        f'｜20日涨幅:{_fmt(_chg(20), "%")}｜60日位置:{_fmt(pos60, "%", 0)}｜20日年化波动:{_fmt(vol20, "%", 0)}'
    )


def _parse_recommend(text, pool):
    """解析模型输出的荐股 JSON，并用真实行情回填、过滤幻觉标的。

    模型只负责 score / confidence / action / reasons，名称、板块、价格、涨跌幅
    一律以服务端行情为准，避免模型编造价格或选出候选池之外的标的。
    返回按评分降序的推荐列表；完全无法解析时返回 None。
    """
    try:
        data = json.loads(text, strict=False)
    except json.JSONDecodeError:
        data = None
    picks = data.get('picks') if isinstance(data, dict) else None

    if not isinstance(picks, list):
        # 容错：标准解析失败时按字段正则提取（小模型常输出畸形 JSON）
        codes = re.findall(r'"code"\s*:\s*"([^"]+)"', text)
        if not codes:
            return None
        scores = re.findall(r'"score"\s*:\s*(\d+)', text)
        confs = re.findall(r'"confidence"\s*:\s*(\d+)', text)
        actions = re.findall(r'"action"\s*:\s*"([^"]*)"', text)
        blocks = re.findall(r'"reasons"\s*:\s*\[(.*?)\]', text, re.S)
        picks = [{
            'code': code,
            'score': scores[i] if i < len(scores) else None,
            'confidence': confs[i] if i < len(confs) else None,
            'action': actions[i] if i < len(actions) else None,
            'reasons': re.findall(r'"((?:[^"\\]|\\.)*)"', blocks[i]) if i < len(blocks) else [],
        } for i, code in enumerate(codes)]

    by_code = {s['code']: s for s in pool}
    result = []
    for p in picks:
        if not isinstance(p, dict):
            continue
        code = str(p.get('code') or '').strip()
        s = by_code.get(code)
        if not s:
            continue  # 候选池之外的代码，视为模型幻觉直接丢弃
        prev = s['prevClose']
        reasons = [str(r).strip() for r in (p.get('reasons') or []) if str(r).strip()][:4]
        result.append({
            'code': code,
            'name': s['name'],
            'sector': s['sector'],
            'price': s['price'],
            'change': (s['price'] - prev) / prev if prev else 0.0,
            'score': _clamp_int(p.get('score'), 0, 100, 75),
            'confidence': _clamp_int(p.get('confidence'), 0, 100, 65),
            'action': '建议买入' if p.get('action') == '建议买入' else '建议关注',
            'reasons': reasons or ['模型未给出具体理由'],
        })

    if not result:
        return None
    result.sort(key=lambda x: -x['score'])
    return result[:6]


def _split_tagged(text, start_tag, end_tag, parse):
    """从完整回答中切分标记块，返回（说明文本, 解析结果）。

    标记包裹的 JSON 交给 parse 解析；解析成功时返回标记之外的说明文本
    （前缀 + 后缀），解析结果为结构化对象。未命中标记或解析失败时，整段
    文本作为说明文本返回、解析结果为 None，保证前端不丢信息。
    """
    text = (text or '').strip()
    if start_tag in text and end_tag in text:
        s = text.index(start_tag) + len(start_tag)
        e = text.index(end_tag, s)
        body = text[s:e].strip().strip('"\'\n\t ')
        parsed = parse(body)
        if parsed is not None:
            outer = (text[:s - len(start_tag)] + text[e + len(end_tag):]).strip().strip('"\n\t \r\'')
            return outer, parsed
    return text, None


@router.post('/generate-strategy')
def agent_generate_strategy(payload: dict = Body(default=None), uid: int = Depends(get_current_user)):
    """策略生成智能体入口（真 Agent：意图识别 → 闲聊直连 / 知识问答 / ReAct 工具 / 迭代研究循环）。

    以 SSE（text/event-stream）流式返回，事件依次为：
        intent   {intent, reason}
        trace    {trace: [...]}   累积快照，前端直接替换
        rag      {count, sources}
        text     "增量文本"        闲聊 / 知识问答逐 token；工具 / 策略为整段
        strategy {...}            策略卡片（研究循环每轮刷新最优）
        done     {}
    生成器为同步 def，由 Starlette 在线程池迭代，长耗时 LLM / 回测不阻塞事件循环。
    """
    p = payload or {}
    messages = p.get('messages') or [{'role': 'user', 'content': p.get('prompt') or ''}]

    def sse():
        try:
            for event, data in agent_core.run_agent_stream(messages, uid):
                yield f'event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'
        except Exception as e:
            print(f'[warn] 智能体流式执行失败：{e}')
            payload = json.dumps({'message': '抱歉，我这边出了点状况，请稍后再问我一次。'}, ensure_ascii=False)
            yield f'event: error\ndata: {payload}\n\n'

    return StreamingResponse(sse(), media_type='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',   # 关闭 nginx 缓冲，保证逐事件下发
        'Connection': 'keep-alive',
    })


def _load_prefs(uid, pref_id=None):
    """按偏好 ID 读取偏好；未指定或不存在时用默认偏好，再无则退回内置默认值。"""
    row = None
    if pref_id:
        row = db.query_one(
            'SELECT * FROM preference_sets WHERE id=%s AND user_id=%s', (pref_id, uid))
    if not row:
        row = db.query_one(
            'SELECT * FROM preference_sets WHERE user_id=%s ORDER BY is_default DESC, id LIMIT 1', (uid,))
    return _row_to_prefset(row) if row else dict(DEFAULT_PREFS)


@router.post('/recommend')
async def agent_recommend(payload: dict = Body(default=None), uid: int = Depends(get_current_user)):
    """自动荐股智能体（非流式）。

    先用真实行情快照构造候选池并推导技术因子，再交给大模型给出评分与理由。
    模型只输出主观字段（score/confidence/action/reasons），名称、板块、价格、
    涨跌幅等行情字段由后端按 code 回填，模型无法编造价格或池外标的。

    请求体：{ prefsId } —— 指定使用哪一套已保存偏好；缺省用默认偏好，
            用户一套偏好都没有时退化为内置默认值（全市场候选池）。

    响应（JSON）：
        { text, recommend }
        text      分析说明
        recommend 荐股结果列表（已回填真实行情，失败时为 null）
    """
    payload = payload or {}
    prefs = _load_prefs(uid, payload.get('prefsId'))
    sectors = prefs.get('sectors') or []
    stocks = get_market()['stocks']

    pool = [s for s in stocks
            if any(sec in s['sector'] or s['sector'] in sec for sec in sectors)] if sectors else []
    if not pool:
        # 未设置关注板块，或所选板块无匹配标的时退化为全市场
        pool = list(stocks)

    table = '\n'.join(_factor_line(s) for s in pool)
    user_msg = prompts.build_recommend_user(prefs, sectors, len(pool), table)

    answer = llm.chat([{'role': 'user', 'content': user_msg}], system_prompt=prompts.RECOMMEND_SYSTEM_PROMPT)
    if not answer.strip():
        answer = '系统繁忙，请稍后重试'
    text, recommend = _split_tagged(answer, llm.RECOMMEND_START, llm.RECOMMEND_END,
                                    lambda body: _parse_recommend(body, pool))
    return {'text': text, 'recommend': recommend}