# -*- coding: utf-8 -*-
"""Modular RAG（模块化检索增强生成）。

按模块化架构把 RAG 拆成可插拔的独立模块：

    查询改写 → 多路检索（向量 + BM25）→ 融合（RRF）→ 重排序 → 上下文压缩

每个模块独立、可替换、可单独测试，由 ModularRAG 主类用配置开关编排成 pipeline。
向量检索复用 rag.py 的 Chroma 库（qwen3-embedding 持久化向量），
BM25 关键词检索基于 jieba + rank_bm25 对全库分块建索引并缓存，
生成器复用 llm.py 的非流式大模型（非模拟）。
"""
import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import jieba
import numpy as np
from rank_bm25 import BM25Okapi

import llm
import prompts
import rag

jieba.setLogLevel(60)  # 静音 jieba 首次加载词典的日志


# ================= 基础数据结构 =================
@dataclass
class Document:
    """检索到的一个文档 / 段落。"""
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0


@dataclass
class RetrievalResult:
    """一路检索的结果。"""
    query: str
    documents: List[Document]
    source: str


def _dedupe(docs: List[Document]) -> List[Document]:
    """按内容去重，同内容保留分数更高者。"""
    seen: Dict[str, Document] = {}
    for d in docs:
        if d.content not in seen or d.score > seen[d.content].score:
            seen[d.content] = d
    return list(seen.values())


def _normalize_scores(docs: List[Document]) -> List[Document]:
    """把分数线性缩放到 [0, 1]，统一不同检索器的量纲。"""
    mx = max((d.score for d in docs if d.score > 0), default=0.0)
    if mx > 0:
        for d in docs:
            d.score = min(1.0, d.score / mx)
    return docs


# ================= 查询改写模块 =================
class QueryRewriter:
    """查询改写：生成多角度查询以提升召回（规则式，零额外延迟）。"""

    STOPWORDS = {
        '的', '了', '是', '在', '我', '有', '和', '就', '不', '人', '都', '一',
        '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着',
        '没有', '看', '好', '自己', '这', '那', '什么', '如何', '为什么', '怎么',
        '哪个', '哪些', '请', '介绍', '一下', '可以', '这个', '吗', '呢', '把',
        '被', '让', '与', '或', '以及', '还是', '对于', '关于',
    }

    SYNONYMS = {
        '股票': ['个股', '标的'],
        '上涨': ['走强', '拉升'],
        '下跌': ['走弱', '回落'],
        '买入': ['建仓', '进场'],
        '卖出': ['减仓', '离场'],
        '策略': ['方案', '方法'],
        '风险': ['回撤', '波动'],
        '收益': ['回报', '盈利'],
    }

    def tokenize(self, text: str) -> List[str]:
        return [w for w in jieba.lcut(text)
                if w.strip() and w not in self.STOPWORDS and len(w) >= 2]

    def extract_keywords(self, text: str, top_k: int = 3) -> List[str]:
        return self.tokenize(text)[:top_k]

    def multi_query(self, query: str) -> List[str]:
        """多查询生成：疑问句变体 + 关键词版本。"""
        queries = [query]
        if '?' in query or '？' in query:
            no_q = query.replace('?', '').replace('？', '').strip()
            if len(no_q) >= 2:
                queries.append(no_q)
        else:
            if len(query) >= 2 and not query.endswith(('是什么', '怎么样', '如何')):
                queries.append(query + '是什么')
        keywords = self.extract_keywords(query)
        if len(keywords) >= 2:
            kw_q = ' '.join(keywords)
            if kw_q != query:
                queries.append(kw_q)
        return list(dict.fromkeys(queries))[:3]

    def expand_synonyms(self, query: str) -> List[str]:
        """同义词扩展：对每个词替换一个同义词产生新查询。"""
        queries = [query]
        words = jieba.lcut(query)
        for i, w in enumerate(words):
            for syn in self.SYNONYMS.get(w, [])[:1]:
                new = words.copy()
                new[i] = syn
                queries.append(''.join(new))
        return list(dict.fromkeys(queries))[:3]

    def rewrite(self, query: str, method: str = 'multi') -> List[str]:
        if method == 'expand':
            return self.expand_synonyms(query)
        if method == 'multi':
            return self.multi_query(query)
        return [query]


# ================= 检索器模块 =================
class VectorRetriever:
    """向量检索：复用 rag.py 的 Chroma 库，返回语义相似的片段。"""

    def __init__(self, top_k: int = 20, min_score: float = 0.3):
        self.top_k = top_k
        self.min_score = min_score

    def search(self, query: str) -> List[Document]:
        try:
            hits = rag.retrieve(query, top_k=self.top_k, min_score=self.min_score)
        except rag.RagError:
            return []
        return [Document(content=h['text'],
                         metadata={'docId': h.get('docId'), 'docName': h.get('docName'),
                                   'chunkIndex': h.get('chunkIndex')},
                         score=h.get('score', 0.0)) for h in hits]


class KeywordRetriever:
    """BM25 关键词检索：jieba 分词 + rank_bm25，对全库分块建倒排索引（惰性缓存）。"""

    def __init__(self, top_k: int = 20):
        self.top_k = top_k
        self._docs: List[str] = []
        self._metas: List[Dict] = []
        self._bm25: Optional[BM25Okapi] = None

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return [w for w in jieba.lcut(text) if w.strip()]

    def build_index(self) -> None:
        """全库分块建 BM25 索引；文档集合未变时复用缓存。"""
        chunks = rag.all_chunks()
        docs = [t for t, _ in chunks]
        if self._bm25 is not None and docs == self._docs:
            return
        self._docs = docs
        self._metas = [m for _, m in chunks]
        self._bm25 = BM25Okapi([self._tokenize(d) for d in docs]) if docs else None

    def search(self, query: str) -> List[Document]:
        try:
            self.build_index()
        except rag.RagError:
            return []
        if not self._bm25:
            return []
        scores = self._bm25.get_scores(self._tokenize(query))
        order = np.argsort(-scores)[:self.top_k]
        docs = []
        for i in order:
            if scores[i] <= 0:
                continue
            m = self._metas[i]
            docs.append(Document(content=self._docs[i],
                                 metadata={'docId': m.get('doc_id'), 'docName': m.get('doc_name'),
                                           'chunkIndex': i},
                                 score=float(scores[i])))
        return docs


# ================= 融合模块 =================
class FusionModule:
    """多路检索结果融合：RRF / 加权 / 拼接。"""

    def __init__(self, method: str = 'rrf'):
        self.method = method

    def reciprocal_rank_fusion(self, results_list: List[List[Document]], k: int = 60) -> List[Document]:
        rrf_scores: Dict[str, float] = defaultdict(float)
        doc_map: Dict[str, Document] = {}
        for rank_list in results_list:
            for rank, doc in enumerate(rank_list[:20]):
                rrf_scores[doc.content] += 1.0 / (k + rank + 1)
                doc_map.setdefault(doc.content, doc)
        docs = []
        for content, score in sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True):
            d = doc_map[content]
            d.score = score
            docs.append(d)
        return docs

    def weighted_fusion(self, results_list: List[List[Document]], weights: List[float]) -> List[Document]:
        merged: Dict[str, Document] = {}
        scores: Dict[str, float] = defaultdict(float)
        for rank_list, w in zip(results_list, weights):
            for doc in rank_list:
                scores[doc.content] += w * doc.score
                merged.setdefault(doc.content, doc)
        docs = []
        for content, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
            d = merged[content]
            d.score = score
            docs.append(d)
        return docs

    def concat(self, results_list: List[List[Document]]) -> List[Document]:
        return _dedupe([d for rank_list in results_list for d in rank_list])

    def fuse(self, results_list: List[List[Document]]) -> List[Document]:
        if self.method == 'weighted':
            return self.weighted_fusion(results_list, [1.0] * len(results_list))
        if self.method == 'concat':
            return self.concat(results_list)
        return self.reciprocal_rank_fusion(results_list)


# ================= 重排序模块 =================
class ReRanker:
    """重排序：中文分词 + 词语重叠 + 短语匹配，对检索结果重新打分排序。"""

    STOPWORDS = {
        '的', '了', '是', '在', '我', '有', '和', '就', '不', '人', '都', '一',
        '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着',
        '没有', '看', '好', '自己', '这', '那', '什么', '如何', '为什么', '怎么',
        '哪个', '哪些', '请', '介绍', '一下',
    }

    def _tokenize_words(self, text: str) -> List[str]:
        text = re.sub(r'[，。！？；：、\s]+', ' ', text)
        return [w for w in jieba.lcut(text)
                if w not in self.STOPWORDS and len(w) >= 2 and not w.isdigit()]

    def token_overlap(self, query: str, document: str) -> float:
        q = set(self._tokenize_words(query))
        if not q:
            return 0.0
        d = set(self._tokenize_words(document))
        return len(q & d) / len(q)

    def phrase_match(self, query: str, document: str) -> float:
        query_clean = re.sub(r'[？?！!。，,、；;：:]', '', query)
        if query_clean and query_clean in document:
            return 1.0
        for part in [p for p in query_clean.split() if len(p) >= 2]:
            if part in document:
                return 0.8
        doc_words = set(self._tokenize_words(document))
        for kw in self._tokenize_words(query_clean):
            if kw in doc_words or kw in document:
                return 0.6
        return 0.0

    def relevance(self, query: str, document: str) -> float:
        base = self.token_overlap(query, document)
        phrase = self.phrase_match(query, document)
        if phrase >= 1.0:
            return max(base, 0.8)
        if phrase > 0.5:
            return base * 0.3 + phrase * 0.7
        return base * 0.5 + phrase * 0.5

    def rerank(self, query: str, documents: List[Document]) -> List[Document]:
        for doc in documents:
            doc.score = self.relevance(query, doc.content) * 0.7 + doc.score * 0.3
        documents.sort(key=lambda d: d.score, reverse=True)
        return documents


# ================= 上下文压缩模块 =================
class ContextCompressor:
    """上下文压缩：分句 → 句子相关性打分 → 保留最相关的句子。"""

    def __init__(self, max_sentences: int = 3):
        self.max_sentences = max_sentences

    @staticmethod
    def split_sentences(text: str) -> List[str]:
        sentences = re.split(r'[.!?。！？;；]+', text)
        return [s.strip() for s in sentences if len(s.strip()) > 10]

    def sentence_relevance(self, query: str, sentence: str) -> float:
        q = set(w for w in jieba.lcut(query) if w.strip())
        if not q:
            return 0.0
        s = set(w for w in jieba.lcut(sentence) if w.strip())
        return len(q & s) / len(q)

    def compress(self, query: str, documents: List[Document]) -> List[Document]:
        out = []
        for doc in documents:
            sentences = self.split_sentences(doc.content)
            if not sentences:
                out.append(doc)
                continue
            scored = sorted(
                ((s, self.sentence_relevance(query, s)) for s in sentences),
                key=lambda x: x[1], reverse=True,
            )
            top = [s for s, _ in scored[:self.max_sentences]]
            # 按原文顺序重组，保持可读性
            seen, ordered = set(top), []
            for s in sentences:
                if s in seen:
                    ordered.append(s)
                    seen.discard(s)
            out.append(Document(
                content=' '.join(ordered) if ordered else doc.content,
                metadata=dict(doc.metadata),
                score=doc.score,
            ))
        return out


# ================= 生成器模块 =================
class Generator:
    """生成器：封装 llm.py 的大模型（非流式），基于检索上下文一次性生成回答。"""

    def generate(self, query: str, documents: List[Document], system_prompt: str = None) -> str:
        context = prompts.build_rag_context(query, [d.content for d in documents])
        return llm.chat([{'role': 'user', 'content': context}], system_prompt=system_prompt)


# ================= Self-RAG 分析模块 =================


class SelfRagModule:
    """Self-RAG 分析器：把「是否需要检索 / 内容是否有用 / 回答是否合格 / 反思修正」
    四步判断交给本地大模型完成，逻辑对齐 self_rag 参考实现。

    前两步用于检索阶段（调用 rag 时分析），后两步用于生成阶段（反思修正）。
    LLM 调用失败时按保守策略兜底（默认照常检索 / 视内容有用 / 保留原回答），
    保证本地模型不可用时不阻断主流程。
    """

    @classmethod
    def _ask(cls, prompt: str) -> str:
        # 判定类调用固定 temperature=0：YES/NO 决策需稳定可复现，
        # 避免同一问题在多次调用间随机翻转（会随机丢弃检索结果）。
        return llm.chat([{'role': 'user', 'content': prompt}],
                        system_prompt=prompts.RAG_SYSTEM, temperature=0).strip()

    @staticmethod
    def _yes(text: str, default: bool) -> bool:
        t = (text or '').strip().lower()
        if t.startswith('yes') or t.startswith('是'):
            return True
        if t.startswith('no') or t.startswith('否'):
            return False
        return default

    def should_retrieve(self, query: str) -> bool:
        """步骤 1：判断问题是否需要检索外部知识才能回答。"""
        return self._yes(self._ask(prompts.build_selfrag_retrieve(query)), default=True)

    def is_context_useful(self, query: str, context: str) -> bool:
        """步骤 2：判断检索到的内容能否准确回答问题。"""
        return self._yes(self._ask(prompts.build_selfrag_useful(query, context)), default=True)

    def should_continue_generate(self, query: str, context: str, answer: str) -> bool:
        """步骤 3：判断回答是否完整、准确、无幻觉。"""
        return self._yes(self._ask(prompts.build_selfrag_complete(query, context, answer)), default=True)

    def reflect_and_correct(self, query: str, context: str, answer: str) -> str:
        """步骤 4：自我反思修正，输出修正后的最终回答。"""
        corrected = self._ask(prompts.build_selfrag_reflect(query, context, answer))
        return corrected or answer


# ================= Module 可插拔配置（持久化 + 热刷新） =================
# 后台「模块设置」面板写的配置文件；缺失时回退到 DEFAULT_CONFIG。
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rag_config.json')

DEFAULT_CONFIG = {
    'enable_rewrite': False,      # 查询改写（规则式，可选增强）
    'enable_fusion': True,        # 多路融合（向量 + BM25）
    'fusion_method': 'rrf',       # rrf / weighted / concat
    'enable_rerank': True,        # 重排序
    'enable_compression': False,  # 上下文压缩
    'enable_self_rag': False,     # 本地大模型分析（Self-RAG：是否检索 / 内容是否有用）
    'rewrite_method': 'multi',    # multi / expand
    'top_k': 4,
    'min_score': 0.3,
}

_FUSION_METHODS = ('rrf', 'weighted', 'concat')
_REWRITE_METHODS = ('multi', 'expand')
_BOOL_KEYS = ('enable_rewrite', 'enable_fusion', 'enable_rerank', 'enable_compression', 'enable_self_rag')


def _sanitize_config(cfg: Dict) -> Dict:
    """收敛配置：只保留已知键、修正类型、钳制取值范围，防止写坏文件或非法入参破坏管线。"""
    c = dict(DEFAULT_CONFIG)
    if isinstance(cfg, dict):
        for k in DEFAULT_CONFIG:
            if k in cfg:
                c[k] = cfg[k]
    for k in _BOOL_KEYS:
        c[k] = bool(c[k])
    if c['fusion_method'] not in _FUSION_METHODS:
        c['fusion_method'] = DEFAULT_CONFIG['fusion_method']
    if c['rewrite_method'] not in _REWRITE_METHODS:
        c['rewrite_method'] = DEFAULT_CONFIG['rewrite_method']
    try:
        c['top_k'] = max(1, min(20, int(c['top_k'])))
    except (TypeError, ValueError):
        c['top_k'] = DEFAULT_CONFIG['top_k']
    try:
        c['min_score'] = max(0.0, min(1.0, float(c['min_score'])))
    except (TypeError, ValueError):
        c['min_score'] = DEFAULT_CONFIG['min_score']
    return c


def load_config() -> Dict:
    """读取持久化配置并合并默认值；文件缺失或损坏时静默回退默认。"""
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            cfg.update(data)
    except (OSError, ValueError):
        pass
    return _sanitize_config(cfg)


def save_config(config: Dict) -> Dict:
    """合并默认值 + 收敛后原子写盘，返回规范化后的完整配置。"""
    cfg = _sanitize_config({**DEFAULT_CONFIG, **(config or {})})
    tmp = CONFIG_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_FILE)
    return cfg


# ================= Modular RAG 主类 =================


class ModularRAG:
    """模块化 RAG 主类：用配置开关把各模块编排为检索 pipeline。"""

    def __init__(self, config: Optional[Dict] = None):
        self.rewriter = QueryRewriter()
        self.vector = VectorRetriever()
        self.keyword = KeywordRetriever()
        self.fusion = FusionModule()
        self.reranker = ReRanker()
        self.compressor = ContextCompressor()
        self.generator = Generator()
        self.self_rag = SelfRagModule()
        self.config: Dict = {}
        self.top_k = int(DEFAULT_CONFIG['top_k'])
        self.min_score = float(DEFAULT_CONFIG['min_score'])
        self._apply_config(config if config is not None else load_config())

    def _apply_config(self, cfg: Dict) -> None:
        """热更新各模块参数，供后台「模块设置」改动后即时生效。"""
        self.config = _sanitize_config(cfg)
        self.top_k = int(self.config['top_k'])
        self.min_score = float(self.config['min_score'])
        router_k = max(self.top_k * 5, 20)
        self.vector.top_k = router_k
        self.vector.min_score = self.min_score
        self.keyword.top_k = router_k
        self.fusion.method = self.config['fusion_method']

    def _merge(self, doc_lists) -> List[Document]:
        return _dedupe([d for lst in doc_lists for d in lst])

    def _pipeline(self, query: str) -> List[Document]:
        cfg = self.config
        queries = self.rewriter.rewrite(query, method=cfg['rewrite_method']) if cfg['enable_rewrite'] else [query]

        vector_docs = self._merge(self.vector.search(q) for q in queries)
        keyword_docs = self._merge(self.keyword.search(q) for q in queries)

        if cfg['enable_fusion']:
            docs = self.fusion.fuse([_normalize_scores(vector_docs), _normalize_scores(keyword_docs)])
        else:
            docs = _dedupe(vector_docs + keyword_docs)

        docs = _normalize_scores(docs)

        if cfg['enable_rerank']:
            docs = self.reranker.rerank(query, docs)
            docs = _normalize_scores(docs)

        if cfg['enable_compression']:
            docs = self.compressor.compress(query, docs)

        return docs[:self.top_k]

    def query(self, query: str) -> List[Document]:
        """检索入口，返回 Document 列表。"""
        q = (query or '').strip()
        if not q:
            return []
        self._apply_config(load_config())  # 每次检索前读取最新配置，支持后台热插拔
        if self.config['enable_self_rag'] and not self.self_rag.should_retrieve(q):
            return []  # 本地大模型判定无需检索
        docs = self._pipeline(q)
        if docs and self.config['enable_self_rag']:
            context = '\n\n'.join(d.content for d in docs)
            if not self.self_rag.is_context_useful(q, context):
                return []  # 本地大模型判定检索内容无用，不注入
        return docs

    def retrieve(self, query: str) -> List[Dict]:
        """返回与 rag.retrieve 兼容的命中片段列表，便于上层直接复用。"""
        return [self._to_hit(d) for d in self.query(query)]

    @staticmethod
    def _to_hit(doc: Document) -> Dict:
        m = doc.metadata
        return {
            'text': doc.content,
            'docId': m.get('docId') or '',
            'docName': m.get('docName') or '向量知识库',
            'chunkIndex': m.get('chunkIndex') if m.get('chunkIndex') is not None else '',
            'score': round(doc.score, 4),
        }


_default_rag: Optional[ModularRAG] = None


def get_modular_rag(config: Optional[Dict] = None) -> ModularRAG:
    """返回模块级单例（BM25 索引惰性构建并缓存，跨请求复用）。"""
    global _default_rag
    if _default_rag is None:
        _default_rag = ModularRAG(config)
    return _default_rag