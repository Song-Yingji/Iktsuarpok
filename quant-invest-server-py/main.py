# -*- coding: utf-8 -*-
"""量化投资平台后端服务（FastAPI）。

提供鉴权、行情、新闻、偏好、智能体、策略回测、自选股、账户等 REST 接口。
运行：python main.py  （默认端口 3000）
"""
import asyncio
import json
import re
import threading
import time
import math
from contextlib import asynccontextmanager

import pymysql
from fastapi import FastAPI, Body, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

import uvicorn

import auth
import db
import llm
from data import (
    get_market, tick_market, get_news, news_error, refresh_news, get_news_categories,
    BACKTEST_FRAMEWORKS,
    DEFAULT_PREFS,
)

PORT = 3000
LATENCY = 0.2  # 模拟网络延迟（秒）


@asynccontextmanager
async def lifespan(app):
    # 启动行情引擎：初始化 + 每 2 秒推进一个 tick（真实服务端随机游走）
    get_market()

    def loop():
        while True:
            time.sleep(2)
            tick_market()

    threading.Thread(target=loop, daemon=True).start()

    def news_loop():
        refresh_news()
        while True:
            time.sleep(60)
            refresh_news()

    threading.Thread(target=news_loop, daemon=True).start()
    yield


app = FastAPI(title='quant-invest-server', lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)


def fail(status, message):
    return JSONResponse(status_code=status, content={'message': message})


def _json_loads(val):
    """读取 MySQL JSON 列：兼容 str/bytes/已解析对象。"""
    if val is None:
        return None
    if isinstance(val, (bytes, bytearray)):
        val = val.decode('utf-8')
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return None
    return val


def get_current_user(authorization: str = Header(default=None)) -> int:
    """从 Authorization: Bearer <token> 解析当前登录用户 id。"""
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail='未登录或登录已过期')
    uid = auth.parse_token(authorization[7:])
    if not uid:
        raise HTTPException(status_code=401, detail='未登录或登录已过期')
    return uid


# ================= 技术指标 =================
def sma(values, n):
    out = [None] * len(values)
    s = 0.0
    for i in range(len(values)):
        s += values[i]
        if i >= n:
            s -= values[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(values, n):
    out = [None] * len(values)
    k = 2.0 / (n + 1)
    prev = values[0]
    for i in range(len(values)):
        prev = values[0] if i == 0 else values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(values, n):
    out = [None] * len(values)
    gain = 0.0
    loss = 0.0
    for i in range(1, len(values)):
        ch = values[i] - values[i - 1]
        gain += max(ch, 0.0)
        loss += max(-ch, 0.0)
        if i > n:
            ch2 = values[i - n] - values[i - n - 1]
            gain -= max(ch2, 0.0)
            loss -= max(-ch2, 0.0)
        if i >= n:
            rs = gain / max(loss, 1e-9)
            out[i] = 100 - 100 / (1 + rs)
    return out


def run_backtest(strategy_id, stock_code, params, capital, framework, range_days):
    m = get_market()
    stock = next((s for s in m['stocks'] if s['code'] == stock_code), None) or m['stocks'][0]
    candles = stock['history'][-range_days:]
    closes = [c['close'] for c in candles]
    n = len(candles)
    signals = [0] * n

    if strategy_id == 'ma_cross':
        fast = sma(closes, params['fast'])
        slow = sma(closes, params['slow'])
        for i in range(1, n):
            if fast[i] and slow[i] and fast[i - 1] and slow[i - 1]:
                if fast[i - 1] <= slow[i - 1] and fast[i] > slow[i]:
                    signals[i] = 1
                if fast[i - 1] >= slow[i - 1] and fast[i] < slow[i]:
                    signals[i] = -1
    elif strategy_id == 'macd':
        ef = ema(closes, params['fast'])
        es = ema(closes, params['slow'])
        dif = [ef[i] - es[i] for i in range(n)]
        dea = ema(dif, params['signal'])
        for i in range(1, n):
            if dif[i - 1] <= dea[i - 1] and dif[i] > dea[i] and dif[i] > 0:
                signals[i] = 1
            if dif[i - 1] >= dea[i - 1] and dif[i] < dea[i]:
                signals[i] = -1
    elif strategy_id == 'boll':
        mid = sma(closes, params['period'])
        for i in range(n):
            if not mid[i]:
                continue
            sl = closes[i - params['period'] + 1:i + 1]
            mean = mid[i]
            var = sum((c - mean) ** 2 for c in sl) / params['period']
            std = math.sqrt(var)
            upper = mean + params['mult'] * std
            lower = mean - params['mult'] * std
            if closes[i] < lower:
                signals[i] = 1
            if closes[i] > upper:
                signals[i] = -1
    elif strategy_id == 'rsi':
        r = rsi(closes, params['period'])
        for i in range(1, n):
            if not r[i] or not r[i - 1]:
                continue
            if r[i - 1] < params['low'] and r[i] >= params['low']:
                signals[i] = 1
            if r[i - 1] > params['high'] and r[i] <= params['high']:
                signals[i] = -1
    elif strategy_id == 'momentum':
        ma20 = sma(closes, 20)
        for i in range(params['lookback'], n):
            high_n = max(c['high'] for c in candles[i - params['lookback']:i])
            if closes[i] > high_n:
                signals[i] = 1
            if ma20[i] and closes[i] < ma20[i]:
                signals[i] = -1

    cash = capital
    shares = 0.0
    entry_price = 0.0
    entry_idx = -1
    equity = []
    trades = []
    points = []
    for i in range(n):
        price = closes[i]
        if signals[i] == 1 and shares == 0:
            shares = cash / price
            entry_price = price
            entry_idx = i
            cash = 0.0
            points.append({'date': candles[i]['date'], 'price': price, 'type': 'buy'})
        elif signals[i] == -1 and shares > 0:
            cash = shares * price
            trades.append({
                'entryDate': candles[entry_idx]['date'], 'exitDate': candles[i]['date'],
                'entryPrice': entry_price, 'exitPrice': price,
                'ret': price / entry_price - 1, 'days': i - entry_idx,
            })
            points.append({'date': candles[i]['date'], 'price': price, 'type': 'sell'})
            shares = 0.0
        if strategy_id == 'momentum' and shares > 0 and price / entry_price - 1 <= -params['stop'] / 100:
            cash = shares * price
            trades.append({
                'entryDate': candles[entry_idx]['date'], 'exitDate': candles[i]['date'],
                'entryPrice': entry_price, 'exitPrice': price,
                'ret': price / entry_price - 1, 'days': i - entry_idx, 'stopped': True,
            })
            points.append({'date': candles[i]['date'], 'price': price, 'type': 'sell'})
            shares = 0.0
        equity.append({'date': candles[i]['date'], 'value': cash + shares * price, 'bench': capital * (price / closes[0])})

    if shares > 0:
        price = closes[n - 1]
        cash = shares * price
        trades.append({
            'entryDate': candles[entry_idx]['date'], 'exitDate': candles[n - 1]['date'],
            'entryPrice': entry_price, 'exitPrice': price,
            'ret': price / entry_price - 1, 'days': n - 1 - entry_idx,
        })

    values = [e['value'] for e in equity]
    rets = [values[i] / values[i - 1] - 1 for i in range(1, len(values))]
    total_return = values[-1] / capital - 1
    bench_return = closes[-1] / closes[0] - 1
    annualized = (values[-1] / capital) ** (252.0 / n) - 1
    peak = values[0]
    max_dd = 0.0
    dd_end = 0
    for i, v in enumerate(values):
        peak = max(peak, v)
        dd = v / peak - 1
        if dd < max_dd:
            max_dd = dd
            dd_end = i
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    std = math.sqrt(var)
    sharpe = (mean / std) * math.sqrt(252) if std > 0 else 0.0
    sorted_rets = sorted(rets)
    cvar_count = max(1, int(len(rets) * 0.05))
    cvar = sum(sorted_rets[:cvar_count]) / cvar_count
    wins = [t for t in trades if t['ret'] > 0]
    losses = [t for t in trades if t['ret'] <= 0]
    win_rate = len(wins) / len(trades) if trades else 0.0
    avg_win = sum(t['ret'] for t in wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(t['ret'] for t in losses) / len(losses)) if losses else 0.0
    if avg_loss > 0:
        pl_ratio = avg_win / avg_loss
    elif avg_win > 0:
        pl_ratio = 9.9
    else:
        pl_ratio = 0.0

    return {
        'stock': stock, 'framework': framework, 'capital': capital, 'rangeDays': range_days,
        'candles': candles, 'equity': equity, 'trades': trades, 'points': points,
        'metrics': {
            'totalReturn': total_return, 'annualized': annualized, 'benchReturn': bench_return,
            'maxDD': max_dd, 'sharpe': sharpe, 'cvar': cvar,
            'winRate': win_rate, 'plRatio': pl_ratio, 'tradeCount': len(trades),
            'finalValue': values[-1], 'ddEnd': dd_end,
        },
    }


# ================= 鉴权 =================
@app.post('/api/auth/login')
async def login(payload: dict = Body(default=None)):
    await asyncio.sleep(LATENCY)
    payload = payload or {}
    username = payload.get('username')
    password = payload.get('password')
    if not username or not password:
        return fail(400, '请输入用户名和密码')
    row = db.query_one('SELECT id, username, password_hash, avatar FROM users WHERE username=%s', (username,))
    if not row or not auth.verify_password(password, row['password_hash']):
        return fail(401, '用户名或密码错误')
    return {'token': auth.make_token(row['id']), 'user': {'id': row['id'], 'username': row['username'], 'avatar': row['avatar']}}


@app.post('/api/auth/register')
async def register(payload: dict = Body(default=None)):
    await asyncio.sleep(LATENCY)
    payload = payload or {}
    username = payload.get('username')
    password = payload.get('password')
    phone = payload.get('phone')
    if not username or not password:
        return fail(400, '请填写完整注册信息')
    if len(password) < 6:
        return fail(400, '密码长度至少 6 位')
    if phone and not re.fullmatch(r'1\d{10}', str(phone)):
        return fail(400, '手机号格式不正确')
    if db.query_one('SELECT id FROM users WHERE username=%s', (username,)):
        return fail(409, '用户名已存在')
    avatar = str(username)[:1].upper()
    uid = db.insert(
        'INSERT INTO users (username, password_hash, phone, avatar) VALUES (%s,%s,%s,%s)',
        (username, auth.hash_password(password), phone or None, avatar),
    )
    return {'token': auth.make_token(uid), 'user': {'id': uid, 'username': username, 'avatar': avatar}}


# ================= 行情 =================
@app.get('/api/market/snapshot')
async def market_snapshot():
    await asyncio.sleep(0.08)
    return get_market()


# ================= 新闻 =================
@app.get('/api/news/categories')
def news_categories():
    return get_news_categories()


@app.get('/api/news')
async def news(category: str = None, keyword: str = None):
    await asyncio.sleep(0.05)
    result = get_news()
    err = news_error()
    if category and category != '全部':
        result = [n for n in result if n['category'] == category]
    if keyword:
        result = [n for n in result if keyword in (n['title'] + n['summary'])]
    return {'items': result, 'error': err}


# ================= 投资偏好（1 用户 : N 套） =================
def _row_to_prefset(row):
    return {
        'id': row['id'],
        'name': row['name'],
        'risk': row['risk'],
        'horizon': row['horizon'],
        'benchmark': row['benchmark'],
        'sectors': _json_loads(row['sectors']) or [],
        'maxPosition': row['max_position'],
        'stopLoss': row['stop_loss'],
        'takeProfit': row['take_profit'],
        'isDefault': bool(row['is_default']),
        'updatedAt': row['updated_at'].strftime('%Y-%m-%d'),
    }


def _prefset_fields(p):
    """从请求体取出偏好字段，缺省或 null 一律用 DEFAULT_PREFS 兜底。"""
    def val(key):
        v = p.get(key)
        return DEFAULT_PREFS[key] if v is None else v

    return (
        val('risk'),
        val('horizon'),
        val('benchmark'),
        json.dumps(val('sectors'), ensure_ascii=False),
        val('maxPosition'),
        val('stopLoss'),
        val('takeProfit'),
    )


@app.get('/api/prefs')
async def list_prefs(uid: int = Depends(get_current_user)):
    """当前用户的全部偏好，默认偏好排在最前。"""
    await asyncio.sleep(0.1)
    rows = db.query(
        'SELECT * FROM preference_sets WHERE user_id=%s ORDER BY is_default DESC, id', (uid,))
    return [_row_to_prefset(r) for r in rows]


@app.post('/api/prefs')
async def create_prefs(payload: dict = Body(default=None), uid: int = Depends(get_current_user)):
    """新增一套偏好；用户的第一套自动成为默认偏好。"""
    await asyncio.sleep(LATENCY)
    p = payload or {}
    name = (p.get('name') or '').strip()
    if not name:
        return fail(400, '请填写偏好名称')
    if db.query_one('SELECT id FROM preference_sets WHERE user_id=%s AND name=%s', (uid, name)):
        return fail(409, '偏好名称已存在')

    fields = _prefset_fields(p)
    is_default = 1 if not db.query_one('SELECT id FROM preference_sets WHERE user_id=%s', (uid,)) else 0
    pid = db.insert(
        'INSERT INTO preference_sets '
        '(user_id, name, risk, horizon, benchmark, sectors, max_position, stop_loss, take_profit, is_default) '
        'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
        (uid, name) + fields + (is_default,),
    )
    return _row_to_prefset(db.query_one('SELECT * FROM preference_sets WHERE id=%s', (pid,)))


@app.put('/api/prefs/{pref_id}')
async def update_prefs(pref_id: int, payload: dict = Body(default=None), uid: int = Depends(get_current_user)):
    """编辑一套偏好；默认标记不在此处变更，切换走 /default 接口。"""
    await asyncio.sleep(LATENCY)
    row = db.query_one('SELECT * FROM preference_sets WHERE id=%s AND user_id=%s', (pref_id, uid))
    if not row:
        return fail(404, '偏好不存在')
    p = payload or {}
    name = (p.get('name') or row['name']).strip()
    if not name:
        return fail(400, '请填写偏好名称')
    if db.query_one('SELECT id FROM preference_sets WHERE user_id=%s AND name=%s AND id<>%s', (uid, name, pref_id)):
        return fail(409, '偏好名称已存在')

    fields = _prefset_fields(p)
    db.execute(
        'UPDATE preference_sets SET name=%s, risk=%s, horizon=%s, benchmark=%s, sectors=%s, '
        'max_position=%s, stop_loss=%s, take_profit=%s WHERE id=%s AND user_id=%s',
        (name,) + fields + (pref_id, uid),
    )
    return _row_to_prefset(db.query_one('SELECT * FROM preference_sets WHERE id=%s', (pref_id,)))


@app.post('/api/prefs/{pref_id}/default')
async def set_default_prefs(pref_id: int, uid: int = Depends(get_current_user)):
    """把指定偏好设为荐股默认偏好，同一用户只保留一个默认。"""
    await asyncio.sleep(0.1)
    if not db.query_one('SELECT id FROM preference_sets WHERE id=%s AND user_id=%s', (pref_id, uid)):
        return fail(404, '偏好不存在')
    db.execute_tx([
        ('UPDATE preference_sets SET is_default=0 WHERE user_id=%s AND id<>%s', (uid, pref_id)),
        ('UPDATE preference_sets SET is_default=1 WHERE id=%s AND user_id=%s', (pref_id, uid)),
    ])
    return {'ok': True}


@app.delete('/api/prefs/{pref_id}')
async def delete_prefs(pref_id: int, uid: int = Depends(get_current_user)):
    """删除一套偏好；若删掉的是默认偏好，自动把剩余的第一套提为默认。"""
    await asyncio.sleep(0.1)
    row = db.query_one('SELECT * FROM preference_sets WHERE id=%s AND user_id=%s', (pref_id, uid))
    if not row:
        return fail(404, '偏好不存在')
    db.execute('DELETE FROM preference_sets WHERE id=%s AND user_id=%s', (pref_id, uid))
    if row['is_default']:
        rest = db.query_one(
            'SELECT id FROM preference_sets WHERE user_id=%s ORDER BY id LIMIT 1', (uid,))
        if rest:
            db.execute('UPDATE preference_sets SET is_default=1 WHERE id=%s', (rest['id'],))
    return {'ok': True}


# ================= 全局设置（与偏好无关） =================
@app.get('/api/settings')
async def get_settings(uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.08)
    row = db.query_one('SELECT * FROM user_settings WHERE user_id=%s', (uid,))
    return {'tradeNotify': bool(row['trade_notify']) if row else True}


@app.post('/api/settings')
async def save_settings(payload: dict = Body(default=None), uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.1)
    p = payload or {}
    db.execute(
        'INSERT INTO user_settings (user_id, trade_notify) VALUES (%s,%s) '
        'ON DUPLICATE KEY UPDATE trade_notify=VALUES(trade_notify)',
        (uid, 1 if p.get('tradeNotify', True) else 0),
    )
    return {'ok': True}


# ================= 智能体 =================
def _clamp_int(v, low, high, default):
    """把模型给出的数值收敛到合法区间，非法值用默认值兜底。"""
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, n))


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


def _stream_tagged(messages, system_prompt, start_tag, end_tag, parse, event_name):
    """流式读取模型输出，把标记包裹的 JSON 解析为结构化事件（SSE 生成器）。

    标记之外的文本按增量下发；标记之内的内容不下发原文，只在解析成功后以
    event_name 事件发出。解析失败则整块降级为普通文本，保证前端不丢信息。
    """
    def _sse(event_type, data):
        return f'data: {json.dumps({"type": event_type, "data": data}, ensure_ascii=False)}\n\n'

    pending = ''        # 待发文本缓冲，防止标记被 chunk 边界截断
    in_block = False    # 是否处于标记包裹的 JSON 内部
    buf = ''            # JSON 内容累积
    tag_max_len = max(len(start_tag), len(end_tag))

    for chunk in llm.chat_stream(messages, system_prompt=system_prompt):
        if not in_block:
            pending += chunk
            if start_tag in pending:
                # 标记之前的引导文字直接丢弃，不发给前端
                pending = pending[pending.index(start_tag) + len(start_tag):]
                in_block = True
                buf = ''
            elif len(pending) > tag_max_len:
                emit, pending = pending[:-tag_max_len], pending[-tag_max_len:]
                yield _sse('text', emit)
        else:
            buf += chunk
            if end_tag in buf:
                idx = buf.index(end_tag)
                body = buf[:idx].strip().strip('"\'\n\t ')
                pending = buf[idx + len(end_tag):].lstrip('"\n\t \r\'')
                in_block = False
                buf = ''
                parsed = parse(body)
                if parsed is None:
                    yield _sse('text', start_tag + body + end_tag)
                else:
                    yield _sse(event_name, parsed)

    if in_block:
        # 没等到结束标记，整块当普通文本发出
        yield _sse('text', start_tag + buf + pending)
    elif pending:
        yield _sse('text', pending)
    yield _sse('done', {})


@app.post('/api/agent/generate-strategy')
async def agent_generate_strategy(payload: dict = Body(default=None)):
    """策略生成智能体（SSE 流式）。

    请求体：
        messages: [{role: 'user'|'assistant', content: '...'}, ...]  多轮对话
        或兼容旧格式：{ prompt: '...' }

    响应（SSE）：
        data: {"type":"text","data":"..."}\n\n
        data: {"type":"strategy","data":{...}}\n\n
        data: {"type":"done","data":{}}\n\n
    """
    p = payload or {}
    messages = p.get('messages')
    if not messages:
        # 兼容旧格式：单条 prompt
        messages = [{'role': 'user', 'content': p.get('prompt') or ''}]

    return StreamingResponse(
        _stream_tagged(messages, llm.SYSTEM_PROMPT, llm.STRATEGY_START, llm.STRATEGY_END,
                       _parse_strategy, 'strategy'),
        media_type='text/event-stream',
    )


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


@app.post('/api/agent/recommend')
async def agent_recommend(payload: dict = Body(default=None), uid: int = Depends(get_current_user)):
    """自动荐股智能体（SSE 流式）。

    先用真实行情快照构造候选池并推导技术因子，再交给大模型给出评分与理由。
    模型只输出主观字段（score/confidence/action/reasons），名称、板块、价格、
    涨跌幅等行情字段由后端按 code 回填，模型无法编造价格或池外标的。

    请求体：{ prefsId } —— 指定使用哪一套已保存偏好；缺省用默认偏好，
            用户一套偏好都没有时退化为内置默认值（全市场候选池）。

    响应（SSE）：
        data: {"type":"text","data":"..."}\n\n          分析说明（流式）
        data: {"type":"recommend","data":[{...}]}\n\n  荐股结果（已回填真实行情）
        data: {"type":"done","data":{}}\n\n
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

    return StreamingResponse(
        _stream_tagged([{'role': 'user', 'content': user_msg}], llm.RECOMMEND_SYSTEM_PROMPT,
                       llm.RECOMMEND_START, llm.RECOMMEND_END,
                       lambda body: _parse_recommend(body, pool), 'recommend'),
        media_type='text/event-stream',
    )


# ================= 策略 / 回测 =================
@app.get('/api/strategy/frameworks')
def get_frameworks():
    return BACKTEST_FRAMEWORKS


@app.post('/api/strategy/backtest')
async def backtest(payload: dict = Body(default=None)):
    await asyncio.sleep(1.8)
    b = payload or {}
    if not b.get('strategyId'):
        return fail(400, '缺少策略ID')
    result = run_backtest(
        strategy_id=b.get('strategyId'),
        stock_code=b.get('stockCode'),
        params=b.get('params') or {},
        capital=b.get('capital') or 1000000,
        framework=b.get('framework'),
        range_days=b.get('rangeDays') or 120,
    )
    return result


# ================= 自选股 =================
@app.get('/api/watchlist')
async def get_watchlist(uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.05)
    rows = db.query('SELECT stock_code FROM watchlist WHERE user_id=%s ORDER BY id', (uid,))
    codes = [r['stock_code'] for r in rows]
    m = get_market()
    return [s for c in codes for s in m['stocks'] if s['code'] == c]


@app.post('/api/watchlist')
async def add_watchlist(payload: dict = Body(default=None), uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.1)
    code = (payload or {}).get('code')
    if not code:
        return fail(400, '缺少股票代码')
    try:
        db.insert('INSERT INTO watchlist (user_id, stock_code) VALUES (%s,%s)', (uid, code))
    except pymysql.err.IntegrityError:
        pass  # 已存在，忽略
    return {'ok': True}


@app.delete('/api/watchlist/{code}')
async def remove_watchlist(code: str, uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.1)
    affected = db.execute('DELETE FROM watchlist WHERE user_id=%s AND stock_code=%s', (uid, code))
    if not affected:
        return fail(404, '自选股不存在')
    return {'ok': True}


# ================= 已保存的量化策略（智能体生成） =================
def _row_to_strategy(row):
    return {
        'id': row['id'],
        'name': row['name'],
        'type': row['type'],
        'engineId': row['engine_id'],
        'params': _json_loads(row['params']) or {},
        'rules': _json_loads(row['rules']) or [],
        'code': row['code'] or '',
        'createdAt': row['created_at'].strftime('%Y-%m-%d'),
    }


@app.get('/api/strategy/saved')
async def list_saved_strategies(uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.1)
    rows = db.query('SELECT * FROM saved_strategies WHERE user_id=%s ORDER BY id DESC', (uid,))
    return [_row_to_strategy(r) for r in rows]


@app.post('/api/strategy/saved')
async def save_strategy(payload: dict = Body(default=None), uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.2)
    p = payload or {}
    if not p.get('name'):
        return fail(400, '缺少策略名称')
    engine_id = p.get('engineId') or 'ma_cross'
    params = p.get('params') or {'fast': 5, 'slow': 20}
    rules = p.get('rules') or []
    code = p.get('code') or ''
    sid = db.insert(
        'INSERT INTO saved_strategies (user_id, name, type, engine_id, params, rules, code) '
        'VALUES (%s,%s,%s,%s,%s,%s,%s)',
        (uid, p['name'], p.get('type'), engine_id,
         json.dumps(params, ensure_ascii=False), json.dumps(rules, ensure_ascii=False), code),
    )
    row = db.query_one('SELECT * FROM saved_strategies WHERE id=%s', (sid,))
    return _row_to_strategy(row)


@app.delete('/api/strategy/saved/{strategy_id}')
async def delete_saved_strategy(strategy_id: int, uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.1)
    affected = db.execute('DELETE FROM saved_strategies WHERE id=%s AND user_id=%s', (strategy_id, uid))
    if not affected:
        return fail(404, '策略不存在')
    return {'ok': True}


# ================= 账户 =================
def _row_to_account(row):
    return {
        'id': row['id'],
        'broker': row['broker'],
        'type': row['type'],
        'accountNo': row['account_no'],
        'status': row['status'],
        'totalAssets': float(row['total_assets']),
        'cash': float(row['cash']),
        'autoTrade': bool(row['auto_trade']),
        'strategyId': row['strategy_id'],
        'created': row['created_at'].strftime('%Y-%m-%d'),
    }


@app.get('/api/accounts')
async def list_accounts(uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.15)
    rows = db.query('SELECT * FROM accounts WHERE user_id=%s ORDER BY id', (uid,))
    return [_row_to_account(r) for r in rows]


@app.post('/api/accounts')
async def create_account(payload: dict = Body(default=None), uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.3)
    payload = payload or {}
    capital = payload.get('capital') or 100000
    aid = db.insert(
        'INSERT INTO accounts (user_id, broker, type, account_no, status, total_assets, cash, auto_trade, strategy_id) '
        'VALUES (%s,%s,%s,%s,%s,%s,%s,0,NULL)',
        (uid, payload.get('broker') or '未命名账户', payload.get('type') or '模拟盘',
         payload.get('accountNo'), 'connected', capital, capital),
    )
    row = db.query_one('SELECT * FROM accounts WHERE id=%s', (aid,))
    return _row_to_account(row)


@app.put('/api/accounts/{account_id}')
async def update_account(account_id: int, payload: dict = Body(default=None), uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.2)
    row = db.query_one('SELECT * FROM accounts WHERE id=%s AND user_id=%s', (account_id, uid))
    if not row:
        return fail(404, '账户不存在')
    patch = payload or {}
    new_auto = patch.get('autoTrade', bool(row['auto_trade']))
    strategy_id = patch.get('strategyId', row['strategy_id'])
    # 兼容前端 select 传来的字符串 id（"5"），解绑时转 None
    strategy_id = int(strategy_id) if strategy_id not in (None, '') else None
    if new_auto and not strategy_id:
        return fail(400, '请先为账户绑定量化策略，再开启自动交易')
    db.execute(
        'UPDATE accounts SET broker=%s, type=%s, account_no=%s, status=%s, '
        'total_assets=%s, cash=%s, auto_trade=%s, strategy_id=%s WHERE id=%s',
        (
            patch.get('broker', row['broker']),
            patch.get('type', row['type']),
            patch.get('accountNo', row['account_no']),
            patch.get('status', row['status']),
            float(patch.get('totalAssets', row['total_assets'])),
            float(patch.get('cash', row['cash'])),
            1 if new_auto else 0,
            strategy_id,
            account_id,
        ),
    )
    updated = db.query_one('SELECT * FROM accounts WHERE id=%s', (account_id,))
    return _row_to_account(updated)


@app.delete('/api/accounts/{account_id}')
async def delete_account(account_id: int, uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.2)
    affected = db.execute('DELETE FROM accounts WHERE id=%s AND user_id=%s', (account_id, uid))
    if not affected:
        return fail(404, '账户不存在')
    return {'ok': True}


@app.get('/api/health')
def health():
    return {'status': 'ok', 'service': 'quant-invest-server', 'lang': 'python'}


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return fail(exc.status_code, exc.detail)


@app.exception_handler(404)
async def not_found(request, exc):
    return fail(404, '接口不存在')


if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=PORT, log_level='info', use_colors=False)