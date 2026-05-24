# AIStock Pro — AI 量化分析与投研系统

## 项目身份

AIStock Pro 是一套 AI 驱动的量化分析与投资研究系统，面向 A 股 + 港股。系统采用 DDD 领域驱动 + 多智能体（MAS）架构，由 Python 3.8+ 异步引擎驱动。

- **架构风格**: DDD + MAS 多智能体 + 图结构 (DAG) 编排
- **版本**: V5.6
- **数据存储**: MySQL (事务数据: 持仓/日线/财务) + **SQLite 宽表** (量化指标, 每字段一列)
- **conda 环境**: `aiteacher` (`D:\develop_env\python_related\anaconda\Anaconda3\envs\aiteacher`)
- **启动**: 双击 `run_backend.bat` → `http://127.0.0.1:8000`
- **加速**: numba.jit 加速筹码 COST 计算 (半衰期指数衰减模型, 45天半衰期)
- **筹码形态**: 5类判定 — 低位单峰密集 / 高位单峰密集 / 双峰密集(近下峰) / 双峰密集(近上峰) / 多峰密集。集中度公式 = (COST90-COST10)/(COST90+COST10)，阈值: <0.12密集, >0.20发散

## 技术栈

| 层 | 技术 |
|---|------|
| Web 框架 | FastAPI + Uvicorn (--reload 热加载) |
| 序列化/配置 | Pydantic V2 + pydantic-settings |
| ORM | SQLAlchemy 2.0 异步 (aiomysql) |
| 量化计算 | Pandas + NumPy |
| 前端 | 原生 HTML/CSS/JS + ECharts 5.5 + Font Awesome 6 |
| AI 提供者 | DeepSeek (Anthropic兼容, 主) / 豆包 Seed / Gemini Vision |
| 任务调度 | TaskEngine (自研, 注册式装饰器) |
| 数据源 | httpx → 新浪/东方财富/腾讯; akshare (财报+港股) |
| 指标存储 | SQLite 宽表 (每字段一列) + numba JIT 加速 |
| Web 搜索 | Brave Search (主), 通过 Clash 代理 127.0.0.1:7890 |

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
│   └── quant/                     # ★ 量化模块 V5.6
│       ├── indicators/            #   16个算子 (每文件一算子, @register 自注册)
│       │   ├── base.py            #   BaseIndicator + @register
│       │   ├── trend/             #   MA, MACD, KDJ
│       │   ├── momentum/          #   RSI, ATR, CCI
│       │   ├── volatility/        #   Bollinger, Bollinger Width
│       │   ├── volume/            #   OBV, VolumeMA, VWAP
│       │   ├── chip/              #   筹码分布 (COST指数衰减, numba加速)
│       │   └── crowding/          #   拥挤度 (turnover_ratio/sharpe_60d)
│       ├── strategies/            #   8个策略 (每文件一策略)
│       ├── decision/              #   决策中心
│       ├── engine/
│       │   ├── engine.py          #   QuantEngine (行情/估值/行业同步)
│       │   ├── indicator_runner.py # 指标计算 (3轮处理, ctx上下文)
│       │   └── indicator_store.py # ★ SQLite 宽表存储 (52列)
│       ├── tasks.py               #   注册任务: sync_market, calc_indicators, ai_recognize
│       └── api/                   #   /api/quant/*
├── portfolio/services/
│   └── ai_import.py               #   AI 截图识别
├── api/                           # 路由 (data.py/positions.py/import_api.py)
└── models/                        # 数据模型 (11张表, 不含StockIndicator)
    └── models.py
├── index.html                     # 指挥中心
├── positions.html                 # 持仓管理
├── research.html                  # AI 投研
├── quant.html                     # ★ 量化决策 (算子/策略/决策/指标计算/数据查看)
├── indicators.html                # ★ 指标数据 (全景卡片 + 时间序列图 + 排名)
├── data.html                      # 数据中心 (6 Tab)
├── import.html                    # 智能导入
├── js/
│   ├── framework/
│   │   ├── api.js / modal.js / task_monitor.js / markdown.js
│   │   └── indicator_compute.js   # ★ 指标计算公共组件
│   ├── ui.js                      # 侧边栏+顶栏
│   ├── common.js                  # escHtml / initCommon
│   └── data-tabs/                 # 数据中心 Tab 模块
│       ├── core.js / macro.js / watchlist.js / health.js
│       ├── financial.js / fundamental.js / alt.js
└── data/indicators.db             # ★ SQLite 指标库 (单文件可备份)
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

新增算子: 继承 `BaseIndicator`, 加 `@register` 装饰器, 放在对应分类目录, `__init__.py` 自动发现。详见 `.claude/rules/quant-indicator-standards.md`。
新增策略: 继承 `TimingStrategy`, 加 `@register_strategy` 装饰器。AI链策略编辑 YAML 文件即可热更新。

### 指标存储 schema (SQLite wide table)

指标存储已从 MySQL JSON blob 迁移至 **SQLite 宽表** (`data/indicators.db`)。
每字段一列, 支持 `pd.read_sql()` 直接读入 DataFrame 做时间序列分析。

```
表: indicators (PRIMARY KEY: stock_code, trade_date)
  数值列 (REAL): price, ma5~ma250, macd/macd_signal/macd_hist, k/d/j,
    rsi, atr, cci, bb_upper/bb_mid/bb_lower/bb_width,
    obv, v_ma5/v_ma10/v_ma20, vwap,
    turnover_20d/turnover_120d, crowding_ratio, sharpe_60d,
    chip_concentration, chip_peak_price, chip_avg_cost, chip_is_single_peak
  文本列 (TEXT): chip_pattern, chip_signal
```
覆盖检测: `GET /quant/indicators/coverage` | 详见 `.claude/rules/quant-indicator-standards.md`

### 数据表 (11张 + SQLite)

| 表 | 存储 | 用途 |
|----|------|------|
| positions | MySQL | 持仓明细 |
| watchlist | MySQL | 自选股 |
| market_data | MySQL | 日K线 (UNIQUE: stock_code+trade_date) |
| indicators | **SQLite** | ★ 指标宽表 (52列, 每字段一列) |
| stock_info | MySQL | 股票基础信息 + PE/PB/市值 |
| financial_statements | MySQL | 季度财报 |
| portfolio_snapshots | MySQL | 持仓每日切片 |
| exchange_rates | MySQL | 汇率/黄金/原油 |
| macro_history | MySQL | 宏观历史序列 |
| trade_history | MySQL | 交易审计 |
| task_definitions | MySQL | 任务定义 |
| task_executions | MySQL | 任务执行记录 |

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
await IndicatorRunner.compute_historical("688012")     # 全量历史 (DELETE+INSERT)
await IndicatorRunner.compute_incremental("688012")    # 增量 (自动降级全量)
await IndicatorRunner.compute_snapshot("688012")       # 快照 (仅今天)

# 指标查询 (SQLite)
from app.domain.quant.engine import indicator_store
row = indicator_store.get_latest("688012")              # 最新快照
hist = indicator_store.get_history("688012", ["rsi","macd"], 120)  # 时间序列
rank = indicator_store.get_field_latest("crowding_ratio")   # 全股票排名
cov = indicator_store.get_coverage(all_codes)           # 覆盖检测

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

### LLM Agent 设计原则 (V5.7+)

**核心原则: LLM 做定性归类，不做主观评分。**

LLM 擅长逻辑推理和模式识别，不擅长产生可验证的数值。
在 Agent prompt 和 Step 间数据传输中:

```
✅ LLM 该输出:
  "行业处于 bottleneck_formation 阶段"     ← 模式识别
  "景气类型是 supply_shock"                ← 归类判断
  "需求是真实终端消费, 非补库"              ← 逻辑推理
  "上涨空间远大于下跌空间"                  ← 定性判断

❌ LLM 不该输出:
  "scarcity_score = 9.2"                 ← 无法验证, 换人可能是 7.5
  "alpha_score = 92"                     ← 下游不知道 92 怎么来的
  "prosperity = 8/10"                    ← 主观且不可复现
  "risk_level = HIGH"                    ← 枚举值同样主观
```

**例外**: 从 DB 读取的客观数据 (PE=45, ROE=15%, price=312) 和程序化计算结果 (Beneish M-Score, supply_rigidity via Step3 计算) 可以传递。

**Step 间传递**: Step N 的输出传给 Step N+1 时，定性标签优先于数字评分。下游 Step 根据定性标签选择分析框架，在自己的环节做程序化定量。

### 版本管理铁律

**每次改动前必须先 git commit 当前状态。** 使用 Write/Edit 工具直接写文件，绝不通过 bash 传递包含 `$`/`{`/反引号的复杂文本。

### 前置原则

- **复杂改动先沟通**: 涉及架构变更、Pipeline 重组、数据格式切换、多文件联动改造等复杂改动时，在动手前先用文字描述方案并与用户确认方向。避免在错误路径上浪费调试时间。简单改动（修 bug、改配置、单文件小改）可直接执行。
- **验证后写系统**: 新增算法/指标/策略时，先在 `temp_lab/` 用真实数据脚本验证，确认效果后再集成到系统。严禁直接在系统文件里边改边试。
- **中间结果落盘**: 长时间 Pipeline 分阶段保存中间结果到 `temp_lab/`，支持各阶段独立调试和秒级报告迭代。

### 投研 Pipeline 断点续跑

投研报告生成分三阶段，每阶段落盘后可独立重跑：

```bash
# 1. 全量跑 (首次, 2-3min)
curl -X POST http://127.0.0.1:8000/api/research/analyze-v4 \
  -H "Content-Type: application/json" \
  -d '{"industry":"SOFC"}'

# 2. 跳过 Phase1, 只重跑审计+定价 (修复审计/定价 bug 后, ~1min)
curl -X POST "http://127.0.0.1:8000/api/research/analyze-v4?skip_phase1=true" \
  -H "Content-Type: application/json" \
  -d '{"industry":"SOFC"}'

# 3. 只改报告格式 (1s, 读 Phase1+Phase2 缓存, 不调任何 Agent)
python temp_lab/regenerate_report.py SOFC
```

中间文件落盘在 `temp_lab/{slug}_phase1_sc.json` 和 `temp_lab/{slug}_phase2_dag.json`。改任何一步只需重跑该步及之后，无需重头开始。

### 标准步骤

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
