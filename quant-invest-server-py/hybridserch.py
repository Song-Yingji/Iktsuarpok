"""
混合检索示例（Hybrid Search）
使用 BGE  embedding + BM25 稀疏检索 + RRF 融合
"""

from pathlib import Path
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import jieba

class HybirdRetrival:

    def __init__(self,K=60,documents=[],query="",top_k=5):
        self.k = K
        self.documents = documents
        self.query = query
        self.top_k = top_k

    # ========== 1. 稠密向量检索（BGE） ==========

    def bgeChou(self,documents,query):
        BASE_DIR = Path(__file__).resolve().parent
        dense_model = SentenceTransformer(str(BASE_DIR/"bgemodels"))

        # 编码文档（原始文档向量化）
        doc_embeddings = dense_model.encode(documents, normalize_embeddings=True)

        # 编码查询（用户查询内容的向量化）
        query_embedding = dense_model.encode([query], normalize_embeddings=True)

        # 计算相似度
        dense_scores = cosine_similarity(query_embedding, doc_embeddings)[0]

        # 获取排名(稠密向量排名结果)
        dense_ranking = np.argsort(-dense_scores)  # 降序

        return dense_ranking

    # ========== 2. 稀疏向量检索（BM25） ==========
    def bm25Xi(self,documents,query):

        # 中文分词（BM25 需要 token 序列）
        def tokenize(text):
            return list(jieba.cut(text))

        # 原始文档分词
        tokenized_docs = [tokenize(doc) for doc in documents]
        bm25 = BM25Okapi(tokenized_docs)

        # 用户查询内容分词
        tokenized_query = tokenize(query)
        bm25_scores = bm25.get_scores(tokenized_query)

        # 获取排名(稀疏向量排名结果)
        bm25_ranking = np.argsort(-bm25_scores)  # 降序

        return bm25_ranking


    # ========== 3. RRF 融合 ==========
    def rrf(self,doc_len,dense_ranking,bm25_ranking):

        # 构建排名映射 {doc_index: rank}
        dense_ranks = {idx: rank for rank, idx in enumerate(dense_ranking, start=1)}
        bm25_ranks = {idx: rank for rank, idx in enumerate(bm25_ranking, start=1)}

        # 计算 RRF 分数
        rrf_scores = {}
        for i in range(doc_len):
            score = 0
            # 稠密向量贡献
            if i in dense_ranks:
                score += 1.0 / (self.k + dense_ranks[i])
            # BM25 贡献
            if i in bm25_ranks:
                score += 1.0 / (self.k + bm25_ranks[i])
            rrf_scores[i] = score

        # 排序：对 rrf_scores 字典按值（value）从大到小排序，返回一个列表。
        # 第一个参数：要排序的元组列表
        # 第二个参数：排序关键字是列表中每个元素（元组）的第二个元素。
        # 第三个参数：从大到小排（默认 False 是从小到大）
        final_ranking = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        return final_ranking,dense_ranks,bm25_ranks



    def get_rrf(self):
        # 稠密排序
        dense_ranking  = self.bgeChou(self.documents,self.query)
        # 稀疏排序
        bm25_ranking = self.bm25Xi(self.documents,self.query)
        #RRF融合
        final_ranking,dense_ranks,bm25_ranks = self.rrf(len(self.documents),dense_ranking,bm25_ranking)

        results = []
        for i, (idx, score) in enumerate(final_ranking[:self.top_k]):
            results.append(self.documents[idx])

        return results


# if __name__ =="__main__":
#     hr = HybirdRetrival(documents=[
#         "Qwen 是阿里云开发的大语言模型，支持多种部署方式。",
#         "通义千问（Qwen）可以通过 vLLM 进行高效推理部署。",
#         "大模型部署需要考虑 GPU 显存、并发量和延迟优化。",
#         "BERT 是 Google 开发的预训练模型，用于理解文本。",
#         "GPT-4 是 OpenAI 的多模态大模型，功能强大。",
#         "vLLM 是一个开源的 LLM 推理引擎，支持 PageAttention。",
#         "机器学习是人工智能的一个分支，包括监督学习和无监督学习。",
#         "Qwen2.5 是最新版本，支持 128K 上下文和工具调用。",
#         "模型量化技术如 GPTQ 和 AWQ 可以减少显存占用。",
#         "Docker 容器化部署可以简化大模型的环境配置。",
#     ],query="Qwen 大模型部署教程",top_k=5)

#     results = hr.get_rrf()

#     for idx,doc in enumerate(results):
#         print(f"第{idx+1}名：{doc}")

        
