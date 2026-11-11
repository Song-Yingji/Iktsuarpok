# -*- coding: utf-8 -*-
"""量化投资平台后端服务（FastAPI）应用入口。

路由按业务拆分在 routers/ 包内，共享工具见 common.py，回测引擎见 backtest.py。
运行：python main.py  （默认端口 3000）
"""
import threading
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import admin_config
import auth
import db
from common import fail
from data import get_market, tick_market, refresh_news
from routers.accounts import router as accounts_router
from routers.admin import router as admin_router
from routers.agent import router as agent_router
from routers.auth import router as auth_router
from routers.kb import router as kb_router
from routers.market import router as market_router
from routers.prefs import router as prefs_router
from routers.strategy import router as strategy_router
from routers.tasks import router as tasks_router
from routers.watchlist import router as watchlist_router

PORT = 3000


def ensure_super_admin():
    """确保库中存在唯一的超级管理员（role=2，首次启动按 admin_config.py 播种）。"""
    try:
        if db.query_one('SELECT id FROM users WHERE role=2 LIMIT 1'):
            return
        name = admin_config.ADMIN_USERNAME
        row = db.query_one('SELECT id FROM users WHERE username=%s', (name,))
        if row:
            db.execute('UPDATE users SET role=2 WHERE id=%s', (row['id'],))
        else:
            db.insert(
                'INSERT INTO users (username, password_hash, phone, avatar, role)'
                ' VALUES (%s,%s,%s,%s,2)',
                (name, auth.hash_password(admin_config.ADMIN_PASSWORD), None, name[:1].upper()),
            )
    except Exception as e:
        print(f'[warn] 超级管理员初始化失败：{e}')


@asynccontextmanager
async def lifespan(app):
    # 启动行情引擎：初始化 + 每 2 秒推进一个 tick（真实服务端随机游走）
    ensure_super_admin()
    get_market()

    def loop():
        while True:
            time.sleep(2)
            tick_market()

    threading.Thread(target=loop, daemon=True).start()

    def news_loop():
        refresh_news()
        while True:
            time.sleep(60)
            refresh_news()

    threading.Thread(target=news_loop, daemon=True).start()
    yield


app = FastAPI(title='quant-invest-server', lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(auth_router)
app.include_router(market_router)
app.include_router(prefs_router)
app.include_router(agent_router)
app.include_router(admin_router)
app.include_router(kb_router)
app.include_router(strategy_router)
app.include_router(watchlist_router)
app.include_router(accounts_router)
app.include_router(tasks_router)


@app.get('/api/health')
def health():
    return {'status': 'ok', 'service': 'quant-invest-server', 'lang': 'python'}


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return fail(exc.status_code, exc.detail)


@app.exception_handler(404)
async def not_found(request, exc):
    return fail(404, '接口不存在')


if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=PORT, log_level='info', use_colors=False)
