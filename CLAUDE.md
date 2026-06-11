# AIStock Pro — AI 量化分析与投研系统

## 项目身份

AIStock Pro 是一套 AI 驱动的量化分析与投资研究系统，面向 A 股 + 港股。系统采用 DDD 领域驱动 + 多智能体（MAS）架构，由 Python 3.8+ 异步引擎驱动。

- **架构风格**: DDD + MAS 多智能体 + 图结构 (DAG) 编排
- **版本**: V5.15
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
| 指标存储 | SQLite 宽表 — `indicators`(技术指标) + `financial_indicators`(财务指标) |
| Web 搜索 | Brave Search (主), 通过 Clash 代理 127.0.0.1:7890 |

## 目录结构 (核心变更)

```
backend/app/
├── framework/                     # 基础设施
│   ├── ai/providers/              # DeepSeek(主)/Doubao/Gemini
│   ├── tasks/                     # TaskEngine V5.1 (按类别信号量+去重)
│   ├── pipeline/                  # ★ Pipeline 基础设施
│   │   ├── checkpoint.py         #   检查点+缓存+跨版本查找+过期
│   │   ├── trace.py              #   TraceContext: 搜索/LLM/DB 全链路记录
│   │   └── glossary.py           #   16类跨Step枚举, prompt注入
│   ├── finance/                   # ★ 基础金融工具包
│   │   ├── valuation.py          #   PE/PB/PS/EV_EBITDA/PEG/FCF 纯函数
│   │   └── model_map.py          #   资产类型→估值模型映射
│   └── ...
├── domain/
│   ├── market_data/               # 行情同步 + 健康检查 + 估值同步 + 宏观数据
│   │   ├── sources/               # Sina/AkShare/Tencent/Push2
│   │   ├── services/              # valuation.py (PE/PB/市值), stock_list.py
│   │   └── api/                   # (路由在 app/api/data.py)
│   ├── research/                  # ★ AI 投研 V5.16 Pipeline
│   │   ├── agents/
│   │   │   ├── base.py            #   ResearchAgent + parse_json()
│   │   │   ├── global_capex_scanner.py  # Step 1a: 宏观周期分析
│   │   │   ├── capital_flow_scanner.py  # Step 1b: 全球资本流向扫描
│   │   │   ├── market_scanner.py        # Step 2: 行业看门人 (V5.10)
│   │   │   ├── supply_chain_hacker.py   # Step 3: 产业链拆解 (V5.9)
│   │   │   ├── financial_auditor.py     # [已删除] 改用 stock_auditor
│   │   │   ├── human_capital_detective.py # [已删除] 改用 stock_auditor
│   │   │   ├── valuation_pricer.py      # [已删除] 改用 stock_auditor
│   │   │   ├── dag_orchestrator.py      # 遗留: DAG 并行编排器
│   │   │   └── coordinator.py           # V3.0 遗留编排器
│   │   ├── services/
│   │   │   ├── data_loader.py     #   数据加载 + Web搜索(双源:Brave∥Tavily) + 8Q财报
│   │   │   ├── report_store.py    #   研报 JSON 文件持久化
│   │   │   └── stock_auditor.py   #   ★ 股票审计工具 (LLM自主规划, 替代旧Step7/8)
│   │   └── api/routes.py          #   /api/research/* + /api/research/pipeline/*
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
├── models/                        # 数据模型 (11张表, 不含StockIndicator)
│   └── models.py
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
├── main.py

backend/scripts/                   # 迁移/维护脚本
└── migrate_v5.*.py

backend/data/                      # ★ 数据文件 (单目录统一管理)
├── indicators.db                  #   SQLite 指标库 (宽表, 52列)
├── macro_report.json              #   宏观周期报告缓存
├── pipeline_checkpoints/          #   投研 Pipeline 检查点
└── research_reports/              #   研报 JSON 输出
```

## 数据同步架构 — 四层设计

### 总体架构

```
用户 / 前端 / 定时器
    │
┌─── API 触发层 ─────────────────────────────────────┐
│  POST /sync/market │ /sync/valuation               │
│  POST /sync/financial │ /sync/industry              │
│  POST /sync/stock-info │ /sync/macro                │
│  POST /sync/daily/auto │ /watchlist/sync            │
└───────┬────────────────────────────────────────────┘
        │
┌───────▼────────────────────────────────────────────┐
│ ① 调度层 — 策略模式 + 信号量                          │
│                                                      │
│  QuantEngine.sync_market_data(code, mode)            │
│    mode = AUTO(智能增量) / FORCE(近10天) / FULL(全量) │
│    AUTO 核心: gap = today - latest_date               │
│      gap<=0 → 跳过(今日已有)                          │
│      周末 gap<=1 → 跳过                               │
│      否则 days_to_fetch = max(gap+5, 10)             │
│                                                      │
│  TaskEngine 异步任务:                                 │
│    sync_market / calc_indicators / ai_recognize      │
│    calc_financial_indicators                         │
│    按类别信号量控制并发, 同类别任务排队不互殴            │
│                                                      │
│  sync_valuation(target_codes) — 估值写入(带质量保护)   │
│  sync_financials_smart/full — 财报季度同步             │
└───────┬────────────────────────────────────────────┘
        │
┌───────▼────────────────────────────────────────────┐
│ ② 网络层 — 职责链 + 断路器                           │
│                                                      │
│  DataRouter                                          │
│  ├─ 优先顺序: SinaSource(pri=1) → AkShareSource(2)   │
│  ├─ 连续失败 2 次 → 标记 OFFLINE → 跳过              │
│  ├─ 每 5 分钟 probe_all() 探测恢复                    │
│  └─ get_daily_data(code, days) → 遍历源→返回首个非空 │
└───────┬────────────────────────────────────────────┘
        │
┌───────▼────────────────────────────────────────────┐
│ ③ 适配层 — 协议抽象 + 统一 Schema                    │
│                                                      │
│  DataSourceProtocol (ABC)                            │
│  ├─ get_daily_data(code, days) → pd.DataFrame        │
│  ├─ health_check() → bool                            │
│  └─ source_name() / priority() → 元信息              │
│                                                      │
│  实现:                                                │
│  ├─ SinaSource                                       │
│  │   A股: 新浪 money.finance (scale=240 日线)        │
│  │   港股: akshare → 腾讯日线                        │
│  │   输出列: trade_date, open/high/low/close,        │
│  │          volume, amount, change_pct               │
│  └─ AkShareSource (与Sina同源, 备降)                 │
│                                                      │
│  ★ 外部数据源辅助适配器 (非 DataSourceProtocol):      │
│  ├─ Tencent 实时行情 (qt.gtimg.cn)                   │
│  │   股本/流通股本/总市值/流通市值/PE/PB              │
│  │   A股6位: sh/sz前缀 → field 73(总)/72(流通)       │
│  │   港股5位: hk前缀 → field 69(总)/70(流通)         │
│  └─ push2.eastmoney.com (需 ut 参数)                 │
│      估值/行业/上市日期/股本                          │
└───────┬────────────────────────────────────────────┘
        │
┌───────▼────────────────────────────────────────────┐
│ ④ 持久化 — 双引擎 + CQRS 读写分离                    │
│                                                      │
│  ├─ MySQL (事务数据, aiomysql)                       │
│  │  market_data / stock_info / stock_valuation       │
│  │  financial_statements / positions / watchlist     │
│  │  写入: async_session → executemany IGNORE         │
│  │  查询: select → ORM 对象                           │
│  │                                                       │
│  └─ SQLite (指标宽表, 每字段一列)                     │
│     indicators.db — 技术指标 (52列)                   │
│     financial_indicators.db — 财务指标 (50列)         │
│     写入: upsert (INSERT OR REPLACE)                 │
│     查询: indicator_store 工具函数                    │
│       ├─ get_latest(code) — 最新快照                 │
│       ├─ get_history(code, fields, days) — 时间序列  │
│       ├─ get_field_latest(field) — 全股票排名        │
│       └─ get_coverage(codes) — 覆盖检测              │
└────────────────────────────────────────────────────┘
```

### 同步链路清单

| 同步类型 | API端点 | 核心函数 | 数据源 | 目标表 |
|---------|---------|---------|-------|-------|
| 行情同步 | POST /sync/market | QuantEngine.sync_market_data | Sina/AkShare → 新浪日线 | market_data |
| 估值同步 | POST /sync/valuation | sync_valuation | Tencent + push2 | stock_info |
| 财务同步 | POST /sync/financial | sync_financials_smart/full | akshare | financial_statements |
| 行业同步 | POST /sync/industry | sync_valuation (内联) | push2 | stock_info.industry |
| 股票列表 | POST /stock-list/sync | sync_stock_list | akshare | stock_masters |
| 宏观同步 | POST /sync/macro | sync_macro | 新浪期货/外汇API | macro_history |
| 汇率同步 | POST /forex/sync | sync_forex | 新浪外汇API | exchange_rates |

### 质量保护机制

每层都有独立防护，防止脏数据穿透：

```
调度层: try/except 包裹每只股票, 单只失败不影响全局
          gap<=0 才跳过(需今天数据已存在), 不保守跳过

网络层: 数据源连续失败2次→自动降级到下一优先级源
          定时探测恢复→自动回升高优先级源

适配层: 空DF返回, 不抛异常到上层
          港股/A股自动识别(5位=港股, 6位=A股)

持久化: executemany IGNORE (不覆盖已有正确数据)
          upsert ON CONFLICT (部分重算不删旧行)
          同步函数内独立db session, 异常自动回滚
```

### 设计评价

**优点:**
- 四层各司其职，改动一层不影响其他层
- 多源自动切换是免费API场景下的务实选择（每日请求上限、网络波动等实际问题）
- CQRS 读写分离得当：MySQL 承业务事务，SQLite 承分析查询
- 信号量按类别隔离，避免大盘同步阻塞指标计算

**值得改进的点:**
1. **双源同构**: SinaSource 和 AkShareSource 对 A股都走新浪接口，不是真正独立的冗余源。如果新浪挂了，两条路都走不通。理想情况是引入一个真正独立的日线源（如腾讯日线或东方财富）
2. **混用 sync/async**: push2 适配器用 `requests.get`（同步）+ `asyncio.to_thread`，而 Sina 用 `httpx.AsyncClient`（异步）。这是演进遗留的 tech debt，统一为 httpx 异步会更干净
3. **串行循环**: 40只股票逐只 sync，网络IO密集时浪费了异步能力。适合当前规模（40只），扩展到数百只需加 `asyncio.gather` + 信号量

## V5.16 投研 Pipeline 架构

### Pipeline 三层设计纲领 (V5.16)

Pipeline 整体定位为**三层递进式研究**，每层职责明确，不可越界：

```
第一层: 趋势发现                       Step 1a + 1b
  ├─ 宏观周期分析 (GlobalCapexScanner)
  └─ 资本流向扫描 (CapitalFlowScanner)
  职责: 判断产业宏观趋势, 发现值得深入的方向。
  输出: 宏观周期结论 + 资本流向图谱, 供用户决定是否继续。

第二层: 产业链剖析                      Step 2 → 3 → 4 → 5
  ├─ 行业看门人   (MarketScanner)       — 定性筛选产业赛道
  ├─ 产业链拆解   (SupplyChainHacker)   — 瓶颈图谱+利润池+竞争格局
  ├─ 系统动力学   (SystemDynamicsAgent) — 产业链演化与外溢效应
  └─ 跨产业关联   (CrossIndustryLinkage) — 跨产业传导路径
  职责: 剖析产业链结构与外溢效应, 为后续选股提供线索。
  核心: 聚焦"产业逻辑"而非"个股研究", 产出供给刚性/利润分配/瓶颈节点。
  线索: output.asset_search_queries 是传递给 Step 6 的唯一搜索接口。

第三层: 资产筛选与验证                   Step 6 (+ StockAuditor 按需调用)
  ├─ 核心资产筛选 (CoreScreeningAgent V5.15) — 四阶段: 线索汇总→搜索→先比较后验证→全局排名
  │    ├─ Phase 1: 线索汇总           (8线索源: a_stock_mapping/bottleneck_inversion/asset_search_query/human_capital)
  │    ├─ Phase 2: 搜索+LLM提取       (双源搜索+深搜a_share_equivalent)
  │    ├─ Phase 3a: 分组+筛选+比较    (_group_by_source → _llm_screen_group → compare_within_source)
  │    ├─ Phase 3b: 逐只验证          (_verify_single: LLM自主定维+tool calling, 无预设维度)
  │    └─ Phase 4: 全局排名           (CandidateComparator.global_ranking + enriched)
  └─ StockAuditor.audit_summary()    — 轻量审计, 供 Step 6 enrichment 对候选池每只标的调用
  职责: 在前道(第二层)提供的产业线索基础上, 挖掘具体资产标的, 通过比较淘汰选出最优解。
  方法: 搜索→LLM提取→分组→Phase A快速筛→同源比较排除→逐只自由验证→全局排名。
  关键变化(V5.15+): 旧Step7/8已删除, 改为StockAuditor按需调用; 比较器不排名只排除; 验证改为LLM自主定维。
```

**层间接口规范:**
- 第二层→第三层: `asset_search_queries` 是**唯一的搜索线索传递通道**（不得跨层直接读取 spillover/瓶颈等内部结构）
- 第三层自身发现的线索（如 `human_capital` 源）仅作为补充，不得覆盖或替代第二层的结构化结论
- 每层不得越界做不属于自己职责的事情（如第二层不做个股验证，第三层不做产业链分析）

### 12 步分析链路

```
Step 1a 宏观周期分析 (GlobalCapexScanner)
  → 独立运行, 输出 macro_report.json, 在数据中心宏观Tab查看
  → 不串联到 pipeline, 用户参考结论后手动选择分析类型

Step 1b 资本流向扫描 (CapitalFlowScanner)
  → 谁在花钱? 花在哪? 约束在哪?
  → 输出 capex_vectors + constraint_vectors

Step 2  行业看门人 (MarketScanner V5.10)
  → 定性筛选: 6-block 输出 + 结构化证据 + 粒度过滤 + 错配分析
  → 用户查看结论后手动选择下一步:
     ├─ [A] 直接资产挖掘 → POST /direct-asset-mine (CoreScreeningAgent step2_only)
     │    从 transmission_order 节点直接挖标的, 跳过产业链深挖
     │    (用于: 产业逻辑强但认知差弱, 市场已定价)
     ├─ [B] 二阶推演      → POST /second-order-extrapolate (SecondOrderExtrapolator)
     │    外推相邻产业的预期差, 寻找市场未定价的机会
     │    (用于: 主产业预期差弱, 但存在跨产业溢出潜力)
     └─ [C] 产业链深挖    → POST /scan/industry-drilldown 走 Step 3→4→5→6
          标准全链路穿透 (用于: 认知差强的产业)

Step 3  产业链拆解 (SupplyChainHacker V5.9)
  → L1-L4 瓶颈图谱 + 供给刚性 + 利润池 + 价值捕获 + 竞争格局

Step 4  系统动力学推演 (SystemDynamicsAgent, 已有)
Step 5  跨产业关联分析 (CrossIndustryLinkageAgent, 已有)
Step 6  核心资产筛选 (CoreScreeningAgent V5.15, 含 step2_only 模式)
Step 7  财务质量审计 → 已移除, 改用 StockAuditor.audit_financial()
Step 8  人力资本审计 → 已移除, 改用 StockAuditor.audit_human_capital()
Step 8  估值定价     → 已移除, 改用 StockAuditor.audit_valuation()
Step 9  市场预期差 (📋 计划中)
Step 10 风险分析 (📋 计划中)
Step 11 综合报告 (📋 计划中)
```

### Agent 清单

| Agent | 文件 | 版本 | Step | 状态 |
|-------|------|------|------|------|
| GlobalCapexScanner | global_capex_scanner.py | V5.7 | 1a | ✅ 完成 |
| CapitalFlowScanner | capital_flow_scanner.py | V1.0 | 1b | ✅ 完成 |
| MarketScanner | market_scanner.py | V5.10 | 2 | ✅ 完成 (证据层+粒度过滤+错配分析) |
| SupplyChainHacker | supply_chain_hacker.py | V5.9 | 3 | ✅ 完成 (定性schema+证据层+自适应搜索) |
| SystemDynamicsAgent | system_dynamics.py | V1.0 | 4 | ✅ 完成 |
| CrossIndustryLinkageAgent | cross_industry_linkage.py | V1.0 | 5 | ✅ 完成 |
| CoreScreeningAgent | core_screening_agent.py | V5.15 | 6 | ✅ 完成 (四阶段: 线索汇总→搜索→比较→验证, LLM自主验证, 含 step2_only/溢出候选/多轮淘汰) |
| SecondOrderExtrapolator | second_order_extrapolator.py | V1.0 | 2B | ✅ 完成 (Path B: 二阶推演) |
| DAGOrchestrator | dag_orchestrator.py | - | 遗留 | ⚠️ 遗留, 未接入新 pipeline |

V3.0 遗留 (向后兼容): SupplyChainAnalyst, IndustryAnalyst, ResearchCoordinator

### Service 清单 (非 Agent)

| Service | 文件 | 用途 |
|---------|------|------|
| StockAuditor | services/stock_auditor.py | ★ 股票审计工具 (替代旧Step7/8) — LLM自主规划financial/human_capital/valuation |
| StockHealthChecker | agents/stock_health_checker.py | 全维度体检 (含技术分析, LLM tool calling) — 与StockAuditor互补 |

### Pipeline 基础设施

| 模块 | 文件 | 用途 |
|------|------|------|
| Checkpoint | framework/pipeline/checkpoint.py | 检查点落盘+缓存+跨版本查找+过期 |
| Trace | framework/pipeline/trace.py | TraceContext: 搜索/LLM/DB 全链路记录 |
| Glossary | framework/pipeline/glossary.py | 16类跨Step枚举定义, prompt注入 |
| ObservationStore | domain/observation/ | ★ 投研观察框架: 提取/存储/查询/前端 badge |
| Valuation | framework/finance/valuation.py | PE/PB/PS/EV_EBITDA/PEG/FCF纯函数 |
| Model Map | framework/finance/model_map.py | 资产类型→估值模型映射 |
| Task Engine | framework/tasks/engine.py V5.1 | 按类别信号量+去重+异步执行 |

### 量化模块架构

#### 技术指标 (日线)
```
指标库 (16算子) → 策略库 (8策略) → 决策中心 (加权投票) → 信号持久化
                   ├─ 6传统 (代码逻辑)
                   └─ 2 AI链 (YAML + LLM推理)
```

新增算子: 继承 `BaseIndicator`, 加 `@register` 装饰器, 放在对应分类目录, `__init__.py` 自动发现。详见 `.claude/rules/quant-indicator-standards.md`。
新增策略: 继承 `TimingStrategy`, 加 `@register_strategy` 装饰器。AI链策略编辑 YAML 文件即可热更新。

#### 财务指标 (季度)
```
FINANCIAL_REGISTRY (27算子) → financial_compute.py (滑动窗口) → financial_indicators (SQLite)
  ├─ profitability (7): roe, margin, roic, roiic, rd_intensity, gross_margin_trend, working_capital...
  ├─ growth (9): revenue_growth, profit_growth, scissor_gap, inflection, operating_leverage...
  ├─ health (5): contract_liability, inventory, ocf_health, burn_rate_months, rd_to_opex
  ├─ quality (3): beneish_m_score, roic_stability, operating_margin_stability
  └─ profile (1): revenue_scale
```

存储列自动从 FINANCIAL_REGISTRY 推导 (35 数值列 + 15 文本列)，新增指标无需手动 DDL。
查询层: `FinancialQueryService` (catalog + on-demand query + SQLite 缓存)。
详见 `.claude/rules/financial-indicator-standards.md`。

### 指标存储 schema (SQLite wide table)

指标存储已从 MySQL JSON blob 迁移至 **SQLite 宽表** (`backend/data/indicators.db`)。
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
| indicators | **SQLite** | ★ 技术指标宽表 (52列, 每字段一列) |
| financial_indicators | **SQLite** | ★ 财务指标宽表 (50列, 自动推导自 FINANCIAL_REGISTRY) |
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

# 财务指标 — 注册/查询/计算
from app.domain.quant.indicators.fundamental import FINANCIAL_REGISTRY
len(FINANCIAL_REGISTRY)                                    # 已注册指标数
from app.domain.quant.indicators.fundamental.base import build_financial_field_registry
build_financial_field_registry()                           # 全字段元数据 (unit/meaning/is_text)

from app.domain.quant.engine.financial_query_service import FinancialQueryService
svc = FinancialQueryService()
catalog = svc.get_catalog()                                # 数据字典 (已缓存)
data = await svc.query("688012", indicators=["roic_pct", "revenue_yoy"], raw_fields=["revenue"])
prompt = svc.format_catalog_for_prompt()                   # LLM prompt 注入

from app.domain.quant.engine.financial_compute import compute_financial_for_codes, filter_a_share_codes
result = await compute_financial_for_codes(codes, mode="local")  # 批量计算

from app.domain.quant.engine import indicator_store
row = indicator_store.get_financial_latest("688012")       # 最新财务指标快照
hist = indicator_store.get_financial_history("688012")     # 财务指标历史序列

# 财务API:
# GET  /api/quant/financial-indicators/registry  — 注册表 (meta())
# GET  /api/quant/financial-indicators/catalog   — 数据字典 (含 unit/meaning)
# POST /api/quant/financial-indicators/query     — Agent 按需组装
# POST /api/quant/financial-indicators/compute   — 批量计算落库
# GET  /api/quant/financial-indicators/{stock_code}[?fields=...]

# 自选股
from app.models.models import WatchlistItem
# API: GET/POST /data/watchlist, POST /data/watchlist/import-positions

# 持仓快照 + 损益
# POST /data/portfolio/snapshot → 当日盈亏+累计盈亏+市值

# 宏观数据
# GET /data/macro/latest → 全部宏观指标
# GET /data/macro/history?code=US10YT → 历史序列

# Pipeline 基础设施
from app.framework.pipeline.checkpoint import (
    generate_run_id, hash_input, load_checkpoint, save_checkpoint,
    save_manifest, load_manifest, list_runs, save_trace, make_display_name
)
from app.framework.pipeline.trace import TraceContext
trace = TraceContext(run_id)
trace.record_search(query, results)
trace.record_llm(prompt, response, model="deepseek-v4-pro")

# 金融工具包
from app.framework.finance import (
    pe_valuation, pb_valuation, ps_valuation,
    ev_ebitda_valuation, peg_valuation, fcf_yield_valuation,
    scenario_weighted, apply_pricing_power_premium,
    apply_quality_adjustment, apply_financial_risk_discount,
    match_asset_type, get_valuation_method
)

# Pipeline API
# 项目列表: GET /api/research/pipeline/runs
# 项目详情: GET /api/research/pipeline/{run_id}
# 节点输出: GET /api/research/pipeline/{run_id}/checkpoint/{step}
# 编辑保存: PUT /api/research/pipeline/{run_id}/checkpoint/{step}
# 溯源日志: GET /api/research/pipeline/{run_id}/trace/{step}
# 星标收藏: PUT /api/research/pipeline/{run_id}/star
# 删除项目: DELETE /api/research/pipeline/{run_id}
# Path A 直挖: POST /api/research/direct-asset-mine (CoreScreeningAgent step2_only)
# Path B 二阶: POST /api/research/second-order-extrapolate (SecondOrderExtrapolator)
# StockAuditor 全量审计: POST /api/research/stock-audit/{code}
# StockAuditor 财务审计: POST /api/research/stock-audit/{code}/financial
# StockAuditor 人力审计: POST /api/research/stock-audit/{code}/human-capital
# StockAuditor 估值定价: POST /api/research/stock-audit/{code}/valuation
# StockAuditor 轻量摘要: POST /api/research/stock-audit/{code}/summary
# StockHealthChecker:    POST /api/research/health-check
# 观察列表: GET /api/observations/stocks/{code} — 单股观察计数
# 观察列表: GET /api/observations/steps/{step} — 按步骤筛选
# 星标收藏: PUT /api/research/pipeline/{run_id}/star
# 删除项目: DELETE /api/research/pipeline/{run_id}

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
4. Agent/策略/算子/财务指标 → 遵循对应 domain 的装饰器注册范式（见 `.claude/rules/`）
   - 技术指标/策略 → `.claude/rules/quant-indicator-standards.md` / `.claude/rules/quant-module.md`
   - 财务指标 → `.claude/rules/financial-indicator-standards.md`
5. 暴露接口 → `domain/<领域>/api/` → `main.py` 注册路由
6. 前端页面 → `<body data-page-id>` + sidebar + topbar + workspace
7. 端到端验证: curl API → 前端按钮 → 页面渲染
8. 更新 `System_Feature_Inventory.md` 和 `CLAUDE.md` (如有架构变更)
9. `smoke_test.py` 通过 (16 API)
10. `git commit` (见 `.claude/rules/quality-gates.md`)
