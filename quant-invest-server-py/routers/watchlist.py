# -*- coding: utf-8 -*-
"""自选股：用户级增删查，返回实时行情对象。"""
import asyncio

import pymysql
from fastapi import APIRouter, Body, Depends

import db
from common import fail, get_current_user
from data import get_market

router = APIRouter(tags=['watchlist'])


@router.get('/api/watchlist')
async def get_watchlist(uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.05)
    rows = db.query('SELECT stock_code FROM watchlist WHERE user_id=%s ORDER BY id', (uid,))
    codes = [r['stock_code'] for r in rows]
    m = get_market()
    return [s for c in codes for s in m['stocks'] if s['code'] == c]


@router.post('/api/watchlist')
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


@router.delete('/api/watchlist/{code}')
async def remove_watchlist(code: str, uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.1)
    affected = db.execute('DELETE FROM watchlist WHERE user_id=%s AND stock_code=%s', (uid, code))
    if not affected:
        return fail(404, '自选股不存在')
    return {'ok': True}