# -*- coding: utf-8 -*-
"""账户凭证服务：账号/密码的加密存取（Fernet 对称加密）。

密码只落密文、接口只进不出：加密后写入 account_credentials 表，
解密仅限后端内部使用（如连接器取凭证登录），不向前端返回明文。
密钥来自环境变量 CRED_SECRET_KEY 或 db_config.CRED_SECRET_KEY（已 gitignore）。
"""
import os

from cryptography.fernet import Fernet

import db
import db_config


def _fernet() -> Fernet:
    key = os.environ.get('CRED_SECRET_KEY') or getattr(db_config, 'CRED_SECRET_KEY', '')
    if not key:
        raise RuntimeError('缺少凭证加密密钥 CRED_SECRET_KEY')
    return Fernet(key.encode())


def encrypt(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt(token: str):
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except Exception:
        return None


def save(account_id: int, login_account=None, password=None):
    """写入/更新凭证：password 为空表示不修改密码，login_account 为 None 表示不修改账号。"""
    row = db.query_one('SELECT * FROM account_credentials WHERE account_id=%s', (account_id,))
    enc = encrypt(password) if password else (row['password_enc'] if row else None)
    login = login_account if login_account is not None else (row['login_account'] if row else None)
    if row:
        db.execute(
            'UPDATE account_credentials SET login_account=%s, password_enc=%s WHERE account_id=%s',
            (login, enc, account_id),
        )
    else:
        db.insert(
            'INSERT INTO account_credentials (account_id, login_account, password_enc) VALUES (%s,%s,%s)',
            (account_id, login, enc),
        )


def get_raw(account_id: int):
    """返回凭证行（含密文），仅后端内部使用。"""
    return db.query_one('SELECT * FROM account_credentials WHERE account_id=%s', (account_id,))


def get_plain(account_id: int) -> dict:
    """返回连接器所需明文凭证，仅后端内部使用，绝不进入接口响应。"""
    row = get_raw(account_id)
    if not row:
        return {'loginAccount': '', 'password': ''}
    return {'loginAccount': row['login_account'] or '', 'password': decrypt(row['password_enc']) or ''}
