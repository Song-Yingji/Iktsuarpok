# -*- coding: utf-8 -*-
"""本地向量知识库（RAG）。

流水线：上传文档 → 递归分块 → 本地 Ollama qwen3-embedding 向量化 → Chroma 本地持久化。

策略生成智能体在收到用户提问时，会先把问题向量化并与本知识库做相似度检索，
把命中片段拼进提示词，与系统提示词一起交给大模型。

向量化走 OpenAI 兼容的 /embeddings 接口，默认指向本地 Ollama（qwen3-embedding:0.6b，1024 维），
也可在 llm_config.py 中换成任意兼容服务（如阿里云百炼 text-embedding-v3）。
依赖：chromadb（向量库）、requests（调用 /embeddings 接口）。
向量由本模块自行计算后显式写入 Chroma，因此不会触发 Chroma 默认嵌入模型的下载。
"""
import html
import io
import os
import re
import tempfile
import time
import uuid
import zipfile
import requests

try:
    import chromadb
except ImportError:  # 未安装时给出可读的提示，而不是启动即崩
    chromadb = None

try:
    import llm_config
except ImportError:
    llm_config = None


def _cfg(key, default=''):
    """读取配置：环境变量优先，其次 llm_config.py，最后用默认值。"""
    v = os.environ.get(key)
    if v:
        return v
    v = getattr(llm_config, key, None) if llm_config else None
    return v if v else default


# ====== 向量化模型（默认本地 Ollama qwen3-embedding:0.6b） ======
EMBED_BASE_URL = _cfg('EMBED_BASE_URL', 'http://localhost:11434/v1').rstrip('/')
EMBED_API_KEY = _cfg('EMBED_API_KEY', 'ollama')   # Ollama 不校验 Key，占位即可
EMBED_MODEL = _cfg('EMBED_MODEL', 'qwen3-embedding:0.6b')
EMBED_BATCH = 10          # 单次请求的文本条数，控制请求体量与显存占用
EMBED_DIM = 1024          # qwen3-embedding:0.6b 输出 1024 维向量

# ====== 分块参数 ======
CHUNK_SIZE = 500          # 每块目标字符数
CHUNK_OVERLAP = 80        # 相邻块重叠字符数，避免跨块语义被切断

# ====== 检索参数 ======
TOP_K = 4                 # 默认召回条数
MIN_SCORE = 0.3           # 余弦相似度下限，低于该值视为不相关

# ====== 本地存储 ======
STORE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kb_store')
COLLECTION_NAME = 'quant_kb'

# 递归分块的分隔符优先级：段落 → 换行 → 中英文句读 → 空白
# 全部降级完仍有超长块时，由 _split_recursive 直接按字符硬切
SEPARATORS = ['\n\n', '\n', '。', '！', '？', '；', '!', '?', ';', '，', '、', ', ', ' ']

TEXT_EXTS = {'.txt', '.md', '.markdown', '.csv', '.log'}


class RagError(Exception):
    """知识库操作失败（配置缺失、格式不支持、外部服务异常等）。"""


# ================= 文本抽取 =================
def _decode(raw):
    """按常见中文编码依次尝试解码。"""
    for enc in ('utf-8', 'utf-8-sig', 'gbk', 'big5'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', 'ignore')


def _extract_pdf(raw):
    """用 pypdfium2 逐页抽取 PDF 文本。"""
    try:
        import pypdfium2 as pdfium
    except ImportError as e:
        raise RagError('未安装 pypdfium2，无法解析 PDF') from e

    tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    try:
        tmp.write(raw)
        tmp.close()
        pdf = pdfium.PdfDocument(tmp.name)
        return '\n'.join(page.get_textpage().get_text_range() for page in pdf)
    except RagError:
        raise
    except Exception as e:
        raise RagError('PDF 解析失败，请确认文件未加密且内容为文本型 PDF') from e
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _extract_docx(raw):
    """docx 本质是 zip，直接读 word/document.xml 取文本，避免额外依赖。"""
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            xml = z.read('word/document.xml').decode('utf-8', 'ignore')
    except Exception as e:
        raise RagError('docx 解析失败，请确认文件为有效的 Word 文档') from e
    xml = re.sub(r'</w:p>', '\n', xml)      # 段落之间补换行
    xml = re.sub(r'<w:tab[^>]*/>', ' ', xml)  # 制表符转空格
    return html.unescape(re.sub(r'<[^>]+>', '', xml))


def extract_text(filename, raw):
    """按扩展名把上传文件解析为纯文本。"""
    ext = os.path.splitext(filename or '')[1].lower()
    if ext in TEXT_EXTS:
        return _decode(raw)
    if ext == '.pdf':
        return _extract_pdf(raw)
    if ext == '.docx':
        return _extract_docx(raw)
    raise RagError(f'暂不支持 {ext or "该"} 格式，请上传 txt / md / pdf / docx')


# ================= 递归分块 =================
def _normalize(text):
    """统一换行、压缩多余空行与空白，降低分块碎片率。"""
    text = (text or '').replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'[ \t\u3000]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _split_recursive(text, size, seps):
    """按分隔符优先级递归切分：段落优先，仍超长则降级到句读，最后硬切。"""
    if len(text) <= size:
        return [text] if text.strip() else []
    if not seps:
        return [text[i:i + size] for i in range(0, len(text), size)]

    sep = seps[0]
    parts = text.split(sep)
    if len(parts) == 1:
        return _split_recursive(text, size, seps[1:])

    # 把分隔符还原到每段末尾，保证不丢字符
    pieces = [p + sep for p in parts[:-1]] + [parts[-1]]
    out = []
    buf = ''
    for p in pieces:
        if len(p) > size:
            if buf.strip():
                out.append(buf)
                buf = ''
            out.extend(_split_recursive(p, size, seps[1:]))
            continue
        if len(buf) + len(p) <= size:
            buf += p
        else:
            if buf.strip():
                out.append(buf)
            buf = p
    if buf.strip():
        out.append(buf)
    return out


def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """把长文切成带重叠的块：递归切分 → 合并过短碎片 → 加相邻重叠。"""
    text = _normalize(text)
    if not text:
        return []

    merged = []
    for c in _split_recursive(text, size, SEPARATORS):
        c = c.strip()
        if not c:
            continue
        # 过短的块与上一块合并，避免出现只有几个字的碎片
        if merged and len(merged[-1]) < size * 0.6 and len(merged[-1]) + len(c) <= size:
            merged[-1] += c
        else:
            merged.append(c)

    if overlap <= 0:
        return merged

    out = []
    for i, c in enumerate(merged):
        out.append(c if i == 0 else merged[i - 1][-overlap:] + c)
    return out


# ================= 向量化 =================
def _embed(texts):
    """调用向量化服务批量编码，返回与输入等长的向量列表（按 index 还原顺序）。"""
    if not EMBED_API_KEY:
        raise RagError('未配置向量化模型 API Key，请在 llm_config.py 中填写 EMBED_API_KEY'
                       '（本地 Ollama 无需真实 Key，填任意非空值即可）')

    vectors = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i:i + EMBED_BATCH]
        try:
            resp = requests.post(
                f'{EMBED_BASE_URL}/embeddings',
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {EMBED_API_KEY}',
                },
                json={'model': EMBED_MODEL, 'input': batch, 'encoding_format': 'float'},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json().get('data') or []
        except requests.RequestException as e:
            raise RagError(f'向量化服务调用失败：{e}') from e
        except ValueError as e:
            raise RagError('向量化服务返回内容无法解析') from e

        data.sort(key=lambda d: d.get('index', 0))
        vectors.extend(d.get('embedding') or [] for d in data)

    if len(vectors) != len(texts) or any(not v for v in vectors):
        raise RagError('向量化结果与文本数量不一致，请稍后重试')
    return vectors


# ================= 向量库 =================
_client = None


def _collection():
    """懒加载 Chroma 本地持久化集合（向量由本模块提供，不使用默认嵌入函数）。"""
    global _client
    if chromadb is None:
        raise RagError('未安装 chromadb，请先执行 pip install -r requirements.txt')
    if _client is None:
        os.makedirs(STORE_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(path=STORE_DIR)
    return _client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=None,
        metadata={'hnsw:space': 'cosine', 'model': EMBED_MODEL},
    )


def add_document(filename, text, replace=True):
    """分块 + 向量化后写入向量库，返回文档信息。同名文档默认覆盖。"""
    chunks = chunk_text(text)
    if not chunks:
        raise RagError('文档内容为空，无法建立索引')

    col = _collection()
    if replace:
        for d in list_docs():
            if d['name'] == filename:
                col.delete(where={'doc_id': d['id']})

    doc_id = f'{int(time.time())}-{uuid.uuid4().hex[:8]}'
    created = time.strftime('%Y-%m-%d %H:%M')
    col.add(
        ids=[f'{doc_id}::{i}' for i in range(len(chunks))],
        documents=chunks,
        embeddings=_embed(chunks),
        metadatas=[{
            'doc_id': doc_id,
            'doc_name': filename,
            'chunk_index': i,
            'chars': len(c),
            'created_at': created,
        } for i, c in enumerate(chunks)],
    )
    return {'id': doc_id, 'name': filename, 'chunks': len(chunks),
            'chars': sum(len(c) for c in chunks), 'createdAt': created}


def list_docs():
    """按文档聚合分块元数据，返回文档列表（新上传的在前）。"""
    col = _collection()
    got = col.get(include=['metadatas'])
    agg = {}
    for m in got.get('metadatas') or []:
        d = agg.setdefault(m['doc_id'], {
            'id': m['doc_id'], 'name': m['doc_name'],
            'chunks': 0, 'chars': 0, 'createdAt': m.get('created_at', ''),
        })
        d['chunks'] += 1
        d['chars'] += int(m.get('chars') or 0)
    return sorted(agg.values(), key=lambda d: d['createdAt'], reverse=True)


def delete_document(doc_id):
    """删除一篇文档的全部分块。"""
    col = _collection()
    if not col.get(where={'doc_id': doc_id}, include=[])['ids']:
        return False
    col.delete(where={'doc_id': doc_id})
    return True


def all_chunks():
    """返回知识库全部文本分块及其元数据，供模块化 RAG 的 BM25 / 重排序等模块建索引。"""
    col = _collection()
    res = col.get(include=['documents', 'metadatas'])
    docs = res.get('documents') or []
    metas = res.get('metadatas') or []
    return list(zip(docs, metas))


def retrieve(query, top_k=TOP_K, min_score=MIN_SCORE):
    """把问题向量化后与知识库比对，返回相似度达标的片段（高到低）。"""
    query = (query or '').strip()
    if not query:
        return []
    col = _collection()
    total = col.count()
    if not total:
        return []

    res = col.query(
        query_embeddings=_embed([query]),
        n_results=min(top_k, total),
        include=['documents', 'metadatas', 'distances'],
    )
    hits = []
    for text, meta, dist in zip(res['documents'][0], res['metadatas'][0], res['distances'][0]):
        # 余弦空间下 distance = 1 - 相似度
        score = 1.0 - float(dist)
        if score < min_score:
            continue
        hits.append({
            'text': text,
            'docId': meta.get('doc_id'),
            'docName': meta.get('doc_name'),
            'chunkIndex': meta.get('chunk_index'),
            'score': score,
        })
    return hits


def stats():
    """知识库概况，供后台展示。"""
    try:
        col = _collection()
        chunks = col.count()
    except RagError:
        chunks = 0
    docs = list_docs() if chunks else []
    return {
        'docs': len(docs),
        'chunks': chunks,
        'model': EMBED_MODEL,
        'dim': EMBED_DIM,
        'chunkSize': CHUNK_SIZE,
        'chunkOverlap': CHUNK_OVERLAP,
        'topK': TOP_K,
        'minScore': MIN_SCORE,
        'storeDir': STORE_DIR,
        'ready': bool(EMBED_API_KEY),
    }
