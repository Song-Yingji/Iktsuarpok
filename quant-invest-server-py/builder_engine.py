# -*- coding: utf-8 -*-
"""自由构建（Strategy Builder）引擎：把画布图 DSL 编译成买卖信号。

图是纯数据（节点 + 连线），不是可执行代码：节点类型走白名单，
参数做范围校验，求值只调用内置指标函数，不 eval 任何用户输入。

图结构：
    {
      'version': 1,
      'nodes': [{'id', 'type', 'params': {...}, 'position': {'x', y}}],
      'edges': [{'id', 'source', 'sourcePort', 'target', 'targetPort'}]
    }
端口类型只有两种：series（数值序列）与 bool（布尔序列）。
"""
import math

from indicators import sma, ema, rsi

# 参数规格：kind 用于校验，default/min/max 同时是前端参数面板的依据
NODE_DEFS = {
    'close': {'label': '收盘价', 'group': 'source', 'inputs': {}, 'outputs': {'value': 'series'}, 'params': {}},
    'high': {'label': '最高价', 'group': 'source', 'inputs': {}, 'outputs': {'value': 'series'}, 'params': {}},
    'low': {'label': '最低价', 'group': 'source', 'inputs': {}, 'outputs': {'value': 'series'}, 'params': {}},
    'volume': {'label': '成交量', 'group': 'source', 'inputs': {}, 'outputs': {'value': 'series'}, 'params': {}},
    'const': {'label': '常量', 'group': 'source', 'inputs': {}, 'outputs': {'value': 'series'},
              'params': {'value': {'label': '数值', 'kind': 'float', 'default': 0, 'min': -1e9, 'max': 1e9}}},

    'ma': {'label': 'MA 均线', 'group': 'indicator', 'inputs': {'source': 'series'}, 'outputs': {'value': 'series'},
           'params': {'period': {'label': '周期', 'kind': 'int', 'default': 5, 'min': 2, 'max': 250}}},
    'ema': {'label': 'EMA 均线', 'group': 'indicator', 'inputs': {'source': 'series'}, 'outputs': {'value': 'series'},
            'params': {'period': {'label': '周期', 'kind': 'int', 'default': 12, 'min': 2, 'max': 250}}},
    'rsi': {'label': 'RSI', 'group': 'indicator', 'inputs': {'source': 'series'}, 'outputs': {'value': 'series'},
            'params': {'period': {'label': '周期', 'kind': 'int', 'default': 14, 'min': 2, 'max': 250}}},
    'macd': {'label': 'MACD', 'group': 'indicator', 'inputs': {'source': 'series'},
             'outputs': {'dif': 'series', 'dea': 'series'},
             'params': {'fast': {'label': '快线周期', 'kind': 'int', 'default': 12, 'min': 2, 'max': 100},
                        'slow': {'label': '慢线周期', 'kind': 'int', 'default': 26, 'min': 2, 'max': 200},
                        'signal': {'label': '信号线周期', 'kind': 'int', 'default': 9, 'min': 2, 'max': 100}}},
    'boll': {'label': 'BOLL 布林带', 'group': 'indicator', 'inputs': {'source': 'series'},
             'outputs': {'upper': 'series', 'mid': 'series', 'lower': 'series'},
             'params': {'period': {'label': '周期', 'kind': 'int', 'default': 20, 'min': 2, 'max': 250},
                        'mult': {'label': '标准差倍数', 'kind': 'float', 'default': 2, 'min': 0.5, 'max': 5}}},

    'cross_up': {'label': '上穿（金叉）', 'group': 'condition', 'inputs': {'a': 'series', 'b': 'series'},
                 'outputs': {'value': 'bool'}, 'params': {}},
    'cross_down': {'label': '下穿（死叉）', 'group': 'condition', 'inputs': {'a': 'series', 'b': 'series'},
                   'outputs': {'value': 'bool'}, 'params': {}},
    'gt': {'label': '大于', 'group': 'condition', 'inputs': {'a': 'series', 'b': 'series'},
           'outputs': {'value': 'bool'}, 'params': {}},
    'lt': {'label': '小于', 'group': 'condition', 'inputs': {'a': 'series', 'b': 'series'},
           'outputs': {'value': 'bool'}, 'params': {}},

    'and': {'label': '且 AND', 'group': 'logic', 'inputs': {'a': 'bool', 'b': 'bool'},
            'outputs': {'value': 'bool'}, 'params': {}},
    'or': {'label': '或 OR', 'group': 'logic', 'inputs': {'a': 'bool', 'b': 'bool'},
           'outputs': {'value': 'bool'}, 'params': {}},
    'not': {'label': '非 NOT', 'group': 'logic', 'inputs': {'a': 'bool'},
            'outputs': {'value': 'bool'}, 'params': {}},

    'buy': {'label': '买入信号', 'group': 'action', 'inputs': {'signal': 'bool'}, 'outputs': {}, 'params': {}},
    'sell': {'label': '卖出信号', 'group': 'action', 'inputs': {'signal': 'bool'}, 'outputs': {}, 'params': {}},
}


def normalize_graph(graph):
    """深拷贝并补齐缺省参数 / 边 id，返回规范化的图。"""
    graph = graph if isinstance(graph, dict) else {}
    nodes = []
    for nd in graph.get('nodes') or []:
        if not isinstance(nd, dict):
            continue
        nd = dict(nd)
        spec = NODE_DEFS.get(nd.get('type'), {}).get('params', {})
        params = dict(nd.get('params') or {})
        for key, ps in spec.items():
            if params.get(key) is None:
                params[key] = ps['default']
        nd['params'] = params
        nodes.append(nd)
    edges = []
    for i, e in enumerate(graph.get('edges') or []):
        if not isinstance(e, dict):
            continue
        e = dict(e)
        e.setdefault('id', f'e{i}')
        edges.append(e)
    return {'version': 1, 'nodes': nodes, 'edges': edges}


def validate_graph(graph):
    """校验图合法性，返回错误列表 [{'nodeId', 'message'}]，空列表即通过。"""
    errors = []

    def err(message, node_id=None):
        errors.append({'nodeId': node_id, 'message': message})

    nodes = graph.get('nodes') or []
    edges = graph.get('edges') or []
    if not nodes:
        return [{'nodeId': None, 'message': '画布为空，请先拖入节点'}]

    by_id = {}
    for nd in nodes:
        nid = nd.get('id')
        if not nid or not isinstance(nid, str):
            err('存在缺少 id 的节点')
            continue
        if nid in by_id:
            err(f'节点 id 重复：{nid}', nid)
            continue
        by_id[nid] = nd

    for nid, nd in by_id.items():
        typ = nd.get('type')
        if typ not in NODE_DEFS:
            err(f'未知节点类型：{typ}', nid)
            continue
        spec = NODE_DEFS[typ]['params']
        params = nd.get('params') or {}
        for key, ps in spec.items():
            v = params.get(key, ps['default'])
            try:
                v = int(float(v)) if ps['kind'] == 'int' else float(v)
            except (TypeError, ValueError):
                err(f'{NODE_DEFS[typ]["label"]} 的「{ps["label"]}」不是合法数值', nid)
                continue
            if not (ps['min'] <= v <= ps['max']):
                err(f'{NODE_DEFS[typ]["label"]} 的「{ps["label"]}」需在 {ps["min"]}~{ps["max"]} 之间', nid)
        if typ == 'macd':
            try:
                if float(params.get('fast', 12)) >= float(params.get('slow', 26)):
                    err('MACD 快线周期必须小于慢线周期', nid)
            except (TypeError, ValueError):
                pass

    incoming = {}  # (target, targetPort) -> (source, sourcePort)
    for e in edges:
        src, dst = e.get('source'), e.get('target')
        sp, tp = e.get('sourcePort'), e.get('targetPort')
        if src not in by_id or dst not in by_id:
            err('存在连向不存在节点的连线')
            continue
        src_def, dst_def = NODE_DEFS.get(by_id[src].get('type')), NODE_DEFS.get(by_id[dst].get('type'))
        if not src_def or not dst_def:
            continue
        if sp not in src_def['outputs']:
            err(f'连线输出端口不存在：{sp}', src)
            continue
        if tp not in dst_def['inputs']:
            err(f'连线输入端口不存在：{tp}', dst)
            continue
        if src_def['outputs'][sp] != dst_def['inputs'][tp]:
            err('连线两端类型不匹配（数值序列与布尔信号不能直连）', dst)
            continue
        if (dst, tp) in incoming:
            err(f'{NODE_DEFS[by_id[dst]["type"]]["label"]} 的输入「{tp}」被重复连线', dst)
            continue
        incoming[(dst, tp)] = (src, sp)

    for nid, nd in by_id.items():
        definition = NODE_DEFS.get(nd.get('type'))
        if not definition:
            continue
        for port in definition['inputs']:
            if (nid, port) not in incoming:
                err(f'{definition["label"]} 的输入「{port}」未连线', nid)

    types = [nd.get('type') for nd in by_id.values()]
    if 'buy' not in types:
        err('缺少「买入信号」节点')
    if 'sell' not in types:
        err('缺少「卖出信号」节点')

    # 环检测：沿连线方向 DFS
    adj = {}
    for (dst, _), (src, _) in incoming.items():
        adj.setdefault(src, []).append(dst)
    state = {}

    def dfs(u):
        state[u] = 1
        for v in adj.get(u, []):
            if state.get(v) == 1:
                return True
            if state.get(v) is None and dfs(v):
                return True
        state[u] = 2
        return False

    for nid in by_id:
        if state.get(nid) is None and dfs(nid):
            err('节点连线存在循环，请断开回路')
            break

    return errors


def _topo_order(graph):
    by_id = {nd['id']: nd for nd in graph['nodes']}
    incoming = {(e['target'], e['targetPort']): (e['source'], e['sourcePort']) for e in graph['edges']}
    deps = {nid: set() for nid in by_id}
    for (dst, _), (src, _) in incoming.items():
        deps[dst].add(src)
    order, done = [], set()
    while len(order) < len(by_id):
        progressed = False
        for nid in by_id:
            if nid not in done and deps[nid] <= done:
                order.append(nid)
                done.add(nid)
                progressed = True
        if not progressed:
            raise ValueError('节点连线存在循环')
    return order, by_id, incoming


def compile_signals(graph, candles):
    """把校验通过的图编译为逐 K 线买卖信号（1 买 / -1 卖 / 0 观望）。

    指标序列整段一次算好，条件逐 bar 求值；语义与内置引擎对齐：
    指标预热期（None）视为条件不成立，买入信号优先于卖出。
    """
    n = len(candles)
    order, by_id, incoming = _topo_order(graph)
    out = {}  # nodeId -> {port: list}

    def src(nid, port):
        s, sp = incoming[(nid, port)]
        return out[s][sp]

    closes = [float(c['close']) for c in candles]
    for nid in order:
        nd = by_id[nid]
        typ, p = nd['type'], nd.get('params') or {}
        if typ in ('close', 'high', 'low', 'volume'):
            key = {'close': 'close', 'high': 'high', 'low': 'low', 'volume': 'volume'}[typ]
            out[nid] = {'value': [float(c[key]) for c in candles]}
        elif typ == 'const':
            out[nid] = {'value': [float(p.get('value', 0))] * n}
        elif typ in ('ma', 'ema', 'rsi'):
            fn = {'ma': sma, 'ema': ema, 'rsi': rsi}[typ]
            out[nid] = {'value': fn(src(nid, 'source'), int(p['period']))}
        elif typ == 'macd':
            s = src(nid, 'source')
            ef, es = ema(s, int(p['fast'])), ema(s, int(p['slow']))
            dif = [ef[i] - es[i] for i in range(n)]
            out[nid] = {'dif': dif, 'dea': ema(dif, int(p['signal']))}
        elif typ == 'boll':
            s = src(nid, 'source')
            period, mult = int(p['period']), float(p['mult'])
            mid = sma(s, period)
            upper, lower = [None] * n, [None] * n
            for i in range(n):
                if mid[i] is None:
                    continue
                window = s[i - period + 1:i + 1]
                std = math.sqrt(sum((x - mid[i]) ** 2 for x in window) / period)
                upper[i], lower[i] = mid[i] + mult * std, mid[i] - mult * std
            out[nid] = {'upper': upper, 'mid': mid, 'lower': lower}
        elif typ in ('cross_up', 'cross_down', 'gt', 'lt'):
            a, b = src(nid, 'a'), src(nid, 'b')
            vals = [False] * n
            for i in range(n):
                if a[i] is None or b[i] is None:
                    continue
                if typ == 'gt':
                    vals[i] = a[i] > b[i]
                elif typ == 'lt':
                    vals[i] = a[i] < b[i]
                elif i >= 1 and a[i - 1] is not None and b[i - 1] is not None:
                    if typ == 'cross_up':
                        vals[i] = a[i - 1] <= b[i - 1] and a[i] > b[i]
                    else:
                        vals[i] = a[i - 1] >= b[i - 1] and a[i] < b[i]
            out[nid] = {'value': vals}
        elif typ in ('and', 'or', 'not'):
            a = src(nid, 'a')
            if typ == 'not':
                out[nid] = {'value': [not x for x in a]}
            else:
                b = src(nid, 'b')
                op = (lambda x, y: x and y) if typ == 'and' else (lambda x, y: x or y)
                out[nid] = {'value': [bool(op(a[i], b[i])) for i in range(n)]}
        elif typ in ('buy', 'sell'):
            out[nid] = {'signal': [bool(x) for x in src(nid, 'signal')]}

    signals = [0] * n
    buys = [out[nid]['signal'] for nid, nd in by_id.items() if nd['type'] == 'buy']
    sells = [out[nid]['signal'] for nid, nd in by_id.items() if nd['type'] == 'sell']
    for i in range(n):
        if any(b[i] for b in buys):
            signals[i] = 1
        elif any(s[i] for s in sells):
            signals[i] = -1
    return signals


# ================= 规则文本 / 伪代码生成 =================
_SERIES_LABEL = {'close': '收盘价', 'high': '最高价', 'low': '最低价', 'volume': '成交量'}
_COND_LABEL = {'cross_up': '上穿', 'cross_down': '下穿', 'gt': '>', 'lt': '<'}


def describe_graph(graph):
    """把图翻译成（规则描述数组, 伪代码文本），保存策略时回填 rules / code。"""
    by_id = {nd['id']: nd for nd in graph['nodes']}
    incoming = {(e['target'], e['targetPort']): (e['source'], e['sourcePort']) for e in graph['edges']}

    def series_expr(nid, port='value'):
        nd = by_id[nid]
        typ, p = nd['type'], nd.get('params') or {}
        if typ in _SERIES_LABEL:
            return _SERIES_LABEL[typ]
        if typ == 'const':
            return f'常量{float(p.get("value", 0)):g}'
        src_id, src_port = incoming[(nid, 'source')]
        base = series_expr(src_id, src_port)
        suffix = '' if base == '收盘价' else f'{base},'
        if typ in ('ma', 'ema', 'rsi'):
            return f'{typ.upper()}({suffix}{int(p["period"])})'
        if typ == 'macd':
            name = 'DIF' if port == 'dif' else 'DEA'
            return f'MACD {name}({suffix}{int(p["fast"])},{int(p["slow"])},{int(p["signal"])})'
        if typ == 'boll':
            name = {'upper': '上轨', 'mid': '中轨', 'lower': '下轨'}[port]
            return f'BOLL{name}({suffix}{int(p["period"])},{float(p["mult"]):g})'
        return typ

    def bool_expr(nid):
        nd = by_id[nid]
        typ = nd['type']
        if typ in _COND_LABEL:
            a_id, a_port = incoming[(nid, 'a')]
            b_id, b_port = incoming[(nid, 'b')]
            return f'{series_expr(a_id, a_port)} {_COND_LABEL[typ]} {series_expr(b_id, b_port)}'
        a_id, _ = incoming[(nid, 'a')]
        if typ == 'not':
            return f'(非 {bool_expr(a_id)})'
        b_id, _ = incoming[(nid, 'b')]
        join = '且' if typ == 'and' else '或'
        return f'({bool_expr(a_id)} {join} {bool_expr(b_id)})'

    def action_expr(typ):
        parts = [bool_expr(incoming[(nd['id'], 'signal')][0])
                 for nd in graph['nodes'] if nd['type'] == typ]
        return ' 或 '.join(parts) if parts else '未设置'

    buy_expr, sell_expr = action_expr('buy'), action_expr('sell')
    rules = [
        f'买入条件：{buy_expr}',
        f'卖出条件：{sell_expr}',
        '执行方式：收盘触发信号，全仓买入 / 卖出（只做多）',
    ]
    code = (
        '# 自由构建策略（画布生成）\n'
        f'买入条件 = {buy_expr}\n'
        f'卖出条件 = {sell_expr}\n\n'
        '空仓 且 买入条件成立 → 以收盘价全仓买入\n'
        '持仓 且 卖出条件成立 → 以收盘价全仓卖出'
    )
    return rules, code