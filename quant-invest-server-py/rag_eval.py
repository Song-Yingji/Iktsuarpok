# -*- coding: utf-8 -*-
"""LlamaIndex 评测服务（纯 LlamaIndex 评估器，不自研指标）。

测评集：用 LlamaIndex `RagDatasetGenerator` 从本地知识库合成问答对
（问题 + 标准答案 + 来源片段），并持久化缓存，知识库变更后自动重建。

指标映射（方案二）：
    上下文精确率 Context Precision -> RetrieverEvaluator precision
    上下文召回率 Context Recall     -> RetrieverEvaluator recall
    忠实度 Faithfulness             -> FaithfulnessEvaluator
    答案相关性 Answer Relevance     -> RelevancyEvaluator
    答案正确率 Answer Correctness   -> CorrectnessEvaluator（官方 1-5 分，汇总归一到 0-1）

评测对象：ModularRAG 全管线（查询改写→多路检索→融合→重排序→压缩→生成），
每题运行一次完整管线，取各级输出（检索片段 + 生成回答）交给 LlamaIndex 评估器打分。
大模型裁判通过 `llm.chat()` 单向适配（temperature=0），不影响业务原生调用路径。
"""
import hashlib
import json
import os
import re
import time
from typing import Any, Dict, List, Optional

import llm as native_llm
import modular_rag
import rag

from llama_index.core.base.llms.types import CompletionResponse, LLMMetadata
from llama_index.core.evaluation import (
    CorrectnessEvaluator,
    FaithfulnessEvaluator,
    RelevancyEvaluator,
    RetrieverEvaluator,
)
from llama_index.core.llama_dataset.generator import RagDatasetGenerator
from llama_index.core.llms.custom import CustomLLM
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

# 评测集缓存文件（与后端同目录）
DATASET_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rag_eval_dataset.json')

# 五项指标在响应中的键（与前端展示一一对应）
METRIC_KEYS = (
    'context_precision',   # 上下文精确率
    'context_recall',      # 上下文召回率
    'faithfulness',        # 忠实度
    'answer_relevance',    # 答案相关性
    'answer_correctness',  # 答案正确率
)


# ================= 大模型裁判适配器 =================
class JudgeLLM(CustomLLM):
    """把项目原生 `llm.chat()` 单向包装成 LlamaIndex LLM，供评估器 / 数据集生成调用。

    只做适配不做改造：temperature=0 保证裁判打分稳定。
    """

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(model_name=getattr(native_llm, 'MODEL_NAME', 'local-llm'))

    def complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponse:
        text = native_llm.chat([{'role': 'user', 'content': prompt}], temperature=0)
        return CompletionResponse(text=text or '')

    def stream_complete(self, prompt: str, formatted: bool = False, **kwargs: Any):
        text = self.complete(prompt).text
        yield CompletionResponse(text=text, delta=text)


# ================= 知识库分块 → LlamaIndex 节点 =================
def _chunk_id(meta: Dict[str, Any]) -> str:
    cid = (meta.get('chunk_id') or '').strip()
    if cid:
        return cid
    return f"{meta.get('doc_id', '')}#{meta.get('chunk_index', '')}"


def _build_chunk_index():
    """遍历知识库分块，构建 LlamaIndex 节点与「内容 / 元信息 → 节点 ID」映射表。

    返回 (nodes, by_text, by_meta, by_position)：
        by_text      文本 → 节点 ID（精确匹配，用于标准答案来源定位）
        by_meta      (docId, chunkIndex) → 节点 ID（向量检索路径）
        by_position  全库分块序号 → 节点 ID（BM25 检索路径的 chunkIndex 语义）
    """
    nodes: List[TextNode] = []
    by_text: Dict[str, str] = {}
    by_meta: Dict[tuple, str] = {}
    by_position: Dict[int, str] = {}
    for pos, (text, meta) in enumerate(rag.all_chunks()):
        cid = _chunk_id(meta)
        nodes.append(TextNode(
            id_=cid,
            text=text,
            metadata={'doc_id': meta.get('doc_id'), 'doc_name': meta.get('doc_name')},
        ))
        by_text.setdefault(text, cid)
        by_meta.setdefault((meta.get('doc_id'), meta.get('chunk_index')), cid)
        by_position[pos] = cid
    return nodes, by_text, by_meta, by_position


# ================= 评测集（RagDatasetGenerator 合成） =================
# 出题指令：知识库与检索链路均以中文为主，强制用中文出题，
# 避免英文合成问题在中文语义检索/自反思判定中被整体丢弃。
_QUESTION_GEN_QUERY = (
    '你是一名出题人，即将为一次测验出题。'
    '请仅根据给定的文档内容，提出 1 个问题，问题类型要多样，'
    '并且严格限制在给定上下文信息范围内。必须用中文提问。'
)
# 合成策略版本：出题方式变化时旧缓存自动失效
_GEN_VERSION = 'zh-v1'


def _kb_fingerprint(nodes: List[TextNode]) -> str:
    raw = _GEN_VERSION + '|' + '|'.join(sorted(n.node_id for n in nodes))
    return hashlib.md5(raw.encode('utf-8')).hexdigest()


def _load_cached_dataset(fingerprint: str, num_questions: int) -> Optional[List[Dict]]:
    try:
        with open(DATASET_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if (isinstance(data, dict) and data.get('fingerprint') == fingerprint
                and len(data.get('examples') or []) >= num_questions):
            return data['examples']
    except (OSError, ValueError):
        pass
    return None


def _save_dataset(fingerprint: str, examples: List[Dict], num_questions: int) -> None:
    payload = {
        'fingerprint': fingerprint,
        'genVersion': _GEN_VERSION,
        'numQuestions': num_questions,
        'createdAt': time.strftime('%Y-%m-%d %H:%M:%S'),
        'judgeModel': getattr(native_llm, 'MODEL_NAME', ''),
        'examples': examples,
    }
    tmp = DATASET_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATASET_FILE)


def _even_sample(items: List[Any], k: int) -> List[Any]:
    """均匀采样 k 个，保证评测覆盖不同文档位置。"""
    if k >= len(items):
        return list(items)
    if k <= 0:
        return []
    step = len(items) / k
    return [items[int(i * step)] for i in range(k)]


def _clean_query(q: str) -> str:
    """去掉出题模板带出的前缀（如「问题：」），保持问题干净。"""
    return re.sub(r'^(问题|Question)\s*[:：]\s*', '', (q or '').strip()).strip()


def _clean_examples(examples: List[Dict]) -> List[Dict]:
    out = []
    for e in examples:
        e = dict(e)
        e['query'] = _clean_query(e.get('query', ''))
        if e['query']:
            out.append(e)
    return out


def build_dataset(num_questions: int = 10, regenerate: bool = False,
                  judge: Optional[JudgeLLM] = None) -> Dict:
    """用 RagDatasetGenerator 从知识库合成评测集（问题 + 标准答案 + 来源分块）。

    合成结果缓存到 `rag_eval_dataset.json`，知识库分块集合变化时自动重建；
    regenerate=True 强制重建。返回 {'examples', 'regenerated', 'fingerprint', 'size'}。
    """
    nodes, by_text, _, _ = _build_chunk_index()
    if not nodes:
        raise rag.RagError('知识库为空，无法合成评测集，请先上传文档')

    fingerprint = _kb_fingerprint(nodes)
    if not regenerate:
        cached = _load_cached_dataset(fingerprint, num_questions)
        if cached:
            cached = _clean_examples(cached)
            return {'examples': cached[:num_questions], 'regenerated': False,
                    'fingerprint': fingerprint, 'size': len(cached)}

    judge = judge or JudgeLLM()
    sampled = _even_sample(nodes, num_questions)
    generator = RagDatasetGenerator(
        nodes=sampled,
        llm=judge,
        num_questions_per_chunk=1,
        question_gen_query=_QUESTION_GEN_QUERY,
        show_progress=False,
        workers=1,
    )
    dataset = generator.generate_dataset_from_nodes()

    examples: List[Dict] = []
    for ex in dataset.examples:
        query = _clean_query(ex.query)
        contexts = [c for c in (ex.reference_contexts or []) if c]
        if not query or not contexts:
            continue
        source_ids = [by_text[c] for c in contexts if c in by_text]
        examples.append({
            'query': query,
            'referenceAnswer': (ex.reference_answer or '').strip(),
            'referenceContexts': contexts,
            'sourceIds': source_ids,
        })
    if not examples:
        raise RuntimeError('评测集合成失败：本地大模型未返回有效问答对')

    _save_dataset(fingerprint, examples, num_questions)
    return {'examples': examples[:num_questions], 'regenerated': True,
            'fingerprint': fingerprint, 'size': len(examples)}


# ================= 检索结果 → LlamaIndex Retriever =================
class _CachedRetriever(BaseRetriever):
    """把 ModularRAG 一次检索的最终片段缓存为 LlamaIndex Retriever。

    RetrieverEvaluator 只读取 node_id 与文本，因此直接回放缓存，
    避免为打分重复跑一遍检索管线造成前后结果不一致。
    """

    def __init__(self, nodes: List[NodeWithScore]):
        super().__init__()
        self._nodes = nodes

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        return list(self._nodes)


def _resolve_node_ids(docs: List[Any], by_text: Dict[str, str],
                      by_meta: Dict[tuple, str], by_position: Dict[int, str]) -> List[str]:
    """把管线输出的片段解析成知识库分块 ID（多种检索路径的元信息语义不同，逐级回退）。"""
    ids: List[str] = []
    for d in docs:
        text = d.content
        m = d.metadata or {}
        cid = by_text.get(text)
        if cid is None:
            cid = by_meta.get((m.get('docId'), m.get('chunkIndex')))
        if cid is None and isinstance(m.get('chunkIndex'), int):
            cid = by_position.get(m.get('chunkIndex'))
        if cid is None:  # 上下文压缩会改写文本，用包含关系回退定位
            for chunk_text, tid in by_text.items():
                if text and (text in chunk_text or chunk_text in text):
                    cid = tid
                    break
        ids.append(cid or '')
    return ids


# ================= 单题评测 =================
def _score(result) -> Optional[float]:
    s = getattr(result, 'score', None)
    try:
        return float(s) if s is not None else None
    except (TypeError, ValueError):
        return None


def _evaluate_one(query: str, expected_ids: List[str], docs: List[Any], answer: str,
                  judge: JudgeLLM, by_text: Dict[str, str], by_meta: Dict[tuple, str],
                  by_position: Dict[int, str]) -> Dict:
    """对一题的管线输出做整体评价：检索侧 + 生成侧共 5 项指标（每项独立容错）。"""
    contexts = [d.content for d in docs]
    retrieved_ids = _resolve_node_ids(docs, by_text, by_meta, by_position)
    nodes = [NodeWithScore(node=TextNode(id_=rid or f'unknown-{i}', text=d.content),
                           score=float(d.score or 0.0))
             for i, (d, rid) in enumerate(zip(docs, retrieved_ids))]

    detail: Dict[str, Any] = {
        'query': query,
        'answer': answer,
        'contexts': contexts,
        'expectedIds': expected_ids,
        'retrievedIds': retrieved_ids,
        'contextPrecision': None, 'contextRecall': None, 'hitRate': None, 'mrr': None,
        'faithfulness': None, 'answerRelevance': None,
        'answerCorrectness': None, 'answerCorrectnessRaw': None,
        'errors': [],
    }

    # 检索侧：上下文精确率 / 上下文召回率（+ 命中率、MRR 作诊断参考）
    if expected_ids and not nodes:
        # 管线整体返回空（如自反思判定不检索）：检索指标按 0 计入均值，而非留空
        detail['contextPrecision'] = 0.0
        detail['contextRecall'] = 0.0
        detail['hitRate'] = 0.0
        detail['mrr'] = 0.0
        detail['errors'].append('管线未返回检索结果，检索指标按 0 计')
    elif expected_ids:
        try:
            ret_evaluator = RetrieverEvaluator.from_metric_names(
                ['hit_rate', 'mrr', 'precision', 'recall'], retriever=_CachedRetriever(nodes))
            result = ret_evaluator.evaluate(query, expected_ids)
            md = result.metric_dict
            detail['contextPrecision'] = float(md.get('precision', 0.0))
            detail['contextRecall'] = float(md.get('recall', 0.0))
            detail['hitRate'] = float(md.get('hit_rate', 0.0))
            detail['mrr'] = float(md.get('mrr', 0.0))
        except Exception as e:
            detail['errors'].append(f'检索评估失败：{e}')
    else:
        detail['errors'].append('缺少来源分块标注，跳过上下文精确率/召回率')

    # 生成侧：忠实度 / 答案相关性（评估器基于问题 + 上下文 + 回答打 0/1 分）
    if answer and contexts:
        try:
            r = FaithfulnessEvaluator(llm=judge).evaluate(query=query, response=answer, contexts=contexts)
            detail['faithfulness'] = _score(r)
        except Exception as e:
            detail['errors'].append(f'忠实度评估失败：{e}')
        try:
            r = RelevancyEvaluator(llm=judge).evaluate(query=query, response=answer, contexts=contexts)
            detail['answerRelevance'] = _score(r)
        except Exception as e:
            detail['errors'].append(f'答案相关性评估失败：{e}')
    elif answer:
        # 管线未提供上下文（如自反思判定丢弃检索结果）：回答无据可依，
        # 忠实度确定性记 0；答案相关性照常评估（衡量回答与问题的相关程度）
        detail['faithfulness'] = 0.0
        detail['errors'].append('无检索上下文，忠实度按 0 计')
        try:
            r = RelevancyEvaluator(llm=judge).evaluate(query=query, response=answer, contexts=contexts)
            detail['answerRelevance'] = _score(r)
        except Exception as e:
            detail['errors'].append(f'答案相关性评估失败：{e}')
    else:
        detail['errors'].append('回答为空，跳过忠实度/答案相关性')

    return detail


def _evaluate_correctness(query: str, answer: str, reference: str, judge: JudgeLLM,
                          detail: Dict) -> None:
    """答案正确率：CorrectnessEvaluator 对照标准答案给 1-5 分。"""
    # RagDatasetGenerator 合成失败时会写入占位串 "Empty Response"，视为无参考答案
    ref = (reference or '').strip()
    if ref.lower() == 'empty response':
        ref = ''
    if not answer or not ref:
        detail['errors'].append('缺少标准答案或回答，跳过答案正确率')
        return
    try:
        r = CorrectnessEvaluator(llm=judge).evaluate(query=query, response=answer, reference=ref)
        raw = _score(r)
        if raw is not None:
            detail['answerCorrectnessRaw'] = raw
            detail['answerCorrectness'] = raw / 5.0  # 官方 1-5 分归一到 0-1 统一展示
    except Exception as e:
        detail['errors'].append(f'答案正确率评估失败：{e}')


# ================= 评测入口 =================
def run_evaluation(num_questions: int = 10, regenerate_dataset: bool = False) -> Dict:
    """跑完整评测并返回汇总结果（后台「效果测评」按钮触发）。

    每题独立容错：单题失败不影响其余题目，失败原因写入该题的 errors。
    """
    start = time.time()
    dataset = build_dataset(num_questions=num_questions, regenerate=regenerate_dataset)
    examples = dataset['examples']
    judge = JudgeLLM()

    nodes, by_text, by_meta, by_position = _build_chunk_index()
    mr = modular_rag.get_modular_rag()
    generator = modular_rag.Generator()

    details: List[Dict] = []
    for ex in examples:
        query = ex['query']
        try:
            docs = mr.query(query)               # 全管线各级输出（检索片段列表）
            # 无检索结果时也照常生成（与线上一致：自反思丢弃上下文后仍由大模型兜底回答），
            # 保证忠实度/相关性/正确率三项生成侧指标有值可评
            answer = generator.generate(query, docs)
            detail = _evaluate_one(query, ex.get('sourceIds') or [], docs, answer,
                                   judge, by_text, by_meta, by_position)
        except Exception as e:
            detail = {'query': query, 'answer': '', 'contexts': [],
                      'expectedIds': ex.get('sourceIds') or [], 'retrievedIds': [],
                      'contextPrecision': None, 'contextRecall': None, 'hitRate': None, 'mrr': None,
                      'faithfulness': None, 'answerRelevance': None,
                      'answerCorrectness': None, 'answerCorrectnessRaw': None,
                      'errors': [f'评测失败：{e}']}
        _evaluate_correctness(query, detail.get('answer') or '',
                              ex.get('referenceAnswer') or '', judge, detail)
        details.append(detail)

    # 汇总：各指标按有效题目取均值
    metrics: Dict[str, Optional[float]] = {}
    field_map = {
        'context_precision': 'contextPrecision',
        'context_recall': 'contextRecall',
        'faithfulness': 'faithfulness',
        'answer_relevance': 'answerRelevance',
        'answer_correctness': 'answerCorrectness',
    }
    for key, field in field_map.items():
        vals = [d[field] for d in details if d.get(field) is not None]
        metrics[key] = round(sum(vals) / len(vals), 4) if vals else None

    return {
        'ok': True,
        'metrics': metrics,
        'details': details,
        'dataset': {
            'size': dataset['size'],
            'used': len(examples),
            'regenerated': dataset['regenerated'],
            'fingerprint': dataset['fingerprint'],
        },
        'elapsedSeconds': round(time.time() - start, 1),
    }
