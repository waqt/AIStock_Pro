# AIStock Pro — AI 量化分析与投研系统

## 项目身份

AIStock Pro 是一套 AI 驱动的量化分析与投资研究系统，面向 A 股 + 港股。系统采用 DDD 领域驱动 + 多智能体（MAS）架构，由 Python 3.10+ 异步引擎驱动。

- **架构风格**: DDD + MAS 多智能体 + 图结构 (DAG) 编排
- **版本**: V4.0
- **数据库名**: `aistock_pro`（MySQL）
- **conda 环境**: `aiteacher` (`D:\develop_env\python_related\anaconda\Anaconda3\envs\aiteacher`)
- **启动**: 双击 `run_backend.bat` → `http://127.0.0.1:8000`

## 技术栈

| 层 | 技术 |
|---|------|
| Web 框架 | FastAPI + Uvicorn (--reload 热加载) |
| 序列化/配置 | Pydantic V2 + pydantic-settings |
| ORM | SQLAlchemy 2.0 异步 (aiomysql) |
| 量化计算 | Pandas + NumPy |
| 前端 | 原生 HTML/CSS/JS + ECharts 5.5 + Font Awesome 6 |
| AI 提供者 | DeepSeek (Anthropic兼容, 主) / 豆包 Seed / Gemini Vision |
| 任务调度 | TaskEngine (自研) + APScheduler |
| 数据源 | httpx → 新浪/东方财富/腾讯; akshare (财报+港股) |
| Web 搜索 | Brave Search (主) → DDG (兜底), 通过 Clash 代理 127.0.0.1:7890 |
| 网页抓取 | WebScraper (异步抓取+正文抽取) |

## 目录结构 (核心变更)

```
backend/app/
├── framework/                     # 基础设施
│   ├── ai/providers/              # DeepSeek(主)/Doubao/Gemini
│   ├── tasks/                     # TaskEngine + APScheduler
│   └── ...
├── domain/
│   ├── market_data/               # 行情同步 + 健康检查 + 估值同步 + 宏观数据
│   │   ├── sources/               # Sina/AkShare/Tencent/Push2
│   │   ├── services/              # valuation.py (PE/PB/市值), stock_list.py
│   │   └── api/                   # (路由在 app/api/data.py)
│   ├── research/                  # ★ AI 投研 V4.0 DAG管道 + V3.0遗留
│   │   ├── agents/
│   │   │   ├── base.py            #   ResearchAgent + parse_json()
│   │   │   ├── market_scanner.py  #   每日市场扫描 (Web实时数据)
│   │   │   ├── global_capex_scanner.py # MAG7 CapEx 前瞻扫描
│   │   │   ├── supply_chain_hacker.py  # L1-L4 供应链降维穿透
│   │   │   ├── financial_auditor.py    # 8Q 剪刀差 + Beneish M-Score
│   │   │   ├── human_capital_detective.py # 创始人/CTO/专利审计
│   │   │   ├── valuation_pricer.py     # PEG/PS 护城河时间窗定价
│   │   │   ├── dag_orchestrator.py     # DAG 并行编排器
│   │   │   └── coordinator.py          # V3.0 遗留编排器
│   │   ├── services/
│   │   │   ├── data_loader.py     #   数据加载 + Web搜索 + 8Q财报
│   │   │   └── report_store.py    #   研报 JSON 文件持久化
│   │   └── api/routes.py          #   /api/research/*
│   └── quant/                     # ★ 量化模块 V1.0
│       ├── indicators/            #   16个算子 (每文件一算子, 装饰器自注册)
│       │   ├── trend/             #   MA, MACD, KDJ
│       │   ├── momentum/          #   RSI, ATR, CCI
│       │   ├── volatility/        #   Bollinger, Bollinger Width
│       │   ├── volume/            #   OBV, VolumeMA, VWAP
│       │   ├── chip/              #   筹码分布 (concentration/peak/pattern)
│       │   └── crowding/          #   拥挤度 (turnover_ratio/sharpe_60d)
│       ├── strategies/            #   8个策略 (每文件一策略)
│       │   ├── traditional/       #   6个传统 (MACD/RSI/Boll/MA/KDJ/Divergence)
│       │   └── ai_chain/          #   2个AI链 (YAML定义, 热编辑, LLM驱动)
│       ├── decision/              #   决策中心 (加权投票, 透明可追溯)
│       ├── engine/
│       │   ├── engine.py          #   QuantEngine (数据同步)
│       │   └── indicator_runner.py # 指标计算引擎 (快照/历史/增量)
│       └── api/                   #   /api/quant/*
├── api/                           # 过渡期路由 (data.py/positions.py)
└── models/                        # 数据模型 (10张表)
    └── models.py                  # Position, MarketData, StockIndicator,
                                   #   StockInfo, StrategySignal, ExchangeRate,
                                   #   TaskDefinition, TaskExecution, TradeHistory, SystemSetting
├── index.html                     # 指挥中心
├── positions.html                 # 持仓管理
├── research.html                  # AI 投研 (V4.0 DAG报告渲染)
├── quant.html                     # ★ 量化决策 (三标签: 算子/策略/决策)
├── data.html                      # 数据中心 (手动同步+指标计算)
├── import.html                    # 智能导入
└── ...
```

## V4.0 投研 MAS 架构

### Agent 矩阵

```
V4.0 DAG 管道 (6个):
  MarketScanner (侦察) → 独立运行, 发现赛道
  GlobalCapexScanner ──┐
                        ├──→ [FinancialAuditor || HumanCapitalDetective] ──→ ValuationPricer ──→ Report
  SupplyChainHacker ───┘        (并行交叉验证)                         (综合定价)        (CIO报告)

V3.0 遗留 (3个, 向后兼容):
  SupplyChainAnalyst, IndustryAnalyst, ResearchCoordinator
```

| Agent | 职责 | API |
|-------|------|-----|
| MarketScanner | Web实时扫描 → 热门赛道 + 每日简报 | POST /research/scan |
| GlobalCapexScanner | MAG7 CapEx → 全球景气方向 | POST /research/capex-scan |
| SupplyChainHacker | L1-L4 供应链瓶颈 + 全量资产发现 | POST /research/supply-chain-hacker |
| FinancialAuditor | 8Q剪刀差 + Beneish M-Score | POST /research/audit/financial/{code} |
| HumanCapitalDetective | 创始人/CTO/专利/股权激励 | POST /research/audit/human-capital |
| ValuationPricer | PEG/PS + 护城河时间窗 | (via DAG) |
| **DAGOrchestrator** | 5专家并行编排 → CIO综合报告 | **POST /research/analyze-v4** |

### 量化模块架构

```
指标库 (16算子) → 策略库 (8策略) → 决策中心 (加权投票) → 信号持久化
                   ├─ 6传统 (代码逻辑)
                   └─ 2 AI链 (YAML + LLM推理)
```

新增算子: 继承 `BaseIndicator`, 加 `@register` 装饰器, 放在对应分类目录, `__init__.py` 自动发现。
新增策略: 继承 `TimingStrategy`, 加 `@register_strategy` 装饰器。AI链策略编辑 YAML 文件即可热更新。

### 数据表 (13张)

| 表 | 用途 |
|----|------|
| positions | 持仓明细 |
| watchlist | 自选股 (分组标签+持仓标记) |
| market_data | 日K线 (stock_code+trade_date唯一索引) |
| stock_indicators | 指标数据 (每日一行, per-date存储) |
| stock_info | 股票基础信息 + PE/PB/市值/换手率 |
| strategy_signals | 策略信号持久化 (stock_code+日期索引) |
| portfolio_snapshots | 持仓每日切片 (价格/市值/盈亏快照) |
| exchange_rates | 汇率/黄金/原油/宏观指标 |
| macro_history | 宏观指标历史序列 (趋势图) |
| financial_statements | 季度财报 (待建表) |
| trade_history | 交易审计流水 |
| task_definitions | 任务定义 (含cron表达式) |
| task_executions | 任务执行记录 |

## 架构约束 (不变)

- `domain/* → framework/* → models/` 单向依赖
- domain 间禁止互相导入
- 所有 DB 操作异步 (`async_session`)
- Web 搜索走 Clash 代理 (`proxy="http://127.0.0.1:7890"`)
- 禁止 `print()` / `requests.get()` / 裸 `asyncio.create_task()`

## 关键模块速查

```python
# 任务引擎
from app.framework.tasks.engine import task_manager
task_id = await task_manager.run_task("sync_market", params={"mode": "AUTO"})
# 已注册: sync_market, calc_indicators, ai_recognize

# 数据源
from app.domain.market_data.sources.router import data_router
df = await data_router.get_daily_data(stock_code, days=120)

# 财务数据 (8Q)
from app.domain.research.services.data_loader import data_loader
fin = await data_loader.load_financial_statements("688012", periods=8)

# 估值同步
from app.domain.market_data.services.valuation import sync_valuation
await sync_valuation(target_codes=["688012"])  # None=全部持仓

# 指标计算
from app.domain.quant.engine.indicator_runner import IndicatorRunner
await IndicatorRunner.compute_historical("688012")     # 全量历史
await IndicatorRunner.compute_incremental("688012")    # 增量
await IndicatorRunner.compute_snapshot("688012")       # 快照

# 决策中心
from app.domain.quant.decision.center import DecisionCenter
center = DecisionCenter(provider=deepseek_provider)
reports = await center.decide(["688012", "002409"])

# 自选股
from app.models.models import WatchlistItem
# API: GET/POST /data/watchlist, POST /data/watchlist/import-positions

# 持仓快照 + 损益
# POST /data/portfolio/snapshot → 当日盈亏+累计盈亏+市值

# 宏观数据
# GET /data/macro/latest → 全部宏观指标
# GET /data/macro/history?code=US10YT → 历史序列

# AI 模型路由
from app.framework.ai.providers.deepseek import DeepSeekProvider
provider = DeepSeekProvider()
provider.chat_flash(prompt)  # 简单任务: deepseek-v4-flash
provider.chat_pro(prompt)    # 复杂推理: deepseek-v4-pro + thinking
```

## 开发流程

1. 查 `docs/03_API_Specifications/System_Feature_Inventory.md` 做关联影响分析
2. 确认需求归属领域 (research/quant/market_data/portfolio)
3. 如需新表 → 修改 `models/models.py` → 启动时 `create_all` 自动建表
4. Agent/策略/算子 → 遵循对应 domain 的装饰器注册范式 (见 `.claude/rules/`)
5. 暴露接口 → `domain/<领域>/api/` → `main.py` 注册路由
6. 前端页面 → `<body data-page-id>` + sidebar + topbar + workspace
7. 端到端验证: curl API → 前端按钮 → 页面渲染
8. 更新 `System_Feature_Inventory.md` 和 `CLAUDE.md` (如有架构变更)
9. `smoke_test.py` 通过 (16 API)
10. `git commit` (见 `.claude/rules/quality-gates.md`)
