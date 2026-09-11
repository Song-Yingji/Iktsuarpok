# QuantAI 智能量化投资系统

一个前后端分离的量化投资平台，内置行情引擎、策略回测、AI 智能体与账户资产管理，适合量化入门学习、策略研究与教学演示。行情与新闻接入真实免费源（历史 K 线用 Baostock 前复权、实时快照用 easyquotation、财经快讯用财联社电报）。

## 功能特性

- **真实行情引擎**：24 只 A 股 + 4 大指数，实时秒级推送；历史 K 线（前复权）与实时快照分别来自 Baostock / easyquotation
- **策略回测**：内置双均线、MACD、布林带、RSI、动量突破 5 种策略模板
- **回测指标**：总收益、年化收益、最大回撤、夏普比率、CVaR、胜率、盈亏比等
- **AI 智能体**：智能荐股、根据自然语言描述生成量化策略
- **账户管理**：模拟盘 + 实盘账户、自动交易绑定
- **财经资讯**：财联社 7×24 小时财经快讯，分类新闻、关键词检索、情绪标签
- **投资偏好**：风险等级、持仓周期、行业板块、止损止盈设置

## 技术栈

| 端 | 技术 |
| --- | --- |
| 前端 | Vue 3 · Vite · Vue Router · ECharts |
| 后端 | Python · FastAPI · Uvicorn · PyMySQL |
| 数据库 | MySQL 5.7+ |

## 目录结构

```
myProject/
├── quant-invest-server-py/   # Python 后端（FastAPI）
│   ├── main.py               # 路由、鉴权、策略回测、智能体接口
│   ├── data.py               # 行情/新闻数据引擎
│   ├── db.py                 # MySQL 数据访问层
│   ├── auth.py               # 密码哈希与签名 token
│   ├── db_config.py          # 数据库连接配置（已 gitignore，勿提交）
│   ├── utils.py              # 伪随机、交易日序列等工具
│   └── requirements.txt      # 后端依赖
├── quant-invest-vue/         # 前端（Vue 3 + Vite）
│   ├── src/                  # 页面、组件、API 层、状态管理
│   ├── index.html
│   └── package.json
├── database_schema.sql       # 数据库建库建表脚本
├── 一键启动量化系统.bat      # 一键启动前后端（Windows）
└── 停止量化系统.bat          # 停止前后端服务
```

## 快速开始

### 环境要求

- Python 3.8+
- Node.js 18+
- MySQL 5.7+

### 1. 初始化数据库

在项目根目录执行建库建表脚本（默认库名 `xb_quant`）：

```bash
mysql -u root -p --default-character-set=utf8mb4 < database_schema.sql
```

用户名、密码、库名等连接信息集中配置在 `quant-invest-server-py/db_config.py`，可按需修改。

### 2. 启动后端（端口 3000）

```bash
cd quant-invest-server-py
pip install -r requirements.txt
python main.py
```

### 3. 启动前端（端口 5189）

```bash
cd quant-invest-vue
npm install
npm run dev
```

### 4. 访问

浏览器打开 http://localhost:5189

> Windows 下也可直接双击 `一键启动量化系统.bat` 自动完成上述步骤并打开浏览器；双击 `停止量化系统.bat` 可关闭服务。

## 页面导航

- 登录 / 注册
- 市场行情：个股与指数快照、K 线、Sparkline 迷你走势
- 自选股：关注的个股实时行情与移除
- 财经资讯：分类浏览与关键词搜索
- AI 智能体：智能荐股、策略生成
- 量化策略：已保存的智能体策略、回测标的/区间/框架选择与回测结果
- 账户管理：账户列表、新增/解绑账户、绑定策略、自动交易开关
- 投资偏好：风险偏好与持仓约束配置

## API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/login` | 登录 |
| POST | `/api/auth/register` | 注册 |
| GET | `/api/market/snapshot` | 行情快照 |
| GET | `/api/market/kline/{code}` | 单标的历史 K 线 |
| GET | `/api/news` | 新闻列表（财联社实时快讯，支持分类/关键字） |
| GET | `/api/news/categories` | 新闻分类 |
| GET/POST | `/api/prefs` | 获取 / 保存投资偏好 |
| POST | `/api/agent/recommend` | 智能荐股 |
| POST | `/api/agent/generate-strategy` | 生成策略 |
| GET | `/api/strategy` | 策略模板列表 |
| GET | `/api/strategy/frameworks` | 回测框架列表 |
| POST | `/api/strategy/backtest` | 执行回测 |
| GET/POST | `/api/strategy/saved` | 已保存策略列表 / 保存策略 |
| DELETE | `/api/strategy/saved/{id}` | 删除已保存策略 |
| GET/POST | `/api/watchlist` | 自选股列表 / 加入自选 |
| DELETE | `/api/watchlist/{code}` | 移除自选 |
| GET/POST | `/api/accounts` | 账户列表 / 新增账户 |
| PUT | `/api/accounts/{id}` | 更新账户 |
| DELETE | `/api/accounts/{id}` | 解绑账户 |

## 依赖清单

### 后端（Python · requirements.txt）

| 包 | 版本 | 用途 |
| --- | --- | --- |
| fastapi | >=0.100 | Web 框架，提供 REST API |
| uvicorn | >=0.23 | ASGI 服务器，运行 FastAPI |
| easyquotation | >=0.7.7 | 实时行情（新浪源） |
| baostock | >=0.8.8 | 历史行情（前复权日 K） |
| requests | >=2.25 | HTTP 请求（财联社新闻等） |
| pymysql | >=1.1 | MySQL 数据库驱动 |

### 前端（npm · package.json）

| 包 | 版本 | 用途 |
| --- | --- | --- |
| vue | ^3.4.38 | 前端框架 |
| vue-router | ^4.4.3 | 前端路由 |
| echarts | ^5.5.1 | 图表（K 线、净值曲线等） |
| vite | ^5.4.8 | 构建工具 / 开发服务器（devDependency） |
| @vitejs/plugin-vue | ^5.1.3 | Vue 单文件组件编译（devDependency） |

## 说明

- 行情（历史 K 线、实时快照）与财经新闻（财联社快讯）接入真实免费源，数据源失效时前端展示「系统繁忙，请稍后重试」等提示；账户、偏好、自选股、已保存策略等用户数据持久化存储于 MySQL，本平台仅供学习演示，不构成任何投资建议。
- 首次启动会联网拉取历史行情并缓存到本地 `_history_cache.json`，之后启动直接读缓存，无需重新联网；该缓存与 `db_config.py`、`__pycache__`、`node_modules` 等均已加入 `.gitignore`，不会误提交到版本库。
- 后端默认监听 `127.0.0.1:3000`，前端通过环境变量 `VITE_API_BASE` 可覆盖其 API 地址（默认 `http://localhost:3000/api`）。
- 股市有风险，投资需谨慎！