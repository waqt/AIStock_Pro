# Step 2: Pipeline 看门人 (MarketScanner V5.11)

## 0. 文档版本

| 版本 | 日期 | 改动说明 | 作者 |
|------|------|---------|------|
| V5.8 | 2026-04 | 初版: 6块定性 + 双模式 | - |
| V5.11 | 2026-05 | 合并V5.9-5.11: 证据层结构化 + industry_granularity + mismatch_analysis 五错配矩阵 + thesis_killers + 路径推荐算法 + profit_redistribution 方向 | Claude |

---

## 1. 定位

Step 2 是整个 Pipeline 的入口过滤器。它不替代 Step 3-11 做深度分析，只回答一个问题：

> 这个行业值不值得进入 Step 3，花几分钟做昂贵的产业链拆解 + 审计 + 估值？

如果值得，**走哪条路径**进入：

| 路径 | 代码 | 场景 | 对应 API |
|------|------|------|---------|
| 直接资产挖掘 | A | 产业逻辑硬 + 认知已定价 → 跳过产业链深挖，直接从 transmission_order 节点挖标的 | `POST /direct-asset-mine` |
| 二阶推演 | B | 主产业弱 + 存在跨产业溢出潜力 → 外推相邻产业预期差 | `POST /second-order-extrapolate` |
| 产业链深挖 | C | 认知差强 → 走标准全链路 Step 3→4→5→6 | `POST /scan/industry-drilldown` |
| 跳过 | KILL | 无基本面基础/investable_exposure=none → 不处理 | - |

---

## 2. 核心原则

### 2.1 五错配框架

只有同时满足以下条件的行业才值得进入深度推演：

| 维度 | 键名 | 核心问题 | LLM 取值 |
|------|------|---------|---------|
| 供需错配 | `supply_demand_mismatch` | 需求增速 > 供给响应速度？ | strong/moderate/weak/uncertain |
| 时间错配 | `timing_mismatch` | 扩产周期远长于需求爆发周期？ | same |
| 认知错配 | `expectation_gap` | 市场尚未理解产业变化深度？ | same |
| 利润迁移 | `profit_redistribution` | 利润正在从一个环节流向另一个？ | `{strength, direction}` |
| 定价错配 | `pricing_gap` | 估值未反映上述错配？ | same |

缺少任何一条 strong，enter_step3 应为 false。

### 2.2 证据质量分级 (V5.9+)

每条 evidence 必须标注质量等级：

| 属性 | 取值 | 说明 |
|------|------|------|
| `quality.level` | high/medium/low | 证据的可信度 |
| `quality.source_type` | 见下表 | 证据来源分类 |

**source_type 枚举 (从高到低低依靠权重)：**

| source_type | 含义 | 裁决权重 |
|-------------|------|---------|
| `company_filing` | 公司财报/公告 | 最高 |
| `industry_data` | 海关/行业协会/产能统计 | 最高 |
| `official_policy` | 政府文件/产业规划 | 高 |
| `sell_side_report` | 券商研报 | 中 |
| `news_media` | 财经媒体 | 低 |
| `self_media` | 自媒体/知乎/公众号 | 仅参考 |
| `ai_summary` | AI 摘要 | 仅参考 |

**裁决约束：**
- 优先采信 `level=high` + `source_type=company_filing/industry_data/official_policy` 的证据
- `self_media/ai_summary` 不得单独支撑 enter_step3 或 priority 判断
- 如果某结论的高质量证据全部缺失，必须在 rationale 中标注"证据质量不足"

### 2.3 禁止输出数字评分

LLM 输出数值不可靠（换 prompt 或 temperature，scarcity_score 可能从 9.2 变 7.5）。Step 2 只输出定性标签。需要量化的指标交给 Step 3-8 用程序化逻辑或 DB 数据计算。

| ❌ 禁止 | ✅ 允许 |
|---------|---------|
| `"scarcity_score": 9.2` | `"phase": "bottleneck_formation"` |
| `"alpha_score": 92` | `"expectation_gap": "strong"` |
| `"risk_level": "HIGH"` | `"priority": "高"` |

---

## 3. 输入

### 3.1 API 入口

```python
POST /api/research/scan?mode=auto
POST /api/research/scan?mode=manual
```

### 3.2 Request Body

```json
// auto 模式 — Pipeline 自动扫描
{
  "mode": "auto",
  "hypothesis_sectors": [
    {"sector": "AI算力基础设施", "confidence": "高", "driver": "MAG7 capex $700B+"},
    {"sector": "半导体设备", "confidence": "高", "driver": "国产替代+全球扩产"}
  ]
}

// manual 模式 — 用户指定单一行业
{
  "mode": "manual",
  "target_industry": "SOFC"
}

// 旧版零参数 (fallback, 逐渐弃用)
{}
```

### 3.3 依赖的外部数据

| 数据 | 来源 | 用途 |
|------|------|------|
| Web 搜索结果 | Brave Search (通过 Clash 代理) | 行业基本面事实依据 |
| 宏观数据 | `data_loader.load_macro()` | cycle_position 的背景参考 |
| 术语表 | `glossary.step2_glossary()` | 注入 10 组枚举定义到 LLM prompt |
| Step 1 预判 (可选) | `hypothesis[].sector` + `driver` | 提供 Step 1 的分析起点 |

### 3.4 Pipeline 调用方式 (auto 模式入口)

```python
# 在 dag_orchestrator.py 或 route handler 中:
from app.domain.research.agents.market_scanner import MarketScanner
scanner = MarketScanner(provider=deepseek_provider)
result = await scanner.analyze({
    "mode": "auto",
    "hypothesis_sectors": [...],
}, trace=trace_context)
```

---

## 4. 内部逻辑

### 4.1 执行流程

```
analyze()
├─ mode == "manual" → _deep_dive_manual()
│   └─ 4轮自适应搜索 → LLM评估 → _build_step3_guidance()
├─ mode == "auto"   → _scan_auto()
│   └─ 对于每个 hypothesis[:5]:
│       2轮搜索 → LLM评估 → _build_step3_guidance()
│   └─ _deduplicate_industries() → 按 priority 排序
└─ mode == "legacy" → _collect_signals() → _identify_hot_industries() → _generate_briefing()
```

### 4.2 搜索策略

**auto 模式 (每行业 2 轮)：**
```
轮次 1: "{industry} 景气度 增速 供需 产能 2026"
轮次 2: "{industry} 产能利用率 CAPEX 扩产周期 龙头订单 2026"
```

**manual 模式 (4 轮)：**
```
轮次 1: "{industry} 行业概况 市场规模 TAM 增速 2026"
轮次 2: "{industry} 供需缺口 产能利用率 交期 CAPEX 扩产周期 2026"
轮次 3: "{industry} 竞争格局 政策环境 国产化率 全球份额 2026"
轮次 4: "{industry} 产业链 上游 下游 传导 瓶颈 成本结构 2026"
```

**自适应降级：** 每轮配置多条 query chain，前一条 0 结果时自动换更简化的 query 重试。

**后处理：**
- `_clean_snippet()` — 过滤 PDF 二进制、HTML 标签、控制字符，截断 250 字符
- 所有 query 带当前年份 (如 `2026`)

### 4.3 LLM Prompt 结构

Prompt 由以下部分组成（按顺序）：

1. **角色定义** — 买方资本配置分析师，Pipeline Gatekeeper
2. **核心原则** — 五错配定义
3. **Step 1 预判信息** — hypothesis 内容
4. **搜索结果** — 格式化嵌入 search_data
5. **输出 schema** — 7 块 JSON 模板（industry_granularity + cycle_position + prosperity + payoff + propagation + time_horizon + mismatch_analysis + thesis_killers + verdict + kill_reasons + catalysts）
6. **粒度判定规则** — industry_granularity 4 分类
7. **证据质量规则** — source_type 枚举 + 裁决权重
8. **证据降权规则** — 低质量证据约束
9. **错配取值** — strong/moderate/weak/uncertain 定义
10. **profit_redistribution.direction** — 4 方向枚举
11. **thesis_killers** — 3 子字段 + 降级规则
12. **同质化避免** — also_supports 机制
13. **行为约束** — rationale 需引用具体 mismatch/标准 kill_reason 枚举
14. **术语注入** — `step2_glossary()` 自动注入 10 组枚举定义

模型：`deepseek-v4-flash`（简单分类任务，不需要 pro 的 thinking 能力）
max_tokens: 6144，超时 90s

### 4.4 行业去重 (V5.9+)

`_deduplicate_industries()` 处理父子行业同时出现的情况：

```python
SUBSECTOR_MAP = {
    "电网设备": ["变压器", "开关设备", "配电自动化", "电力电子"],
    "半导体": ["封装", "刻蚀", "光刻", "存储", "先进封装", "半导体设备", "半导体材料"],
    # ...
}
```

如果父行业和子行业同时出现在结果集中，保留子行业（更具体可操作），剔除父行业。

### 4.5 路径推荐算法 (V5.10+) ⭐

`_recommend_path(ma, cycle_phase, mkt_repricing, thesis_killers)` 实现确定性决策树：

```
                    ┌─ investable_exposure=none ──→ KILL (high)
                    │
  thesis_killers  ──┤
                    └─ S in (weak, uncertain) ──→ KILL (high)
                    │
                    └─ E == strong ──┐
                                     │ cycle_phase 调制:
                                     │   theme_emergence    → high_priority ⭐⭐
                                     │   bottleneck_formation → high ⭐
                                     │   capital_frenzy     → medium [警告]
                                     │   demand_explosion   → high ⭐
                                     │ mkt_repricing 调制:
                                     │   晚期 → -1 级
                                     │   早期 → boost
                                     │ tk 降级:
                                     │   substitution/policy high → -1 级
                                     │   investable_exposure=limited → -1 级
                                     └─→ Path C (high/medium)
                    │
                    └─ E == weak + S == strong + P == strong ──┐
                                     │ D == weak  → A (medium)
                                     │ D == strong → A (high) ⭐
                                     │ D == uncertain → A (medium)
                                     └─→ Path A
                    │
                    └─ S == strong + P in (weak, moderate) ──→ Path B (low)
                    │
                    └─ Fallback ──→ Path B/C (low)
```

**优先级链**: thesis_killers(investable_exposure=none → KILL) > KILL ≥ Path C > Path A > Path B

**cycle_phase 对 E=strong 的语义影响：**

| cycle_phase | E=strong 的真实含义 | confidence 调整 |
|-------------|-------------------|----------------|
| theme_emergence | 主题刚浮现，市场根本还没看 | high_priority ⭐⭐ |
| bottleneck_formation | 形成期+认知差，预期差最大 | high ⭐ |
| demand_explosion | 需求爆发但没人看懂 | high ⭐ |
| capital_frenzy | 狂热期认知差可能是假象 | medium [⚠️] |
| capacity_release | 产能释放中，认知差可能是反向指标 | medium/low |
| commoditization | 商品化阶段，认知差危险 | low |

**market_repricing_stage 调节：**

| stage | 对 Path C 影响 | 对 Path A 影响 |
|-------|---------------|---------------|
| 早期 | confidence +1 级 | 无 |
| 中期 | 不变 | 无 |
| 晚期 | confidence -1 级 | 下调至 medium |

### 4.6 _step3_guidance 输出 (V5.10+)

`_build_step3_guidance()` 聚合 LLM 输出为下游可消费的结构化决策指引：

```python
{
    "industry_name_for_search": str,          # 供 Step 3 搜索用
    "cycle_phase": str,                       # 周期阶段
    "cycle_meaning": str,                     # 阶段含义指引
    "prosperity_type": str,                   # 景气类型
    "prosperity_meaning": str,                # 分析框架指引
    "propagation_depth": str,                 # 传导深度
    "enter_step3": bool,                      # 是否进入 Step 3
    "priority": str,                          # 优先级别
    "mismatch_summary": str,                  # "S=strong/T=moderate/E=weak/..."
    "recommended_path": {                     # 路径推荐
        "path": "A|B|C|KILL",
        "confidence": "high|medium|low|high_priority",
        "rationale": "...",
        "highlight": bool,
        "cycle_phase_modulation": "...",
        "mismatch_status": "..."
    },
    "profit_redistribution_detail": {
        "strength": "strong",
        "direction": "upstream"
    },
    "thesis_killers": {...},                  # 原始 thesis_killers
    "market_repricing_stage": str,            # 重新定价阶段
    "industry_granularity": str,              # industry_granularity.type
    "search_focus": str,                      # 给 Step 3 的搜索指引
    "key_uncertainties": [...],
    "core_contradiction": str
}
```

---

## 5. 输出

### 5.1 完整 JSON Schema

```json
{
  // ═══ 元信息 ═══
  "agent": "MarketScanner",
  "mode": "auto|manual",

  // ═══ 块 0: 粒度判定 (V5.9+) ═══
  "industry": "AI算力基础设施",

  "industry_granularity": {
    "type": "specific_industry|subsector|macro_theme|asset_class",
    "action": "allow|skip|split_or_skip",
    "reason": "判定理由"
  },
  // 粒度判定标准:
  //   specific_industry (CoWoS/HBM/SOFC) → action=allow
  //   subsector (AI算力/半导体设备) → action=allow, 以最具错配特征的子环节为准
  //   macro_theme (新质生产力/碳中和) → action=split_or_skip, enter_step3=false
  //   asset_class (黄金ETF/REITs) → action=skip, enter_step3=false

  // ═══ 块 1: 周期定位 ═══
  "cycle_position": {
    "phase": "theme_emergence|demand_explosion|bottleneck_formation|capital_frenzy|capacity_release|commoditization",
    "sub_phase": "early|mid|late",
    "evidence": [
      {"fact": "transformer lead time > 52 weeks", "from": "search[1.2]·行业报告",
       "quality": {"level": "high", "source_type": "industry_data"}}
    ],
    "next_phase": "...",
    "estimated_duration": "12-18个月",
    "phase_switch_trigger": "当XXX发生时进入下一阶段..."
  },

  // ═══ 块 2: 景气验证 ═══
  "prosperity": {
    "type": "demand_explosion|supply_shock|policy_driven|replacement_cycle|capex_cycle|inventory_cycle",
    "demand_quality": "real_demand|inventory_restock|policy_pull_forward|channel_stuffing",
    "demand_evidence": [
      {"fact": "AI数据中心在建项目+40%", "from": "search[2.3]·行业报告",
       "quality": {"level": "high", "source_type": "industry_data"}}
    ],
    "growth_narrative": "需求爆发 vs 供给刚性 → 缺口持续到2028",
    "core_contradiction": "需求增速35% vs 供给响应周期3-5年",
    "driver_decomposition": [
      {"driver": "AI数据中心电力需求",
       "weight": "主导|重要|辅助",
       "certainty": "高|中|低",
       "duration": "3-5年",
       "leading_indicator": "MAG7 capex",
       "evidence": [
         {"fact": "...", "from": "search[1.1]·...",
          "quality": {"level": "high", "source_type": "company_filing"}}
       ]}
    ]
  },

  // ═══ 块 3: 赔率判断 ═══
  "payoff": {
    "asymmetry": "强非对称|对称|负非对称",
    "narrative": "若兑现→利润5x; 若证伪→需求只是推迟非消失",
    "evidence": [
      {"fact": "...", "from": "search[3.1]·公司公告",
       "quality": {"level": "high", "source_type": "company_filing"}}
    ]
  },

  // ═══ 块 4: 传导链预判 ═══
  "propagation": {
    "depth": "深|中|浅",
    "transmission_order": [
      {"stage": 1, "node": "环节名", "reason": "最先受益的原因",
       "evidence": [{"fact": "...", "from": "search[...]·...",
         "quality": {"level": "medium", "source_type": "news_media"}}]}
    ],
    "last_beneficiary": "最后受益环节",
    "last_bottleneck": "最后解决/约束最强的环节",
    "alpha_implication": "先配X中期Y后期Z"
  },

  // ═══ 块 5: 时间维度 ═══
  "time_horizon": {
    "alpha_window": "6-12个月",
    "profit_expansion_window": "12-24个月",
    "capacity_relief_eta": "2028H1",
    "market_repricing_stage": "早期|中期|晚期",
    "evidence": [
      {"fact": "...", "from": "search[...]·...",
       "quality": {"level": "medium", "source_type": "sell_side_report"}}
    ]
  },

  // ═══ 块 6: 五错配矩阵 ═══
  "mismatch_analysis": {
    "supply_demand_mismatch": "strong|moderate|weak|uncertain",
    "timing_mismatch": "strong|moderate|weak|uncertain",
    "expectation_gap": "strong|moderate|weak|uncertain",
    "profit_redistribution": {
      "strength": "strong|moderate|weak|uncertain",
      "direction": "upstream|midstream|downstream|分散"
    },
    // ↑ V5.10+ 双格式兼容: 旧checkpoint 中 profit_redistribution 可能为纯字符串 "strong"
    "pricing_gap": "strong|moderate|weak|uncertain",
    "evidence": [
      {"fact": "支撑各维度判断的关键事实", "from": "search[X.Y]·来源",
       "quality": {"level": "high", "source_type": "industry_data"}}
    ]
  },

  // ═══ 块 6b: 论文杀手 (V5.10+, 独立于五错配) ═══
  "thesis_killers": {
    "substitution_risk": "low|medium|high",
    "policy_block_risk": "low|medium|high",
    "investable_exposure": "sufficient|limited|none",
    "details": "解释性文字"
  },
  // 即使 S+T+E+P+$ 全 strong, 如果 thesis_killers 有高风险, verdict 应降级。

  // ═══ 块 7: 最终判断 ═══
  "verdict": {
    "enter_step3": true|false,
    "priority": "高|中|低|跳过",
    "rationale": "引用 mismatch_analysis 具体结果 + 综合判断",
    "key_uncertainties": ["不确定性1"],
    "evidence": [
      {"fact": "支撑 verdict 的关键事实", "from": "search[X.Y]·...",
       "quality": {"level": "high", "source_type": "industry_data"}}
    ]
  },

  // ═══ 块 8: 拒绝理由 (enter_step3=false 时必需) ═══
  "kill_reasons": [
    {"reason": "需求来自渠道补库存|已进入资本狂热后期|估值透支3年增长|"
               "政策抢装非真实需求|供给扩张>需求|传导链<3层Alpha空间有限",
     "monitor_signal": "什么指标变化会触发证伪",
     "data_source_hint": "可从哪获取这个指标"}
  ],

  // ═══ 块 9: 催化事件 ═══
  "catalysts": [
    {"type": "earnings|product|policy|capacity|order",
     "catalyst": "催化事件描述",
     "expected_date": "预计发生时间",
     "watch_signal": "什么数据确认催化兑现",
     "status": "pending"}
  ],

  // ═══ Step 2 → Step 3 决策指引 (程序化生成, V5.9+) ═══
  "_step3_guidance": {
    "industry_name_for_search": "...",
    "cycle_phase": "...",
    "cycle_meaning": "...",
    "prosperity_type": "...",
    "prosperity_meaning": "...",
    "propagation_depth": "深",
    "enter_step3": true,
    "priority": "高",
    "mismatch_summary": "S=strong/T=moderate/E=weak/P=strong/$=uncertain",
    "recommended_path": {
      "path": "A|B|C|KILL",
      "confidence": "high|medium|low|high_priority",
      "rationale": "...",
      "highlight": true|false,
      "cycle_phase_modulation": "...",
      "mismatch_status": "..."
    },
    "profit_redistribution_detail": {
      "strength": "strong",
      "direction": "upstream"
    },
    "thesis_killers": {},
    "market_repricing_stage": "早期|中期|晚期",
    "industry_granularity": "specific_industry|subsector|...",
    "search_focus": "周期阶段=... → 搜索建议...; 景气类型=... → 分析框架...",
    "key_uncertainties": [],
    "core_contradiction": ""
  }
}
```

### 5.2 auto 模式包装

```json
{
  "agent": "MarketScanner",
  "mode": "auto",
  "industries": [{...}, {...}],   // 按 priority 排序
  "count": 5
}
```

### 5.3 manual 模式返回

```json
{
  "agent": "MarketScanner",
  "mode": "manual",
  "industry": "SOFC",
  // ... 所有 7+ 块 ...
  "_step3_guidance": {...}
}
```

---

## 6. 向后兼容 (V5.10+)

### 6.1 profit_redistribution 双格式

旧 checkpoint（V5.9 之前）的 `profit_redistribution` 为纯字符串 `"strong"`。V5.10+ 改为 dict `{"strength": "strong", "direction": "upstream"}`。

处理代码 (`_recommend_path()` + `_build_step3_guidance()`):

```python
P_raw = ma.get("profit_redistribution", "uncertain")
if isinstance(P_raw, str):
    P_strength = P_raw
    P_direction = "unknown"
elif isinstance(P_raw, dict):
    P_strength = P_raw.get("strength", "uncertain")
    P_direction = P_raw.get("direction", "unknown")
else:
    P_strength = "uncertain"
    P_direction = "unknown"
```

### 6.2 缺失 thesis_killers

当旧 checkpoint 无 `thesis_killers` 字段时，默认值：

```python
tk_default = {
    "substitution_risk": "uncertain",
    "policy_block_risk": "uncertain",
    "investable_exposure": "uncertain"
}
```

`_recommend_path()` 收到空/None tk 时不会触发任何 thesis_killers 相关的降级或 KILL。

### 6.3 缺失 recommended_path

旧 checkpoint 无 `_step3_guidance.recommended_path`。前端渲染时显示"无推荐"。

---

## 7. 下游消费关系

### 7.1 消费的上游

| 来源 | 提供 | 用途 |
|------|------|------|
| Step 1a (Macro) | `macro_report.benefited_sectors` | auto 模式的候选行业清单 |
| Step 1a (Macro) | `macro_report.macro_conclusion` | 宏观背景注入 prompt |
| Step 1b (CapitalFlow) | `capex_vectors + constraint_vectors` | 通过用户手动选择触发扫描 |

### 7.2 提供给下游

| 消费方 | 字段 | 用途 |
|--------|------|------|
| Pipeline 路由 | `_step3_guidance.recommended_path` | 决定走 Path A/B/C |
| Pipeline 路由 | `verdict.enter_step3` | false → 跳过该行业 |
| Step 3 (SupplyChain) | `propagation.transmission_order` | L1-L4 展开顺序骨架 |
| Step 3 (SupplyChain) | `_step3_guidance.search_focus` | 搜索方向指引 |
| Step 3 (SupplyChain) | `_step3_guidance.cycle_phase` | 景气阶段上下文 |
| Step 4 (SysDynamics) | `prosperity.type` | 决定推演路径 |
| Step 4 (SysDynamics) | `cycle_position.phase` | 走对应阶段模板 |
| Step 4 (SysDynamics) | `propagation.transmission_order` | 沿链条推演 |
| Step 6 (Screening) | `payoff.asymmetry` | 提高/降低权重 |
| Step 6 (Screening) | `_step3_guidance.profit_redistribution_detail.direction` | 选取利润集中环节 |
| Step 8 (HumanCapital) | `cycle_position.phase` | 估值方法选择参考 |
| Step 9 (Expectation) | `prosperity.demand_quality` | 预期差审查 |
| 观察框架 | 所有 `evidence` + `thesis_killers` + `recommended_path` | 提取为观察条目 |

---

## 8. 故意不做的事

| 建议 | 拒绝理由 | 正确归属 |
|------|---------|---------|
| 资本市场状态 (crowding/ownership) | Step 2 只有 web search，无法获取 ETF持仓/机构配置数据 | Step 9 ExpectationGapAgent |
| 共识状态 (market_attention/consensus) | 需要券商覆盖数据、卖方评级分布 | Step 9 |
| supply_rigidity 评分/利润率分布 | Step 2 不做定量计算 | Step 3 SupplyChainHacker |
| 估值定价 (PE/PB/EV) | Step 2 不做数值计算 | Step 6/8 ValuationPricer |
| 财务审计 (8Q/Beneish) | 需要详细财报数据 | Step 7 FinancialAuditor |

---

## 9. 实现

### 9.1 文件

```python
backend/app/domain/research/agents/market_scanner.py
```

### 9.2 方法清单

| 方法 | 角色 | 访问 |
|------|------|------|
| `analyze()` | 主入口，根据 mode 分派 | public async |
| `_scan_auto()` | auto 模式：候选行业→搜索→评估→排序 | private async |
| `_deep_dive_manual()` | manual 模式：4 轮搜索→深度全景 | private async |
| `_evaluate_industry()` | LLM 评估：构建 prompt → 调用 flash → 解析 JSON | private async |
| `_search_with_fallback()` | 自适应搜索：query chain 逐级降级 | private async |
| `_clean_snippet()` | 搜索结果清洗：过滤 PDF/HTML/控制字符 | static |
| `_deduplicate_industries()` | 父子行业去重 | static |
| `_recommend_path()` | **★ 五错配→路径推荐决策树** | static |
| `_build_step3_guidance()` | 构建下游决策指引（含推荐路径） | static |
| `_collect_signals()` / `_identify_hot_industries()` / `_generate_briefing()` | Legacy 零参数扫描模式 | private async |

### 9.3 配置

| 参数 | 值 | 说明 |
|------|-----|------|
| 每次搜索请求条目数 | 3-4 | `num` 参数 |
| LLM 模型 | `deepseek-v4-flash` | 简单分类任务 |
| max_tokens | 6144 | 输出 7+ 块 JSON |
| 超时 | 90s | 单个行业评估 |
| auto 模式最大行业数 | 5 | `hypothesis_sectors[:5]` |
| glossary 注入类别 | 10 组 | 见 `step2_glossary()` |

### 9.4 依赖

```python
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.pipeline.glossary import step2_glossary
from app.framework.logger import logger
```

---

## 10. 验证清单

### 10.1 语法与导入

- [ ] `python -m py_compile market_scanner.py` 通过
- [ ] `python -c "from app.domain.research.agents.market_scanner import MarketScanner"` 通过

### 10.2 API 验证

```bash
# auto 模式
curl -s "http://127.0.0.1:8000/api/research/scan" \
  -H "Content-Type: application/json" \
  -d '{"mode":"auto","hypothesis_sectors":[{"sector":"SOFC","confidence":"高"}]}' | \
  python -c "import json,sys; d=json.load(sys.stdin); assert d['mode']=='auto'; assert len(d['industries'])>0; print('PASS')"

# manual 模式
curl -s "http://127.0.0.1:8000/api/research/scan" \
  -H "Content-Type: application/json" \
  -d '{"mode":"manual","target_industry":"SOFC"}' | \
  python -c "import json,sys; d=json.load(sys.stdin); assert d['mode']=='manual'; assert 'cycle_position' in d; print('PASS')"
```

### 10.3 输出验证

- [ ] `verdict.priority` 为定性标签（"高"/"中"/"低"），不出现数字分数
- [ ] 每条 evidence 有 `quality.level` + `quality.source_type`
- [ ] `profit_redistribution` 为 dict（新）或 str（旧）均不报错
- [ ] `_step3_guidance.recommended_path.path` 为 A/B/C/KILL 之一
- [ ] `thesis_killers` 存在（新生成）或缺失（旧 checkpoint）均不报错

### 10.4 前端联动

- [ ] 行业列表展示每个行业的详情 📊 按钮
- [ ] 点击后展示五错配颜色矩阵 + 路径徽章 + thesis_killer 标签
- [ ] 路径徽章颜色: A=蓝 B=紫 C=绿 KILL=红
