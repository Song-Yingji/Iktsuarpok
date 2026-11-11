# -*- coding: utf-8 -*-
"""量化交易任务：标的 / 策略 / 账户三要素卡片管理与自动交易开关。"""
import asyncio
import json

from fastapi import APIRouter, Body, Depends

import db
from common import _json_loads, fail, get_current_user

router = APIRouter(tags=['quant-tasks'])


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


@router.get('/api/quant-tasks')
async def list_quant_tasks(uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.1)
    rows = db.query('SELECT * FROM quant_tasks WHERE user_id=%s ORDER BY id', (uid,))
    return [_row_to_task(r) for r in rows]


@router.post('/api/quant-tasks')
async def create_quant_task(uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.2)
    tid = db.insert(
        'INSERT INTO quant_tasks (user_id, stock_codes, strategy_id, account_id, auto_trade) VALUES (%s,%s,%s,%s,%s)',
        (uid, json.dumps([]), None, None, 0),
    )
    row = db.query_one('SELECT * FROM quant_tasks WHERE id=%s', (tid,))
    return _row_to_task(row)


@router.put('/api/quant-tasks/{task_id}')
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


@router.delete('/api/quant-tasks/{task_id}')
async def delete_quant_task(task_id: int, uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.1)
    affected = db.execute('DELETE FROM quant_tasks WHERE id=%s AND user_id=%s', (task_id, uid))
    if not affected:
        return fail(404, '交易任务不存在')
    return {'ok': True}