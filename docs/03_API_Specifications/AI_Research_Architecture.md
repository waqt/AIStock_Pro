# AI 投研模块 — 多智能体架构设计

> V3.0 | 2026-05-18

## 一、架构总览

```
┌─────────────────── frontend/research.html ────────────────────┐
│  [每日市场扫描]  [深度供应链下钻]  [多Agent联合分析]            │
│                                                                 │
│  右侧面板:                                                      │
│    核心结论 → 核心标的表(14列) → 供应链L1-L4图谱                │
│    → 景气周期预测 → 全球对标估值 → 风险警示 → 跟踪指标          │
└──────────────────────┬────────────────────────────────────────┘
                       │ POST /api/research/{scan, supply-chain, analyze}
                       ▼
┌────────────────── api/routes.py ──────────────────────────────┐
│  POST /scan           → MarketScanner                          │
│  POST /supply-chain   → SupplyChainAnalyst (V3.0)              │
│  POST /analyze        → ResearchCoordinator → 多Agent合成       │
│  GET  /data/search    → 股票搜索                                │
│  GET  /data/stock/{c} → 单股数据 (行情+基本面+指标)             │
└──────────────────────┬────────────────────────────────────────┘
                       │
          ┌────────────┼──────────────┐
          ▼            ▼              ▼
     MarketScanner  SupplyChain   IndustryAnalyst
     (主动扫描)      Analyst(V3.0)  (行业景气)
          │            │              │
          └────────────┼──────────────┘
                       │
          ┌────────────▼──────────────────────┐
          │  ResearchCoordinator (编排器)      │
          │  注册Agent → 逐一调用 → LLM合成   │
          └────────────┬──────────────────────┘
                       │
          ┌────────────▼──────────────────────┐
          │  ResearchDataLoader (数据加载器)   │
          │  DB查询 + Web搜索的统一入口        │
          └────────────┬──────────────────────┘
                       │
          ┌────────────▼──────────────────────┐
          │  DeepSeekProvider (AI提供者)       │
          │  chat() → api.deepseek.com        │
          └───────────────────────────────────┘
```

## 二、Agent 体系

### 继承层级

```
BaseAgent (framework/agents/base.py)
  抽象基类: analyze(), stream(), load_context()
    │
    └── ResearchAgent (domain/research/agents/base.py)
          注入 data_loader, 标准化 load_context → build_prompt → LLM → parse_result 流程
            │
            ├── MarketScanner         每日主动扫描
            ├── SupplyChainAnalyst    供应链深度下钻 (主力)
            ├── IndustryAnalyst       行业景气度分析
            └── ResearchCoordinator   多Agent编排器
```

### 各 Agent 详细能力

#### 1. MarketScanner — 每日市场扫描

| 属性 | 说明 |
|------|------|
| 触发方式 | 零参数, 用户点击"开始扫描" |
| 输入 | 无 (全自动) |
| 数据来源 | 持仓数据 + 宏观数据 + Web搜索 (全球宏观/政策/资金流) |
| AI调用 | 1次 (信号采集 + LLM识别热门赛道) |
| 产出 | 热门赛道列表 (含景气评分 + 原因 + A股映射代码) + 每日简报 |

**工作流**:
1. `load_context()` → 拉取持仓、宏观、市场数据
2. `build_prompt()` → 拼接全球市场信号
3. DeepSeek 分析 → **热力赛道识别** + 评分 (1-10)
4. 生成 Markdown 每日简报

---

#### 2. SupplyChainAnalyst V3.0 — 供应链深度下钻 (主力Agent)

| 属性 | 说明 |
|------|------|
| 触发方式 | 用户输入行业关键词 + 可选股票代码 |
| 输入 | `industry` (行业), `stock_codes` (可选A股代码) |
| 数据来源 | DB (持仓+宏观+基本面) + Web搜索 (DDG → Brave 双源, 通过Clash代理) |
| AI调用 | Phase1: 最多3轮 (每轮搜索→LLM→自检), Phase2: 1次 |
| 产出 | 结构化JSON深度报告 |

**Phase 1: 迭代深研 (3轮)**
```
Round 1: search("{行业} 产业 供应链 技术壁垒 龙头公司") → LLM分析 → 自检缺口
Round 2: search(缺口关键词) → LLM分析 → 自检缺口
Round 3: search(更深缺口) → LLM分析 → 自检缺口 → 满足条件则停止
```
每轮 LLM 输出: `{findings: [...], gaps: [...], need_more_search: bool}`

**Phase 2: 结构化深度报告**
```
CIO视角 → 输出完整JSON:
  summary           核心结论 (2-3句)
  core_stocks[]     核心标的 (每只14字段)
  supply_chain_map[] L1→L4 供应链瓶颈下钻
  temporal[]        景气周期时间维度预测
  valuation_peers[] 全球对标估值
  risk_alerts[]     风险警示
  watchlist[]       后续跟踪指标
```

**核心标的字段** (每只):
| 字段 | 说明 |
|------|------|
| code, name, exchange | 基本标识 |
| revenue, revenue_growth | 营收及增速 |
| profit, profit_growth | 利润及增速 |
| gross_margin | 毛利率 |
| market_cap, target_mcap | 当前/目标市值 |
| upside | 上涨空间% |
| global_peer, peer_ps, peer_pe | 全球对标+估值锚 |
| key_tech | 核心技术壁垒 |
| moat, moat_type | 护城河原因+类型 |
| founder_background, human_capital_score | 人力资本审计 |
| scissor_gap (revenue_growth, profit_growth, margin_trend, contract_liability_change, verdict) | 财务剪刀差 |
| risk, catalysts, position_suggest | 风险/催化剂/建议仓位 |

---

#### 3. IndustryAnalyst — 行业景气度分析

| 属性 | 说明 |
|------|------|
| 触发方式 | 被 Coordinator 调用, 或单独使用 |
| 输入 | `industry` (行业) |
| 数据来源 | DB (基本面 PE/PB) + 宏观数据 |
| 产出 | 行业景气度评分 + 成分股估值对比 |

**工作流**:
1. 加载行业基本面数据 (PE分位、利润增速)
2. LLM 分析行业生命周期 + 景气周期位置
3. 输出景气评分 + 持仓行业分布建议

---

#### 4. ResearchCoordinator — 多Agent编排器

| 属性 | 说明 |
|------|------|
| 触发方式 | `POST /api/research/analyze` |
| 输入 | `question`, `stock_codes`, `industry` |
| 工作模式 | 注册分析师 → 逐一调用 → LLM合成最终报告 |

**工作流**:
1. 遍历已注册的 Agent
2. 每个 Agent 独立 `analyze(ctx)` → 生成子报告
3. 汇总所有子报告 → LLM 合成最终综合报告

> ⚠️ 当前状态: 编排逻辑较简单，只是顺序调用+合成，无辩论/博弈机制

---

## 三、数据依赖

### DataLoader 能力清单

| 方法 | 数据来源 | 说明 |
|------|---------|------|
| `load_market_data(codes, days)` | DB (market_data表) | 日线行情 |
| `load_fundamentals(codes)` | DB (stock_info表) | PE/PB/市值 |
| `load_indicators(codes)` | DB (stock_indicators表) | 技术指标 |
| `load_positions()` | DB (positions表) | 持仓明细 |
| `load_macro()` | DB (exchange_rates表) | 汇率+宏观 |
| `load_sector_overview()` | DB 聚合查询 | 行业概览 |
| `load_financials(code)` | 暂未实现 | 财务三表 |
| `search_web(query, num)` | DDG→Brave via Clash | 实时网络搜索 |
| `deep_research(query, rounds)` | 多轮搜索 | 逐层深入搜索 |
| `search_stocks(q)` | DB (stock_info表) | 股票代码搜索 |

### 数据缺口

| 缺口 | 影响 | 严重程度 |
|------|------|---------|
| 财务三表数据 | 深度报告的营收/利润纯靠估算 | 🔴 高 |
| 行业分类 (industry字段) | 行业级分析缺乏数据支撑 | 🔴 高 |
| 机构研报/新闻 | 无法感知市场情绪和一致预期 | 🟡 中 |
| 资金流向 (北向/主力) | 缺少资金面信号 | 🟡 中 |

---

## 四、前端页面

`frontend/research.html` — AI 投研指挥中心

**左侧面板**:
- 每日市场扫描 (按钮 + 赛道卡片)
- 深度供应链分析 (输入框 + 下钻按钮)
- 分析进度 (Phase1→自检→Phase2)
- 当前分析状态

**右侧面板** (V3.0 结构化渲染):
1. 核心结论 (CIO Summary)
2. 核心标的表 (14列: 代码/名称/营收/利润增速/毛利率/对标PE/市值/目标市值/上涨空间/护城河/原因/核心技术/全球对标/风险)
3. 供应链图谱 (L1显性瓶颈 → L4设备/测试瓶颈, 预期差评分)
4. 景气周期预测 (需求增速/供需缺口/缺口填补/热度)
5. 全球对标估值 (对标公司 + PE/PS)
6. 风险警示 (地缘/技术替代/财务/物理)
7. 跟踪指标

**技术特性**:
- localStorage 缓存，刷新不丢失上次分析
- 赛道卡片点击自动填入并触发深度分析
- 兼容 V3.0 新格式 + Legacy 旧格式

---

## 五、协作流程

### 场景1: 用户主动探索
```
用户输入 "AI算力" → SupplyChainAnalyst
  → Phase1: 3轮搜索+自检
  → Phase2: CIO结构化报告
  → 前端渲染完整报告
```

### 场景2: 每日自动扫描
```
用户点击"开始扫描" → MarketScanner
  → 采集全球信号 + 持仓数据
  → LLM识别Top赛道
  → 展示赛道卡片 + 每日简报
  → 点击赛道卡片 → 触发SupplyChainAnalyst深度下钻
```

### 场景3: 多Agent联合 (当前较基础)
```
POST /api/research/analyze → ResearchCoordinator
  → IndustryAnalyst: 行业景气度分析
  → SupplyChainAnalyst: 供应链深度分析
  → LLM合成两方观点 → 综合报告
```

---

## 六、后续演进方向

| 优先级 | 方向 | 说明 |
|--------|------|------|
| P0 | 财务数据接入 | 补齐深度报告的定量基础 |
| P0 | 行业分类补齐 | 让行业分析有数据支撑 |
| P1 | 个股深度研报 | 单只股票的全面深度分析 |
| P1 | 持仓诊断Agent | 自动体检持仓风险 |
| P2 | 研报历史持久化 | DB存储 + 前端浏览 |
| P2 | 智能推送 | 定时扫描异动通知 |
| P3 | 多Agent辩论 | 多头vs空头博弈 |
| P3 | 策略Agent | 回测 + 策略生成 |
