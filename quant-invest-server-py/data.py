# -*- coding: utf-8 -*-
"""数据引擎：真实历史行情（Baostock）、实时快照（easyquotation）、财经新闻（财联社）与静态配置。"""
import datetime
import json
import os
import threading

from utils import hash_seed

# ============ 大盘指数 ============
INDICES = [
    {'code': 'SH000001', 'name': '上证指数', 'base': 3128.45},
    {'code': 'SZ399001', 'name': '深证成指', 'base': 9862.13},
    {'code': 'SZ399006', 'name': '创业板指', 'base': 1932.76},
    {'code': 'SH000300', 'name': '沪深300', 'base': 3685.22},
]

# ============ 个股 ============
# code, name, sector 行业板块, base 基准价(今开附近), pe 市盈率
STOCKS = [
    {'code': '600519', 'name': '贵州茅台', 'sector': '白酒消费', 'base': 1685.0, 'pe': 24.5},
    {'code': '000858', 'name': '五粮液', 'sector': '白酒消费', 'base': 142.3, 'pe': 18.2},
    {'code': '603288', 'name': '海天味业', 'sector': '食品消费', 'base': 38.64, 'pe': 35.2},
    {'code': '600887', 'name': '伊利股份', 'sector': '食品消费', 'base': 26.35, 'pe': 16.8},
    {'code': '000333', 'name': '美的集团', 'sector': '家电消费', 'base': 68.92, 'pe': 13.4},
    {'code': '601888', 'name': '中国中免', 'sector': '消费旅游', 'base': 68.15, 'pe': 24.6},
    {'code': '601318', 'name': '中国平安', 'sector': '保险金融', 'base': 48.65, 'pe': 8.6},
    {'code': '600036', 'name': '招商银行', 'sector': '银行金融', 'base': 35.42, 'pe': 6.2},
    {'code': '000001', 'name': '平安银行', 'sector': '银行金融', 'base': 11.28, 'pe': 4.8},
    {'code': '601988', 'name': '中国银行', 'sector': '银行金融', 'base': 4.62, 'pe': 6.0},
    {'code': '600030', 'name': '中信证券', 'sector': '券商金融', 'base': 22.86, 'pe': 14.3},
    {'code': '300059', 'name': '东方财富', 'sector': '券商金融', 'base': 15.63, 'pe': 28.4},
    {'code': '300750', 'name': '宁德时代', 'sector': '新能源', 'base': 198.75, 'pe': 22.1},
    {'code': '002594', 'name': '比亚迪', 'sector': '新能源车', 'base': 245.6, 'pe': 20.8},
    {'code': '601012', 'name': '隆基绿能', 'sector': '光伏新能源', 'base': 18.42, 'pe': 12.5},
    {'code': '601899', 'name': '紫金矿业', 'sector': '有色金属', 'base': 17.56, 'pe': 12.1},
    {'code': '688981', 'name': '中芯国际', 'sector': '半导体', 'base': 88.34, 'pe': 45.6},
    {'code': '000725', 'name': '京东方A', 'sector': '电子科技', 'base': 4.18, 'pe': 22.7},
    {'code': '002415', 'name': '海康威视', 'sector': '人工智能', 'base': 32.18, 'pe': 19.7},
    {'code': '002230', 'name': '科大讯飞', 'sector': '人工智能', 'base': 45.26, 'pe': 72.3},
    {'code': '600050', 'name': '中国联通', 'sector': '通信运营', 'base': 5.46, 'pe': 16.2},
    {'code': '600276', 'name': '恒瑞医药', 'sector': '医药生物', 'base': 46.85, 'pe': 38.9},
    {'code': '300760', 'name': '迈瑞医疗', 'sector': '医药生物', 'base': 268.4, 'pe': 26.3},
    {'code': '600900', 'name': '长江电力', 'sector': '公用事业', 'base': 27.83, 'pe': 19.5},
]


# ============ 真实历史行情（Baostock，前复权，截至最近已收盘交易日） ============
_HISTORY_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_history_cache.json')

# 迷你走势（spark）时间窗口：取最近多少个交易日收盘价。
# 前端对 spark 做归一化（以窗口首日为基准的累计涨跌幅），窗口取 120 天（约半年，指数历史缓存上限）。
SPARK_DAYS = 120


def _bs_symbol(code):
    """转为 Baostock 证券代码：600519 -> sh.600519，SH000001 -> sh.000001。"""
    c = code.upper()
    if c.startswith('SH'):
        return 'sh.' + c[2:]
    if c.startswith('SZ'):
        return 'sz.' + c[2:]
    if c.startswith('6'):
        return 'sh.' + c
    if c.startswith(('0', '3')):
        return 'sz.' + c
    return c


def _fetch_real_histories():
    """一次性拉取全部标的真实历史日K，返回 {code: [candle]}；失败返回 None。

    个股用前复权(adjustflag=2)、指数用不复权(3)。历史只保留到最近一个已收盘
    交易日（剔除今天这根），今日行情交给实时源 easyquotation，实现「历史K线与
    今日实时分离」，从而历史回测口径一致、不被盘中实时价污染。
    """
    try:
        import baostock as bs
    except Exception:
        return None

    try:
        lg = bs.login()
    except Exception:
        return None
    if getattr(lg, 'error_code', '1') != '0':
        return None
    try:
        today = datetime.date.today()
        today_s = today.strftime('%Y-%m-%d')
        specs = [('2', s) for s in STOCKS] + [('3', i) for i in INDICES]
        result = {}
        for adjust, s in specs:
            code = s['code']
            days = 240 if adjust == '2' else 120
            start = (today - datetime.timedelta(days=int(days * 1.6))).strftime('%Y-%m-%d')
            try:
                rs = bs.query_history_k_data_plus(
                    _bs_symbol(code), 'date,open,high,low,close,volume',
                    start_date=start, end_date=today_s,
                    frequency='d', adjustflag=adjust)
            except Exception:
                continue
            rows = []
            while getattr(rs, 'error_code', '1') == '0' and rs.next():
                rows.append(rs.get_row_data())
            if not rows:
                continue
            candles = []
            for r in rows:
                try:
                    d, o, h, l, c, v = r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])
                except (TypeError, ValueError, IndexError):
                    continue
                if d >= today_s:
                    continue
                candles.append({'date': d, 'open': o, 'high': h, 'low': l, 'close': c, 'volume': v})
            if candles:
                result[code] = candles[-days:]
        return result or None
    finally:
        try:
            bs.logout()
        except Exception:
            pass


def _load_history_cache():
    try:
        with open(_HISTORY_CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _save_history_cache(data):
    try:
        with open(_HISTORY_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f)
    except OSError:
        pass


def _apply_histories(data):
    """把真实历史写入内存行情项（实时 tick 会继续覆盖 spark 末点，不冲突）。"""
    m = _market
    if not m or not data:
        return
    for s in m['stocks']:
        if s['code'] in data:
            s['history'] = data[s['code']]
            s['spark'] = [round(c['close'], 2) for c in s['history'][-SPARK_DAYS:]]
    for ix in m['indices']:
        if ix['code'] in data:
            ix['spark'] = [round(c['close'], 2) for c in data[ix['code']][-SPARK_DAYS:]]


def _refresh_real_histories():
    """后台任务：拉真实历史，成功后更新内存并写本地缓存；失败标记历史不可用。"""
    m = _market
    data = _fetch_real_histories()
    if data:
        _apply_histories(data)
        _save_history_cache(data)
        if m is not None:
            m['historyError'] = False
    elif m is not None:
        # 拉取失败且内存中仍无任何真实历史 → 标记不可用（前端提示，不回退模拟）
        m['historyError'] = not any(s['history'] for s in m['stocks'])


# ============ 行情引擎（单例，模拟实时推送） ============
_market = None


def get_market():
    global _market
    if _market:
        return _market

    cached = _load_history_cache() or {}

    stocks = []
    for s in STOCKS:
        history = cached.get(s['code']) or []
        if history:
            last = history[-1]  # 最近一个已收盘交易日（昨收）
            prev_close = last['close']
            volume = last['volume']
            amount = last['volume'] * last['close']
            spark = [round(c['close'], 2) for c in history[-SPARK_DAYS:]]
        else:
            prev_close = s['base']
            volume = 0
            amount = 0
            spark = []
        rnd = hash_seed('meta-' + s['code'])
        item = dict(s)
        item.update({
            'history': history,
            'prevClose': prev_close,
            'open': prev_close,
            'price': prev_close,
            'lastPrice': prev_close,
            'high': prev_close,
            'low': prev_close,
            'volume': volume,
            'amount': amount,
            'turnover': 0.4 + rnd() * 3.2,
            'spark': spark,
        })
        stocks.append(item)

    indices = []
    for ix in INDICES:
        history = cached.get(ix['code']) or []
        if history:
            last = history[-1]
            prev_close = last['close']
            spark = [round(c['close'], 2) for c in history[-SPARK_DAYS:]]
        else:
            prev_close = ix['base']
            spark = []
        item = dict(ix)
        item.update({
            'prevClose': prev_close,
            'open': prev_close,
            'price': prev_close,
            'lastPrice': prev_close,
            'high': prev_close,
            'low': prev_close,
            'amount': 0,
            'spark': spark,
        })
        indices.append(item)

    _market = {
        'stocks': stocks,
        'indices': indices,
        'realtimeError': False,
        'historyError': not any(s['history'] for s in stocks),
    }

    # 后台拉真实历史：有缓存会刷新最新，无缓存则首次补全（失败标记 historyError）
    try:
        threading.Thread(target=_refresh_real_histories, daemon=True).start()
    except Exception:
        pass
    return _market


def _to_prefixed(code):
    """把内部代码（如 600519 / SH000001）转换为 easyquotation 带市场前缀的代码。"""
    c = code.upper()
    if c.startswith('SH'):
        return 'sh' + c[2:]
    if c.startswith('SZ'):
        return 'sz' + c[2:]
    if c.startswith('6'):
        return 'sh' + c
    if c.startswith(('0', '3')):
        return 'sz' + c
    if c.startswith(('4', '8')):
        return 'bj' + c
    return c


_quotation = None


def _get_quotation():
    """惰性初始化 easyquotation 新浪行情源，失败返回 None。"""
    global _quotation
    if _quotation is False:
        return None
    if _quotation is None:
        try:
            import easyquotation
            _quotation = easyquotation.use('sina')
        except Exception:
            _quotation = False
            return None
    return _quotation


def _fetch_realtime(codes):
    """拉取一组代码的实时行情，返回 {原始code: quote}；失败返回 None。"""
    q = _get_quotation()
    if q is None:
        return None
    prefixed_codes = [_to_prefixed(c) for c in codes]
    try:
        data = q.stocks(prefixed_codes, prefix=True)
    except Exception:
        return None
    prefix_map = {_to_prefixed(c): c for c in codes}
    result = {}
    for k, v in (data or {}).items():
        orig = prefix_map.get(k)
        if orig:
            result[orig] = v
    return result


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _apply_stock_quote(s, q):
    """把 easyquotation 行情写入个股字典。"""
    now = _num(q.get('now')) if isinstance(q, dict) else None
    if now is None:
        return
    s['lastPrice'] = s['price']
    s['price'] = now
    if _num(q.get('open')) is not None:
        s['open'] = _num(q.get('open'))
    if _num(q.get('high')) is not None:
        s['high'] = _num(q.get('high'))
    if _num(q.get('low')) is not None:
        s['low'] = _num(q.get('low'))
    if _num(q.get('close')) is not None:
        s['prevClose'] = _num(q.get('close'))
    # 新浪语义：turnover=成交量(股)，volume=成交额(元)
    if _num(q.get('turnover')) is not None:
        s['volume'] = int(_num(q.get('turnover')))
    if _num(q.get('volume')) is not None:
        s['amount'] = _num(q.get('volume'))
    if s['spark']:
        s['spark'][-1] = round(now, 2)
    else:
        s['spark'].append(round(now, 2))


def _apply_index_quote(ix, q):
    """把 easyquotation 行情写入指数字典。"""
    now = _num(q.get('now')) if isinstance(q, dict) else None
    if now is None:
        return
    ix['lastPrice'] = ix['price']
    ix['price'] = now
    if _num(q.get('open')) is not None:
        ix['open'] = _num(q.get('open'))
    if _num(q.get('high')) is not None:
        ix['high'] = _num(q.get('high'))
    if _num(q.get('low')) is not None:
        ix['low'] = _num(q.get('low'))
    if _num(q.get('close')) is not None:
        ix['prevClose'] = _num(q.get('close'))
    if ix['spark']:
        ix['spark'][-1] = round(now, 2)
    else:
        ix['spark'].append(round(now, 2))


def tick_market():
    """推进一个 tick：只用真实行情，失败标记异常（不回退模拟）。"""
    m = get_market()
    codes = [s['code'] for s in m['stocks']] + [i['code'] for i in m['indices']]
    quotes = _fetch_realtime(codes)
    if quotes:
        for s in m['stocks']:
            q = quotes.get(s['code'])
            if q:
                _apply_stock_quote(s, q)
        for ix in m['indices']:
            q = quotes.get(ix['code'])
            if q:
                _apply_index_quote(ix, q)
        m['realtimeError'] = False
    else:
        # 实时行情源失效：保持价格不动，标记异常，交给前端提示
        m['realtimeError'] = True
    return m


# ============ 财经新闻（财联社电报，实时） ============
_news = []
_news_error = True
_news_lock = threading.Lock()

# 板块分类关键词（按顺序命中即归入对应分类）
_NEWS_CATEGORY_RULES = [
    ('宏观政策', ['央行', '降准', '降息', '财政', '发改委', '国常会', '监管', '政策', '利率', '存款准备金', 'LPR', '证监会']),
    ('公司公告', ['公告', '披露', '中标', '定增', '回购', '增持', '减持', '分红', '重组', '并购', '业绩', '半年报', '年报', '季报', '异动']),
    ('新能源', ['新能源', '光伏', '锂电', '锂电池', '储能', '风电', '充电桩', '氢能', '宁德时代', '比亚迪']),
    ('半导体', ['半导体', '芯片', '晶圆', '光刻', '集成电路', '中芯', '存储', '封装']),
    ('人工智能', ['人工智能', 'AI', '大模型', '算力', '机器人', '智能驾驶']),
    ('医药生物', ['医药', '医疗', '疫苗', '创新药', '集采', '医保', '药']),
    ('银行金融', ['银行', '存款', '贷款', '房贷', '信贷', '保险']),
    ('券商金融', ['券商', '证券', 'IPO', '融资融券', '两融', '北向']),
    ('有色金属', ['黄金', '白银', '铜', '铝', '锂矿', '稀土', '有色', '原油', '煤炭']),
    ('消费', ['消费', '白酒', '茅台', '五粮液', '免税', '旅游', '零售', '家电', '食品', '百货']),
    ('全球市场', ['美联储', '美元', '美股', '纳斯达克', '标普', '道指', '欧洲', '日本', '港股']),
    ('市场动态', ['A股', '沪深', '沪指', '深成指', '创业板', '成交额', '涨停', '跌停', '大盘', '指数', '收盘', '融资余额']),
]

_SENT_POS = ['上调', '增长', '突破', '中标', '增持', '回购', '新高', '扩大', '降准', '降息', '利好', '盈利', '超预期', '获批', '翻倍', '上涨', '净流入', '扩张', '涨停', '提振', '回暖', '创新高']
_SENT_NEG = ['下调', '下跌', '亏损', '减持', '处罚', '违规', '风险', '下滑', '违约', '暴雷', '跌停', '净流出', '萎缩', '承压', '利空', '降级', '立案', '诉讼', '破产', '爆仓', '警示']


def _derive_category(text):
    for cat, kws in _NEWS_CATEGORY_RULES:
        if any(k in text for k in kws):
            return cat
    return '财经快讯'


def _derive_sentiment(text):
    pos = sum(1 for w in _SENT_POS if w in text)
    neg = sum(1 for w in _SENT_NEG if w in text)
    if pos > neg:
        return '利好'
    if neg > pos:
        return '利空'
    return '中性'


def _strip_bracket(s):
    s = (s or '').strip()
    while s.startswith('【') and '】' in s:
        s = s[s.index('】') + 1:].strip()
    return s


def _fetch_cls_news(count=20):
    """拉取财联社电报快讯，返回前端契约格式列表；失败返回 None。"""
    try:
        import requests
    except Exception:
        return None
    try:
        sess = requests.Session()
        sess.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        })
        try:
            sess.get('https://m.cls.cn/telegraph', timeout=10)
        except Exception:
            pass
        params = {'refresh_type': '1', 'rn': str(count), 'app': 'CailianpressWap', 'sv': '1'}
        resp = sess.get('https://m.cls.cn/nodeapi/telegraphs', params=params, timeout=15)
        resp.raise_for_status()
        roll = (resp.json().get('data') or {}).get('roll_data') or []
    except Exception:
        return None
    if not roll:
        return None

    tz = datetime.timezone(datetime.timedelta(hours=8))
    items = []
    for i, row in enumerate(roll):
        if not isinstance(row, dict):
            continue
        title = _strip_bracket(row.get('title') or '')
        content = _strip_bracket(row.get('content') or '')
        brief = _strip_bracket(row.get('brief') or '')
        if not title:
            title = brief or content
        if not title:
            continue
        if len(title) > 40:
            title = title[:40] + '…'
        summary = brief or content
        if not summary:
            summary = title
        try:
            t = datetime.datetime.fromtimestamp(int(row.get('ctime')), tz)
        except Exception:
            t = datetime.datetime.now()
        text = title + ' ' + summary + ' ' + content
        items.append({
            'id': row.get('id') or (i + 1),
            'time': t.strftime('%Y-%m-%d %H:%M'),
            'source': '财联社',
            'category': _derive_category(text),
            'sentiment': _derive_sentiment(text),
            'title': title,
            'summary': summary,
            'content': content or summary,
        })
    items.sort(key=lambda x: x['time'], reverse=True)
    return items


def refresh_news():
    """拉取并更新内存新闻；失败时保留旧数据，仅在无任何可展示数据时才标记错误。"""
    global _news, _news_error
    items = _fetch_cls_news()
    with _news_lock:
        if items:
            _news = items
            _news_error = False
        else:
            _news_error = len(_news) == 0


def get_news():
    with _news_lock:
        return list(_news)


def news_error():
    with _news_lock:
        return _news_error


def get_news_categories():
    return ['全部'] + [c for c, _ in _NEWS_CATEGORY_RULES]

# ============ 回测框架 ============
BACKTEST_FRAMEWORKS = [
    {'id': 'quant', 'name': 'QuantEngine 自研框架', 'desc': '平台内置，支持 Tick 级模拟与 GPU 加速，回测速度最快', 'tag': '推荐'},
    {'id': 'backtrader', 'name': 'Backtrader', 'desc': 'Python 社区经典事件驱动框架，指标库丰富'},
    {'id': 'vnpy', 'name': 'vn.py', 'desc': '国产开源框架，回测与实盘交易接口一体化'},
    {'id': 'zipline', 'name': 'Zipline', 'desc': 'Quantopian 开源引擎，适合美股日频策略研究'},
]

# ============ 投资偏好默认值 ============
# 默认值需与前端 quant-invest-vue/src/lib/constants.js 的 DEFAULT_PREFS 保持一致，修改请同步两边
DEFAULT_PREFS = {
    'risk': '稳健型',
    'horizon': '中线（1-6个月）',
    'sectors': ['新能源', '人工智能', '医药生物'],
    'maxPosition': 25,
    'stopLoss': 8,
    'takeProfit': 30,
    'benchmark': '沪深300',
}

