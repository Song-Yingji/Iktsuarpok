# -*- coding: utf-8 -*-
"""前台用户鉴权：登录 / 注册。"""
import asyncio
import re

from fastapi import APIRouter, Body

import auth
import db
from common import LATENCY, fail

router = APIRouter(prefix='/api/auth', tags=['auth'])


@router.post('/login')
async def login(payload: dict = Body(default=None)):
    await asyncio.sleep(LATENCY)
    payload = payload or {}
    username = payload.get('username')
    password = payload.get('password')
    if not username or not password:
        return fail(400, '请输入用户名和密码')
    row = db.query_one('SELECT id, username, password_hash, avatar FROM users WHERE username=%s', (username,))
    if not row or not auth.verify_password(password, row['password_hash']):
        return fail(401, '用户名或密码错误')
    return {'token': auth.make_token(row['id']), 'user': {'id': row['id'], 'username': row['username'], 'avatar': row['avatar']}}


@router.post('/register')
async def register(payload: dict = Body(default=None)):
    await asyncio.sleep(LATENCY)
    payload = payload or {}
    username = payload.get('username')
    password = payload.get('password')
    phone = payload.get('phone')
    if not username or not password:
        return fail(400, '请填写完整注册信息')
    if len(password) < 6:
        return fail(400, '密码长度至少 6 位')
    if phone and not re.fullmatch(r'1\d{10}', str(phone)):
        return fail(400, '手机号格式不正确')
    if db.query_one('SELECT id FROM users WHERE username=%s', (username,)):
        return fail(409, '用户名已存在')
    avatar = str(username)[:1].upper()
    uid = db.insert(
        'INSERT INTO users (username, password_hash, phone, avatar) VALUES (%s,%s,%s,%s)',
        (username, auth.hash_password(password), phone or None, avatar),
    )
    return {'token': auth.make_token(uid), 'user': {'id': uid, 'username': username, 'avatar': avatar}}