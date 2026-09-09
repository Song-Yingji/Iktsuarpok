# -*- coding: utf-8 -*-
"""量化投资平台后端服务（FastAPI）。

接口路径与响应格式与旧 Node/Express 版完全一致，前端零改动。
运行：python main.py  （默认端口 3000）
"""
import asyncio
import re
import threading
import time
import math
from contextlib import asynccontextmanager

from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import uvicorn

from data import (
    get_market, tick_market, NEWS, STRATEGIES, BACKTEST_FRAMEWORKS,
    ACCOUNTS_INIT, POSITIONS_INIT, DEFAULT_PREFS, gen_equity_curve,
)
from utils import hash_seed

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
    if len(password) < 6:
        return fail(400, '密码长度至少 6 位')
    return {'token': 'mock-token-' + str(int(time.time() * 1000)), 'user': {'username': username, 'avatar': str(username)[:1].upper()}}


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
    return {'token': 'mock-token-' + str(int(time.time() * 1000)), 'user': {'username': username, 'avatar': str(username)[:1].upper()}}


# ================= 行情 =================
@app.get('/api/market/snapshot')
async def market_snapshot():
    await asyncio.sleep(0.08)
    return get_market()


@app.get('/api/market/kline/{code}')
async def market_kline(code: str):
    await asyncio.sleep(0.12)
    s = next((x for x in get_market()['stocks'] if x['code'] == code), None)
    return s['history'] if s else fail(404, '标的不存在')


# ================= 新闻 =================
@app.get('/api/news/categories')
def news_categories():
    cats = []
    for n in NEWS:
        if n['category'] not in cats:
            cats.append(n['category'])
    return ['全部'] + cats


@app.get('/api/news')
async def news(category: str = None, keyword: str = None):
    await asyncio.sleep(0.15)
    result = list(NEWS)
    if category and category != '全部':
        result = [n for n in result if n['category'] == category]
    if keyword:
        result = [n for n in result if keyword in (n['title'] + n['summary'])]
    return result


# ================= 投资偏好 =================
prefs_store = dict(DEFAULT_PREFS)


@app.get('/api/prefs')
async def get_prefs():
    await asyncio.sleep(0.1)
    return dict(prefs_store)


@app.post('/api/prefs')
async def save_prefs(payload: dict = Body(default=None)):
    await asyncio.sleep(LATENCY)
    prefs_store.update(payload or {})
    return {'ok': True}


# ================= 智能体 =================
REASON_TPL = [
    '均线呈多头排列，MACD 金叉后红柱持续放大',
    '北向资金连续 3 日净流入，主力资金关注度提升',
    '最新季报营收同比增长 {g}%，基本面超预期',
    '突破前期震荡平台上沿，量能配合放大',
    'RSI 自超卖区回升，短线反弹动能积聚',
    '机构评级上调至"买入"，目标价空间 {t}%',
    '行业景气度上行，板块轮动资金持续流入',
    '波动率收敛后选择向上突破，布林带开口扩张',
]


@app.post('/api/agent/recommend')
async def agent_recommend(payload: dict = Body(default=None)):
    await asyncio.sleep(1.4)
    prefs = payload or {}
    sectors = prefs.get('sectors') or []
    m = get_market()
    seed = 'rec-' + ','.join(sectors) + str(int(time.time()))
    rnd = hash_seed(seed)

    if not sectors:
        pool = list(m['stocks'])
    else:
        pool = [
            s for s in m['stocks']
            if any(sec in s['sector'] or s['sector'] in sec for sec in sectors)
        ]
    picked = sorted(pool, key=lambda _: rnd() - 0.5)[:6]
    result = []
    for s in picked:
        score = int(78 + rnd() * 19 + 0.5)
        reasons = []
        for _ in range(3):
            tpl = REASON_TPL[int(rnd() * len(REASON_TPL))]
            tpl = tpl.replace('{g}', str(12 + int(rnd() * 30 + 0.5)))
            tpl = tpl.replace('{t}', str(15 + int(rnd() * 35 + 0.5)))
            reasons.append(tpl)
        result.append({
            'code': s['code'], 'name': s['name'], 'sector': s['sector'],
            'price': s['price'], 'change': (s['price'] - s['prevClose']) / s['prevClose'],
            'score': score, 'confidence': int(62 + rnd() * 33 + 0.5),
            'action': '建议买入' if rnd() > 0.25 else '建议关注',
            'reasons': list(dict.fromkeys(reasons)),
        })
    result.sort(key=lambda x: -x['score'])
    return result


@app.post('/api/agent/generate-strategy')
async def agent_generate_strategy(payload: dict = Body(default=None)):
    await asyncio.sleep(1.6)
    p = (payload or {}).get('prompt') or ''
    if re.search(r'macd|金叉', p, re.IGNORECASE):
        return {
            'name': 'AI-MACD 零轴金叉策略',
            'type': '趋势跟踪',
            'rules': [
                '入场：DIF 在零轴上方上穿 DEA（金叉），且当日成交量 > 5 日均量 1.2 倍',
                '加仓：回踩 DEA 不破且红柱再次放大时加仓 50%',
                '离场：DIF 下穿 DEA（死叉）或收盘跌破 20 日均线止损',
                '风控：单笔亏损达 8% 强制止损，单票仓位不超过 30%',
            ],
            'code': '# 由策略生成智能体输出\n'
                    'def init(ctx):\n'
                    '    ctx.indicator(\'MACD\', fast=12, slow=26, signal=9)\n'
                    '    ctx.indicator(\'MA\', period=20)\n'
                    '\n'
                    'def on_bar(ctx, bar):\n'
                    '    macd = ctx.indicators[\'MACD\']\n'
                    '    if macd.dif > 0 and ctx.cross_up(macd.dif, macd.dea) \\\n'
                    '       and bar.volume > ctx.ma(\'volume\', 5) * 1.2:\n'
                    '        ctx.buy(bar.symbol, weight=0.3)\n'
                    '    if ctx.cross_down(macd.dif, macd.dea) or bar.close < ctx.ma(20):\n'
                    '        ctx.sell_all(bar.symbol)',
        }
    if re.search(r'动量|轮动|突破|排名', p):
        return {
            'name': 'AI-多标的动量轮动策略',
            'type': '动量轮动',
            'rules': [
                '股票池：沪深300 成分股，每周五收盘后排名',
                '入场：选取过去 20 日涨幅前 3 且站上 20 日均线的标的等权买入',
                '换仓：排名跌出前 10 或跌破 20 日均线时卖出',
                '风控：组合最大回撤超过 12% 时降仓至 50%',
            ],
            'code': 'def init(ctx):\n'
                    '    ctx.universe = ctx.index_members(\'HS300\')\n'
                    '    ctx.rebalance(\'weekly\')\n'
                    '\n'
                    'def on_rebalance(ctx):\n'
                    '    ranked = ctx.rank(ctx.universe, \'momentum_20d\')\n'
                    '    for s in ranked[:3]:\n'
                    '        if ctx.close(s) > ctx.ma(s, 20):\n'
                    '            ctx.buy(s, weight=1/3)\n'
                    '    for pos in ctx.positions:\n'
                    '        if pos.symbol not in ranked[:10]:\n'
                    '            ctx.sell_all(pos.symbol)',
        }
    return {
        'name': 'AI-双均线趋势策略',
        'type': '趋势跟踪',
        'rules': [
            '入场：5 日均线上穿 20 日均线（金叉），次日开盘买入',
            '离场：5 日均线下穿 20 日均线（死叉），次日开盘卖出',
            '过滤：仅在 60 日均线向上时允许开仓，规避熊市',
            '风控：单笔止损 8%，单票最大仓位 30%',
        ],
        'code': 'def init(ctx):\n'
                '    ctx.indicator(\'MA\', 5)\n'
                '    ctx.indicator(\'MA\', 20)\n'
                '    ctx.indicator(\'MA\', 60)\n'
                '\n'
                'def on_bar(ctx, bar):\n'
                '    if ctx.cross_up(ctx.ma(5), ctx.ma(20)) and ctx.ma(60).slope > 0:\n'
                '        ctx.buy(bar.symbol, weight=0.3)\n'
                '    if ctx.cross_down(ctx.ma(5), ctx.ma(20)):\n'
                '        ctx.sell_all(bar.symbol)',
    }


# ================= 策略 / 回测 =================
@app.get('/api/strategy')
def get_strategies():
    return STRATEGIES


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


# ================= 账户 =================
accounts = [dict(a) for a in ACCOUNTS_INIT]


@app.get('/api/accounts')
async def list_accounts():
    await asyncio.sleep(0.15)
    return [dict(a) for a in accounts]


@app.post('/api/accounts')
async def create_account(payload: dict = Body(default=None)):
    await asyncio.sleep(0.3)
    payload = payload or {}
    capital = payload.get('capital') or 100000
    acc = {
        'id': 'ACC-' + str(len(accounts) + 1).zfill(3),
        'status': 'connected', 'totalAssets': capital, 'cash': capital,
        'autoTrade': False, 'strategyId': None, 'strategyEnabled': False,
        'created': time.strftime('%Y-%m-%d'),
    }
    acc.update(payload)
    accounts.append(acc)
    return dict(acc)


@app.put('/api/accounts/{account_id}')
async def update_account(account_id: str, payload: dict = Body(default=None)):
    await asyncio.sleep(0.2)
    acc = next((a for a in accounts if a['id'] == account_id), None)
    if not acc:
        return fail(404, '账户不存在')
    patch = payload or {}
    if patch.get('autoTrade') and not acc.get('strategyId') and not patch.get('strategyId'):
        return fail(400, '请先为账户绑定量化策略，再开启自动交易')
    acc.update(patch)
    return dict(acc)


# ================= 持仓 / 资产 =================
@app.get('/api/positions')
async def positions():
    await asyncio.sleep(0.15)
    m = get_market()
    positions_list = []
    for p in POSITIONS_INIT:
        s = next((x for x in m['stocks'] if x['code'] == p['code']), None)
        price = s['price'] if s else p['cost']
        name = s['name'] if s else p['code']
        market_value = price * p['qty']
        cost_value = p['cost'] * p['qty']
        positions_list.append({
            'code': p['code'], 'name': name, 'qty': p['qty'], 'cost': p['cost'], 'price': price,
            'marketValue': market_value, 'pnl': market_value - cost_value,
            'pnlPct': price / p['cost'] - 1, 'weight': 0,
            'dayPct': (s['price'] - s['prevClose']) / s['prevClose'] if s else 0,
        })
    total_market_value = sum(p['marketValue'] for p in positions_list)
    cash = 326500
    total_assets = total_market_value + cash
    for p in positions_list:
        p['weight'] = p['marketValue'] / total_assets
    total_pnl = sum(p['pnl'] for p in positions_list)
    day_pnl = sum(p['marketValue'] * p['dayPct'] / (1 + p['dayPct']) for p in positions_list)
    return {
        'accounts': [{**a, 'curve': gen_equity_curve(a['id'], a['totalAssets'])} for a in accounts],
        'positions': positions_list,
        'summary': {
            'totalAssets': total_assets, 'totalMarketValue': total_market_value, 'cash': cash,
            'totalPnl': total_pnl, 'dayPnl': day_pnl, 'totalCost': total_market_value - total_pnl,
        },
    }


@app.get('/api/health')
def health():
    return {'status': 'ok', 'service': 'quant-invest-server', 'lang': 'python'}


@app.exception_handler(404)
async def not_found(request, exc):
    return fail(404, '接口不存在')


if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=PORT, log_level='info', use_colors=False)