# QuantAI 智能量化投资系统

一个前后端分离的量化投资平台，内置行情引擎、策略回测、AI 智能体与账户资产管理，适合量化入门学习、策略研究与教学演示。所有行情与账户数据均为服务端模拟生成，无需接入真实券商接口即可运行。

## 功能特性

- **模拟行情引擎**：24 只 A 股 + 5 大指数，实时随机游走推送秒级行情
- **策略回测**：内置双均线、MACD、布林带、RSI、动量突破 5 种策略模板，参数可调
- **回测指标**：总收益、年化收益、最大回撤、夏普比率、CVaR、胜率、盈亏比等
- **AI 智能体**：智能荐股、根据自然语言描述生成量化策略
- **账户管理**：模拟盘 + 实盘账户、自动交易绑定、资产曲线
- **持仓资产**：实时估值、盈亏、仓位占比、当日盈亏
- **财经资讯**：分类新闻、关键词检索、情绪标签
- **投资偏好**：风险等级、持仓周期、行业板块、止损止盈设置

## 技术栈

| 端 | 技术 |
| --- | --- |
| 前端 | Vue 3 · Vite · Vue Router · ECharts |
| 后端 | Python · FastAPI · Uvicorn |

## 目录结构

```
myProject/
├── quant-invest-server-py/   # Python 后端（FastAPI）
│   ├── main.py               # 路由、鉴权、策略回测、智能体接口
│   ├── data.py               # 行情/新闻/账户/持仓数据引擎
│   ├── utils.py              # 伪随机、交易日序列等工具
│   └── requirements.txt      # 后端依赖
├── quant-invest-vue/         # 前端（Vue 3 + Vite）
│   ├── src/                  # 页面、组件、API 层、状态管理
│   ├── index.html
│   └── package.json
├── 一键启动量化系统.bat      # 一键启动前后端（Windows）
└── 停止量化系统.bat          # 停止前后端服务
```

## 快速开始

### 环境要求

- Python 3.8+
- Node.js 16+

### 1. 启动后端（端口 3000）

```bash
cd quant-invest-server-py
pip install -r requirements.txt
python main.py
```

### 2. 启动前端（端口 5189）

```bash
cd quant-invest-vue
npm install
npm run dev
```

### 3. 访问

浏览器打开 http://localhost:5189

> Windows 下也可直接双击 `一键启动量化系统.bat` 自动完成上述两步并打开浏览器；双击 `停止量化系统.bat` 可关闭服务。

## 页面导航

- 登录 / 注册
- 市场行情：个股与指数快照、K 线、Sparkline 迷你走势
- 量化策略：策略模板选择、参数调节、回测结果与净值曲线
- 资产持仓：账户汇总、持仓明细、仓位权重
- 账户管理：账户列表、新增账户、绑定策略、自动交易开关
- 财经资讯：分类浏览与关键词搜索
- AI 智能体：智能荐股、策略生成
- 投资偏好：风险偏好与持仓约束配置

## API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/login` | 登录 |
| POST | `/api/auth/register` | 注册 |
| GET | `/api/market/snapshot` | 行情快照 |
| GET | `/api/market/kline/{code}` | 单标的历史 K 线 |
| GET | `/api/news` | 新闻列表（支持分类/关键字） |
| GET | `/api/news/categories` | 新闻分类 |
| GET/POST | `/api/prefs` | 获取 / 保存投资偏好 |
| POST | `/api/agent/recommend` | 智能荐股 |
| POST | `/api/agent/generate-strategy` | 生成策略 |
| GET | `/api/strategy` | 策略模板列表 |
| GET | `/api/strategy/frameworks` | 回测框架列表 |
| POST | `/api/strategy/backtest` | 执行回测 |
| GET/POST | `/api/accounts` | 账户列表 / 新增账户 |
| PUT | `/api/accounts/{id}` | 更新账户 |
| GET | `/api/positions` | 持仓与资产汇总 |

## 说明

- 本项目所有数据（行情、新闻、账户、持仓）均为**本地模拟生成**，仅供学习演示，不构成任何投资建议。
- 后端默认监听 `127.0.0.1:3000`，前端通过环境变量 `VITE_API_BASE` 可覆盖其 API 地址（默认 `http://localhost:3000/api`）。