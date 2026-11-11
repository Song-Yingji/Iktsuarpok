# -*- coding: utf-8 -*-
"""后台管理：管理员登录与用户管理（三级权限）。"""
import asyncio
import re

from fastapi import APIRouter, Body, Depends

import auth
import db
from common import (
    LATENCY, ROLE_ADMIN, ROLE_SUPER, ROLE_USER,
    _clamp_int, fail, get_current_admin,
)

router = APIRouter(prefix='/api/admin', tags=['admin'])


@router.post('/login')
async def admin_login(payload: dict = Body(default=None)):
    """后台管理员登录：查库校验账号密码，且要求 role >= 1。"""
    await asyncio.sleep(LATENCY)
    p = payload or {}
    username = (p.get('username') or '').strip()
    password = p.get('password') or ''
    if not username or not password:
        return fail(400, '请输入账号和密码')
    row = db.query_one(
        'SELECT id, username, password_hash, role FROM users WHERE username=%s',
        (username,),
    )
    if not row or not auth.verify_password(password, row['password_hash']):
        return fail(401, '账号或密码错误')
    if row['role'] < 1:
        return fail(403, '该账号没有后台管理权限')
    return {
        'token': auth.make_admin_token(row['id']),
        'admin': {'id': row['id'], 'username': row['username'], 'role': row['role']},
    }


def _row_to_user(row):
    return {
        'id': row['id'],
        'username': row['username'],
        'phone': row['phone'],
        'avatar': row['avatar'],
        'role': row['role'],
        'createdAt': row['created_at'].strftime('%Y-%m-%d %H:%M'),
    }


_USER_COLS = 'id, username, phone, avatar, role, created_at'


@router.get('/users')
async def admin_list_users(_: dict = Depends(get_current_admin)):
    """用户列表：包含普通用户与管理员，超级管理员置顶。"""
    await asyncio.sleep(0.05)
    rows = db.query(f'SELECT {_USER_COLS} FROM users ORDER BY role DESC, id ASC')
    return [_row_to_user(r) for r in rows]


@router.post('/users')
async def admin_create_user(payload: dict = Body(default=None),
                            current: dict = Depends(get_current_admin)):
    """新增用户，role 只能给 0（普通用户）或 1（管理员）；授予权限仅限超级管理员。"""
    await asyncio.sleep(LATENCY)
    p = payload or {}
    username = (p.get('username') or '').strip()
    password = p.get('password') or ''
    phone = (p.get('phone') or '').strip()
    if not username or not password:
        return fail(400, '请填写用户名和密码')
    if len(username) > 50:
        return fail(400, '用户名不能超过 50 个字符')
    if len(password) < 6:
        return fail(400, '密码长度至少 6 位')
    if phone and not re.fullmatch(r'1\d{10}', phone):
        return fail(400, '手机号格式不正确')
    if db.query_one('SELECT id FROM users WHERE username=%s', (username,)):
        return fail(409, '用户名已存在')
    role = _clamp_int(p.get('role'), ROLE_USER, ROLE_ADMIN, ROLE_USER)
    if role != ROLE_USER and current['role'] < ROLE_SUPER:
        return fail(403, '仅超级管理员可授予后台管理权限')
    uid = db.insert(
        'INSERT INTO users (username, password_hash, phone, avatar, role)'
        ' VALUES (%s,%s,%s,%s,%s)',
        (username, auth.hash_password(password), phone or None, username[:1].upper(), role),
    )
    row = db.query_one(f'SELECT {_USER_COLS} FROM users WHERE id=%s', (uid,))
    return _row_to_user(row)


@router.put('/users/{user_id}')
async def admin_update_user(user_id: int, payload: dict = Body(default=None),
                            current: dict = Depends(get_current_admin)):
    """编辑用户：用户名、手机号、密码、权限等级（留空字段不改）；权限变更仅限超级管理员。"""
    await asyncio.sleep(LATENCY)
    p = payload or {}
    row = db.query_one('SELECT id, username, role FROM users WHERE id=%s', (user_id,))
    if not row:
        return fail(404, '用户不存在')

    fields, args = [], []
    if 'username' in p:
        username = (p.get('username') or '').strip()
        if not username:
            return fail(400, '用户名不能为空')
        if len(username) > 50:
            return fail(400, '用户名不能超过 50 个字符')
        if username != row['username'] and db.query_one(
                'SELECT id FROM users WHERE username=%s', (username,)):
            return fail(409, '用户名已存在')
        fields += ['username=%s', 'avatar=%s']
        args += [username, username[:1].upper()]
    if 'phone' in p:
        phone = (p.get('phone') or '').strip()
        if phone and not re.fullmatch(r'1\d{10}', phone):
            return fail(400, '手机号格式不正确')
        fields.append('phone=%s')
        args.append(phone or None)
    if 'role' in p:
        if current['role'] < ROLE_SUPER:
            return fail(403, '仅超级管理员可修改用户权限')
        want = _clamp_int(p.get('role'), ROLE_USER, ROLE_SUPER, ROLE_USER)
        if row['role'] == ROLE_SUPER:
            if want != ROLE_SUPER:
                return fail(400, '超级管理员不可取消管理员权限')
        elif want == ROLE_SUPER:
            return fail(400, '超级管理员全局唯一，不可通过接口授予')
        else:
            fields.append('role=%s')
            args.append(want)
    if p.get('password'):
        if len(p['password']) < 6:
            return fail(400, '密码长度至少 6 位')
        fields.append('password_hash=%s')
        args.append(auth.hash_password(p['password']))
    if not fields:
        return fail(400, '没有需要更新的内容')

    args.append(user_id)
    db.execute('UPDATE users SET ' + ', '.join(fields) + ' WHERE id=%s', tuple(args))
    updated = db.query_one(f'SELECT {_USER_COLS} FROM users WHERE id=%s', (user_id,))
    return _row_to_user(updated)


@router.delete('/users/{user_id}')
async def admin_delete_user(user_id: int, current: dict = Depends(get_current_admin)):
    """删除用户（连带其偏好/策略/账户/自选股）。

    超级管理员与当前登录账号不可删；普通管理员只能删除普通用户，不能删除管理员账号。
    """
    await asyncio.sleep(LATENCY)
    row = db.query_one('SELECT id, role FROM users WHERE id=%s', (user_id,))
    if not row:
        return fail(404, '用户不存在')
    if row['role'] == ROLE_SUPER:
        return fail(400, '超级管理员不可删除')
    if row['id'] == current['id']:
        return fail(400, '不能删除当前登录账号')
    if row['role'] >= ROLE_ADMIN and current['role'] < ROLE_SUPER:
        return fail(403, '仅超级管理员可删除管理员账号')
    db.execute('DELETE FROM users WHERE id=%s', (user_id,))
    return {'ok': True}