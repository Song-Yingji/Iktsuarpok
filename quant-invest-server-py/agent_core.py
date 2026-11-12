# -*- coding: utf-8 -*-
"""智能体编排层：意图识别 → 四路分发（闲聊直连 / 知识问答 RAG / ReAct 工具 / 迭代研究循环）。

- chat：注入闲聊提示词直连大模型，不碰工具。
- knowledge：量化 / 投资知识问答，先检索本地知识库再据参考资料回答。
- tool：ReAct（Thought→Action→Observation）循环调用 agent_tools 白名单工具。
- strategy：R&D-Agent(Q) 式有界迭代 Research→Development→Feedback，
  Development 生成结构化策略并送真实历史回测，Feedback 以绩效合成奖励、
  用简化多臂老虎机（epsilon-greedy）在「保留最优」与「探索新引擎」间权衡。
策略始终为结构化 DSL（engineId+params），不 eval 任何模型代码。

对外入口 run_agent_stream 是生成器，边执行边产出事件，由路由包装成 SSE：
闲聊 / 知识问答逐 token 流式，工具 / 策略路由实时推送每步 trace 与策略卡片。
意图识别走「高置信度规则优先、含糊才调模型」，省掉一次串行大模型往返。
"""
import json
import random
import re

import agent_tools
import backtest
import llm
import prompts

MAX_REACT_STEPS = 6
MAX_ROUNDS = 3
EPSILON = 0.3          # 探索概率（简化 bandit）
STOP_REWARD = 0.55     # 奖励达标即提前收敛

# 引擎参数规格（与 prompts.SYSTEM_PROMPT 保持一致），用于收敛模型给出的参数
ENGINE_SPECS = {
    'ma_cross': {'fast': (2, 30, 5), 'slow': (10, 120, 20)},
    'macd': {'fast': (5, 20, 12), 'slow': (15, 40, 26), 'signal': (5, 15, 9)},
    'rsi': {'period': (6, 30, 14), 'low': (10, 40, 30), 'high': (60, 90, 70)},
    'boll': {'period': (10, 60, 20), 'mult': (1, 3, 2)},
    'momentum': {'lookback': (10, 60, 20), 'stop': (3, 20, 8)},
}


def _extract_json(text):
    """从模型输出中提取第一个平衡的 JSON 对象，容忍前后杂散文字。"""
    text = (text or '').strip()
    start = text.find('{')
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1], strict=False)
                except json.JSONDecodeError:
                    return None
    return None


def _rule_intent(text):
    """高置信度规则：命中即确定意图，省掉一次分类用的大模型往返。

    只覆盖措辞明确的请求；含糊的一律返回 None 交给 LLM 判定，避免误路由。
    """
    if re.search(r'(写|生成|设计|创建|构建|做)(一[个套]|个|套)?策略', text) or \
            re.search(r'^\s*(写|生成|设计|创建|构建|做|帮我写|给我|来).{0,30}策略', text):
        return 'strategy'
    if re.search(r'(什么是|是什么|什么意思|原理|含义|区别|怎么用|如何使用|如何理解|怎么理解|怎么算|如何计算)', text):
        return 'knowledge'
    if re.search(r'(加入|添加|移除|删除).{0,6}自选|自选.{0,6}(加入|添加|移除|删除)', text):
        return 'tool'
    if re.search(r'(查|查询|查一下|看下|看一下).{0,10}(行情|走势|基本面|新闻|快讯|股价|价格|多少钱)', text):
        return 'tool'
    if re.search(r'分析.{0,8}(走势|基本面|行情|这只|该股|股)', text):
        return 'tool'
    if re.search(r'(财经新闻|最新新闻|今日新闻|有什么新闻|新闻快讯|有哪些新闻)', text):
        return 'tool'
    if re.search(r'^\s*(你好|您好|hi|hello|嗨|哈喽|在吗|在么|谢谢|多谢|再见|拜拜)[\s!！。~～]*$', text, re.I):
        return 'chat'
    if re.search(r'(介绍一下你|介绍下你|你是谁|你叫什么|你能做什么|你会什么)', text):
        return 'chat'
    return None


def _fallback_intent(text):
    """LLM 分类失败时的宽松兜底，保证四路分发总有结果。"""
    if re.search(r'(写|生成|设计|创建|做|构建).{0,8}策略', text):
        return 'strategy'
    if re.search(r'(什么是|是什么|什么意思|原理|含义|区别|为什么|怎么用|如何使用|如何理解|怎么理解)', text):
        return 'knowledge'
    if re.search(r'(自选|加入|移除|删除|查询|查一?下|走势|基本面|行情|分析|新闻|快讯|多少钱|涨|跌)', text):
        return 'tool'
    return 'chat'


def classify_intent(query):
    rule = _rule_intent(query)
    if rule:
        return rule, '规则命中，跳过分类模型'
    obj = _extract_json(llm.chat([{'role': 'user', 'content': query}], system_prompt=prompts.INTENT_PROMPT))
    intent = (obj or {}).get('intent')
    if intent not in ('strategy', 'knowledge', 'tool', 'chat'):
        return _fallback_intent(query), '规则兜底'
    return intent, (obj or {}).get('reason') or ''


def _clamp_params(engine, params):
    spec = ENGINE_SPECS.get(engine, {})
    out = {}
    for key, (lo, hi, default) in spec.items():
        try:
            v = float((params or {}).get(key, default))
        except (TypeError, ValueError):
            v = default
        v = max(lo, min(hi, v))
        out[key] = int(v) if key != 'mult' else round(v, 2)
    return out


def _reward(m):
    if not m:
        return -1.0
    ann = max(-1, min(1, m.get('annualized', 0)))
    sharpe = max(0, min(1, m.get('sharpe', 0) / 3))
    dd = max(0, min(1, 1 + m.get('maxDD', 0)))
    win = max(0, min(1, m.get('winRate', 0)))
    return 0.4 * ann + 0.3 * sharpe + 0.2 * dd + 0.1 * win


def _rules_code(engine, p):
    if engine == 'ma_cross':
        rules = [f'入场：{p["fast"]}日均线上穿{p["slow"]}日均线（金叉）买入',
                 f'离场：{p["fast"]}日均线下穿{p["slow"]}日均线（死叉）卖出',
                 '执行：收盘触发信号，全仓进出（只做多）']
        code = f'def init(ctx):\n    ctx.indicator("MA", {p["fast"]})\n    ctx.indicator("MA", {p["slow"]})\n\ndef on_bar(ctx, bar):\n    if ctx.cross_up(ctx.ma({p["fast"]}), ctx.ma({p["slow"]})):\n        ctx.buy(bar.symbol)\n    if ctx.cross_down(ctx.ma({p["fast"]}), ctx.ma({p["slow"]})):\n        ctx.sell_all(bar.symbol)'
    elif engine == 'macd':
        rules = [f'DIF 上穿 DEA 且 DIF>0（零轴上金叉）买入', 'DIF 下穿 DEA（死叉）卖出',
                 f'参数：EMA{p["fast"]}/{p["slow"]}，DEA{p["signal"]}']
        code = f'def init(ctx):\n    ctx.indicator("MACD", {p["fast"]}, {p["slow"]}, {p["signal"]})\n\ndef on_bar(ctx, bar):\n    if ctx.cross_up(ctx.dif, ctx.dea) and ctx.dif > 0:\n        ctx.buy(bar.symbol)\n    if ctx.cross_down(ctx.dif, ctx.dea):\n        ctx.sell_all(bar.symbol)'
    elif engine == 'rsi':
        rules = [f'RSI{p["period"]} 从下方上穿{p["low"]}（超卖回升）买入', f'RSI 从上方下穿{p["high"]}（超买回落）卖出']
        code = f'def init(ctx):\n    ctx.indicator("RSI", {p["period"]})\n\ndef on_bar(ctx, bar):\n    if ctx.cross_up(ctx.rsi, {p["low"]}):\n        ctx.buy(bar.symbol)\n    if ctx.cross_down(ctx.rsi, {p["high"]}):\n        ctx.sell_all(bar.symbol)'
    elif engine == 'boll':
        rules = [f'收盘价跌破布林下轨（{p["period"]}日,{p["mult"]}倍标准差）买入', '收盘价突破布林上轨卖出']
        code = f'def init(ctx):\n    ctx.indicator("BOLL", {p["period"]}, {p["mult"]})\n\ndef on_bar(ctx, bar):\n    if bar.close < ctx.lower:\n        ctx.buy(bar.symbol)\n    if bar.close > ctx.upper:\n        ctx.sell_all(bar.symbol)'
    else:
        rules = [f'收盘价突破前{p["lookback"]}日高点买入', f'跌破 MA20 或止损{p["stop"]}%卖出']
        code = f'def init(ctx):\n    ctx.indicator("MA", 20)\n\ndef on_bar(ctx, bar):\n    if bar.close > ctx.high_n({p["lookback"]}):\n        ctx.buy(bar.symbol)\n    if bar.close < ctx.ma(20) or ctx.drawdown > {p["stop"]} / 100:\n        ctx.sell_all(bar.symbol)'
    return rules, code


FALLBACK_TEXT = '抱歉，我这边暂时没响应过来，请稍后再问我一次。'


def run_chat(messages):
    """闲聊：直连大模型，逐 token 流式输出。"""
    yield 'trace', {'type': 'chat'}
    got = False
    for delta in llm.chat_stream(messages, system_prompt=prompts.CHAT_PROMPT):
        got = True
        yield 'text', delta
    if not got:
        yield 'text', FALLBACK_TEXT


def run_knowledge(messages, ctx):
    """知识问答：先检索本地知识库，再据参考资料流式作答。"""
    query = messages[-1].get('content', '') if messages else ''
    rag_result, rag_text = agent_tools.rag_search({'query': query}, ctx)
    rag_count = rag_result.get('count', 0)
    sources = [{'docName': h['docName'], 'score': h['score']} for h in rag_result.get('hits', [])]
    yield 'trace', {'type': 'knowledge', 'count': rag_count}
    yield 'rag', {'count': rag_count, 'sources': sources}
    system = prompts.build_knowledge_system(rag_text)
    got = False
    for delta in llm.chat_stream(messages, system_prompt=system):
        got = True
        yield 'text', delta
    if not got:
        yield 'text', FALLBACK_TEXT


def run_react(messages, ctx):
    """工具路由：ReAct 循环，每步实时推送 trace，最后给出面向用户的回答。"""
    tools_desc = '\n'.join(f'- {name}: {t["desc"]}' for name, t in agent_tools.TOOLS.items())
    system = prompts.build_react_system(tools_desc)
    history = [dict(m) for m in messages]
    trace, observations, text = [], [], ''
    for step in range(1, MAX_REACT_STEPS + 1):
        resp = llm.chat(history, system_prompt=system)
        obj = _extract_json(resp)
        if not obj:
            text = resp or FALLBACK_TEXT
            trace.append({'type': 'react', 'step': step, 'thought': '', 'final': True})
            yield 'trace', trace[-1]
            break
        if obj.get('final_answer'):
            text = obj['final_answer']
            trace.append({'type': 'react', 'step': step, 'thought': obj.get('thought', ''), 'final': True})
            yield 'trace', trace[-1]
            break
        action = obj.get('action') or {}
        name, args = action.get('tool'), action.get('args') or {}
        result, obs = agent_tools.run_tool(name, args, ctx)
        if name == 'rag_search' and result.get('count'):
            yield 'rag', {'count': result['count'],
                          'sources': [{'docName': h['docName'], 'score': h['score']} for h in result.get('hits', [])]}
        observations.append(obs)
        trace.append({'type': 'react', 'step': step, 'thought': obj.get('thought', ''),
                      'tool': name, 'args': args, 'observation': obs})
        yield 'trace', trace[-1]
        history.append({'role': 'assistant', 'content': resp})
        history.append({'role': 'user', 'content': f'Observation: {obs}'})
    if not text:
        text = '已完成操作：\n' + '\n'.join(observations) if observations else FALLBACK_TEXT
    yield 'text', text


def run_research(messages, ctx):
    """策略路由：有界迭代研究循环，每轮回测后立即推送 trace 与当前最优策略。"""
    query = messages[-1].get('content', '') if messages else ''
    rag_result, rag_text = agent_tools.rag_search({'query': query}, ctx)
    rag_count = rag_result.get('count', 0)
    sources = [{'docName': h['docName'], 'score': h['score']} for h in rag_result.get('hits', [])]
    yield 'rag', {'count': rag_count, 'sources': sources}

    best, best_reward, best_metrics = None, -1.0, None
    engine_stats, feedback, rounds = {}, '', 0
    for round_no in range(1, MAX_ROUNDS + 1):
        engine_hint = None
        if round_no > 1 and engine_stats:
            top = max(engine_stats, key=lambda e: sum(engine_stats[e]) / len(engine_stats[e]))
            if random.random() < EPSILON:
                engine_hint = random.choice([e for e in ENGINE_SPECS if e != top])
            else:
                engine_hint = top
        user = prompts.build_research_user(query, rag_text, feedback, engine_hint)
        obj = _extract_json(llm.chat([{'role': 'user', 'content': user}], system_prompt=prompts.RESEARCH_PROMPT)) or {}
        engine = obj.get('engineId') if obj.get('engineId') in ENGINE_SPECS else (engine_hint or 'ma_cross')
        params = _clamp_params(engine, obj.get('params'))
        stock = agent_tools._find_stock(obj.get('code')) or agent_tools._find_stock('600519')
        code = stock['code']
        try:
            metrics = backtest.run_backtest(engine, code, params, 1000000, '内置引擎', 120)['metrics']
        except Exception as e:
            print(f'[warn] 研究循环回测失败：{e}')
            metrics = None
        reward = _reward(metrics)
        engine_stats.setdefault(engine, []).append(reward)
        if reward > best_reward:
            best_reward, best_metrics = reward, metrics
            rules, code_text = _rules_code(engine, params)
            best = {'name': obj.get('name') or f'{engine} 策略', 'type': obj.get('type') or '自定义',
                    'engineId': engine, 'params': params, 'rules': rules, 'code': code_text}
            yield 'strategy', best
        decision = 'stop' if (reward >= STOP_REWARD or round_no == MAX_ROUNDS) else 'iterate'
        rounds += 1
        yield 'trace', {'type': 'research', 'round': round_no, 'engine': engine, 'params': params, 'code': code,
                        'rationale': obj.get('rationale', ''), 'reward': round(reward, 3), 'decision': decision,
                        'metrics': {k: round(metrics[k], 3) for k in ('annualized', 'maxDD', 'sharpe', 'winRate')} if metrics else None}
        if decision == 'stop':
            break
        if metrics:
            feedback = (f'上一轮 {engine} 参数{params} 回测：年化{metrics["annualized"]:.1%}、'
                        f'最大回撤{metrics["maxDD"]:.1%}、夏普{metrics["sharpe"]:.2f}、胜率{metrics["winRate"]:.1%}。'
                        f'请据此调整参数或引擎以提升风险调整后收益。')
        else:
            feedback = '上一轮回测失败，请换一个引擎或更稳健的参数。'

    if not best:
        params = _clamp_params('ma_cross', {})
        rules, code_text = _rules_code('ma_cross', params)
        best = {'name': '双均线交叉策略', 'type': '趋势跟踪', 'engineId': 'ma_cross',
                'params': params, 'rules': rules, 'code': code_text}
        yield 'strategy', best
    m = best_metrics or {}
    text = (f'我按你的想法跑了 {rounds} 轮「提假设→真实回测→复盘调整」，最终留下表现最稳的一版：'
            f'「{best["name"]}」。'
            + (f'它在测试区间里年化 {m.get("annualized", 0):.1%}、最大回撤 {m.get("maxDD", 0):.1%}、'
               f'夏普 {m.get("sharpe", 0):.2f}、胜率 {m.get("winRate", 0):.1%}。' if m else '')
            + '历史表现不代表未来，建议保存后换个标的或区间再复测确认；思路对但参数不合意的话，告诉我再调。')
    yield 'text', text


def run_agent_stream(messages, uid):
    """流式编排：意图识别 → 四路分发，逐个产出 (event, data) 供路由包装成 SSE。

    事件：intent / trace（累积快照，前端直接替换）/ rag / text（增量字符串）/ strategy / done。
    各路由只 yield 单步 trace，这里统一累积，前端无需自己拼接。
    """
    msgs = [dict(m) for m in (messages or [])]
    query = msgs[-1].get('content', '') if msgs and msgs[-1].get('role') == 'user' else ''
    intent, reason = classify_intent(query)
    ctx = {'uid': uid}
    trace = [{'type': 'intent', 'intent': intent, 'reason': reason}]
    yield 'intent', {'intent': intent, 'reason': reason}
    yield 'trace', {'trace': list(trace)}
    if intent == 'chat':
        route = run_chat(msgs)
    elif intent == 'knowledge':
        route = run_knowledge(msgs, ctx)
    elif intent == 'tool':
        route = run_react(msgs, ctx)
    else:
        route = run_research(msgs, ctx)
    for event, data in route:
        if event == 'trace':
            trace.append(data)
            yield 'trace', {'trace': list(trace)}
        else:
            yield event, data
    yield 'done', {}