# -*- coding: utf-8 -*-
"""策略回测引擎：内置五策略的信号生成 + 自由构建图信号，共用模拟交易与绩效计算。"""
import math

import builder_engine
from data import get_market
from indicators import sma, ema, rsi


def simulate(candles, signals, capital, stop_loss=None):
    """逐 K 线模拟交易并计算绩效指标。

    只做多、全仓进出、收盘价成交；stop_loss 为百分比止损线（仅动量策略使用）。
    """
    closes = [c['close'] for c in candles]
    n = len(candles)
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
        if stop_loss is not None and shares > 0 and price / entry_price - 1 <= -stop_loss / 100:
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
        'candles': candles, 'equity': equity, 'trades': trades, 'points': points,
        'metrics': {
            'totalReturn': total_return, 'annualized': annualized, 'benchReturn': bench_return,
            'maxDD': max_dd, 'sharpe': sharpe, 'cvar': cvar,
            'winRate': win_rate, 'plRatio': pl_ratio, 'tradeCount': len(trades),
            'finalValue': values[-1], 'ddEnd': dd_end,
        },
    }


def run_backtest(strategy_id, stock_code, params, capital, framework, range_days):
    m = get_market()
    stock = next((s for s in m['stocks'] if s['code'] == stock_code), None) or m['stocks'][0]
    candles = stock['history'][-range_days:]
    closes = [c['close'] for c in candles]
    n = len(candles)
    stop_loss = None

    if strategy_id == 'builder':
        graph = builder_engine.normalize_graph(params)
        errors = builder_engine.validate_graph(graph)
        if errors:
            raise ValueError(errors[0]['message'])
        signals = builder_engine.compile_signals(graph, candles)
    else:
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
            stop_loss = params['stop']

    result = simulate(candles, signals, capital, stop_loss)
    return {
        'stock': stock, 'framework': framework, 'capital': capital, 'rangeDays': range_days,
        **result,
    }