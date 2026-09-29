# -*- coding: utf-8 -*-
"""MySQL 数据访问层：连接管理 + 查询/写入辅助（基于 PyMySQL）。"""
import pymysql
from pymysql.cursors import DictCursor

import db_config


def get_conn():
    return pymysql.connect(
        host=db_config.DB_HOST,
        port=db_config.DB_PORT,
        user=db_config.DB_USER,
        password=db_config.DB_PASSWORD,
        database=db_config.DB_NAME,
        charset='utf8mb4',
        cursorclass=DictCursor,
        autocommit=False,
    )


def query(sql, args=None):
    """执行查询，返回 list[dict]。"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args or ())
            return cur.fetchall()
    finally:
        conn.close()


def query_one(sql, args=None):
    rows = query(sql, args)
    return rows[0] if rows else None


def execute(sql, args=None):
    """执行写操作（UPDATE/DELETE），返回受影响行数 rowcount。"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            affected = cur.execute(sql, args or ())
        conn.commit()
        return affected
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def insert(sql, args=None):
    """执行 INSERT，返回自增主键 lastrowid。"""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args or ())
            last_id = cur.lastrowid
        conn.commit()
        return last_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_tx(statements):
    """在单个事务内按顺序执行多条写语句，返回最后一条 INSERT 的自增主键。

    statements: [(sql, args), ...]，用于「先改后插」这类需要原子性的场景
    （如切换默认偏好：先清掉旧的默认标记，再写入新的）。
    """
    conn = get_conn()
    try:
        last_id = None
        with conn.cursor() as cur:
            for sql, args in statements:
                cur.execute(sql, args or ())
                last_id = cur.lastrowid
        conn.commit()
        return last_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()