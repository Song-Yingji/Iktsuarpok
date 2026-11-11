# -*- coding: utf-8 -*-
"""行情快照与财经资讯（只读公开接口）。"""
import asyncio

from fastapi import APIRouter

from data import get_market, get_news, news_error, get_news_categories

router = APIRouter(tags=['market'])


@router.get('/api/market/snapshot')
async def market_snapshot():
    await asyncio.sleep(0.08)
    return get_market()


@router.get('/api/news/categories')
def news_categories():
    return get_news_categories()


@router.get('/api/news')
async def news(category: str = None, keyword: str = None):
    await asyncio.sleep(0.05)
    result = get_news()
    err = news_error()
    if category and category != '全部':
        result = [n for n in result if n['category'] == category]
    if keyword:
        result = [n for n in result if keyword in (n['title'] + n['summary'])]
    return {'items': result, 'error': err}