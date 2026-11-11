# -*- coding: utf-8 -*-
"""AI 智能体：策略生成（Quant Buffett）与智能荐股（Recommend Buffett）。"""
import json
import re

from fastapi import APIRouter, Body, Depends

import db
import llm
import modular_rag
import rag
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


def _parse_strategy(text):
    """解析模型输出的策略 JSON，对常见畸形做容错。

    小模型容易产出两类非法 JSON：字符串值里含真实换行、数组/对象括号写错。
    标准解析失败时退化为按字段正则提取，保证仍能拿到可保存的策略。
    """
    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError:
        pass

    def pick_str(key):
        m = re.search(r'"%s"\s*:\s*"((?:[^"\\]|\\.)*)"' % key, text, re.S)
        return m.group(1) if m else None

    name = pick_str('name')
    if not name:
        return None

    rules_m = re.search(r'"rules"\s*:\s*\[(.*?)(?:"code"|\]|$)', text, re.S)
    rules = re.findall(r'"((?:[^"\\]|\\.)*)"', rules_m.group(1)) if rules_m else []

    params_m = re.search(r'"params"\s*:\s*\{(.*?)\}', text, re.S)
    params = {}
    if params_m:
        for k, v in re.findall(r'"([A-Za-z_]\w*)"\s*:\s*(-?\d+(?:\.\d+)?)', params_m.group(1)):
            params[k] = float(v) if '.' in v else int(v)

    return {
        'name': name,
        'type': pick_str('type') or '自定义策略',
        'engineId': pick_str('engineId') or 'ma_cross',
        'params': params,
        'rules': rules,
        'code': pick_str('code') or '',
    }


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


def _rag_context(query):
    """检索本地知识库，返回（拼接好的参考资料文本, 命中片段列表）。

    走模块化 RAG 管线（查询改写→多路检索→RRF 融合→重排序→上下文压缩），
    知识库为空、未配置向量模型或检索失败时返回空串，静默降级为普通对话，
    保证 RAG 不可用不影响策略生成主流程。
    """
    if not (query or '').strip():
        return '', []
    try:
        hits = modular_rag.get_modular_rag().retrieve(query)
    except rag.RagError:
        return '', []
    except Exception as e:
        print(f'[warn] 模块化 RAG 检索失败：{e}')
        return '', []
    if not hits:
        return '', []

    blocks = [
        f'[{i + 1}] 来源《{h["docName"]}》（相似度 {h["score"]:.2f}）\n{h["text"]}'
        for i, h in enumerate(hits)
    ]
    return '## 参考资料（来自本地知识库，请优先依据以下内容回答）\n' + '\n\n'.join(blocks), hits


@router.post('/generate-strategy')
async def agent_generate_strategy(payload: dict = Body(default=None)):
    """策略生成智能体（非流式，带 RAG 检索增强）。

    请求体：
        messages: [{role: 'user'|'assistant', content: '...'}, ...]  多轮对话
        或兼容旧格式：{ prompt: '...' }

    检索增强：把用户最新提问向量化，在本地知识库中做相似度检索，命中片段与
    原始问题拼成新的用户消息，再和 llm.SYSTEM_PROMPT 一起交给大模型。
    知识库为空或不可用时静默降级为普通对话，不影响原有功能。

    响应（JSON）：
        { rag: {count, sources}, text, strategy }
        rag      本轮命中的知识库来源
        text     除策略 JSON 之外的说明文本
        strategy 解析出的策略对象（未生成时为 null）
    """
    p = payload or {}
    messages = p.get('messages')
    if not messages:
        # 兼容旧格式：单条 prompt
        messages = [{'role': 'user', 'content': p.get('prompt') or ''}]

    msgs = [dict(m) for m in messages]
    hits = []
    if msgs and msgs[-1].get('role') == 'user':
        context, hits = _rag_context(msgs[-1].get('content') or '')
        if context:
            msgs[-1]['content'] = f'{context}\n\n## 我的问题\n{msgs[-1]["content"]}'

    answer = llm.chat(msgs, system_prompt=llm.SYSTEM_PROMPT)
    if not answer.strip():
        answer = '系统繁忙，请稍后重试'
    text, strategy = _split_tagged(answer, llm.STRATEGY_START, llm.STRATEGY_END, _parse_strategy)
    return {
        'rag': {
            'count': len(hits),
            'sources': [{'docName': h['docName'], 'score': round(h['score'], 3)} for h in hits],
        },
        'text': text,
        'strategy': strategy,
    }


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
    user_msg = f'''请从下面的候选池中选出最值得关注的 3~6 只标的，给出评分与理由。

## 我的投资偏好
- 风险等级：{prefs.get('risk') or '未设置'}
- 持仓周期：{prefs.get('horizon') or '未设置'}
- 关注板块：{'、'.join(sectors) if sectors else '不限'}
- 止损 / 止盈：{prefs.get('stopLoss', '--')}% / {prefs.get('takeProfit', '--')}%
- 最大单票仓位：{prefs.get('maxPosition', '--')}%

## 候选标的实时行情与技术因子（共 {len(pool)} 只）
{table}

请先输出一两句简短的分析说明，然后按约定格式输出荐股 JSON。'''

    answer = llm.chat([{'role': 'user', 'content': user_msg}], system_prompt=llm.RECOMMEND_SYSTEM_PROMPT)
    if not answer.strip():
        answer = '系统繁忙，请稍后重试'
    text, recommend = _split_tagged(answer, llm.RECOMMEND_START, llm.RECOMMEND_END,
                                    lambda body: _parse_recommend(body, pool))
    return {'text': text, 'recommend': recommend}