# -*- coding: utf-8 -*-
"""投资偏好（1 用户 : N 套）与全局设置（交易提醒）。"""
import asyncio
import json

from fastapi import APIRouter, Body, Depends

import db
from common import LATENCY, _json_loads, fail, get_current_user
from data import DEFAULT_PREFS

router = APIRouter(tags=['prefs'])


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


@router.get('/api/prefs')
async def list_prefs(uid: int = Depends(get_current_user)):
    """当前用户的全部偏好，按创建顺序返回，切换默认偏好不改变列表顺序。"""
    await asyncio.sleep(0.1)
    rows = db.query(
        'SELECT * FROM preference_sets WHERE user_id=%s ORDER BY id', (uid,))
    return [_row_to_prefset(r) for r in rows]


@router.post('/api/prefs')
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


@router.put('/api/prefs/{pref_id}')
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


@router.post('/api/prefs/{pref_id}/default')
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


@router.delete('/api/prefs/{pref_id}')
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
@router.get('/api/settings')
async def get_settings(uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.08)
    row = db.query_one('SELECT * FROM user_settings WHERE user_id=%s', (uid,))
    return {'tradeNotify': bool(row['trade_notify']) if row else True}


@router.post('/api/settings')
async def save_settings(payload: dict = Body(default=None), uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.1)
    p = payload or {}
    db.execute(
        'INSERT INTO user_settings (user_id, trade_notify) VALUES (%s,%s) '
        'ON DUPLICATE KEY UPDATE trade_notify=VALUES(trade_notify)',
        (uid, 1 if p.get('tradeNotify', True) else 0),
    )
    return {'ok': True}