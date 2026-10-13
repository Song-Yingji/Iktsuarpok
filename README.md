# Iktsuarpok 智能量化投资系统

一个前后端分离的量化投资平台，内置真实行情引擎、策略回测、AI 智能体与账户资产管理，适合量化入门学习、策略研究与教学演示。行情与新闻接入真实免费源（历史 K 线用 Baostock 前复权、实时快照用 easyquotation、财经快讯用财联社电报），量化策略由大模型根据自然语言描述生成。

## 功能特性

- **真实行情引擎**：24 只 A 股 + 4 大指数，实时秒级推送；历史 K 线（前复权）与实时快照分别来自 Baostock / easyquotation，二者严格分离
- **AI 策略生成（Quant Buffett）**：用自然语言描述投资想法，大模型一次性返回对话内容与结构化策略，可一键保存到「我的量化策略」；内置 RAG 检索增强，回答前先召回本地知识库片段
- **AI 智能荐股（Recommend Buffett）**：从已保存的偏好中选一套，按关注板块筛选标的，输出评分、置信度与理由，可一键加入自选股
- **向量知识库（RAG）**：独立后台管理页上传文档，经递归分块与本地 Ollama `qwen3-embedding` 向量化后写入本地 Chroma；策略生成时走模块化检索管线（查询改写 → 多路检索 → RRF 融合 → 重排序 → 上下文压缩）召回 Top-K 片段拼入提示词；可开启本地大模型 Self-RAG 分析（判定是否检索、内容是否有用）
- **知识库管理后台**：左侧功能导航（用户管理 / 上传文档 / 检索测试）+ 右侧面板，支持文档上传 / 列表 / 删除、知识库统计与检索测试
- **后台模块设置**：可插拔模块化 RAG 检索管线——按需开启 / 关闭「查询改写 / 多路融合 / 重排序 / 上下文压缩 / 本地大模型分析（Self-RAG）」各模块，并调整融合方式、改写方式、召回条数与相似度下限，保存后策略生成即时生效
- **效果测评（LlamaIndex）**：后台一键测评当前 RAG 配置，评测集由 LlamaIndex `RagDatasetGenerator` 从知识库自动合成（问题 + 标准答案 + 来源片段，按指纹缓存复用），输出上下文精确率 / 上下文召回率 / 忠实度 / 答案相关性 / 答案正确率五项指标与逐题明细；并以蛛网图 + 柱状图对比「优化前基线 / 行业标准 / 一键测评」三组分数
- **后台用户管理**：查看全部用户（含管理员），新增 / 编辑 / 删除账号；权限变更（是否管理员）与删除管理员账号仅超级管理员可操作，普通管理员只能删除普通用户，且变更即时生效（每次请求回库复核）
- **策略回测**：内置双均线、MACD、布林带、RSI、动量突破 5 种回测引擎，选择标的 / 区间 / 框架即可回测
- **回测指标**：总收益、年化收益、最大回撤、夏普比率、CVaR、胜率、盈亏比等
- **账户管理**：模拟盘 / 实盘账户独立管理；登录凭证与账户本体分离、Fernet 加密存储，连接器层按账户类型路由（模拟盘固定 100 万、实盘经平台适配器拉取），连接测试成功后自动读取账户资金回填
- **量化交易**：交易任务卡片管理——每张卡片配置标的 / 策略 / 账户（Chip 标签展示、三列对齐，标的超 3 个可点开查看全部）；点「修改」弹窗编辑、保存后生效，三要素齐备才能开启自动交易
- **财经资讯**：财联社 7×24 小时快讯，分类浏览、关键词检索、情绪标签
- **投资偏好**：可保存多套偏好并自定义名称、设为默认，供荐股使用；列表式管理，新增 / 编辑通过弹窗完成
- **交易提醒**：独立开关，存于 `user_settings`，在量化交易页调整

## 技术栈

| 端 | 技术 |
| --- | --- |
| 前端 | Vue 3 · Vite · Vue Router · ECharts |
| 后端 | Python · FastAPI · Uvicorn · PyMySQL |
| 数据库 | MySQL 5.7+ |
| 大模型 | OpenAI 兼容 API（目前是本地 Ollama `qwen3:0.6b` 可切换任意兼容模型）|
| 向量知识库 | Chroma（本地持久化）· 本地 Ollama `qwen3-embedding:0.6b` 向量化（1024 维） |
| 效果测评 | LlamaIndex（评测集合成 + Retriever / Faithfulness / Relevancy / Correctness 评估器） |

## 目录结构

```
Iktsuarpok/
├── quant-invest-server-py/       # Python 后端（FastAPI）
│   ├── main.py                   # 路由、鉴权、指标计算、回测、智能体、后台管理接口
│   ├── data.py                   # 行情 / 新闻数据引擎与静态配置
│   ├── db.py                     # MySQL 数据访问层
│   ├── auth.py                   # PBKDF2 密码哈希与 HMAC 签名 token（用户 / 管理员双 scope）
│   ├── admin_config.py           # 超级管理员账号（仅首次启动播种，全局唯一、不可删除）
│   ├── credentials.py            # 账户登录凭证 Fernet 加密存取（account_credentials 表）
│   ├── connectors.py             # 账户连接器层：按账户类型路由，连接测试与资金读取（模拟盘 / 通用 HTTP）
│   ├── rag.py                    # 本地向量知识库：文本抽取 → 递归分块 → 向量化 → Chroma
│   ├── modular_rag.py            # 模块化 RAG：查询改写 → 多路检索（向量 + BM25）→ RRF 融合 → 重排序 → 上下文压缩
│   ├── rag_eval.py               # LlamaIndex 效果测评：评测集合成（缓存）+ 五项指标评估
│   ├── llm.py                    # 大模型接入层（非流式调用 + 系统提示词）
│   ├── llm_config.py             # 大模型 / 向量化模型 API 配置（已 gitignore，需自行创建）
│   ├── db_config.py              # 数据库连接配置（已 gitignore，需自行创建）
│   ├── kb_store/                 # Chroma 向量库本地持久化目录（运行时自动生成，已 gitignore）
│   ├── utils.py                  # 确定性伪随机工具
│   └── requirements.txt          # 后端依赖
├── quant-invest-vue/             # 前端（Vue 3 + Vite）
│   ├── src/
│   │   ├── api/index.js          # 统一请求封装 + 用户 / 管理员双 token
│   │   ├── components/           # Layout、智能体组件、通用 ui 组件、admin 后台面板（用户 / 文档 / 检索 / 模块设置 / 效果测评）
│   │   ├── lib/                  # constants.js 静态选项、utils.js 格式化
│   │   ├── pages/                # 各业务页面（含 Admin.vue / AdminLogin.vue 后台）
│   │   ├── router/index.js       # 路由与登录守卫（前台 / 后台两套独立登录态）
│   │   ├── store/                # app.js 全局状态、agent.js 智能体状态
│   │   └── styles/global.css
│   ├── index.html
│   └── package.json
├── .venv/                        # Python 虚拟环境（后端依赖安装于此，已 gitignore）
├── database_schema.sql           # 数据库建库建表脚本
├── 一键启动量化系统.bat          # 一键启动前后端（Windows）
└── 停止量化系统.bat              # 停止前后端服务
```

## 快速开始

### 环境要求

- Python 3.10+（推荐 3.10 / 3.11；3.13 部分依赖可能尚无预编译 wheel）
- Node.js 18+
- MySQL 5.7+
- Ollama（可选，用于本地对话模型与向量化模型；不装也可改配任意 OpenAI 兼容的云端服务）

### 1. 创建虚拟环境并安装后端依赖

后端依赖统一装在项目根目录的 `.venv/` 中，与系统全局 Python 隔离（该目录已加入 `.gitignore`）。

```bash
# 在项目根目录执行
python -m venv .venv          # 创建虚拟环境

# Windows 激活
.venv\Scripts\activate
# macOS / Linux 激活
source .venv/bin/activate

# 激活后安装依赖（激活成功时命令行提示符前会出现 (.venv)）
pip install --upgrade pip
pip install -r quant-invest-server-py/requirements.txt
```

> 也可以不激活，直接用虚拟环境内的解释器绝对路径执行：`.venv\Scripts\python.exe`（Windows）或 `.venv/bin/python`（macOS / Linux）。
> 创建时若 `python` 指向了 IDE 自带的解释器，请改用完整路径，例如 `D:\python\python.exe -m venv .venv`。

### 2. 初始化数据库

在项目根目录执行建库建表脚本（默认库名 `xb_quant`）：

```bash
mysql -u root -p --default-character-set=utf8mb4 < database_schema.sql
```

然后在 `quant-invest-server-py/db_config.py` 中填写连接信息（默认 `127.0.0.1:3306`，用户 `root`）。

### 3. 配置大模型与向量化模型

在 `quant-invest-server-py/llm_config.py` 中填写配置。对话模型与向量化模型相互独立：

```python
# -*- coding: utf-8 -*-
# ====== 对话模型（策略生成 / 智能荐股） ======
# 默认使用本地 Ollama 的 qwen3:0.6b，无需联网、无需申请 token。
# Ollama 不校验 API Key，API_KEY 填任意非空值即可（留空会回退为 'ollama'）。
API_BASE_URL = 'https://your-endpoint/v1'
API_KEY = 'ollama'
MODEL_NAME = 'qwen3:0.6b'

# ====== 向量化模型（RAG 知识库专用） ======
# 默认使用本地 Ollama 的 qwen3-embedding:0.6b（输出 1024 维向量），无需联网、无需申请 token。
# Ollama 不校验 API Key，EMBED_API_KEY 填任意非空值即可（留空会回退为 'ollama'）。
EMBED_BASE_URL = 'http://localhost:11434/v1'
EMBED_API_KEY = 'ollama'
EMBED_MODEL = 'qwen3-embedding:0.6b'
```

> 可切换为任意 OpenAI 兼容服务（含本地 Ollama，`API_BASE_URL` 填 `http://localhost:11434/v1` 即可）。模型越小对长系统提示词的指令遵循越弱，建议使用 7B 以上模型以保证策略 JSON 的格式正确率。
> 向量化模型同理，任何兼容 `/embeddings` 接口的服务都可替换 `EMBED_BASE_URL` / `EMBED_MODEL`，例如阿里云百炼的 `text-embedding-v3`（同样 1024 维）；换模型后建议清空 `kb_store/` 重新建立索引，避免不同模型的向量混用。

#### 本地向量模型准备（Ollama）

```bash
ollama pull qwen3-embedding:0.6b   # 约 0.6GB，输出 1024 维向量
ollama list                        # 确认模型已就绪
```

> 验证接口可用：`curl http://localhost:11434/v1/embeddings -d '{"model":"qwen3-embedding:0.6b","input":"测试"}'`，返回 1024 个浮点数即正常。
> 该项目也支持批量的 `/v1/embeddings`（`input` 传数组），后台一次请求编码 10 个分块。

### 4. 启动后端（端口 3000）

```bash
cd quant-invest-server-py
python main.py
```

> 依赖已在第 1 步装进 `.venv`，此处无需再执行 `pip install`。若未激活虚拟环境，请用绝对路径启动：`..\.venv\Scripts\python.exe main.py`。
> 不要使用系统全局的 `python`：若 PATH 中存在 IDE 自带的解释器，它通常没有安装 fastapi，会直接报 `ModuleNotFoundError`。

### 5. 启动前端（端口 5189）

```bash
cd quant-invest-vue
npm install
npm run dev
```

### 6. 访问

浏览器打开 http://localhost:5189

> Windows 下也可直接双击 `一键启动量化系统.bat` 自动完成上述步骤并打开浏览器；双击 `停止量化系统.bat` 可关闭服务。

## 虚拟环境管理

后端使用项目根目录的 `.venv/`，由 Python 标准库 `venv` 创建，不需要额外安装 virtualenv。

| 操作 | Windows | macOS / Linux |
| --- | --- | --- |
| 激活 | `.venv\Scripts\activate` | `source .venv/bin/activate` |
| 退出 | `deactivate` | `deactivate` |
| 不激活直接运行 | `.venv\Scripts\python.exe main.py` | `.venv/bin/python main.py` |

常用维护命令（激活后执行）：

```bash
pip list                        # 查看当前环境已安装的包
pip install -r quant-invest-server-py/requirements.txt   # 按清单补装 / 更新依赖
pip install <包名>              # 新增依赖，记得同步写入 requirements.txt
```

删除重建（环境损坏，或需要更换 Python 版本时）：

```bash
# Windows
rmdir /s /q .venv
python -m venv .venv

# macOS / Linux
rm -rf .venv
python3 -m venv .venv
```

> `.venv/` 已加入 `.gitignore`，不会提交到版本库；换机器后重新执行「快速开始」第 1 步即可，无需拷贝环境目录。
> 切换 Python 大版本（如 3.10 → 3.12）后必须删除 `.venv` 重建，否则 `chromadb` 等含二进制扩展的包会因 ABI 不匹配而导入失败。
> `一键启动量化系统.bat` 会优先使用 `.venv\Scripts\python.exe`，未检测到虚拟环境时回退到系统 `python` 并给出提示。

## 页面导航

- 登录 / 注册
- 市场行情：个股与指数快照、K 线、Sparkline 迷你走势，个股可一键加自选
- 自选股：关注的个股实时行情与移除
- 财经资讯：分类浏览与关键词搜索
- AI 智能体：智能荐股（Recommend Buffett）、策略生成（Quant Buffett）
- 量化策略：已保存的智能体策略列表、删除、选择回测标的 / 区间 / 框架并查看回测结果
- 账户管理：账户列表、新增 / 编辑 / 解绑账户，登录凭证加密存储，连接测试成功后自动读取资金
- 量化交易：交易任务卡片（标的 / 策略 / 账户标签化展示、三列对齐）、「修改」弹窗编辑、自动交易开关（标的 + 策略 + 账户齐备才可开启）、交易提醒开关
- 投资偏好：多套偏好的列表管理，新增 / 编辑通过弹窗完成，可设为默认供荐股使用
- 后台管理（`/admin/login`）：左侧功能导航 + 右侧面板，分为用户管理、向量知识库、检索测试、模块设置、效果测评五块；管理员登录后可管理账号与后台权限、上传 / 删除文档、查看知识库统计、做检索测试，可插拔模块化 RAG 管线的各模块与检索参数，并一键运行 LlamaIndex 效果测评

> 后台管理入口与前台的登录态完全独立（各自保存 token）。后台账号即 `users` 表中的普通用户，勾选「后台管理权限」后即可登录后台；超级管理员由后端首次启动时按 `admin_config.py` 播种（默认 `admin / 123456`），全局唯一且不可删除、不可取消管理员身份。

## 系统流程

> 以下流程图使用 Mermaid 语法编写，可在 GitHub、Typora、VS Code（安装 Mermaid 插件）等支持 Mermaid 的 Markdown 查看器中直接渲染。

### 1. 系统整体架构

```mermaid
graph TB
    subgraph FE["前端 Vue 3 + Vite"]
        PAGES[pages 页面]
        COMP[components 组件<br/>Layout / StrategyAgent / RecommendAgent / ui]
        APIJS[api/index.js 统一请求]
        STORE[store/app.js 全局状态<br/>store/agent.js 智能体状态]
    end

    subgraph BE["后端 FastAPI (main.py)"]
        AUTH[auth.py 密码哈希 + 签名 token<br/>用户 / 管理员双 scope]
        ADMIN[admin_config.py 管理员固定账号]
        LLM[llm.py 大模型接入层]
        RAG[rag.py 向量知识库<br/>分块 / 向量化 / 检索]
        MODRAG[modular_rag.py 模块化检索管线<br/>改写 / 多路检索 / RRF 融合 / 重排 / 压缩]
        DATA[data.py 行情 / 新闻引擎]
        DB[db.py MySQL 数据访问]
        UTIL[utils.py 确定性伪随机]
    end

    subgraph SRC["外部数据源"]
        BS[Baostock<br/>历史日 K 前复权]
        EQ[easyquotation<br/>实时快照 新浪源]
        CLS[财联社电报<br/>7×24 快讯]
        LLMS[大模型<br/>OpenAI 兼容 API]
        EMB[本地 Ollama qwen3-embedding<br/>1024 维向量化]
    end

    MYSQL[(MySQL xb_quant)]
    CHROMA[(Chroma 本地向量库<br/>kb_store/)]

    PAGES --> COMP
    PAGES --> APIJS
    COMP --> STORE
    STORE --> APIJS
    APIJS -->|HTTP /api| BE
    LLM --> LLMS
    RAG --> EMB
    RAG --> CHROMA
    MODRAG --> RAG
    MODRAG --> CHROMA
    DATA --> BS
    DATA --> EQ
    DATA --> CLS
    DB --> MYSQL
```

### 2. 登录鉴权流程

```mermaid
flowchart TD
    A[打开应用] --> B{localStorage 有 token 且有效?}
    B -- 否 --> C[登录 / 注册页]
    C --> D[POST /api/auth/login 或 register]
    D --> E[PBKDF2 校验密码]
    E --> F{密码正确?}
    F -- 否 --> G[返回失败提示]
    G --> C
    F -- 是 --> H[签发 HMAC 签名 token]
    H --> I[前端存 token 到 localStorage]
    I --> J[请求自动带 Authorization 头]
    J --> K[后端 get_current_user 校验]
    K --> L{token 有效?}
    L -- 否 --> M[返回 401<br/>前端清登录态跳回登录]
    M --> B
    L -- 是 --> N[按 user_id 隔离读写数据库]
```

### 3. 行情与新闻数据流

```mermaid
flowchart LR
    A[前端：行情页 / 自选股页 / 资讯页] --> B[GET /api/market/snapshot]
    A --> C[GET /api/news]
    B --> D[data.py 数据引擎]
    C --> D
    D --> E[历史 K 线<br/>Baostock 前复权<br/>缓存 _history_cache.json]
    D --> F[实时快照<br/>easyquotation 新浪源<br/>每 2 秒刷新]
    D --> G[财联社快讯<br/>内存缓存 60 秒后台刷新]
    E --> H[拼装 JSON 快照]
    F --> H
    G --> I[分类 / 情绪标签]
    H --> A
    I --> A
```

> 历史 K 线只保留到最近一个已收盘交易日，今日行情交给实时源，二者严格分离，避免盘中实时价污染回测口径。

### 4. AI 智能体：智能荐股流程（Recommend Buffett）

```mermaid
flowchart TD
    A[AI 智能体页 · 智能荐股] --> B[下拉选择偏好集<br/>默认选中「默认偏好」]
    B --> C[POST /api/agent/recommend<br/>body: prefsId]
    C --> D[后端按 prefsId 取偏好<br/>按关注板块构造候选池<br/>推导均线 / 涨幅 / 波动率等真实因子]
    D --> E[调用大模型]
    E --> F[一次性返回分析说明<br/>text]
    F --> G[一次性返回荐股列表<br/>recommend · 后端回填真实行情]
    G --> H[展示荐股列表<br/>评分 / 置信度 / 理由]
    H --> I{加入自选?}
    I -- 是 --> J[POST /api/watchlist 入库]
    J --> K[自选股页展示<br/>按钮变为「已加入自选」]
    I -- 否 --> Z[结束]
```

> 候选池之外的代码（模型幻觉）在解析阶段即被丢弃；名称、板块、价格、涨跌幅均由后端按 code 回填真实行情。
> `prefsId` 缺省或该偏好已被删除时，后端回落到默认偏好；用户一套偏好都没有时使用内置默认值（全市场候选池）。

### 4.1 投资偏好：多套偏好管理

```mermaid
flowchart TD
    A[偏好页] --> B[GET /api/prefs<br/>列表：按创建顺序返回]
    B --> C{操作}
    C -- 添加偏好 --> D[弹出偏好表单<br/>名称 + 风险 / 期限 / 板块 / 风控]
    D --> E{点击保存?}
    E -- 是 --> F[POST /api/prefs 落库]
    E -- 否 / 关闭弹窗 --> G[丢弃，不落库]
    C -- 编辑 --> H[PUT /api/prefs/id]
    C -- 设为默认 --> I[POST /api/prefs/id/default<br/>同用户只保留一个默认]
    C -- 删除 --> J[DELETE /api/prefs/id<br/>若删的是默认则自动提一套为默认]
    F --> B
    H --> B
    I --> B
    J --> B
```

> 偏好名称在同一用户下唯一；用户保存的第一套偏好自动成为默认偏好。
> 交易提醒开关与偏好无关，单独存在 `user_settings`，不参与荐股提示词，可在量化交易页调整。

### 5. AI 智能体：策略生成流程（Quant Buffett）

```mermaid
sequenceDiagram
    autonumber
    participant U as 用户
    participant V as StrategyAgent.vue
    participant S as store/agent.js
    participant A as api/index.js
    participant M as main.py
    participant R as modular_rag.py 模块化管线
    participant L as llm.py + 大模型

    U->>V: 输入消息并发送
    V->>S: send(text)
    S->>S: 追加用户消息 + 空的 bot 占位消息
    S->>S: buildHistory 过滤欢迎语 / 空消息<br/>策略消息转为摘要文本
    S->>A: chatStream(history, handlers)
    A->>M: POST /api/agent/generate-strategy
    M->>R: 模块化管线检索<br/>改写 / 多路检索 / RRF 融合 / 重排
    R-->>M: 命中片段（含相似度）
    M->>M: 片段与原始问题拼成新的用户消息
    M->>L: chat(拼接后的 messages) 非流式请求
    L-->>M: 完整回答文本
    M->>M: 按标记切分说明文本与策略 JSON 并解析
    M-->>A: 返回 JSON（rag + text + strategy）
    A-->>S: onRag / onText / onStrategy 回调
    S->>V: 一次性渲染检索图标、说明文本与策略卡片
    A-->>S: onDone
    S->>V: typing = false
    U->>V: 点击「保存到我的量化策略」
    V->>S: saveStrategy(msg)
    S->>M: POST /api/strategy/saved
    S->>V: 提示已保存
```

> 知识库为空、未配置向量模型或检索失败时，后端响应中 `rag.count` 为 0 且直接跳过检索，策略生成照常进行，RAG 不可用不影响主流程。

#### 5.1 后端标记切分与解析

模型可能在一次回复里混合「闲聊文字」与「策略 JSON」，后端用 `===STRATEGY_JSON===` / `===END_STRATEGY===` 两个标记把两者切开：标记之外的部分作为说明文本返回，标记之内的 JSON 解析为结构化策略对象；未命中标记或解析失败时整段文本作为说明文本返回、策略字段为 `null`。

```mermaid
flowchart LR
    A[完整回答文本] --> B{存在开始与结束标记?}
    B -- 否 --> F[整段作为说明文本<br/>strategy 为 null]
    B -- 是 --> C[提取标记内 JSON 并解析]
    C --> D{解析成功?}
    D -- 否 --> F
    D -- 是 --> E[返回 说明文本 + 策略对象]
```

解析策略时先按标准 JSON 解析（`strict=False`，容忍字符串内真实换行），失败再按字段正则兜底提取，保证小模型输出的畸形 JSON 也能落成可保存的策略。

#### 5.2 智能体状态生命周期

聊天记录、荐股结果提升到模块级 store，路由切换不丢失：

```mermaid
flowchart LR
    A[进入智能体页] --> B[onMounted 拉取偏好 / 自选 / 滚动到底部]
    B --> C[对话中：store 持有消息数组]
    C --> D[切换到其他页面<br/>组件卸载，store 数据保留]
    D --> E[返回智能体页<br/>直接恢复聊天与结果]
    C --> F[刷新浏览器<br/>内存态清空，回到欢迎语]
    C --> G[退出登录<br/>resetAgentState 清空]
```

### 6. 向量知识库构建与 RAG 检索

#### 6.1 后台构建知识库（管理员）

```mermaid
flowchart TD
    A[后台登录页 /admin/login] --> B[POST /api/admin/login<br/>查 users 表校验密码，且 role ≥ 1]
    B --> C[签发独立的管理员 token<br/>scope=admin 且携带用户 id，存 admin_token]
    C --> D[管理后台 /admin<br/>左侧功能导航 + 右侧面板]
    D --> U[用户管理<br/>列表 / 新增 / 编辑 / 删除 / 设置管理员]
    U --> U1[每次请求回库复核<br/>账号被删或取消权限即失效]
    D --> E[上传文档<br/>txt / md / csv / log / pdf / docx，≤10MB]
    E --> F[文本抽取<br/>txt 自动识别 utf-8/gbk，pdf 用 pypdfium2，docx 解析 document.xml]
    F --> G[递归分块<br/>段落 → 换行 → 中英文句读 → 空白<br/>目标 500 字 / 重叠 80 字]
    G --> H[本地 Ollama qwen3-embedding 向量化<br/>每批 10 条，1024 维]
    H --> I[写入本地 Chroma<br/>kb_store/ 持久化]
    I --> J[文档列表 / 统计刷新<br/>同名文档覆盖旧索引]
    D --> K[检索测试<br/>POST /api/admin/search]
    K --> H
```

> 文档切块采用递归分块策略：优先按段落切，仍超长则依次降级到换行、中英文句读（`。！？；，、` 等）、空白，全部降级完仍超长才按字符硬切；过短的碎片会与相邻块合并，并给每块加上相邻 80 字重叠，避免语义被切断。

#### 6.2 策略生成时的 RAG 检索

```mermaid
flowchart LR
    A[用户提问] --> B[查询改写<br/>规则式多查询生成，可选]
    B --> C[多路检索<br/>向量 + BM25]
    C --> D[RRF 融合<br/>倒数排序融合]
    D --> E[重排序<br/>分词 + 词语重叠 + 短语匹配]
    E --> F[上下文压缩<br/>保留最相关句子，可选]
    F --> G[召回 Top-K 片段<br/>默认 4 条]
    G --> H[命中片段拼成「参考资料」<br/>与原始问题组成新的用户消息]
    H --> I[新提示词 + 系统提示词<br/>一起交给大模型]
    I --> J[一次性返回回答与结构化策略]
```

> 检索由 `modular_rag.py` 的模块化管线完成：向量检索复用 Chroma（qwen3-embedding 余弦相似度），BM25 关键词检索基于 jieba + rank_bm25 对全库分块建索引，二者经 RRF 融合后做重排序与（可选的）上下文压缩。各模块由配置开关编排，知识库为空或检索失败时静默跳过、响应中 `rag.count` 为 0，策略生成照常进行。开启「本地大模型分析（Self-RAG）」后，检索前后会各调用一次本地大模型（非流式 `llm.chat`）做判定：判定无需检索时直接返回 0 条、判定检索内容无用时不注入，从而过滤与问题无关的知识库噪声。检索到的片段以「## 参考资料（来自本地知识库，请优先依据以下内容回答）」的形式前置在用户问题之前，原问题保留在「## 我的问题」段落下，二者与代码里的系统提示词一起送入大模型。命中时会在该条回答的气泡外右下角出现一个检索图标（底部与气泡齐平），点击后浮层在图标右侧单行展开「已检索本地知识库，命中 N 条参考片段」，点击空白处或发起新操作会自动收起，未命中则不显示图标。

#### 6.3 效果测评（LlamaIndex）

进入后台「效果测评」后，先用 LlamaIndex `RagDatasetGenerator` 从知识库均匀采样分块合成评测集（问题 + 标准答案 + 来源片段），按知识库指纹缓存到 `rag_eval_dataset.json`，分块集合变化后自动重建；随后每题跑一遍完整模块化管线（检索 + 生成），把检索片段与生成回答交给 LlamaIndex 评估器打分，汇总为五项指标：上下文精确率（RetrieverEvaluator precision）、上下文召回率（recall）、忠实度（FaithfulnessEvaluator）、答案相关性（RelevancyEvaluator）、答案正确率（CorrectnessEvaluator，官方 1-5 分归一到 0-1）。每题独立容错，单题失败不影响其余题目。

### 7. 量化策略回测与量化交易任务

```mermaid
flowchart TD
    A[量化策略页] --> B[GET /api/strategy/saved<br/>列出已保存的智能体策略]
    B --> C{操作}
    C -- 删除 --> D[DELETE /api/strategy/saved/id<br/>交易任务里的失效引用自动置空]
    C -- 回测 --> E[选择回测标的 / 区间 / 框架]
    E --> F[POST /api/strategy/backtest]
    F --> G[展示指标与净值曲线<br/>总收益 / 年化 / 最大回撤 / 夏普 / CVaR / 胜率]
    H[量化交易页] --> I[GET /api/quant-tasks<br/>交易任务卡片：标的 / 策略 / 账户]
    I --> J{操作}
    J -- 新增任务 --> K[POST /api/quant-tasks]
    J -- 修改 --> L[弹窗编辑标的 / 策略 / 账户<br/>点击保存才落库 PUT /api/quant-tasks/id<br/>进入编辑时自动关闭自动交易]
    J -- 自动交易 --> M{三要素齐备?}
    M -- 是 --> N[PUT /api/quant-tasks/id 开启]
    M -- 否 --> O[开关禁用 / 提示先补全配置]
    J -- 删除 --> P[DELETE /api/quant-tasks/id]
```

> 策略的新增入口只在智能体页（生成后点「保存到我的量化策略」），量化策略页仅支持删除与回测。
>
> 删除已保存的策略或账户时，交易任务里的对应引用会被置空（`_scrub_task_refs` 把 `strategy_id` / `account_id` 置 NULL）；自动交易开关按「标的 + 策略 + 账户三者齐备」校验，引用缺失即无法开启，避免出现「自动交易开着却没有策略 / 账户」的状态；智能体页历史消息上的「已保存」标记也会在再次进入该页时自动失效，可重新保存。
>
> 账户资金不由用户手填：创建时为 0，连接测试成功后由连接器层自动读取回填（模拟盘固定 1,000,000，实盘经平台适配器拉取）。账户的登录凭证（登录账号 / 密码）与账户本体分离存入 `account_credentials`，密码经 Fernet 加密，接口响应只回显登录账号与 `hasPassword` 标记，永不返回密码。

## API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/login` | 登录 |
| POST | `/api/auth/register` | 注册 |
| GET | `/api/market/snapshot` | 行情快照（含全部标的与历史 K 线） |
| GET | `/api/news` | 新闻列表（财联社实时快讯，支持分类 / 关键字） |
| GET | `/api/news/categories` | 新闻分类 |
| GET | `/api/prefs` | 偏好列表（多套，按创建顺序返回） |
| POST | `/api/prefs` | 新增一套偏好（首套自动设为默认） |
| PUT | `/api/prefs/{id}` | 编辑偏好 |
| POST | `/api/prefs/{id}/default` | 设为荐股默认偏好 |
| DELETE | `/api/prefs/{id}` | 删除偏好（删默认时自动补选一套） |
| GET/POST | `/api/settings` | 交易提醒开关（与偏好无关，不参与荐股提示词） |
| POST | `/api/agent/recommend` | 智能荐股（非流式，body 传 `prefsId`） |
| POST | `/api/agent/generate-strategy` | 策略生成智能体（非流式） |
| GET | `/api/strategy/frameworks` | 回测框架列表 |
| POST | `/api/strategy/backtest` | 执行回测 |
| GET/POST | `/api/strategy/saved` | 已保存策略列表 / 保存策略 |
| DELETE | `/api/strategy/saved/{id}` | 删除已保存策略 |
| GET/POST | `/api/watchlist` | 自选股列表 / 加入自选 |
| DELETE | `/api/watchlist/{code}` | 移除自选 |
| GET/POST | `/api/accounts` | 账户列表 / 新增账户（可带登录凭证，密码加密存储，响应不含密码） |
| PUT | `/api/accounts/{id}` | 更新账户（密码留空表示不修改） |
| POST | `/api/accounts/{id}/test-connection` | 连接测试，成功后自动读取资金并回填 |
| DELETE | `/api/accounts/{id}` | 解绑账户（连带清理交易任务里的失效引用） |
| GET/POST | `/api/quant-tasks` | 交易任务列表 / 新增任务 |
| PUT | `/api/quant-tasks/{id}` | 更新任务（标的 / 策略 / 账户 / 自动交易开关） |
| DELETE | `/api/quant-tasks/{id}` | 删除任务 |
| POST | `/api/admin/login` | 后台管理员登录（查 `users` 表校验，要求 `role` ≥ 1） |
| GET | `/api/admin/users` | 用户列表（含管理员，超级管理员置顶） |
| POST | `/api/admin/users` | 新增用户（`role` 可给 0 普通用户 / 1 管理员；授予权限仅限超级管理员） |
| PUT | `/api/admin/users/{id}` | 编辑用户（用户名 / 手机号 / 密码 / 权限等级；权限变更仅限超级管理员） |
| DELETE | `/api/admin/users/{id}` | 删除用户（连带其偏好 / 策略 / 账户 / 自选股；普通管理员只能删普通用户） |
| GET | `/api/admin/kb/stats` | 知识库统计（文档数 / 分块数 / 向量模型 / 存储位置） |
| GET | `/api/admin/docs` | 已入库文档列表 |
| POST | `/api/admin/docs` | 上传文档（multipart，≤10MB）并建立索引 |
| DELETE | `/api/admin/docs/{id}` | 删除文档及其全部分块 |
| POST | `/api/admin/search` | 检索测试（问题向量化后做相似度比对） |
| GET | `/api/admin/rag-config` | 读取模块化 RAG 配置（模块开关 / 融合与改写方式 / 召回参数） |
| PUT | `/api/admin/rag-config` | 保存模块化 RAG 配置，保存后策略生成检索即时生效 |
| GET | `/api/admin/rag-eval/dataset` | 评测集缓存状态（是否存在 / 题目数 / 裁判模型） |
| POST | `/api/admin/rag-eval` | 效果测评（body：`numQuestions` 1–20 默认 10、`regenerate` 是否重建评测集） |
| GET | `/api/health` | 健康检查 |

> 后台接口统一要求 `Authorization: Bearer <admin_token>`，由 `get_current_admin` 校验；管理员 token 的 scope 为 `admin` 且携带用户 id，与普通用户 token 互不通用，越权访问返回 401。
>
> 用户权限由 `users.role` 单字段表示：`0` 普通用户 / `1` 管理员 / `2` 超级管理员。**权限变更（授予 / 取消管理员）与删除管理员账号仅超级管理员可操作**：普通管理员调用用户管理接口时若携带 `role` 字段会被拒绝（403），删除 `role ≥ 1` 的账号也会被拒绝（403）；前端不会提交 `role` 字段，且权限开关、管理员行的删除按钮呈禁用态。删除用户与设置权限均受保护：超级管理员（`role=2`，全局唯一）不可删除、不可取消管理员身份，且不可通过接口授予；当前登录账号不可删除自己。删除用户时其偏好、策略、账户、自选股由外键 `ON DELETE CASCADE` 一并清理。

### 策略生成接口的响应格式

`POST /api/agent/generate-strategy` 请求体为 `{ messages: [{role, content}, ...] }`，响应为 JSON：

```json
{
  "rag": { "count": 2, "sources": [{ "docName": "...", "score": 0.812 }] },
  "text": "说明文本",
  "strategy": { "name": "...", "engineId": "...", "params": {}, "rules": [], "code": "..." }
}
```

后端先对最新一条用户提问做知识库检索，命中时把片段拼进该条消息，并把命中条数放回 `rag`；前端只据此在气泡外右下角显示一个检索图标（点击可查看命中条数）。知识库为空或不可用时 `rag.count` 为 0，不做任何注入，也不显示图标。

后端用 `===STRATEGY_JSON===` / `===END_STRATEGY===` 标记切分说明文本与策略 JSON；策略块不会以原始文本返回，解析成功才填充 `strategy`，否则 `strategy` 为 `null`、整段文本落入 `text`。解析采用「标准 JSON（`strict=False`，容忍字符串内换行）→ 字段正则兜底」两级策略，兼容小模型输出的畸形 JSON。

### 智能荐股接口的响应格式

`POST /api/agent/recommend` 请求体为 `{ prefsId }` —— 指定使用哪一套已保存偏好；`prefsId` 缺省、或该偏好已被删除时，后端回落到默认偏好，用户一套偏好都没有时使用内置默认值。响应为 JSON：

```json
{
  "text": "分析说明",
  "recommend": [{ "code": "...", "name": "...", "price": "...", "change": "...", "score": "...", "confidence": "...", "action": "...", "reasons": ["..."] }]
}
```

与策略接口不同，荐股流程在调用模型前先用真实行情快照构造候选池（按偏好板块筛选，无匹配时退化为全市场）并推导技术因子（均线、区间位置、涨幅、年化波动率等），把因子表交给模型分析。模型只输出主观字段（`score` / `confidence` / `action` / `reasons`），名称、板块、价格、涨跌幅一律由后端按 `code` 回填真实行情，候选池之外的代码视为幻觉直接丢弃，因此模型无法编造价格或池外标的。JSON 用 `===RECOMMEND_JSON===` / `===END_RECOMMEND===` 包裹，解析失败时整块降级为普通文本落入 `text`。

> 偏好只在服务端按 `prefsId` 读取并校验归属（`user_id` 隔离），前端无法通过伪造请求体越权使用他人偏好。

## 依赖清单

### 后端（Python · requirements.txt）

> 以下依赖安装到项目根目录的 `.venv/` 虚拟环境中，不使用系统全局 Python。

| 包 | 版本 | 用途 |
| --- | --- | --- |
| fastapi | >=0.100 | Web 框架，提供 REST API |
| uvicorn | >=0.23 | ASGI 服务器，运行 FastAPI |
| easyquotation | >=0.7.7 | 实时行情（新浪源） |
| baostock | >=0.8.8 | 历史行情（前复权日 K） |
| requests | >=2.25 | HTTP 请求（财联社新闻、大模型非流式调用、向量化接口） |
| pymysql | >=1.1 | MySQL 数据库驱动 |
| chromadb | >=0.4.24 | 本地向量知识库（持久化 + 余弦相似度检索） |
| pypdfium2 | >=4.0 | PDF 文本抽取 |
| python-multipart | >=0.0.6 | FastAPI 解析 multipart 上传 |
| numpy | >=1.24 | 数值计算（模块化 RAG 检索打分 / 排序） |
| jieba | >=0.42 | 中文分词（BM25 关键词检索与重排序） |
| rank_bm25 | >=0.2.2 | BM25 关键词检索（多路检索的稀疏路） |
| llama-index-core | >=0.13,<0.14 | 效果测评（LlamaIndex 评估器 + `RagDatasetGenerator` 评测集合成） |

### 前端（npm · package.json）

| 包 | 版本 | 用途 |
| --- | --- | --- |
| vue | ^3.4.38 | 前端框架 |
| vue-router | ^4.4.3 | 前端路由 |
| echarts | ^5.5.1 | 图表（K 线、净值曲线等） |
| vite | ^5.4.8 | 构建工具 / 开发服务器（devDependency） |
| @vitejs/plugin-vue | ^5.1.3 | Vue 单文件组件编译（devDependency） |

## 说明

- 行情（历史 K 线、实时快照）与财经新闻（财联社快讯）接入真实免费源，数据源失效时前端展示「系统繁忙，请稍后重试」等提示；账户、偏好、自选股、已保存策略、量化交易任务等用户数据持久化存储于 MySQL，按 `user_id` 隔离。
- 首次启动会联网拉取历史行情并缓存到本地 `_history_cache.json`，之后启动直接读缓存，无需重新联网。
- 智能体对话记录保存在前端内存 store 中：切换页面不会丢失，刷新浏览器会重置，退出登录自动清空。
- 向量知识库数据保存在后端 `quant-invest-server-py/kb_store/`（Chroma 本地持久化目录），重启服务不丢失，已加入 `.gitignore`；删除该目录即清空知识库，需重新上传文档建立索引。
- 模块化 RAG 的插拔配置由后台「模块设置」保存到 `quant-invest-server-py/rag_config.json`（运行时自动生成，已加入 `.gitignore`）；删除该文件即恢复为代码里的默认配置。
- 效果测评的评测集缓存于 `quant-invest-server-py/rag_eval_dataset.json`（运行时自动生成，已加入 `.gitignore`）；知识库分块集合变化后自动重新合成，删除该文件即强制重建。测评过程需多次调用大模型（合成题目 + 裁判打分），耗时随题目数增长。
- 向量化默认走本地 Ollama（`qwen3-embedding:0.6b`），上传文档与检索时需保证 Ollama 在 `localhost:11434` 运行；Ollama 未启动时后台会提示「向量化服务调用失败」，知识库不可用但策略生成等其它功能不受影响。换用其它向量模型后必须清空 `kb_store/` 重建索引，不同模型的向量不可混用。
- 后台账号复用 `users` 表，权限由单字段 `role` 表示（`0` 普通用户 / `1` 管理员 / `2` 超级管理员）：`role ≥ 1` 即可登录后台，可在「用户管理」中开关授予（仅超级管理员可操作）。超级管理员（`role=2`）全局唯一，由后端首次启动时按 `admin_config.py` 播种（默认 `admin / 123456`），不可删除、不可取消管理员身份。后台登录态与前台的 `quant_token` 完全独立。
- 后台用户管理接口每次请求都会回库复核管理员身份，账号被删除或被取消权限后，其已签发的 token 立即失效（返回 401 并跳回登录页）。
- `db_config.py`（数据库密码）与 `llm_config.py`（大模型 / 向量化模型 API Key）含敏感信息，已加入 `.gitignore`，请勿提交到版本库。
- 后端默认监听 `127.0.0.1:3000`，前端通过环境变量 `VITE_API_BASE` 可覆盖其 API 地址（默认 `http://localhost:3000/api`）。
- 后端依赖统一安装在项目根目录的 `.venv/` 虚拟环境（已 gitignore），与系统全局 Python 隔离；`一键启动量化系统.bat` 优先使用 `.venv\Scripts\python.exe`，未检测到虚拟环境时回退到系统 `python` 并给出提示。
- 本平台仅供学习演示，不构成任何投资建议，股市有风险，投资需谨慎！
