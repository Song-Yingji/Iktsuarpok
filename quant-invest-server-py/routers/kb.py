# -*- coding: utf-8 -*-
"""后台管理（知识库）：文档管理、检索测试、模块化 RAG 配置与效果测评。"""
import asyncio
import os

from fastapi import APIRouter, Body, Depends, File, UploadFile

import modular_rag
import rag
import rag_eval
from common import _clamp_int, fail, get_current_admin

router = APIRouter(prefix='/api/admin', tags=['admin-kb'])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 单文件上限 10MB


@router.get('/kb/stats')
async def admin_kb_stats(_: str = Depends(get_current_admin)):
    """知识库概况：文档数、分块数、向量模型、存储位置等。"""
    await asyncio.sleep(0.05)
    try:
        return rag.stats()
    except rag.RagError as e:
        return fail(500, str(e))


@router.get('/docs')
async def admin_list_docs(_: str = Depends(get_current_admin)):
    """已入库文档列表。"""
    await asyncio.sleep(0.05)
    try:
        return rag.list_docs()
    except rag.RagError as e:
        return fail(500, str(e))


@router.post('/docs')
async def admin_upload_doc(file: UploadFile = File(...), _: str = Depends(get_current_admin)):
    """上传文档：解析文本 → 递归分块 → 向量化 → 写入本地 Chroma 库。

    同名文档会覆盖旧索引。响应体为入库后的文档信息。
    """
    raw = await file.read()
    if not raw:
        return fail(400, '文件内容为空')
    if len(raw) > MAX_UPLOAD_BYTES:
        return fail(400, '文件过大，请上传 10MB 以内的文档')

    filename = os.path.basename(file.filename or '未命名文档')
    try:
        text = rag.extract_text(filename, raw)
        doc = rag.add_document(filename, text)
    except rag.RagError as e:
        return fail(400, str(e))
    return doc


@router.delete('/docs/{doc_id}')
async def admin_delete_doc(doc_id: str, _: str = Depends(get_current_admin)):
    """按文档 ID 删除其全部向量分块。"""
    await asyncio.sleep(0.05)
    try:
        if not rag.delete_document(doc_id):
            return fail(404, '文档不存在')
    except rag.RagError as e:
        return fail(500, str(e))
    return {'ok': True}


@router.post('/search')
async def admin_search(payload: dict = Body(default=None), _: str = Depends(get_current_admin)):
    """检索测试：把问题向量化后在知识库中做相似度比对，返回命中片段。"""
    p = payload or {}
    query = (p.get('query') or '').strip()
    if not query:
        return fail(400, '请输入检索内容')
    top_k = _clamp_int(p.get('topK'), 1, 20, rag.TOP_K)
    try:
        return rag.retrieve(query, top_k=top_k)
    except rag.RagError as e:
        return fail(400, str(e))


@router.get('/rag-config')
async def admin_get_rag_config(_: str = Depends(get_current_admin)):
    """模块化 RAG 配置：当前各模块开关与检索参数。"""
    return modular_rag.load_config()


@router.put('/rag-config')
async def admin_save_rag_config(payload: dict = Body(default=None),
                                _: str = Depends(get_current_admin)):
    """保存模块化 RAG 配置（模块开关 / 融合方式 / 召回参数），策略生成检索时即时生效。"""
    try:
        return modular_rag.save_config(payload or {})
    except OSError as e:
        return fail(500, f'配置写入失败：{e}')


@router.get('/rag-eval/dataset')
def admin_rag_eval_dataset(_: str = Depends(get_current_admin)):
    """效果测评：只读当前评测集缓存状态（题目数量联动、是否需重新合成）。"""
    try:
        return rag_eval.dataset_status()
    except Exception as e:
        print(f'[warn] 读取评测集状态失败：{e}')
        return fail(500, f'读取评测集状态失败：{e}')


@router.post('/rag-eval')
def admin_rag_eval(payload: dict = Body(default=None), _: str = Depends(get_current_admin)):
    """效果测评（LlamaIndex）：对当前模块化 RAG 配置跑五项指标。

    评测集由 LlamaIndex RagDatasetGenerator 从知识库合成（缓存复用），
    每题跑一遍完整管线后用 LlamaIndex 评估器打分：
    上下文精确率 / 上下文召回率 / 忠实度 / 答案相关性 / 答案正确率。

    请求体：{ numQuestions: 1~20（默认 10）, regenerate: 是否重建评测集 }
    评测耗时较长（每题需多次大模型调用），前端同步等待即可。
    """
    p = payload or {}
    num = _clamp_int(p.get('numQuestions'), 1, 20, 10)
    try:
        return rag_eval.run_evaluation(num_questions=num,
                                       regenerate_dataset=bool(p.get('regenerate')))
    except rag.RagError as e:
        return fail(400, str(e))
    except Exception as e:
        # 详细原因（缺语料 / 模型异常等）只进后端日志，前端统一友好文案
        import traceback
        print(f'[warn] RAG 效果测评失败：{e}')
        traceback.print_exc()
        return fail(500, '服务器繁忙，请稍后重试')