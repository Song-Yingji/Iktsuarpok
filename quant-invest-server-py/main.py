# -*- coding: utf-8 -*-
"""量化投资平台后端服务（FastAPI）。

提供鉴权、行情、新闻、偏好、智能体、策略回测、自选股、账户等 REST 接口。
运行：python main.py  （默认端口 3000）
"""
import asyncio
import json
import os
import re
import threading
import time
import math
from contextlib import asynccontextmanager

import pymysql
from fastapi import FastAPI, Body, Depends, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import uvicorn

import admin_config
import auth
import connectors
import credentials
import db
import llm
import modular_rag
import rag
import rag_eval
from data import (
    get_market, tick_market, get_news, news_error, refresh_news, get_news_categories,
    BACKTEST_FRAMEWORKS,
    DEFAULT_PREFS,
)

PORT = 3000
LATENCY = 0.2  # 模拟网络延迟（秒）


def ensure_super_admin():
    """确保库中存在唯一的超级管理员（role=2，首次启动按 admin_config.py 播种）。"""
    try:
        if db.query_one('SELECT id FROM users WHERE role=2 LIMIT 1'):
            return
        name = admin_config.ADMIN_USERNAME
        row = db.query_one('SELECT id FROM users WHERE username=%s', (name,))
        if row:
            db.execute('UPDATE users SET role=2 WHERE id=%s', (row['id'],))
        else:
            db.insert(
                'INSERT INTO users (username, password_hash, phone, avatar, role)'
                ' VALUES (%s,%s,%s,%s,2)',
                (name, auth.hash_password(admin_config.ADMIN_PASSWORD), None, name[:1].upper()),
            )
    except Exception as e:
        print(f'[warn] 超级管理员初始化失败：{e}')


@asynccontextmanager
async def lifespan(app):
    # 启动行情引擎：初始化 + 每 2 秒推进一个 tick（真实服务端随机游走）
    ensure_super_admin()
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


def get_current_admin(authorization: str = Header(default=None)) -> dict:
    """从 Authorization: Bearer <token> 解析后台管理员。

    每次请求都回库复核，确保账号未被删除、且管理员身份未被取消。
    """
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail='管理员未登录或登录已过期')
    uid = auth.parse_admin_token(authorization[7:])
    if not uid:
        raise HTTPException(status_code=401, detail='管理员未登录或登录已过期')
    row = db.query_one('SELECT id, username, role FROM users WHERE id=%s', (uid,))
    if not row or row['role'] < 1:
        raise HTTPException(status_code=401, detail='管理员权限已变更，请重新登录')
    return row


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
    """当前用户的全部偏好，按创建顺序返回，切换默认偏好不改变列表顺序。"""
    await asyncio.sleep(0.1)
    rows = db.query(
        'SELECT * FROM preference_sets WHERE user_id=%s ORDER BY id', (uid,))
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


@app.post('/api/agent/generate-strategy')
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


@app.post('/api/agent/recommend')
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


# ================= 后台管理（知识库） =================
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 单文件上限 10MB


@app.post('/api/admin/login')
async def admin_login(payload: dict = Body(default=None)):
    """后台管理员登录：查库校验账号密码，且要求 role >= 1。"""
    await asyncio.sleep(LATENCY)
    p = payload or {}
    username = (p.get('username') or '').strip()
    password = p.get('password') or ''
    if not username or not password:
        return fail(400, '请输入账号和密码')
    row = db.query_one(
        'SELECT id, username, password_hash, role FROM users WHERE username=%s',
        (username,),
    )
    if not row or not auth.verify_password(password, row['password_hash']):
        return fail(401, '账号或密码错误')
    if row['role'] < 1:
        return fail(403, '该账号没有后台管理权限')
    return {
        'token': auth.make_admin_token(row['id']),
        'admin': {'id': row['id'], 'username': row['username'], 'role': row['role']},
    }


@app.get('/api/admin/kb/stats')
async def admin_kb_stats(_: str = Depends(get_current_admin)):
    """知识库概况：文档数、分块数、向量模型、存储位置等。"""
    await asyncio.sleep(0.05)
    try:
        return rag.stats()
    except rag.RagError as e:
        return fail(500, str(e))


@app.get('/api/admin/docs')
async def admin_list_docs(_: str = Depends(get_current_admin)):
    """已入库文档列表。"""
    await asyncio.sleep(0.05)
    try:
        return rag.list_docs()
    except rag.RagError as e:
        return fail(500, str(e))


@app.post('/api/admin/docs')
async def admin_upload_doc(file: UploadFile = File(...), _: str = Depends(get_current_admin)):
    """上传文档：解析文本 → 递归分块 → 向量化 → 写入本地 Chroma 库。

    同名文档会覆盖旧索引。响应体为入库后的文档信息。
    """
    raw = await file.read()
    if not raw:
        return fail(400, '文件内容为空')
    if len(raw) > MAX_UPLOAD_BYTES:
        return fail(400, '文件过大，请上传 10MB 以内的文档')

    filename = os.path.basename(file.filename or '未命名文档')
    try:
        text = rag.extract_text(filename, raw)
        doc = rag.add_document(filename, text)
    except rag.RagError as e:
        return fail(400, str(e))
    return doc


@app.delete('/api/admin/docs/{doc_id}')
async def admin_delete_doc(doc_id: str, _: str = Depends(get_current_admin)):
    """按文档 ID 删除其全部向量分块。"""
    await asyncio.sleep(0.05)
    try:
        if not rag.delete_document(doc_id):
            return fail(404, '文档不存在')
    except rag.RagError as e:
        return fail(500, str(e))
    return {'ok': True}


@app.post('/api/admin/search')
async def admin_search(payload: dict = Body(default=None), _: str = Depends(get_current_admin)):
    """检索测试：把问题向量化后在知识库中做相似度比对，返回命中片段。"""
    p = payload or {}
    query = (p.get('query') or '').strip()
    if not query:
        return fail(400, '请输入检索内容')
    top_k = _clamp_int(p.get('topK'), 1, 20, rag.TOP_K)
    try:
        return rag.retrieve(query, top_k=top_k)
    except rag.RagError as e:
        return fail(400, str(e))


@app.get('/api/admin/rag-config')
async def admin_get_rag_config(_: str = Depends(get_current_admin)):
    """模块化 RAG 配置：当前各模块开关与检索参数。"""
    return modular_rag.load_config()


@app.put('/api/admin/rag-config')
async def admin_save_rag_config(payload: dict = Body(default=None),
                                _: str = Depends(get_current_admin)):
    """保存模块化 RAG 配置（模块开关 / 融合方式 / 召回参数），策略生成检索时即时生效。"""
    try:
        return modular_rag.save_config(payload or {})
    except OSError as e:
        return fail(500, f'配置写入失败：{e}')


@app.get('/api/admin/rag-eval/dataset')
def admin_rag_eval_dataset(_: str = Depends(get_current_admin)):
    """效果测评：只读当前评测集缓存状态（题目数量联动、是否需重新合成）。"""
    try:
        return rag_eval.dataset_status()
    except Exception as e:
        print(f'[warn] 读取评测集状态失败：{e}')
        return fail(500, f'读取评测集状态失败：{e}')


@app.post('/api/admin/rag-eval')
def admin_rag_eval(payload: dict = Body(default=None), _: str = Depends(get_current_admin)):
    """效果测评（LlamaIndex）：对当前模块化 RAG 配置跑五项指标。

    评测集由 LlamaIndex RagDatasetGenerator 从知识库合成（缓存复用），
    每题跑一遍完整管线后用 LlamaIndex 评估器打分：
    上下文精确率 / 上下文召回率 / 忠实度 / 答案相关性 / 答案正确率。

    请求体：{ numQuestions: 1~20（默认 10）, regenerate: 是否重建评测集 }
    评测耗时较长（每题需多次大模型调用），前端同步等待即可。
    """
    p = payload or {}
    num = _clamp_int(p.get('numQuestions'), 1, 20, 10)
    try:
        return rag_eval.run_evaluation(num_questions=num,
                                       regenerate_dataset=bool(p.get('regenerate')))
    except rag.RagError as e:
        return fail(400, str(e))
    except Exception as e:
        # 详细原因（缺语料 / 模型异常等）只进后端日志，前端统一友好文案
        import traceback
        print(f'[warn] RAG 效果测评失败：{e}')
        traceback.print_exc()
        return fail(500, '服务器繁忙，请稍后重试')


# ================= 后台管理（用户管理） =================
# role 权限等级：0 普通用户 / 1 管理员 / 2 超级管理员
ROLE_USER, ROLE_ADMIN, ROLE_SUPER = 0, 1, 2


def _row_to_user(row):
    return {
        'id': row['id'],
        'username': row['username'],
        'phone': row['phone'],
        'avatar': row['avatar'],
        'role': row['role'],
        'createdAt': row['created_at'].strftime('%Y-%m-%d %H:%M'),
    }


_USER_COLS = 'id, username, phone, avatar, role, created_at'


@app.get('/api/admin/users')
async def admin_list_users(_: dict = Depends(get_current_admin)):
    """用户列表：包含普通用户与管理员，超级管理员置顶。"""
    await asyncio.sleep(0.05)
    rows = db.query(f'SELECT {_USER_COLS} FROM users ORDER BY role DESC, id ASC')
    return [_row_to_user(r) for r in rows]


@app.post('/api/admin/users')
async def admin_create_user(payload: dict = Body(default=None),
                            current: dict = Depends(get_current_admin)):
    """新增用户，role 只能给 0（普通用户）或 1（管理员）；授予权限仅限超级管理员。"""
    await asyncio.sleep(LATENCY)
    p = payload or {}
    username = (p.get('username') or '').strip()
    password = p.get('password') or ''
    phone = (p.get('phone') or '').strip()
    if not username or not password:
        return fail(400, '请填写用户名和密码')
    if len(username) > 50:
        return fail(400, '用户名不能超过 50 个字符')
    if len(password) < 6:
        return fail(400, '密码长度至少 6 位')
    if phone and not re.fullmatch(r'1\d{10}', phone):
        return fail(400, '手机号格式不正确')
    if db.query_one('SELECT id FROM users WHERE username=%s', (username,)):
        return fail(409, '用户名已存在')
    role = _clamp_int(p.get('role'), ROLE_USER, ROLE_ADMIN, ROLE_USER)
    if role != ROLE_USER and current['role'] < ROLE_SUPER:
        return fail(403, '仅超级管理员可授予后台管理权限')
    uid = db.insert(
        'INSERT INTO users (username, password_hash, phone, avatar, role)'
        ' VALUES (%s,%s,%s,%s,%s)',
        (username, auth.hash_password(password), phone or None, username[:1].upper(), role),
    )
    row = db.query_one(f'SELECT {_USER_COLS} FROM users WHERE id=%s', (uid,))
    return _row_to_user(row)


@app.put('/api/admin/users/{user_id}')
async def admin_update_user(user_id: int, payload: dict = Body(default=None),
                            current: dict = Depends(get_current_admin)):
    """编辑用户：用户名、手机号、密码、权限等级（留空字段不改）；权限变更仅限超级管理员。"""
    await asyncio.sleep(LATENCY)
    p = payload or {}
    row = db.query_one('SELECT id, username, role FROM users WHERE id=%s', (user_id,))
    if not row:
        return fail(404, '用户不存在')

    fields, args = [], []
    if 'username' in p:
        username = (p.get('username') or '').strip()
        if not username:
            return fail(400, '用户名不能为空')
        if len(username) > 50:
            return fail(400, '用户名不能超过 50 个字符')
        if username != row['username'] and db.query_one(
                'SELECT id FROM users WHERE username=%s', (username,)):
            return fail(409, '用户名已存在')
        fields += ['username=%s', 'avatar=%s']
        args += [username, username[:1].upper()]
    if 'phone' in p:
        phone = (p.get('phone') or '').strip()
        if phone and not re.fullmatch(r'1\d{10}', phone):
            return fail(400, '手机号格式不正确')
        fields.append('phone=%s')
        args.append(phone or None)
    if 'role' in p:
        if current['role'] < ROLE_SUPER:
            return fail(403, '仅超级管理员可修改用户权限')
        want = _clamp_int(p.get('role'), ROLE_USER, ROLE_SUPER, ROLE_USER)
        if row['role'] == ROLE_SUPER:
            if want != ROLE_SUPER:
                return fail(400, '超级管理员不可取消管理员权限')
        elif want == ROLE_SUPER:
            return fail(400, '超级管理员全局唯一，不可通过接口授予')
        else:
            fields.append('role=%s')
            args.append(want)
    if p.get('password'):
        if len(p['password']) < 6:
            return fail(400, '密码长度至少 6 位')
        fields.append('password_hash=%s')
        args.append(auth.hash_password(p['password']))
    if not fields:
        return fail(400, '没有需要更新的内容')

    args.append(user_id)
    db.execute('UPDATE users SET ' + ', '.join(fields) + ' WHERE id=%s', tuple(args))
    updated = db.query_one(f'SELECT {_USER_COLS} FROM users WHERE id=%s', (user_id,))
    return _row_to_user(updated)


@app.delete('/api/admin/users/{user_id}')
async def admin_delete_user(user_id: int, current: dict = Depends(get_current_admin)):
    """删除用户（连带其偏好/策略/账户/自选股）。

    超级管理员与当前登录账号不可删；普通管理员只能删除普通用户，不能删除管理员账号。
    """
    await asyncio.sleep(LATENCY)
    row = db.query_one('SELECT id, role FROM users WHERE id=%s', (user_id,))
    if not row:
        return fail(404, '用户不存在')
    if row['role'] == ROLE_SUPER:
        return fail(400, '超级管理员不可删除')
    if row['id'] == current['id']:
        return fail(400, '不能删除当前登录账号')
    if row['role'] >= ROLE_ADMIN and current['role'] < ROLE_SUPER:
        return fail(403, '仅超级管理员可删除管理员账号')
    db.execute('DELETE FROM users WHERE id=%s', (user_id,))
    return {'ok': True}


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
    _scrub_task_refs(uid, drop_strategy_id=strategy_id)
    return {'ok': True}


# ================= 账户 =================
def _row_to_account(row, cred=None):
    cred = cred or {}
    return {
        'id': row['id'],
        'name': row['name'],
        'type': row['type'],
        'platformUrl': row['platform_url'],
        'loginAccount': cred.get('login_account') or '',
        'hasPassword': bool(cred.get('password_enc')),
        'status': row['status'],
        'connectStatus': row['connect_status'],
        'lastChecked': row['last_checked'].strftime('%Y-%m-%d %H:%M') if row['last_checked'] else None,
        'totalAssets': float(row['total_assets']),
        'cash': float(row['cash']),
        'created': row['created_at'].strftime('%Y-%m-%d'),
    }


@app.get('/api/accounts')
async def list_accounts(uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.15)
    rows = db.query('SELECT * FROM accounts WHERE user_id=%s ORDER BY id', (uid,))
    creds = {
        c['account_id']: c
        for c in db.query(
            'SELECT * FROM account_credentials WHERE account_id IN (SELECT id FROM accounts WHERE user_id=%s)',
            (uid,),
        )
    }
    return [_row_to_account(r, creds.get(r['id'])) for r in rows]


@app.post('/api/accounts')
async def create_account(payload: dict = Body(default=None), uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.3)
    payload = payload or {}
    name = (payload.get('name') or '').strip()
    if not name:
        return fail(400, '请填写账户显示名称')
    # 资金不由用户设定，创建时为 0，连接成功后由连接器自动读取
    aid = db.insert(
        'INSERT INTO accounts (user_id, name, type, platform_url, status, connect_status, total_assets, cash) '
        'VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
        (uid, name, payload.get('type') or '模拟盘', payload.get('platformUrl') or None,
         'connected', 'untested', 0, 0),
    )
    if payload.get('loginAccount') or payload.get('password'):
        credentials.save(aid, payload.get('loginAccount') or '', payload.get('password') or '')
    row = db.query_one('SELECT * FROM accounts WHERE id=%s', (aid,))
    return _row_to_account(row, credentials.get_raw(aid))


@app.put('/api/accounts/{account_id}')
async def update_account(account_id: int, payload: dict = Body(default=None), uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.2)
    row = db.query_one('SELECT * FROM accounts WHERE id=%s AND user_id=%s', (account_id, uid))
    if not row:
        return fail(404, '账户不存在')
    patch = payload or {}
    db.execute(
        'UPDATE accounts SET name=%s, type=%s, platform_url=%s, status=%s, '
        'total_assets=%s, cash=%s WHERE id=%s',
        (
            patch.get('name', row['name']),
            patch.get('type', row['type']),
            patch.get('platformUrl', row['platform_url']),
            patch.get('status', row['status']),
            float(patch.get('totalAssets', row['total_assets'])),
            float(patch.get('cash', row['cash'])),
            account_id,
        ),
    )
    # 凭证只进不出：密码留空表示不修改；接口响应永不包含密码
    if 'loginAccount' in patch or patch.get('password'):
        credentials.save(account_id, patch.get('loginAccount'), patch.get('password') or None)
    updated = db.query_one('SELECT * FROM accounts WHERE id=%s', (account_id,))
    return _row_to_account(updated, credentials.get_raw(account_id))


@app.post('/api/accounts/{account_id}/test-connection')
async def test_account_connection(account_id: int, uid: int = Depends(get_current_user)):
    row = db.query_one('SELECT * FROM accounts WHERE id=%s AND user_id=%s', (account_id, uid))
    if not row:
        return fail(404, '账户不存在')
    cred = credentials.get_plain(account_id)
    connector = connectors.get_connector(row['type'])
    result = await asyncio.to_thread(
        connector.check_connection, row['platform_url'], cred['loginAccount'], cred['password']
    )
    status = 'ok' if result['ok'] else 'fail'
    # 连接成功后自动读取账户资金（模拟盘固定 100 万，真实盘由平台适配器读取）
    balance = None
    if result['ok']:
        balance = await asyncio.to_thread(
            connector.fetch_balance, row['platform_url'], cred['loginAccount'], cred['password']
        )
        if balance['ok']:
            db.execute(
                'UPDATE accounts SET connect_status=%s, last_checked=NOW(), total_assets=%s, cash=%s WHERE id=%s',
                (status, balance['totalAssets'], balance['cash'], account_id),
            )
        else:
            db.execute('UPDATE accounts SET connect_status=%s, last_checked=NOW() WHERE id=%s', (status, account_id))
    else:
        db.execute('UPDATE accounts SET connect_status=%s, last_checked=NOW() WHERE id=%s', (status, account_id))
    updated = db.query_one('SELECT last_checked, total_assets, cash FROM accounts WHERE id=%s', (account_id,))
    message = result['message']
    if balance:
        message = f"{message}；{balance['message']}"
    return {
        'connectStatus': status,
        'message': message,
        'lastChecked': updated['last_checked'].strftime('%Y-%m-%d %H:%M') if updated['last_checked'] else None,
        'totalAssets': float(updated['total_assets']),
        'cash': float(updated['cash']),
    }


@app.delete('/api/accounts/{account_id}')
async def delete_account(account_id: int, uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.2)
    affected = db.execute('DELETE FROM accounts WHERE id=%s AND user_id=%s', (account_id, uid))
    if not affected:
        return fail(404, '账户不存在')
    _scrub_task_refs(uid, drop_account_id=account_id)
    return {'ok': True}


# ================= 量化交易任务 =================
def _row_to_task(row):
    return {
        'id': row['id'],
        'stockCodes': _json_loads(row['stock_codes']) or [],
        'strategyId': row['strategy_id'],
        'accountId': row['account_id'],
        'autoTrade': bool(row['auto_trade']),
        'created': row['created_at'].strftime('%Y-%m-%d %H:%M'),
    }


def _scrub_task_refs(uid, drop_account_id=None, drop_strategy_id=None):
    """删除账户/策略后，清掉交易任务里的失效引用。"""
    for t in db.query('SELECT id, strategy_id, account_id FROM quant_tasks WHERE user_id=%s', (uid,)):
        changed = False
        strategy_id = t['strategy_id']
        if drop_strategy_id is not None and strategy_id == drop_strategy_id:
            strategy_id = None
            changed = True
        account_id = t['account_id']
        if drop_account_id is not None and account_id == drop_account_id:
            account_id = None
            changed = True
        if changed:
            db.execute('UPDATE quant_tasks SET strategy_id=%s, account_id=%s WHERE id=%s',
                       (strategy_id, account_id, t['id']))


@app.get('/api/quant-tasks')
async def list_quant_tasks(uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.1)
    rows = db.query('SELECT * FROM quant_tasks WHERE user_id=%s ORDER BY id', (uid,))
    return [_row_to_task(r) for r in rows]


@app.post('/api/quant-tasks')
async def create_quant_task(uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.2)
    tid = db.insert(
        'INSERT INTO quant_tasks (user_id, stock_codes, strategy_id, account_id, auto_trade) VALUES (%s,%s,%s,%s,%s)',
        (uid, json.dumps([]), None, None, 0),
    )
    row = db.query_one('SELECT * FROM quant_tasks WHERE id=%s', (tid,))
    return _row_to_task(row)


@app.put('/api/quant-tasks/{task_id}')
async def update_quant_task(task_id: int, payload: dict = Body(default=None), uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.1)
    row = db.query_one('SELECT * FROM quant_tasks WHERE id=%s AND user_id=%s', (task_id, uid))
    if not row:
        return fail(404, '交易任务不存在')
    p = payload or {}
    codes = p.get('stockCodes', _json_loads(row['stock_codes']) or [])
    strategy_id = p.get('strategyId', row['strategy_id'])
    strategy_id = int(strategy_id) if strategy_id not in (None, '') else None
    account_id = p.get('accountId', row['account_id'])
    account_id = int(account_id) if account_id not in (None, '') else None
    auto_trade = 1 if p.get('autoTrade', bool(row['auto_trade'])) else 0
    db.execute(
        'UPDATE quant_tasks SET stock_codes=%s, strategy_id=%s, account_id=%s, auto_trade=%s WHERE id=%s',
        (json.dumps(list(codes)), strategy_id, account_id, auto_trade, task_id),
    )
    updated = db.query_one('SELECT * FROM quant_tasks WHERE id=%s', (task_id,))
    return _row_to_task(updated)


@app.delete('/api/quant-tasks/{task_id}')
async def delete_quant_task(task_id: int, uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.1)
    affected = db.execute('DELETE FROM quant_tasks WHERE id=%s AND user_id=%s', (task_id, uid))
    if not affected:
        return fail(404, '交易任务不存在')
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