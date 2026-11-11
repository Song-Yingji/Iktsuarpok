# -*- coding: utf-8 -*-
"""跨路由共享的请求级工具：统一错误响应、JSON 列读取、鉴权依赖、数值收敛。"""
import json

from fastapi import Header, HTTPException
from fastapi.responses import JSONResponse

import auth
import db

LATENCY = 0.2  # 模拟网络延迟（秒）

# role 权限等级：0 普通用户 / 1 管理员 / 2 超级管理员
ROLE_USER, ROLE_ADMIN, ROLE_SUPER = 0, 1, 2


def fail(status, message):
    return JSONResponse(status_code=status, content={'message': message})


def _json_loads(val):
    """读取 MySQL JSON 列：兼容 str/bytes/已解析对象。"""
    if val is None:
        return None
    if isinstance(val, (bytes, bytearray)):
        val = val.decode('utf-8')
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return None
    return val


def _clamp_int(v, low, high, default):
    """把模型给出的数值收敛到合法区间，非法值用默认值兜底。"""
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, n))


def get_current_user(authorization: str = Header(default=None)) -> int:
    """从 Authorization: Bearer <token> 解析当前登录用户 id。"""
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail='未登录或登录已过期')
    uid = auth.parse_token(authorization[7:])
    if not uid:
        raise HTTPException(status_code=401, detail='未登录或登录已过期')
    return uid


def get_current_admin(authorization: str = Header(default=None)) -> dict:
    """从 Authorization: Bearer <token> 解析后台管理员。

    每次请求都回库复核，确保账号未被删除、且管理员身份未被取消。
    """
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail='管理员未登录或登录已过期')
    uid = auth.parse_admin_token(authorization[7:])
    if not uid:
        raise HTTPException(status_code=401, detail='管理员未登录或登录已过期')
    row = db.query_one('SELECT id, username, role FROM users WHERE id=%s', (uid,))
    if not row or row['role'] < 1:
        raise HTTPException(status_code=401, detail='管理员权限已变更，请重新登录')
    return row