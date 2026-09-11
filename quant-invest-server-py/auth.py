# -*- coding: utf-8 -*-
"""鉴权工具：密码加盐哈希与签名 token（基于 Python 标准库，零额外依赖）。"""
import base64
import hashlib
import hmac
import os
import time

SECRET_KEY = os.environ.get('XB_QUANT_SECRET', 'xb-quant-internal-secret')
_TOKEN_TTL = 30 * 24 * 3600  # 30 天
_PBKDF2_ITERATIONS = 100000


def hash_password(password):
    """返回 'salt_hex$dk_hex' 形式的加盐哈希。"""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, _PBKDF2_ITERATIONS)
    return salt.hex() + '$' + dk.hex()


def verify_password(password, stored):
    try:
        salt_hex, dk_hex = stored.split('$')
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, _PBKDF2_ITERATIONS)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def make_token(user_id):
    """生成带签名与过期时间的 token：base64(user_id:exp).signature"""
    exp = int(time.time()) + _TOKEN_TTL
    raw = f'{user_id}:{exp}'
    payload = raw.encode('utf-8')
    sig = hmac.new(SECRET_KEY.encode('utf-8'), payload, hashlib.sha256).hexdigest()
    b64 = base64.urlsafe_b64encode(raw.encode('utf-8')).decode('utf-8')
    return b64 + '.' + sig


def parse_token(token):
    """校验 token 并返回 user_id；无效或过期返回 None。"""
    try:
        b64, sig = token.split('.')
        raw = base64.urlsafe_b64decode(b64.encode('utf-8')).decode('utf-8')
        uid_str, exp_str = raw.split(':')
        exp = int(exp_str)
        if exp < int(time.time()):
            return None
        payload = f'{uid_str}:{exp_str}'.encode('utf-8')
        expect = hmac.new(SECRET_KEY.encode('utf-8'), payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expect, sig):
            return None
        return int(uid_str)
    except Exception:
        return None