<div align="center">
  <h1>AIStock Pro</h1>
  <p><strong>AI 驱动的个人量化投资操作系统</strong></p>
  <p>A 股 + 港股 · 投研 Pipeline · 量化引擎 · 数据中心 · 持仓管理</p>
  <p>
    <img src="https://img.shields.io/badge/version-5.16-gold" alt="V5.16">
    <img src="https://img.shields.io/badge/Python-3.8%2B-blue" alt="Python">
    <img src="https://img.shields.io/badge/FastAPI-Async-green" alt="FastAPI">
    <img src="https://img.shields.io/badge/LLM-DeepSeek-purple" alt="DeepSeek">
    <img src="https://img.shields.io/badge/license-MIT-red" alt="MIT">
  </p>
</div>

---

## 📋 项目简介

**AIStock Pro** 是一套 AI 驱动的量化分析与投资研究系统，面向 A 股 + 港股市场。
系统采用 DDD 领域驱动 + 多智能体（MAS）架构，将 AI 的分析能力、系统的量化计算能力、
人的决策判断力，以模块化方式组织成一套可进化的投资操作系统。

核心特色：将 **Serenity 供应链瓶颈投资法** 系统化为 AI 可自动运行的 Pipeline，
从宏观周期到个股筛选全链路自动化。

---

## ✨ 核心功能

### 🧠 AI 投研 Pipeline（12 步分析链路）

| 步骤 | 模块 | 能力 |
|------|------|------|
| Step 1a | 宏观周期分析 | MAG7 CapEx 扫描 + LLM 景气判定 |
| Step 1b | 资本流向扫描 | 谁在花钱？花在哪？约束在哪？|
| Step 2 | 行业看门人 | 6-Block 定性筛选 + 三路径分叉 |
| **Step 3 ★** | **产业链拆解** | **L1-L4 瓶颈图谱 + 利润池 + 竞争格局 + 资产发现** |
| Step 4 | 系统动力学 | 供给/需求/政策三维推演 |
| Step 5 | 跨产业关联 | 溢出效应 + 传导路径 |
| **Step 6 ★** | **核心资产筛选** | **四阶段筛选：搜索→LLM→比较→验证→排名** |
| Step 7-8 | 财务审计/人力审计/估值 | 可选步骤，21 种估值方法 |

Pipeline 三路径分叉：
- **[A] 直挖** — 从产业节点直接挖标的，跳过深挖
- **[B] 二阶推演** — 外推相邻产业预期差
- **[C] 深挖** — 标准全链路（Step 3→4→5→6）

### 📊 量化决策中心

| 能力 | 数量 | 详情 |
|------|------|------|
| 技术指标算子 | 16 | MA/MACD/KDJ/RSI/ATR/CCI/Bollinger/OBV/VWAP/筹码(COST, numba加速)/拥挤度 |
| 财务指标 | 27 | ROIC/剪刀差/Beneish M-Score/合同负债...季度滚动 |
| 估值方法 | 21 | 绝对4 + 相对6 + 先进4 + 动态6 + 复合1 |
| 量化策略 | 8 | 6传统(代码) + 2AI链(YAML热编辑) |
| 决策方式 | 加权投票 | 传统 1.0 / AI 链 1.2, BUY > SELL × 1.5 阈值 |

### 🌐 数据中心

- 多源行情同步（Akshare → Sina 双源降级，增量感知）
- 宏观指标追踪（黄金/原油/汇率/美债/美元指数）
- 估值同步（PE/PB/市值/换手率）
- 源探活（5 分钟间隔检测数据源在线状态）
- 6 Tab 架构：宏观 / 自选股 / 行情体检 / 基本面 / 财务报告 / 另类数据

### 📋 智能持仓管理

- AI 截图导入（豆包 → DeepSeek → Gemini 链式 OCR）
- Excel 导入 / 自由文本解析
- 每日快照 + 损益计算
- 交易审计历史

### 👁️ 投研观察监控

- Pipeline 输出自动提取观察点
- watch_events 催化剂追踪
- Monitor 定时巡检
- 机会/风险 front-end badge 预警

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    前端 (12+ HTML 页面)                      │
│  index | positions | research | quant | data               │
│  indicators | financial | observations | valuation          │
│  health-check | import | settings                           │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTP
┌──────────┬──────────┬──────────┬──────────┬──────────────┐
│ Research │  Quant   │  Market  │Portfolio │ Observation  │
│ Step 1~12│ 16算子   │   Data   │ CRUD     │ 提取+监控     │
│ 8 Agents │ 8策略    │ 行情同步  │ 快照+损益 │ 催化剂追踪   │
│ Pipeline │ 21估值   │ 宏观+估值 │ AI导入    │              │
│ 3分叉     │ 27财务   │ 源探活    │ 交易审计   │              │
└─────┬────┴───┬──────┴───┬──────┴───┬──────┴──────────────┘
      │        │          │          │
      └────────┴──────────┴──────────┘
                          │
┌─────────────────────────────────────────────────────────────┐
│               Framework (基础设施层)                          │
│  AI Providers(DeepSeek/Doubao/Gemini) | TaskEngine V5.1    │
│  Pipeline Infra(Checkpoint/Trace/Glossary)                  │
│  DB Session(异步) | Config | Logger | Stage Classifier      │
└─────────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────────────┐
│  Data Layer (MySQL + SQLite + JSON)                          │
│  MySQL: market_data / positions / stock_info / financial_.. │
│  SQLite: indicators.db(52列) / financial_indicators(50列)   │
│  JSON: research_reports/ / pipeline_checkpoints/            │
└─────────────────────────────────────────────────────────────┘
```

### 架构约束

- **DDD 分层**: `domain/* → framework/* → models/`，domain 间禁止互相 import
- **装饰器注册**: 指标/策略/估值/Agent 均通过装饰器自动发现
- **SQLite 宽表**: 每字段一列，`pd.read_sql()` 直接读 DataFrame
- **纯函数指标**: 所有算子纯函数，无 I/O，无状态，向量化计算

---

## 🛠️ 技术栈

| 层 | 技术 |
|----|------|
| 后端框架 | Python 3.8+ / FastAPI / Uvicorn |
| ORM | SQLAlchemy 2.0 Async + aiomysql |
| 量化计算 | Pandas / NumPy / numba(筹码加速) |
| AI 提供者 | DeepSeek (主模型, Anthropic兼容) / 豆包(OCR) / Gemini Vision(OCR备份) |
| Web 搜索 | Brave Search (主) / Tavily (备) |
| 金融数据 | Tushare Pro (财务/基本面) |
| 前端 | 原生 HTML/CSS/JS + ECharts 5.5 + Font Awesome 6 |
| 任务调度 | 自研 TaskEngine V5.1 (信号量+去重) |
| 数据存储 | MySQL + SQLite 宽表 + JSON 文件 |
| 加速 | numba.jit (COST 指数衰减模型, 45天半衰期) |

---

## 🚀 快速开始

```bash
# 1. 克隆项目
git clone https://github.com/yourname/aistock-pro.git
cd aistock-pro

# 2. 配置环境
# 复制 .env.example 为 .env，填入 API Key（实际 .env 被 .gitignore 排除，不会误提交）
cp backend/.env.example backend/.env
# 编辑 backend/.env 填入你的密钥

# 3. conda 环境 (或 pip install -r requirements.txt)
conda activate aiteacher

# 4. 启动
cd backend
python main.py
# → http://127.0.0.1:8000

# 5. 配置数据源
# 系统会自动检测数据库状态，初次启动自动建表
# 在数据中心页面点击"全量同步"拉取行情数据
```

### 环境要求

| 依赖 | 用途 | 必填 | 注册地址 |
|------|------|------|---------|
| Python 3.8+ | 运行环境 | ✅ | — |
| MySQL 5.7+ | 事务数据存储 | ✅ | — |
| **DeepSeek API Key** | AI 投研核心 (主模型) | ✅ | [platform.deepseek.com](https://platform.deepseek.com/) |
| **Brave Search API Key** | Web 搜索 (2000次/月免费) | ✅ | [api.search.brave.com](https://api.search.brave.com/) |
| 豆包/Doubao API Key | OCR 图像识别（持仓截图导入） | ⚠️ 可选 | [console.volcengine.com](https://console.volcengine.com/) |
| Gemini Vision API Key | OCR 图像识别备份 | ⚠️ 可选 | [aistudio.google.com](https://aistudio.google.com/) |
| Tavily API Key | Web 搜索备份 (1000次/月免费) | ⚠️ 可选 | [tavily.com](https://tavily.com/) |
| Tushare Token | 金融财务数据源 | ⚠️ 可选 | [tushare.pro](https://tushare.pro/) |

> 🔒 **安全说明**：`backend/.env` 已在 `.gitignore` 中排除，你的 API Key 不会误提交到 Git。
> 配置模板见 `backend/.env.example`，不含真实密钥。

---

## 🗺️ 路线图

| 阶段 | 内容 | 状态 |
|------|------|------|
| **Phase 1** | Data Center Tab 补齐 · 估值引擎接入 · 前端拆分 · TempLab | 🏗️ 进行中 |
| **Phase 2** | AgentRegistry · 消费/公司级 Agent · 观测监控自动化 · 智能复盘 · 量化策略扩展 | 📋 |
| **Phase 3** | 策略定时运行 · 超级交易员 V1 (模拟环境) · 另类数据搜索工具 | 📋 |
| **Phase 4** | 实盘接口 · 高频行情 · Chat Bot · Step 9-11 | 📋 |

完整路线图详见 [docs/RoadMap/系统蓝图与分阶段路线图.md](docs/RoadMap/系统蓝图与分阶段路线图.md)。

---

## 📚 文档索引

| 文档 | 路径 |
|------|------|
| 项目架构与快速参考 | `CLAUDE.md` |
| DDD 分层边界规则 | `.claude/rules/ddd-boundaries.md` |
| 量化指标设计标准 | `.claude/rules/quant-indicator-standards.md` |
| 量化模块开发范式 | `.claude/rules/quant-module.md` |
| 财务指标设计标准 | `.claude/rules/financial-indicator-standards.md` |
| 前端开发规范 | `.claude/rules/frontend-pattern.md` |
| 导入与代码规范 | `.claude/rules/import-convention.md` |
| 日志输出规范 | `.claude/rules/logging-standards.md` |
| 数据模型变更规则 | `.claude/rules/model-change.md` |
| 开发质量门禁 | `.claude/rules/quality-gates.md` |
| 全系统功能清单 (210项) | `docs/03_API_Specifications/System_Feature_Inventory.md` |
| 系统路线图 | `docs/RoadMap/系统蓝图与分阶段路线图.md` |
| 投研系统设计 (15文档) | `docs/02_Architecture/AI_Research_System/` |

---

## 📂 目录结构速览

```
backend/
├── app/
│   ├── main.py                    # FastAPI 入口 + 路由注册
│   ├── api/                       # 通用路由 (data/tasks/positions/import)
│   ├── domain/
│   │   ├── research/              # AI 投研 Pipeline (8 Agents)
│   │   │   ├── agents/            #   各 Agent 实现
│   │   │   ├── services/          #   数据加载/报告存储
│   │   │   └── api/               #   投研 API 路由
│   │   ├── quant/                 # 量化中心
│   │   │   ├── indicators/        #   16 技术指标 + 27 财务指标
│   │   │   ├── strategies/        #   8 策略
│   │   │   ├── decision/          #   决策中心
│   │   │   ├── valuation/         #   21 估值方法
│   │   │   ├── engine/            #   计算引擎 + SQLite 存储
│   │   │   └── api/               #   量化 API 路由
│   │   ├── market_data/           # 数据中心
│   │   ├── portfolio/             # 持仓管理
│   │   └── observation/           # 投研观察监控
│   ├── framework/                 # 基础设施
│   │   ├── ai/providers/          #   DeepSeek/Doubao/Gemini
│   │   ├── tasks/                 #   TaskEngine V5.1
│   │   ├── pipeline/              #   Checkpoint/Trace/Glossary
│   │   └── finance/               #   Valuation/ModelMap/StageClassifier
│   └── models/                    # 数据模型 (11 表)
├── frontend/                      # 前端静态文件 (12+ 页面)
│   ├── research.html / quant.html / data.html / ...
│   └── js/                        # JavaScript 模块
└── data/                          # 数据文件
    ├── indicators.db              # SQLite 指标库 (52列宽表)
    └── research_reports/          # 研报 JSON 输出
```

---

## 📊 数据流

```
行情同步 (定时) → MarketData (MySQL)
       │
       ├──→ IndicatorRunner → indicators.db (SQLite 宽表, 52列)
       ├──→ 估值同步 → stock_info (PE/PB/市值)
       ├──→ 量化策略 → 决策中心 → StrategySignal
       └──→ 持仓快照 → portfolio_snapshots

投研 Pipeline (手动触发)
       │
       Step 1a → 1b → 2 → [A/B/C] → 3 → 4 → 5 → 6 → (7/8)
       │                                            │
       └──→ research_reports/ (JSON)               └──→ observations.db
```

---

## 🤝 贡献

个人项目，欢迎 Issue 和 PR。

---

## 📄 License

MIT License

---

<div align="center">
  <p>AIStock Pro &mdash; V5.16</p>
  <p>以 Serenity 瓶颈投资法为核心方法的 AI 量化投资操作系统</p>
</div>
