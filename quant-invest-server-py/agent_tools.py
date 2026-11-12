# -*- coding: utf-8 -*-
"""智能体工具层：白名单工具 + 参数校验，供 ReAct 与迭代研究循环调用。

所有工具只读行情 / 知识库或做受限的自选股 DB 操作，不 eval 任何用户输入。
每个工具返回 (result_dict, summary_text)：前者供程序消费，后者作为 Observation 回喂模型。
"""
import math

import pymysql
import requests

import db
import modular_rag
import rag
from data import get_market, get_news, refresh_news
from indicators import sma, ema, rsi

# 历史数据尺度：后端仅保有日线（≤240 天）+ 实时快照，工具据此设计查询粒度
MAX_HISTORY_DAYS = 240


def _norm_code(code):
    code = str(code or '').strip().lower()
    for pre in ('sh.', 'sz.', 'sh', 'sz'):
        if code.startswith(pre):
            code = code[len(pre):]
    return code.strip('.')


def _find_stock(key):
    key = str(key or '').strip()
    if not key:
        return None
    code = _norm_code(key)
    for s in get_market()['stocks']:
        if s['code'] == code or s['name'] == key:
            return s
    return None


def _pct(v, digits=2):
    return '--' if v is None else f'{v:.{digits}f}%'


def _yi(v):
    return None if v in (None, '', '-') else round(float(v) / 1e8, 2)


# ---------------- 行情查询 ----------------
def query_stock(args, ctx):
    s = _find_stock(args.get('code') or args.get('name'))
    if not s:
        return {'error': f'未找到标的：{args.get("code")}'}, f'未找到标的 {args.get("code")}，仅支持平台内置 A 股。'
    hist = s.get('history') or []
    start, end = args.get('start'), args.get('end')
    if start or end:
        sel = [c for c in hist if (not start or c['date'] >= start) and (not end or c['date'] <= end)]
    else:
        sel = hist[-int(args.get('days') or 30):]
    closes = [c['close'] for c in sel]
    stats = {}
    if len(closes) >= 2:
        stats = {
            '区间涨幅%': round((closes[-1] / closes[0] - 1) * 100, 2),
            '区间最高': max(closes), '区间最低': min(closes),
            '日均成交量': round(sum(c['volume'] for c in sel) / len(sel), 0),
        }
    price, prev = s.get('price') or 0, s.get('prevClose') or 0
    realtime = {
        '现价': price, '涨跌幅%': round((price - prev) / prev * 100, 2) if prev else 0,
        '今开': s.get('open'), '最高': s.get('high'), '最低': s.get('low'),
        '成交量': s.get('volume'), '换手率%': s.get('turnover'),
    }
    result = {'code': s['code'], 'name': s['name'], 'sector': s['sector'],
              'realtime': realtime, 'range': {'start': sel[0]['date'] if sel else None,
                                             'end': sel[-1]['date'] if sel else None, 'days': len(sel)},
              'stats': stats, 'recent': sel[-5:]}
    summary = (f'{s["name"]}({s["code"]}) 现价{price} {_pct(realtime["涨跌幅%"])}；'
               f'区间{result["range"]["start"]}~{result["range"]["end"]}共{len(sel)}天，'
               f'区间涨幅{_pct(stats.get("区间涨幅%"))}，最高{stats.get("区间最高")}最低{stats.get("区间最低")}。')
    return result, summary


# ---------------- 自选股（DB 操作，需登录 uid） ----------------
def add_watchlist(args, ctx):
    s = _find_stock(args.get('code') or args.get('name'))
    if not s:
        return {'error': '未找到标的'}, f'未找到标的 {args.get("code")}，无法加入自选。'
    already = {'ok': False, 'already': True, 'code': s['code'], 'name': s['name']}
    if db.query_one('SELECT id FROM watchlist WHERE user_id=%s AND stock_code=%s', (ctx['uid'], s['code'])):
        return already, f'{s["name"]}({s["code"]}) 股票已在自选股中，无需重复添加。'
    try:
        db.insert('INSERT INTO watchlist (user_id, stock_code) VALUES (%s,%s)', (ctx['uid'], s['code']))
    except pymysql.err.IntegrityError:
        return already, f'{s["name"]}({s["code"]}) 股票已在自选股中，无需重复添加。'
    return {'ok': True, 'code': s['code'], 'name': s['name']}, f'已将 {s["name"]}({s["code"]}) 加入自选股。'


def remove_watchlist(args, ctx):
    s = _find_stock(args.get('code') or args.get('name'))
    if not s:
        return {'error': '未找到标的'}, f'未找到标的 {args.get("code")}，无法移除。'
    db.execute('DELETE FROM watchlist WHERE user_id=%s AND stock_code=%s', (ctx['uid'], s['code']))
    return {'ok': True, 'code': s['code'], 'name': s['name']}, f'已将 {s["name"]}({s["code"]}) 从自选股移除。'


# ---------------- 基本面（联网东方财富，失败回退静态 PE） ----------------
def fundamentals(args, ctx):
    s = _find_stock(args.get('code') or args.get('name'))
    if not s:
        return {'error': '未找到标的'}, f'未找到标的 {args.get("code")}。'
    code = s['code']
    secid = ('1.' if code.startswith(('6', '9', '5')) else '0.') + code
    fields = 'f57,f58,f162,f167,f116,f117,f173,f183,f184,f105,f185,f186,f187,f188'
    try:
        resp = requests.get('https://push2.eastmoney.com/api/qt/stock/get',
                            params={'secid': secid, 'fields': fields, 'invt': '2', 'fltt': '2'},
                            timeout=8, headers={'User-Agent': 'Mozilla/5.0'})
        d = (resp.json() or {}).get('data') or {}
    except Exception as e:
        d = {}
        print(f'[warn] 东方财富基本面获取失败：{e}')

    def num(key, scale=1.0):
        v = d.get(key)
        if v in (None, '', '-'):
            return None
        try:
            return round(float(v) / scale, 2)
        except (TypeError, ValueError):
            return None

    online = {
        '市盈率(动)': num('f162'), '市净率': num('f167'),
        '总市值(亿)': _yi(d.get('f116')), '流通市值(亿)': _yi(d.get('f117')),
        'ROE%': num('f173'), '总营收(亿)': _yi(d.get('f183')), '营收同比%': num('f184'),
        '净利润(亿)': _yi(d.get('f105')), '净利同比%': num('f185'),
        '毛利率%': num('f186'), '净利率%': num('f187'), '资产负债率%': num('f188'),
    }
    online = {k: v for k, v in online.items() if v is not None}
    if online:
        result = {'code': code, 'name': s['name'], 'sector': s['sector'], 'source': '东方财富(联网,参考)', **online}
        summary = (f'{s["name"]} 基本面(东方财富)：PE(动){online.get("市盈率(动)", "--")}、PB{online.get("市净率", "--")}、'
                   f'总市值{online.get("总市值(亿)", "--")}亿、ROE{online.get("ROE%", "--")}%、'
                   f'营收同比{_pct(online.get("营收同比%"))}、净利同比{_pct(online.get("净利同比%"))}。')
    else:
        result = {'code': code, 'name': s['name'], 'sector': s['sector'], 'source': '本地静态(联网失败)', 'pe': s.get('pe')}
        summary = f'{s["name"]} 联网基本面获取失败，回退本地静态 PE={s.get("pe")}，板块{s["sector"]}。'
    return result, summary


# ---------------- 走势分析 ----------------
def analyze_trend(args, ctx):
    s = _find_stock(args.get('code') or args.get('name'))
    if not s:
        return {'error': '未找到标的'}, f'未找到标的 {args.get("code")}。'
    closes = [c['close'] for c in (s.get('history') or [])]
    if len(closes) < 30:
        return {'error': '历史数据不足'}, f'{s["name"]} 历史数据不足，无法分析走势。'
    ma5, ma20, ma60 = sma(closes, 5)[-1], sma(closes, 20)[-1], sma(closes, 60)[-1] if len(closes) >= 60 else None
    r = rsi(closes, 14)[-1]
    ef, es = ema(closes, 12), ema(closes, 26)
    dif = [ef[i] - es[i] for i in range(len(closes))]
    dea = ema(dif, 9)[-1]
    rets = [closes[i] / closes[i - 1] - 1 for i in range(len(closes) - 20, len(closes))]
    mean = sum(rets) / len(rets)
    vol = math.sqrt(sum((x - mean) ** 2 for x in rets) / len(rets)) * math.sqrt(252) * 100
    hi, lo = max(closes[-60:]), min(closes[-60:])
    pos = (closes[-1] - lo) / (hi - lo) * 100 if hi > lo else 50.0
    chg20 = (closes[-1] / closes[-21] - 1) * 100
    if ma5 and ma20 and ma5 > ma20 and closes[-1] > ma20:
        verdict = '多头趋势（均线多头排列，价格站上 MA20）'
    elif ma5 and ma20 and ma5 < ma20 and closes[-1] < ma20:
        verdict = '空头趋势（均线空头排列，价格跌破 MA20）'
    else:
        verdict = '震荡整理（均线纠缠，方向不明）'
    result = {'code': s['code'], 'name': s['name'], 'MA5': round(ma5, 2), 'MA20': round(ma20, 2),
              'MA60': round(ma60, 2) if ma60 else None, 'RSI14': round(r, 1),
              'MACD_DIF': round(dif[-1], 3), 'MACD_DEA': round(dea, 3),
              '20日年化波动%': round(vol, 1), '60日位置%': round(pos, 0), '20日涨幅%': round(chg20, 2),
              '支撑': round(lo, 2), '压力': round(hi, 2), '趋势': verdict}
    summary = (f'{s["name"]} 走势：{verdict}；MA5={result["MA5"]}/MA20={result["MA20"]}/MA60={result["MA60"]}，'
               f'RSI14={result["RSI14"]}，20日涨幅{_pct(chg20)}，60日位置{_pct(pos, 0)}，'
               f'支撑{result["支撑"]}压力{result["压力"]}。')
    return result, summary


# ---------------- 财经新闻（财联社缓存，支持关键词 / 分类过滤） ----------------
def query_news(args, ctx):
    items = get_news()
    if not items:
        refresh_news()
        items = get_news()
    keyword = (args.get('keyword') or '').strip()
    category = (args.get('category') or '').strip()
    if category and category != '全部':
        items = [n for n in items if n.get('category') == category]
    if keyword:
        items = [n for n in items if keyword in (n.get('title', '') + n.get('summary', '') + n.get('content', ''))]
    try:
        limit = max(1, min(20, int(args.get('limit') or 5)))
    except (TypeError, ValueError):
        limit = 5
    sel = items[:limit]
    result = {'count': len(sel), 'total': len(items),
              'items': [{'time': n['time'], 'category': n['category'], 'sentiment': n['sentiment'],
                         'title': n['title'], 'summary': n['summary']} for n in sel]}
    if not sel:
        return result, f'未检索到匹配的新闻（关键词={keyword or "无"}、分类={category or "全部"}，当前缓存 {len(items)} 条）。'
    lines = '\n'.join(f'[{n["time"]}][{n["category"]}/{n["sentiment"]}] {n["title"]}' for n in sel)
    return result, f'财经快讯{len(sel)}条（共匹配{len(items)}条）：\n{lines}'


# ---------------- RAG 检索（仅检索，不改后台配置） ----------------
def rag_search(args, ctx):
    query = (args.get('query') or '').strip()
    if not query:
        return {'hits': []}, '检索词为空。'
    try:
        hits = modular_rag.get_modular_rag().retrieve(query)
    except rag.RagError:
        hits = []
    except Exception as e:
        print(f'[warn] 工具 RAG 检索失败：{e}')
        hits = []
    result = {'count': len(hits), 'hits': [{'docName': h['docName'], 'score': round(h['score'], 3), 'text': h['text']} for h in hits]}
    if not hits:
        return result, '本地知识库未命中相关片段。'
    text = '\n'.join(f'[{i + 1}]《{h["docName"]}》{h["text"][:200]}' for i, h in enumerate(hits))
    return result, f'知识库命中{len(hits)}条：\n{text}'


# ---------------- 工具注册表（ReAct 可用；generate_strategy 仅策略意图专属，不在此列） ----------------
TOOLS = {
    'query_stock': {
        'desc': '查询某只 A 股的实时快照与指定日期区间（或最近 N 天）的日线行情、区间统计。参数 code(必填,代码或名称), start/end(可选,YYYY-MM-DD), days(可选,默认30)',
        'fn': query_stock,
    },
    'add_watchlist': {
        'desc': '把某只股票加入当前用户自选股。参数 code(必填,代码或名称)',
        'fn': add_watchlist,
    },
    'remove_watchlist': {
        'desc': '把某只股票从当前用户自选股移除。参数 code(必填,代码或名称)',
        'fn': remove_watchlist,
    },
    'fundamentals': {
        'desc': '联网查询某只股票的基本面（PE/PB/市值/ROE/营收/利润/毛利率等，东方财富）。参数 code(必填)',
        'fn': fundamentals,
    },
    'analyze_trend': {
        'desc': '分析某只股票的技术走势（均线/RSI/MACD/波动率/支撑压力/趋势结论）。参数 code(必填)',
        'fn': analyze_trend,
    },
    'query_news': {
        'desc': '查询财经新闻快讯（财联社，含分类与情绪标签）。参数 keyword(可选,关键词), category(可选,宏观政策/公司公告/新能源/半导体/人工智能/医药生物/银行金融/券商金融/有色金属/消费/全球市场/市场动态), limit(可选,默认5)',
        'fn': query_news,
    },
    'rag_search': {
        'desc': '检索本地量化知识库（仅检索，不改变后台 RAG 配置）。参数 query(必填,检索词)',
        'fn': rag_search,
    },
}


def run_tool(name, args, ctx):
    tool = TOOLS.get(name)
    if not tool:
        return {'error': f'未知工具：{name}'}, f'未知工具 {name}。'
    try:
        return tool['fn'](args or {}, ctx)
    except Exception as e:
        print(f'[warn] 工具 {name} 执行失败：{e}')
        return {'error': str(e)}, f'工具 {name} 执行失败：{e}'