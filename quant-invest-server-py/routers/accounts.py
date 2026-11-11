# -*- coding: utf-8 -*-
"""账户管理：模拟盘 / 实盘账户 CRUD、凭证加密存取与连接测试。"""
import asyncio

from fastapi import APIRouter, Body, Depends

import connectors
import credentials
import db
from common import fail, get_current_user
from routers.tasks import _scrub_task_refs

router = APIRouter(tags=['accounts'])


def _row_to_account(row, cred=None):
    cred = cred or {}
    return {
        'id': row['id'],
        'name': row['name'],
        'type': row['type'],
        'platformUrl': row['platform_url'],
        'loginAccount': cred.get('login_account') or '',
        'hasPassword': bool(cred.get('password_enc')),
        'status': row['status'],
        'connectStatus': row['connect_status'],
        'lastChecked': row['last_checked'].strftime('%Y-%m-%d %H:%M') if row['last_checked'] else None,
        'totalAssets': float(row['total_assets']),
        'cash': float(row['cash']),
        'created': row['created_at'].strftime('%Y-%m-%d'),
    }


@router.get('/api/accounts')
async def list_accounts(uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.15)
    rows = db.query('SELECT * FROM accounts WHERE user_id=%s ORDER BY id', (uid,))
    creds = {
        c['account_id']: c
        for c in db.query(
            'SELECT * FROM account_credentials WHERE account_id IN (SELECT id FROM accounts WHERE user_id=%s)',
            (uid,),
        )
    }
    return [_row_to_account(r, creds.get(r['id'])) for r in rows]


@router.post('/api/accounts')
async def create_account(payload: dict = Body(default=None), uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.3)
    payload = payload or {}
    name = (payload.get('name') or '').strip()
    if not name:
        return fail(400, '请填写账户显示名称')
    # 资金不由用户设定，创建时为 0，连接成功后由连接器自动读取
    aid = db.insert(
        'INSERT INTO accounts (user_id, name, type, platform_url, status, connect_status, total_assets, cash) '
        'VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
        (uid, name, payload.get('type') or '模拟盘', payload.get('platformUrl') or None,
         'connected', 'untested', 0, 0),
    )
    if payload.get('loginAccount') or payload.get('password'):
        credentials.save(aid, payload.get('loginAccount') or '', payload.get('password') or '')
    row = db.query_one('SELECT * FROM accounts WHERE id=%s', (aid,))
    return _row_to_account(row, credentials.get_raw(aid))


@router.put('/api/accounts/{account_id}')
async def update_account(account_id: int, payload: dict = Body(default=None), uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.2)
    row = db.query_one('SELECT * FROM accounts WHERE id=%s AND user_id=%s', (account_id, uid))
    if not row:
        return fail(404, '账户不存在')
    patch = payload or {}
    db.execute(
        'UPDATE accounts SET name=%s, type=%s, platform_url=%s, status=%s, '
        'total_assets=%s, cash=%s WHERE id=%s',
        (
            patch.get('name', row['name']),
            patch.get('type', row['type']),
            patch.get('platformUrl', row['platform_url']),
            patch.get('status', row['status']),
            float(patch.get('totalAssets', row['total_assets'])),
            float(patch.get('cash', row['cash'])),
            account_id,
        ),
    )
    # 凭证只进不出：密码留空表示不修改；接口响应永不包含密码
    if 'loginAccount' in patch or patch.get('password'):
        credentials.save(account_id, patch.get('loginAccount'), patch.get('password') or None)
    updated = db.query_one('SELECT * FROM accounts WHERE id=%s', (account_id,))
    return _row_to_account(updated, credentials.get_raw(account_id))


@router.post('/api/accounts/{account_id}/test-connection')
async def test_account_connection(account_id: int, uid: int = Depends(get_current_user)):
    row = db.query_one('SELECT * FROM accounts WHERE id=%s AND user_id=%s', (account_id, uid))
    if not row:
        return fail(404, '账户不存在')
    cred = credentials.get_plain(account_id)
    connector = connectors.get_connector(row['type'])
    result = await asyncio.to_thread(
        connector.check_connection, row['platform_url'], cred['loginAccount'], cred['password']
    )
    status = 'ok' if result['ok'] else 'fail'
    # 连接成功后自动读取账户资金（模拟盘固定 100 万，真实盘由平台适配器读取）
    balance = None
    if result['ok']:
        balance = await asyncio.to_thread(
            connector.fetch_balance, row['platform_url'], cred['loginAccount'], cred['password']
        )
        if balance['ok']:
            db.execute(
                'UPDATE accounts SET connect_status=%s, last_checked=NOW(), total_assets=%s, cash=%s WHERE id=%s',
                (status, balance['totalAssets'], balance['cash'], account_id),
            )
        else:
            db.execute('UPDATE accounts SET connect_status=%s, last_checked=NOW() WHERE id=%s', (status, account_id))
    else:
        db.execute('UPDATE accounts SET connect_status=%s, last_checked=NOW() WHERE id=%s', (status, account_id))
    updated = db.query_one('SELECT last_checked, total_assets, cash FROM accounts WHERE id=%s', (account_id,))
    message = result['message']
    if balance:
        message = f"{message}；{balance['message']}"
    return {
        'connectStatus': status,
        'message': message,
        'lastChecked': updated['last_checked'].strftime('%Y-%m-%d %H:%M') if updated['last_checked'] else None,
        'totalAssets': float(updated['total_assets']),
        'cash': float(updated['cash']),
    }


@router.delete('/api/accounts/{account_id}')
async def delete_account(account_id: int, uid: int = Depends(get_current_user)):
    await asyncio.sleep(0.2)
    affected = db.execute('DELETE FROM accounts WHERE id=%s AND user_id=%s', (account_id, uid))
    if not affected:
        return fail(404, '账户不存在')
    _scrub_task_refs(uid, drop_account_id=account_id)
    return {'ok': True}