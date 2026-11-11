# -*- coding: utf-8 -*-
"""策略 / 回测：回测框架与引擎入口，以及智能体生成策略的保存管理。"""
import asyncio
import json

from fastapi import APIRouter, Body, Depends

import builder_engine
import db
from backtest import run_backtest
from common import _json_loads, fail, get_current_user
from data import BACKTEST_FRAMEWORKS
from routers.tasks import _scrub_task_refs

router = APIRouter(prefix='/api/strategy', tags=['strategy'])


@router.get('/frameworks')
def get_frameworks():
    return BACKTEST_FRAMEWORKS


@router.post('/backtest')
async def backtest(payload: dict = Body(default=None)):
    await asyncio.sleep(1.8)
    b = payload or {}
    if not b.get('strategyId'):
        return fail(400, '缺少策略ID')
    try:
        result = run_backtest(
            strategy_id=b.get('strategyId'),
            stock_code=b.get('stockCode'),
            params=b.get('params') or {},
            capital=b.get('capital') or 1000000,
            framework=b.get('framework'),
            range_days=b.get('rangeDays') or 120,
        )
    except ValueError as e:
        return fail(400, str(e))
    return result


@router.post('/builder/validate')
async def validate_builder(payload: dict = Body(default=None), uid: int = Depends(get_current_user)):
    """自由构建画布校验：返回错误列表；通过时附带生成的规则文本与伪代码预览。"""
    graph = builder_engine.normalize_graph((payload or {}).get('graph'))
    errors = builder_engine.validate_graph(graph)
    if errors:
        return {'ok': False, 'errors': errors}
    rules, code = builder_engine.describe_graph(graph)
    return {'ok': True, 'errors': [], 'rules': rules, 'code': code}


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


@router.get('/saved')
async def list_saved_strategies(uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.1)
    rows = db.query('SELECT * FROM saved_strategies WHERE user_id=%s ORDER BY id DESC', (uid,))
    return [_row_to_strategy(r) for r in rows]


@router.post('/saved')
async def save_strategy(payload: dict = Body(default=None), uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.2)
    p = payload or {}
    if not p.get('name'):
        return fail(400, '缺少策略名称')
    engine_id = p.get('engineId') or 'ma_cross'
    if engine_id == 'builder':
        graph = builder_engine.normalize_graph(p.get('params'))
        errors = builder_engine.validate_graph(graph)
        if errors:
            return fail(400, errors[0]['message'])
        params = graph
        rules, code = builder_engine.describe_graph(graph)
    else:
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


@router.put('/saved/{strategy_id}')
async def update_saved_strategy(strategy_id: int, payload: dict = Body(default=None),
                                uid: int = Depends(get_current_user)):
    """编辑已保存策略（名称 / 参数）；builder 策略重新校验并再生成规则文本。"""
    await asyncio.sleep(0.2)
    row = db.query_one('SELECT * FROM saved_strategies WHERE id=%s AND user_id=%s', (strategy_id, uid))
    if not row:
        return fail(404, '策略不存在')
    p = payload or {}
    name = (p.get('name') or row['name']).strip()
    if not name:
        return fail(400, '缺少策略名称')
    params = _json_loads(row['params']) or {}
    rules = _json_loads(row['rules']) or []
    code = row['code'] or ''
    if 'params' in p:
        if row['engine_id'] == 'builder':
            graph = builder_engine.normalize_graph(p.get('params'))
            errors = builder_engine.validate_graph(graph)
            if errors:
                return fail(400, errors[0]['message'])
            params = graph
            rules, code = builder_engine.describe_graph(graph)
        else:
            params = p.get('params') or {}
            rules = p.get('rules') or rules
            code = p.get('code') or code
    db.execute(
        'UPDATE saved_strategies SET name=%s, params=%s, rules=%s, code=%s WHERE id=%s AND user_id=%s',
        (name, json.dumps(params, ensure_ascii=False), json.dumps(rules, ensure_ascii=False),
         code, strategy_id, uid),
    )
    updated = db.query_one('SELECT * FROM saved_strategies WHERE id=%s', (strategy_id,))
    return _row_to_strategy(updated)


@router.delete('/saved/{strategy_id}')
async def delete_saved_strategy(strategy_id: int, uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.1)
    affected = db.execute('DELETE FROM saved_strategies WHERE id=%s AND user_id=%s', (strategy_id, uid))
    if not affected:
        return fail(404, '策略不存在')
    _scrub_task_refs(uid, drop_strategy_id=strategy_id)
    return {'ok': True}