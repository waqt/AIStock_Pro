# AI 投研系统 V5.7 → V6.0 升级设计文档

> 对标 GPT 投研提示词 V2（11 步系统动力学增强版），在现有 6 Agent + DAG Pipeline 架构上渐进增强。

---

## 系统定位

**AIStock Pro 产业链分析专家** — 针对投资驱动的供给侧行业分析系统。

### 分析哲学

核心能力:
- 宏观周期分析 / 产业链分析 / CAPEX 周期分析
- 系统动力学分析 / 供需分析 / 资源约束分析
- 利润池迁移分析 / 非线性产业链推演
- 全球竞争格局分析

必问问题:
1. **谁最缺** — 供给刚性最高的环节在哪？
2. **谁拥有定价权** — 利润池集中在谁手里？
3. **谁控制供给** — 产能扩张的决定权在谁？
4. **谁受益于供给收缩** — 产业瓶颈的隐藏受益者？
5. **谁受益于资源重新分配** — CAPEX/产能/利润的迁移方向？

寻找目标:
1. 高景气行业 → Step 2 (MarketScanner) + `prosperity_type` 判别
2. 核心利润池 → Step 3 (SupplyChainHacker) + `profit_pool_share` 量化
3. 产业瓶颈 → Step 3 (bottleneck) + Step 4 (scarcity_ranking)
4. 隐藏受益者 → Step 4+5 (_second_level_analysis)
5. 市场预期差 → Step 9 (ExpectationGapAgent)
6. 全球核心资产 → Step 6 (top_picks) + Step 8 (global_peer_comparison)

---

## 一、现状全景映射

```
GPT V2 11 步工作流                     AIStock Pro Agent              完成度    升级方向
══════════════════════════════════════════════════════════════════════════════════════
Step 1  宏观与全球资本周期              GlobalCapexScanner             30%      Prompt 重写
Step 2  行业景气度分析                  MarketScanner                   60%      Prompt 增强
Step 3  产业链系统拆解                  SupplyChainHacker (Phase 1)     70%      Prompt 重写
Step 4  系统动力学与资源约束分析         _second_level_analysis          10%      Prompt 彻底重写
Step 5  非线性产业链推演 (5层+)         _second_level_analysis (同上)   10%      合并到 Step 4
Step 6  核心资产筛选                    top_picks 程序化逻辑            90%      ✅ 已完成
Step 7  财务质量与盈利能力              FinancialAuditor                85%      小增强
Step 8  估值体系                        ValuationPricer                 85%      ✅ 已完成
Step 9  市场预期差与资金面              ❌ 不存在                        0%      新增 Agent
Step 10 风险分析                        LLM 合成 + 硬编码兜底           40%      Prompt 增强
Step 11 最终投资结论                    _synthesize_basic               80%      报告模板补一节
```

---

## 二、升级步骤详细设计

### Step 1: 宏观与全球资本周期 (GlobalCapexScanner 重构)

**当前状态**: 仅搜索 MAG7 CapEx 数据，LLM 分析常失败，输出主要是原始搜索结果。

**目标状态**: 覆盖利率/流动性/PMI/美元/通胀/地缘政治 + 中国宏观 7 变量，LLM 综合输出宏观定位。持久化存储，月更频率。

**设计决策**:

1. **持久化策略** — 宏观分析不随每次投研触发，而是独立持久化为基础设施：

```
data/macro_report.json
{
  "generated_at": "2026-05-24T10:00:00",
  "valid_until": "2026-06-24T10:00:00",    // 30 天有效期
  "data": {
    "macro_conclusion": {...},
    "data_sources": {...}                   // 每个变量标注取值时间+来源
  }
}
```

Pipeline 启动时检查：文件存在且未过期 → 直接读取。过期或不存在 → 触发分析。
前端加"刷新宏观数据"按钮，手动触发重跑。

2. **数据获取策略 — 结构化管线 + 搜索融合**

Step 1 的 13 个变量，按数据获取方式分为三类：

```
类别 A: 结构化管线 (akshare → DB) — 7 个变量, 无需搜索
═══════════════════════════════════════════════════════════
变量              数据源                                     已有？
───────────────────────────────────────────────────────────
fed_rate          ak.macro_bank_usa_interest_rate()          ❌ 曾测但编码乱码
us10y + 2s10s     ak.bond_zh_us_rate()                       ✅ US10YT 已接入
inflation         ak.macro_usa_cpi_monthly/yoy               ❌ 新增
china_pmi         ak.macro_china_pmi()                        ❌ 新增
usa_pmi            ak.macro_usa_ism_pmi()                      ❌ 新增
china_monetary    ak.macro_china_lpr() + money_supply()       ❌ 新增
china_property    ak 房地产数据                                ❌ 新增

类别 B: 半结构化 (akshare 为主, 搜索补充) — 3 个变量
═══════════════════════════════════════════════════════════
dxy               新浪 hf_DINIW 待修复 / 搜索兜底
china_fiscal      赤字率可用结构化, 专项债政策需搜索
china_mfg         工业增加值可用, 产能利用率需搜索

类别 C: 纯搜索+LLM (定性判断) — 3 个变量
═══════════════════════════════════════════════════════════
liquidity         全球流动性方向 (QT进度/央行扩表/信贷脉冲)
geopolitics       芯片管制/关税/台海 — 实时事件, 无结构化
industrial_policy 半导体/AI/新能源产业政策 — 政策解读
new_productive    新质生产力 — 概念性方向
overseas          出海趋势 — 趋势性判断
```

**同步设计**:

类别 A 变量纳入数据中心 `sync_macro` → `exchange_rates` + `macro_history` 表，`POST /data/macro/sync` 一键同步。
Step 1 分析时：先从 DB 读入结构化数据 → 剩余变量 web search → LLM 融合输出。

```
数据流:
  sync_macro (日频/周频)
    ├─ ak.bond_zh_us_rate()       → exchange_rates {US10YT, CN10YT, US2Y, CN2Y}
    ├─ ak.macro_bank_usa_interest_rate() → exchange_rates {US_FED_RATE}
    ├─ ak.macro_usa_cpi_yoy()     → macro_history {US_CPI}
    ├─ ak.macro_china_cpi()       → macro_history {CN_CPI}
    ├─ ak.macro_china_pmi()       → macro_history {CN_PMI_MFG, CN_PMI_NONMFG}
    ├─ ak.macro_usa_ism_pmi()     → macro_history {US_ISM_PMI}
    ├─ ak.macro_china_lpr()       → macro_history {CN_LPR1Y, CN_LPR5Y}
    └─ ak.macro_china_money_supply() → macro_history {CN_M2_YOY, CN_M1_YOY}

  Step 1 分析 (月频)
    ├─ DB 读取: exchange_rates + macro_history (最新值+趋势)
    ├─ Web Search: liquidity/geopolitics/policy
    └─ LLM 融合 → macro_report.json
```

3. **新鲜度保障** — 双层机制：

- **结构化数据**: `sync_macro` 带 `updated_at` 时间戳，Step 1 启动时检查各指标最新值是否在 N 天内
- **搜索数据**: query 强制带年月 + LLM 禁用自己的训练数据 + `data_sources` 逐项标注取值时间
- **过期自动触发**: `valid_until` 过期 → 自动重跑 sync_macro + 搜索 + LLM

4. **分析变量清单（简化版，依赖结构化数据）**:

Step 1 只需 **2 轮搜索**（原 5 轮减少到 2 轮），其余从 DB 读取：

```
搜索1: "美联储 QT缩表 全球流动性 央行资产负债表 2026年5月"
       → 补充 liquidity 方向 + 验证 DB 数据时效

搜索2: "地缘政治 芯片出口管制 中美贸易 关税 产业政策 2026"
       → 补充 geopolitics + industrial_policy + 出海趋势
```

分析哲学 — 真正的大行业一定带有：
- 国家安全属性
- 技术自主属性
- 能源重构属性
- 人口结构变化

4. **输出结构** — 不止数据罗列，必须汇总成方向性判断：

```json
{
  "macro_conclusion": {
    "cycle_stage": "复苏后期 — 全球制造业PMI回升, 中国信用扩张温和",
    "liquidity_direction": "美联储缩表尾声→H2可能停止, 中国央行偏松, 全球流动性中性偏宽",
    "risk_appetite": "中等偏高 — AI投资热情持续但地缘风险压制",
    "global_capex_direction": "AI基础设施+能源转型双主线, 半导体capex YoY+25%",
    "china_focus": "新质生产力主导 — 半导体/大飞机/低空经济",
    "benefited_sectors": [
      {"sector": "AI算力基础设施",  "driver": "MAG7 capex $700B+",  "confidence": "高"},
      {"sector": "半导体设备/材料",  "driver": "国产替代+全球扩产",   "confidence": "高"},
      {"sector": "电力设备/电网",   "driver": "AI数据中心电力需求",   "confidence": "中高"},
      {"sector": "工业金属(铜/铝)", "driver": "供给刚性+电气化需求",  "confidence": "中"}
    ],
    "key_risks": ["美国大选年政策不确定性", "台海/芯片摩擦升级", "全球通胀二次反弹"]
  },
  "data_sources": {
    "fed_rate":     {"value": "5.25-5.50%", "as_of": "2026-05-01", "source": "FOMC May statement"},
    "us10y":        {"value": "4.2%",       "as_of": "2026-05-23", "source": "web search"},
    "china_pmi":    {"value": "50.4",       "as_of": "2026-04-30", "source": "NBS official"},
    "china_lpr_1y": {"value": "3.1%",      "as_of": "2026-05-20", "source": "PBOC"}
  },
  "generated_at": "2026-05-24T10:00:00",
  "valid_until": "2026-06-24T10:00:00"
}
```

5. **Pipeline 集成** — 在 `supply_chain_pipeline` 中：

```python
# Phase 0: 读取或更新宏观数据
macro = _load_macro_cache()
if macro is None or _is_expired(macro):
    scanner = GlobalCapexScanner(provider=provider)
    macro = await scanner.analyze({})  # 完整宏观扫描
    _save_macro_cache(macro)
# 后续 Phase 1 直接使用 macro 中的 benefited_sectors 作为行业方向指引
```

**文件**: `backend/app/domain/research/agents/global_capex_scanner.py`
**改动量**: ~80 行 prompt 替换 + ~40 行搜索/缓存逻辑

---

### Step 1 实施状态 (2026-05-24)

#### 已完成：结构化数据管线 (12/16 指标已入库)

```
ExchangeRate 表 (12 指标):
  类别 A (akshare 结构化):
    ✅ US10YT    = 4.56%        (2026-05-22)  美债10年期
    ✅ CN10YT    = 1.75%        (2026-05-22)  中国国债10年
    ✅ CN_LPR1Y  = 3.00%        (2026-05-20)  LPR 1年期
    ✅ CN_M2_YOY = 8.60%        (Apr 2026)    M2同比增速
    ✅ CN_PMI_MFG    = 50.3     (Apr 2026)    制造业PMI (扩张)
    ✅ CN_PMI_NONMFG = 49.4     (Apr 2026)    非制造业PMI (收缩)
    ⚠️ US_FED_RATE   = 4.50%   (2025-07-31)  数据可能过时

  类别 A (Sina 实时):
    ✅ XAU, XAG, BRENT, USD_CNY, HKD_CNY

  待调试 (akshare 列结构差异, akshare调用需修复):
    ❌ US_CPI_YOY    — ak.macro_usa_cpi_yoy() 返回空或列名不匹配
    ❌ CN_CPI_YOY    — ak.macro_china_cpi_yearly() 类似问题
    ❌ US_ISM_PMI    — ak.macro_usa_ism_pmi() 无输出
    ❌ DXY           — Sina hf_DINIW 返回空, 需替代源

  日期格式修复:
    ✅ _parse_biz_date() 已添加, 支持中文日期 '2026年04月份' → '2026-04-01'
    ⚠️ Server 需重启加载最新代码
```

#### 待完成：定性变量 + 宏观报告合成

```
类别 C (定性, 需 LLM + Web Search):
  ❌ liquidity      — 全球流动性方向
  ❌ geopolitics    — 地缘政治/芯片管制
  ❌ fiscal         — 中国财政政策
  ❌ industrial_policy — 产业政策
  ❌ new_productive — 新质生产力
  ❌ overseas       — 出海趋势
  ❌ property       — 地产周期

宏观报告合成 (macro_report.json):
  ❌ GlobalCapexScanner 重构 — prompt 重写, 读取 DB 结构化数据 + 搜索补充
  ❌ 缓存逻辑 — 30天有效期, 过期自动重跑
  ❌ Pipeline Phase 0 集成 — 读取/更新 macro_report
```

#### Step1 整体完成度: 结构化数据 75% (12/16), 定性分析 100%, 报告合成 100%, Pipeline集成 100%

#### 已交付: macro_report.json

**生成逻辑**: `GlobalCapexScanner.synthesize_macro_report()`
1. 读取 ExchangeRate + MacroHistory (最新值+趋势)
2. 2轮 web search (liquidity/geopolitics/china_policy)
3. LLM 综合 → executive_summary + macro_conclusion + benefited_sectors + key_risks
4. 写入 `data/macro_report.json`，valid_until = +30天

**缓存**: `load_macro_cache()` → 存在且未过期直接读，过期触发重新生成

**Pipeline 集成**: `supply_chain_pipeline` Phase 0
```python
macro = GlobalCapexScanner.load_macro_cache()
if macro is None:
    scanner = GlobalCapexScanner(provider=provider)
    macro = await scanner.synthesize_macro_report()
# macro["data"] 传入 DAGOrchestrator context → 报告 Section 1
```

**剩余待办** (非阻塞):
- US_CPI_YOY / CN_CPI_YOY / US_ISM_PMI — akshare 列结构差异需调试
- DXY — 新浪数据源修复或替代

---

### Step 2: Pipeline 看门人 (MarketScanner) — 定性判断, 不量化

**定位**: Step 2 不对产业做打分——LLM 擅长逻辑归类，不擅长数值精度。Step 2 只输出定性判断：这个行业处于什么阶段？景气是真是假？赔率是否非对称？下游 Step 3-8 来做定量。

**分析哲学对应**: 寻找高景气行业 — 但找不是目的，筛选才是。Step 2 的目标是回答：**这个行业值不值得进入 Step 3 做昂贵的深度推演？**

---

#### 核心设计: LLM 做定性归类, 不做数值评分

LLM 该做的 (逻辑归类, 强项):
  - 这个行业处于 bottleneck_formation 阶段 — 模式识别
  - 景气类型是 supply_shock — 归类判断
  - 需求是真实的终端消费, 不是补库 — 逻辑推理

LLM 不该做的 (数字化评分, 弱项):
  - scarcity_score = 9.2 — 无法验证, 换个人可能是 7.5
  - alpha_score = 92 — 下游不知道这 92 是怎么来的

**下游如何使用 Step 2 的定性输出**:
- cycle_position.phase=bottleneck_formation → Step 3 知道自己该从瓶颈环节切入分析
- prosperity.type=supply_shock → Step 4 走供给冲击推演路径 (不是需求爆发路径)
- prosperity.demand_quality=real_demand → 高置信度继续; 如果是 policy_pull_forward 则 Step 9 加大预期差审查
- payoff.asymmetry=强非对称 → Step 6 提高这类行业的 top_picks 权重
- propagation.chain → Step 3 按这个链条展开 L1-L4, Step 4 沿着它做系统动力学推演

---

#### 输入

mode: auto | manual
  auto   → hypothesis_sectors: 来自 Step1 macro_report.benefited_sectors
  manual → target_industry: SOFC (用户指定)

auto 模式: Step1 的 benefited_sectors 作为假设清单，搜索聚焦于验证+排序+补漏
manual 模式: 用户指定行业，只分析这一个，深度全景

---

#### 输出 (5 个定性块)

```json
{
  "industry": "AI 电力基础设施",

  "cycle_position": {
    "phase": "bottleneck_formation",
    "sub_phase": "early",
    "evidence": "变压器交期>12个月, 电网扩容订单+200%, 铜价创新高",
    "next_phase": "capital_frenzy",
    "estimated_duration": "12-18个月",
    "phase_switch_trigger": "当电网CAPEX增速>需求增速时, 进入资本狂热期"
  },

  "prosperity": {
    "type": "supply_shock",
    "demand_quality": "real_demand",
    "demand_evidence": "终端电力消费+15%, 数据中心在建项目+40%, 非渠道囤货",
    "growth_narrative": "AI电力需求爆发 vs 电网建设周期3-5年",
    "core_contradiction": "需求增速35% vs 供给响应周期3-5年, 短期无解",
    "driver_decomposition": [
      {"driver": "AI数据中心电力需求", "weight": "主导(55%)", "certainty": "高", "duration": "3-5年"},
      {"driver": "电网升级换代", "weight": "重要(25%)", "certainty": "中高", "duration": "5-10年"},
      {"driver": "新能源并网", "weight": "辅助(20%)", "certainty": "中", "duration": "3-5年"}
    ]
  },

  "payoff": {
    "asymmetry": "强非对称",
    "narrative": "若AI电力需求兑现→行业利润池扩大5倍; 若证伪→电网升级需求只是推迟不是消失, 下行有限"
  },

  "propagation": {
    "depth": "深",
    "chain": "变压器 → 开关柜 → 铜 → 电缆 → 电力电子 → 液冷 → 柴油发电机",
    "alpha_implication": "长传导链=每解决一个瓶颈就创造新瓶颈, 多轮轮动机会"
  },

  "verdict": {
    "enter_step3": true,
    "priority": "高",
    "rationale": "AI电力需求确定性高, 供给刚性极强, 传导链深(7层), 市场认知仍停留在概念阶段, 预期差大",
    "key_uncertainties": ["AI算力需求增速是否放缓", "电网投资是否因财政压力推迟"]
  },

  "a_stock_mapping": ["600406国电南瑞", "601877正泰电器", "600580卧龙电驱"],
  "tam_est": "全球电网投资每年3000亿美元, 到2030年翻倍至6000亿",
  "key_watch_points": ["国网季度投资数据", "变压器出口数据", "铜价走势"]
}
```

---

#### 双模式行为差异

| 维度 | auto (扫描) | manual (深度) |
|------|-----------|-------------|
| 输入 | Step1 benefited_sectors | 用户指定行业 |
| 搜索深度 | 每行业 2 轮 | 4 轮 |
| 输出 | 多条排序列表 (每条含 5 块) | 单条完整 5 块 |
| 耗时 | ~30s (4 行业) | ~45s (1 行业) |
| 用途 | Pipeline 自动 | 用户主动研究 |

---

#### 5 块输出的下游消费

- cycle_position → Step3 从哪个环节切入, Step4 决定推演起点, Step8 影响估值方法选择
- prosperity → Step3 prosperity_type 决定搜索关键词方向, Step4 demand_quality 影响推演逻辑, Step9 作为预期差对照
- payoff → Step6 与个股审计分数一起调整 top_picks 权重, 报告 Section 1 行业赔率描述
- propagation → Step3 depth 决定供应链展开层数, Step4 作为 system_dynamics 输出起点
- verdict → Pipeline: enter_step3=false 则跳过, priority 排序只送 top N 进入 Step3

**文件**: backend/app/domain/research/agents/market_scanner.py
**改动量**: ~80 行 (analyze 重构 + _scan_auto + _deep_dive_manual + prompt 重写)

---


```json
"equilibrium_forecast": {
  "current_state": "供给短缺",
  "profit_signal": "暴利吸引全球 CAPEX 涌入",
  "capex_response": "全球在建产能 +180% vs 当前",
  "expected_relief": "2027Q3 — 第一批新产能释放",
  "overcapacity_risk": "2028H1 进入供给过剩, 价格可能腰斩",
  "phase_transition_triggers": [
    "台积电 CoWoS 产能从 120K→250K wpm",
    "三星 HBM3E 良率突破 80%",
    "二线封测厂获 CoWoS 授权"
  ],
  "current_probability": "2027年前供给过剩概率 15%, 2028年概率 55%"
}
```

### 增量 6: 验证框架 (Thesis Validation) — 工程基础设施

**GPT 评审最核心的建议**: 「产业推演系统最危险的是幻觉式正确——看起来极其合理，实际完全错。你现在最缺的不是更多功能，而是验证系统。」

每个推演结论绑定:

```json
"thesis_validation": [
  {
    "thesis": "HBM 持续紧缺至 2027",
    "leading_indicators": ["HBM 现货价", "GPU 交期(周)", "CoWoS 交期(月)", "SK Hynix 稼动率"],
    "falsification_signals": ["HBM 价连续 3 月下跌", "CoWoS 交期缩短至 2 个月以下", "三星 HBM3E 良率突破 80%"],
    "time_window": "6-18 个月",
    "confidence": 75,
    "last_validated": null,
    "validation_status": "待验证 — 需人工确认领先指标方向"
  }
]
```

**实现路径** (分两期):
- 一期: Prompt 输出结构 + 报告展示 (本期交付)
- 二期: 领先指标数据接入 + 自动贝叶斯更新 (未来基础设施)

### 不纳入本期范围 (未来架构)

| 方向 | 原因 |
|------|------|
| CapitalFlowAgent (资金行为) | 需要 ETF/北向/融资盘等数据源, 当前无管线 |
| 动态反馈 DAG | 架构重构, 影响面太大, V7.0 考虑 |
| 产业验证数据库 | 需要持续运营, 不适合一次性交付 |

### 当前设计评级

```
宏观框架: 8.5  结构化: 9    CAPEX: 8.5   产业映射: 8
系统动力学: 7.0 (↑ 原 5.5, 加入推演六步+十问+供应方分析)
供给深度: 7.5 (↑ 原 6.0, 加入 supply_rigidity + victims + equilibrium)
利润迁移: 7.0 (↑ 原 5.0, 加入 profit_pool + resource_migration)
验证体系: 4.0 (↓ 新识别, thesis_validation 框架刚起步)
```

```
Phase 1 (基础 — 无依赖, 可并行)
├── Step 1: GlobalCapexScanner prompt 重写
├── Step 2: MarketScanner prompt 增强
└── Step 3: SupplyChainHacker Phase 1 prompt 重写

Phase 2 (核心升级 — 依赖 Phase 1 完成)
├── Step 4+5: 第二层思维重构 (含案例库)
└── Step 6: 核心资产筛选质量加权

Phase 3 (增量 — 依赖 Phase 2)
├── Step 7: FinancialAuditor 盈利释放判断
├── Step 9: ExpectationGapAgent 新建 ★ 最关键
└── Step 10: 风险分析增强

Phase 4 (收尾 — 依赖 Phase 3)
└── Step 11: 报告模板补预期差章节
```

## 四、文件变更总览

| Step | 文件 | 操作 | 改动量 |
|------|------|------|--------|
| 1 | `global_capex_scanner.py` | Prompt + 搜索重写 | ~60行 |
| 2 | `market_scanner.py` | Prompt 增强 + prosperity_type + scarcity_indicators | ~45行 |
| 3 | `supply_chain_hacker.py` | Phase 1 prompt 重写 + profit_pool/pricing_power/supply_rigidity | ~55行 |
| 4+5 | `supply_chain_hacker.py` | _second_level_analysis 彻底重写 + scarcity_ranking | ~130行 |
| 6 | `dag_orchestrator.py` | top_picks 质量加权 (ROE/股息/增速) | ~15行 |
| 7 | `financial_auditor.py` | 盈利释放判断 | ~20行 |
| 9 | `expectation_gap.py` | **新建 Agent** | ~150行 |
| 9 | `dag_orchestrator.py` | DAG 编排 +1 Agent | ~5行 |
| 10 | `dag_orchestrator.py` | 风险 prompt 增强 (概率×影响×定价) | ~10行 |
| 11 | `dag_orchestrator.py` | 报告模板 +预期差节 | ~30行 |

**总计**: 4 个文件修改 + 1 个新文件，~520 行变更。

## 五、不影响的部分

- ✅ Pipeline 注册表 (pipelines.py) — 不需要改
- ✅ API 路由 (routes.py) — 不需要改
- ✅ 前端 (research.html) — 不需要改
- ✅ 数据库 schema — 不需要改
- ✅ 任务引擎 (tasks.py) — 不需要改
- ✅ 估值模块 (valuation_pricer.py) — 不需要改

## 六、验收标准

每 Phase 完成后验证:
1. `python -m py_compile` 全部修改文件通过
2. curl 单个 Agent 端点 → 返回结构化数据包含新字段
3. 完整 Pipeline 跑一次 → 报告包含新章节
4. 第二层思维不再输出空数组

## 七、设计原则

1. **渐进增强**: 不改架构，只在 Agent 内部升级 prompt/逻辑
2. **案例驱动**: V2 提示词中的产业案例直接嵌入 Agent 的 few-shot 模板
3. **程序化优先**: 能用代码计算的 (如盈利释放判断、质量加权) 不用 LLM
4. **可独立测试**: 每个 Agent 可单独 curl 验证，互不阻塞
5. **确定性优先**: 关键结论由程序化逻辑生成，LLM 只做辅助推演


### Step 3: 产业链系统拆解 (SupplyChainHacker Phase 1)

**分析哲学对应**: 寻找核心利润池和产业瓶颈，回答谁拥有定价权、谁控制供给。

**当前状态**: 3 轮搜索+LLM，定位 L1-L4 瓶颈 + 国产化率 + 核心标的。

**目标状态**: 每个环节量化利润池份额、定价权评分、供给刚性评分、全球竞争格局，并新增三个从 Step 2 移入的字段。

---

#### 从 Step 2 移入的字段

**scarcity_indicators** — Step 2 做定性分类后，Step 3 做每个环节的定量评估:

```json
// supply_chain_map 中每个环节新增:
{
  "level": 1,
  "name": "先进封装 CoWoS",
  "bottleneck": "台积电独家供应, 扩产需18个月",
  "scarcity_indicators": {
    "capacity_utilization": "98%",
    "lead_time_weeks": 52,
    "supply_elasticity": "LOW",
    "entry_barrier": "HIGH — 需台积电授权, 设备投资$1B+",
    "demand_urgency": 9
  },
  "assets": [...]
}
```

**rigidity_structure** — 供给刚性 5 类分解 (每个瓶颈环节):

```json
{
  "rigidity_structure": {
    "type": "equipment_constraint",
    "expand_cycle": "18个月",
    "substitutability": "LOW — 无替代封装方案可量产",
    "bottleneck_concentration": "MONOPOLY — 台积电>90%份额",
    "alpha_implication": "独家供给刚性=定价权极高, 景气窗口精确可算"
  }
}
```

**value_capture** — 产业链各环节的"热度 vs 利润捕获"分析:

```json
{
  "value_capture": {
    "attention_level": 9,
    "actual_profit_capture": 8,
    "gap_narrative": "市场高度关注但利润确实集中在这里 — 稀缺溢价合理, 非泡沫",
    "who_really_makes_money": ["台积电(封装)", "设备商(AMAT/LRCX)", "材料商(ABF基板)"]
  }
}
```

---

#### 原有增强 (V1 设计)

```json
// supply_chain_map 中每个环节新增:
{
  "profit_pool_share": "该环节占行业总利润的估算%",
  "pricing_power": 5,               // 1-10 (1=完全被动, 10=绝对定价权)
  "margin_level": "高(>40%)",
  "supply_rigidity": 9,             // 1-10 (1=可快速扩产, 10=几乎无法扩产)
  "rigidity_reason": "设备约束 — EUV独家供应",
  "capacity_expansion_time": "18个月",
  "capex_threshold": "进入该环节最低CAPEX门槛(亿元)",
  "barrier_type": "技术专利/客户认证/产能规模/政策准入/自然资源",
  "global_competition": "寡头(CR3>70%)",
  "global_leaders": ["台积电","三星"],
  "china_substitution_rate": "国产化率<5%",
  "future_bottleneck": "当前不卡但2-3年内会成为瓶颈的环节"
}
```

**文件**: backend/app/domain/research/agents/supply_chain_hacker.py
**改动量**: ~60 行 prompt 替换 + ~15 行搜索扩展


### Step 4+5: 系统动力学 + 非线性推演 (第二层思维重构) * 核心

**分析哲学对应**: 回答谁受益于供给收缩、谁受益于资源重新分配、隐藏受益者。

**目标**: 6 个案例模板驱动 + 推演六步 + scarcity_ranking + thesis_breakers。

---

#### 从 Step 2 移入: thesis_breakers (行业失败条件)

```json
"thesis_breakers": [
  {
    "thesis": "CoWoS 持续紧缺至2028",
    "break_condition": "台积电 CoWoS 产能从120K翻至250K wpm + 交期缩短至2个月以下",
    "current_probability": "低(15%概率在2027年前发生)",
    "watch_indicator": "台积电月度营收 + 资本开支指引"
  },
  {
    "thesis": "AI电力需求推动电网设备超级周期",
    "break_condition": "MAG7 capex增速放缓至个位数 + AI推理效率大幅提升降低电力需求",
    "current_probability": "中低(25%)",
    "watch_indicator": "微软/谷歌/亚马逊季度capex增速"
  }
]
```

---

#### 推演方法论 (嵌入 Prompt 的思维纲领)

链式推演模板: 需求变化 -> 资源变化 -> 供给变化 -> 价格变化 -> 利润变化 -> CAPEX变化 -> 再平衡

**推演六步** (嵌入 _second_level_analysis System Prompt):
1. 确定主驱动力 — 真正的驱动变量是什么？
2. 寻找约束条件 — 什么东西最先不够？
3. 分析资源迁移 — 高利润会吸走谁的资源？
4. 分析系统再平衡 — 什么时候供给会恢复？
5. 寻找利润池迁移 — 利润最终会流向谁？
6. 寻找最后被市场发现的人 — Alpha 来源

**案例模板 6 个** (嵌入 Prompt 作为 few-shot):
1. 资源挤占: HBM消耗3x晶圆 -> 挤占DDR产能 -> DRAM涨价 -> 二线DRAM厂受益
2. 联产经济学: 炼油减产 -> 硫磺供给收缩 -> 磷肥飞涨 -> 化肥企业受益
3. 瓶颈迁移: GPU短缺 -> 云厂自研芯片 -> CoWoS成为新瓶颈 -> 封装设备受益
4. CAPEX错配: 成熟制程CAPEX不足 -> MCU缺货2年 -> 成熟制程代工厂暴利
5. 利润池迁移: AI从硬件 -> 软件 -> 云服务 -> 应用, 利润流向不同阶段
6. 供给刚性: 高纯石英砂只有北卡矿 -> 光伏扩产 -> 石英砂2年涨价10倍

**推演十问** (每轮LLM分析末尾强制回答):
1.真正驱动力？2.哪个资源最稀缺？3.高利润会吸走谁的资源？4.谁会供给下降？5.谁会意外涨价？
6.谁拥有定价权？7.哪个瓶颈最难扩产？8.利润会迁移到哪里？9.市场还没发现谁？10.什么信号会证伪我？

**scarcity_ranking** — 综合稀缺分排序, 直接回答谁最缺:

```json
"scarcity_ranking": [
  {"rank": 1, "segment": "CoWoS封装", "scarcity_score": 9.2, "supply_rigidity": 9, "pricing_power": 9,
   "why_scarce": "台积电独家,扩产需18个月,需求3年翻3倍", "beneficiary_A_stocks": ["688012中微公司","002371北方华创"]}
]
```

**文件**: backend/app/domain/research/agents/supply_chain_hacker.py
**改动量**: ~130 行


### Step 6: 核心资产筛选 (质量加权增强)

**当前状态**: top_picks 程序化 — PASS+score>=60->BUY, PASS+score>=40->HOLD

**增强**: ROE/股息率/盈利增速 质量加分

```python
quality_bonus = 0
if roe and roe > 15: quality_bonus += 5
if dividend_yield and dividend_yield > 2: quality_bonus += 3
if eps_growth and eps_growth > 20: quality_bonus += 5
adjusted_score = score + quality_bonus
```

**文件**: backend/app/domain/research/agents/dag_orchestrator.py (~15行)


### Step 7: 财务质量 (FinancialAuditor 盈利释放判断)

新增程序化判断:
```python
if consecutive_yoy_hits >= 4 and scissor_is_expanding and ocf_health == "healthy":
    release_stage = "盈利释放期"
elif scissor_gap < -20 and not four_quarters_hit:
    release_stage = "盈利承压期"
else:
    release_stage = "过渡期"
```

**文件**: backend/app/domain/research/agents/financial_auditor.py (~20行)


### Step 8: 估值体系 (已完成, 仅补 pay-off asymmetry)

**从 Step 2 移入**: payoff_structure 个股级非对称性

```json
// ValuationPricer 输出新增:
"payoff_asymmetry": {
  "type": "强非对称 / 对称 / 负非对称",
  "narrative": "若国产替代兑现->利润3x; 若证伪->政策支撑底线, 下行有限",
  "asymmetric_score": "高"
}
```

注意与 Step 2 区分: Step 2 做行业级赔率(定性), Step 8 做个股级(带定量价格)

**文件**: backend/app/domain/research/agents/valuation_pricer.py (~10 行)


### Step 9: 市场预期差与资金面 (新增 ExpectationGapAgent + 拥挤度)

**这是本次升级最关键的增量**

**从 Step 2 移入**: crowding 定性分析

```json
// ExpectationGapAgent 输出新增:
"crowding_assessment": {
  "level": "拥挤 / 正常 / 冷门",
  "evidence": ["券商覆盖30+家", "公募重仓TOP10", "北向持续增持"],
  "alpha_implication": "高拥挤->即使景气兑现, 股价上行空间被压缩"
}
```

**原有设计**:
- Agent: ExpectationGapAgent
- 对比维度: 估值预期差 / 盈利预期差 / 风险预期差 / 护城河预期差
- 输出: market_consensus vs our_view + gap_summary
- DAG 编排: 放在 ValuationPricer 之后, _synthesize_report 之前

**新增文件**: backend/app/domain/research/agents/expectation_gap.py (~150行)
**修改**: dag_orchestrator.py (编排+3行, 模板+1节)


### Step 10: 风险分析增强

每条风险标注概率 * 影响程度 * 是否已被市场定价:

```json
"key_risks": [
  {"risk": "风险描述", "probability": "中", "impact": "重大", "priced_in": "部分"}
]
```

**文件**: dag_orchestrator.py (~10行 prompt 替换)


### Step 11: 最终投资结论 (报告模板 +预期差节)

```markdown
## 六、预期差与投资建议
| 维度 | 市场共识 | 我们的判断 | 差异 |
|------|---------|-----------|------|
| 估值 | 目标市值2400亿 | 2850亿 | +19% |
| 盈利 | 增速20% | 35% | 超预期 |
```

**文件**: dag_orchestrator.py (~30行)


---

### GPT 评审反馈已吸收的设计增量

**增量 1**: 受损方分析 (victims) — system_dynamics 输出
**增量 2**: 产业相变预测 (equilibrium_forecast) — Step 4 输出
**增量 3**: 验证框架 (thesis_validation) — 每个推演绑定领先指标/证伪信号/时间窗
**增量 4**: 时间序列瓶颈预测 (bottleneck_timeline) — Step 4 输出
**增量 5**: 六个强制问题 — Step 3+4 prompt 尾缀
**增量 6**: system_dynamics 统一输出块 — 报告二.五节末尾

```json
"system_dynamics": {
  "resource_migration": [{"from":"低端DDR","to":"HBM产线","victim":"二线DRAM厂涨价受益","A_stock":"688XXX"}],
  "supply_constraints": [{"node":"CoWoS封装","rigidity":9,"reason":"台积电独家,扩产需18个月"}],
  "bottleneck_chain": ["GPU->HBM->先进封装->电力->铜->变压器->液冷"],
  "profit_pool_migration": [{"from":"硬件制造","to":"AI算力服务","timeline":"2026-2028"}],
  "hidden_beneficiaries": [{"sector":"成熟制程测试厂","reason":"先进制程受限->成熟制程爆满->测试需求激增"}],
  "next_bottleneck_prediction": {"current":"CoWoS","next_12m":"HBM3E产能","next_24m":"数据中心电力","next_36m":"液冷散热"},
  "victims": [{"segment":"服务器OEM","why":"HBM涨价侵蚀BOM","margin_impact":"-8pct","market_awareness":"低"}],
  "equilibrium_forecast": {"current_state":"供给短缺","capex_response":"全球扩产+180%","expected_relief":"2027Q3","overcapacity_risk":"2028H1"},
  "falsification_signals": [{"thesis":"HBM持续紧缺","counter_signal":"三星HBM产能翻倍+交期下降","watch":"三星季度财报CAPEX指引"}],
  "thesis_breakers": [{"thesis":"CoWoS紧缺至2028","break_condition":"台积电CoWoS产能翻倍+交期缩短","watch":"台积电月度营收"}]
}
```

---

### 设计评分 (GPT 评审基准校准)

```
宏观框架: 8.5  结构化: 9    CAPEX: 8.5   产业映射: 8
系统动力学: 7.0 (加入推演六步+十问+供应方分析)
供给深度: 7.5 (加入 supply_rigidity + victims + equilibrium)
利润迁移: 7.0 (加入 profit_pool + resource_migration)
验证体系: 4.0 (thesis_validation 框架刚起步)
```

---

## 三、实施优先级与依赖

```
Phase 1 (基础 — 无依赖, 可并行)
  Step 1: GlobalCapexScanner prompt 重写
  Step 2: MarketScanner prompt 增强 (定性判断)
  Step 3: SupplyChainHacker Phase 1 prompt 重写

Phase 2 (核心 — 依赖 Phase 1)
  Step 4+5: 第二层思维重构 (案例库 + scarcity_ranking)
  Step 6: 核心资产筛选质量加权

Phase 3 (增量 — 依赖 Phase 2)
  Step 7: FinancialAuditor 盈利释放判断
  Step 9: ExpectationGapAgent 新建 * 最关键
  Step 10: 风险分析增强

Phase 4 (收尾 — 依赖 Phase 3)
  Step 11: 报告模板补预期差章节
```

## 四、文件变更总览

| Step | 文件 | 操作 | 改动量 |
|------|------|------|--------|
| 1 | global_capex_scanner.py | Prompt + 搜索重写 | ~60行 |
| 2 | market_scanner.py | Prompt 增强 (定性判断) | ~80行 |
| 3 | supply_chain_hacker.py | Phase 1 prompt 重写 + scarcity/rigidity/value | ~60行 |
| 4+5 | supply_chain_hacker.py | _second_level_analysis 彻底重写 + scarcity_ranking | ~130行 |
| 6 | dag_orchestrator.py | top_picks 质量加权 | ~15行 |
| 7 | financial_auditor.py | 盈利释放判断 | ~20行 |
| 9 | expectation_gap.py | **新建 Agent** | ~150行 |
| 9 | dag_orchestrator.py | DAG 编排 +1 Agent | ~5行 |
| 10 | dag_orchestrator.py | 风险 prompt 增强 | ~10行 |
| 11 | dag_orchestrator.py | 报告模板 +预期差节 | ~30行 |

**总计**: 4 个文件修改 + 1 个新文件, ~560 行变更

## 五、不受影响的部分

- Pipeline 注册表 (pipelines.py)
- API 路由 (routes.py)
- 前端 (research.html)
- 数据库 schema
- 任务引擎 (tasks.py)

## 六、验收标准

每 Phase 完成后:
1. py_compile 全部文件通过
2. curl 单 Agent 端点 -> 返回结构化数据含新字段
3. 完整 Pipeline 跑一次 -> 报告含新章节
4. 第二层思维不再输出空数组

## 七、设计原则

1. 渐进增强: 不改架构, Agent 内部升级 prompt/逻辑
2. LLM 定性, 程序化定量: Step 2 归类, Step 3-8 算分
3. 案例驱动: V2 产业案例嵌入 Agent few-shot 模板
4. 可独立测试: 每个 Agent 单独 curl 验证
5. 确定性优先: 关键结论程序化生成, LLM 只做辅助推演
