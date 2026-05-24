# Step 2: Pipeline 看门人 (MarketScanner)

## 1. 定位

Step 2 是整个 Pipeline 的入口过滤器。它不替代 Step 3-11 做深度分析，只回答一个问题：

> 这个行业值不值得进入 Step 3，花 3 分钟做昂贵的产业链拆解 + 审计 + 估值？

决策依据不是"这个行业好不好"，而是"这个行业是否存在值得深挖的 Alpha 潜力"。

---

## 2. 输入

### 来源: Step 1 macro_report

```json
// auto 模式 — Pipeline 自动
{
  "mode": "auto",
  "hypothesis_sectors": [
    {"sector": "AI算力基础设施", "confidence": "高", "driver": "MAG7 capex $700B+"},
    {"sector": "半导体设备",      "confidence": "高", "driver": "国产替代+全球扩产"},
    {"sector": "电力设备",       "confidence": "中高", "driver": "AI数据中心电力需求"},
    {"sector": "工业金属",       "confidence": "中",   "driver": "供给刚性+电气化"}
  ]
}

// manual 模式 — 用户指定
{
  "mode": "manual",
  "target_industry": "SOFC"
}
```

---

## 3. 输出

### 3.1 输出格式

每个候选行业输出一个 JSON 对象，包含 5 个定性块。auto 模式输出多条（排序列表），manual 模式输出单条（深度全景）。

```json
{
  "industry": "AI 电力基础设施",

  // ═══ 块 1: 周期定位 ═══
  "cycle_position": {
    "phase": "bottleneck_formation",
    // theme_emergence | demand_explosion | bottleneck_formation | capital_frenzy | capacity_release | commoditization
    "sub_phase": "early",
    // early | mid | late
    "evidence": "变压器交期>12个月, 电网扩容订单YoY+200%, 铜价创新高",
    // 支持此阶段判断的具体证据（必须引搜索结果）
    "next_phase": "capital_frenzy",
    "estimated_duration": "12-18个月",
    "phase_switch_trigger": "当电网CAPEX增速超过需求增速时, 进入资本狂热期"
  },

  // ═══ 块 2: 景气验证 ═══
  "prosperity": {
    "type": "supply_shock",
    // demand_explosion | supply_shock | policy_driven | replacement_cycle | capex_cycle | inventory_cycle
    "demand_quality": "real_demand",
    // real_demand | inventory_restock | policy_pull_forward | channel_stuffing
    "demand_evidence": "终端电力消费+15%, 数据中心在建项目+40%, 非渠道囤货",
    // 支持需求真实性判断的证据
    "growth_narrative": "AI电力需求爆发 vs 电网建设周期3-5年 → 供需缺口至少持续到2028",
    "core_contradiction": "需求增速35% vs 供给响应周期3-5年, 短期无解, 涨价压力持续",
    // 行业当前最核心的矛盾是什么
    "driver_decomposition": [
      {"driver": "AI数据中心电力需求", "weight": "主导", "certainty": "高", "duration": "3-5年", "leading_indicator": "MAG7 capex"},
      {"driver": "电网升级换代", "weight": "重要", "certainty": "中高", "duration": "5-10年", "leading_indicator": "国网投资计划"},
      {"driver": "新能源并网", "weight": "辅助", "certainty": "中", "duration": "3-5年"}
    ]
    // weight: 主导 | 重要 | 辅助 — 不做数字百分比
  },

  // ═══ 块 3: 赔率判断 ═══
  "payoff": {
    "asymmetry": "强非对称",
    // 强非对称 | 对称 | 负非对称
    "narrative": "若AI电力需求兑现→行业利润池扩大5倍; 若证伪→电网升级需求只是推迟不是消失, 下行有限"
  },

  // ═══ 块 4: 传导链预判 ═══
  "propagation": {
    "depth": "深",
    // 深(>5层) | 中(3-5层) | 浅(<3层)
    "chain": "变压器 → 开关柜 → 铜 → 电缆 → 电力电子 → 液冷 → 柴油发电机",
    "alpha_implication": "长传导=每解决一个瓶颈就创造新瓶颈, 多轮轮动机会"
  },

  // ═══ 块 5: 最终判断 ═══
  "verdict": {
    "enter_step3": true,
    "priority": "高",
    // 高 | 中 | 低 | 跳过 — 定性排序, 不做数字
    "rationale": "AI电力需求确定性高, 供给刚性极强(电网建设3-5年), 传导链深(7层), 市场认知仍停留在概念阶段, 预期差大",
    "key_uncertainties": ["AI算力需求增速是否放缓", "电网投资是否因财政压力推迟"]
  },

  // ═══ 辅助信息 ═══
  "a_stock_mapping": ["600406国电南瑞", "601877正泰电器", "600580卧龙电驱"],
  "tam_est": "全球电网投资每年3000亿美元, 到2030年翻倍至6000亿",
  "key_watch_points": ["国网季度投资数据", "变压器出口数据", "铜价走势"]
}
```

### 3.2 字段取值规则

| 字段 | 类型 | 取值规则 |
|------|------|---------|
| `cycle_position.phase` | 枚举 | 6 阶段之一, 必须从搜索结果中找到支撑证据 |
| `cycle_position.sub_phase` | 枚举 | early/mid/late, 基于"距离下阶段还有多远"判断 |
| `prosperity.type` | 枚举 | 6 类之一, 决定下游 Step 3/4/8 的分析路径 |
| `prosperity.demand_quality` | 枚举 | 4 类之一, 如果是 policy_pull_forward 需在 rationale 中强调风险 |
| `prosperity.driver_decomposition[].weight` | 定性 | "主导"/"重要"/"辅助", 不输出数字百分比 |
| `payoff.asymmetry` | 枚举 | "强非对称"/"对称"/"负非对称" |
| `propagation.depth` | 枚举 | "深"/"中"/"浅" |
| `verdict.priority` | 枚举 | "高"/"中"/"低"/"跳过" |
| 所有带 "evidence" 的字段 | 文本 | 必须引用搜索中的具体数据或事实 |
| 所有带 "narrative/rationale" 的字段 | 文本 | LLM 自由发挥, 1-3 句 |

### 3.3 设计约束（为什么不做数字评分）

LLM 的数值输出不可靠 — 同一个行业, 换一个 prompt 或调一次 temperature, scarcity_score 可能从 9.2 变成 7.5。这些数字传给下游会造成系统性偏差。

Step 2 只输出定性标签。需要量化的指标（supply_rigidity、pricing_power、ROE）交给 Step 3-8 用程序化逻辑或 DB 数据计算。

---

## 4. 行为规范

### 4.1 auto 模式（扫描）

1. 从 `hypothesis_sectors` 获取候选行业列表
2. 对每个行业做 2 轮搜索：
   - 第 1 轮: `"{industry} 景气度 增速 供需 产能 2026"`
   - 第 2 轮: `"{industry} 产能利用率 CAPEX 扩产周期 龙头订单 2026"`
3. LLM 综合搜索结果, 按 3.1 格式输出每行业
4. 按 `verdict.priority` 排序, 只把 `enter_step3=true` 的送入 Step 3

### 4.2 manual 模式（深度）

1. 输入 `target_industry`, 只分析这一个行业
2. 做 4 轮搜索:
   - 第 1 轮: 行业概况 + 增速 + TAM
   - 第 2 轮: 供需缺口 + 产能 + 交期
   - 第 3 轮: 竞争格局 + 政策环境
   - 第 4 轮: 产业链传导链 + 上下游
3. 输出完整 5 块（同 auto, 但 `verdict` 中优先级固定为"高"）

### 4.3 搜索策略

- 所有搜索 query 必须带当前年份（如 `2026`）
- 搜索结果中优先使用有具体数字的片段（"交期 52 周" > "交期长"）
- 如果搜索返回质量差（全广告/过时）, 在 evidence 中标注"数据质量有限, 以下判断置信度较低"

---

## 5. 与其他 Step 的接口

### 5.1 消费的上游

| 来源 | 字段 | 用途 |
|------|------|------|
| Step 1 | `macro_report.benefited_sectors` | auto 模式的候选行业清单 |
| Step 1 | `macro_report.macro_conclusion` | 宏观背景注入 prompt, 不做重复分析 |

### 5.2 提供给下游

| 消费方 | 字段 | 用途 |
|--------|------|------|
| Pipeline | `verdict.enter_step3` | false → 跳过该行业 |
| Pipeline | `verdict.priority` | 排序, top N 进入 Step 3 |
| Step 3 | `propagation.chain` | 作为 L1-L4 展开的骨架 |
| Step 3 | `prosperity.type` | supply_shock → 搜索聚焦产能/交期; demand_explosion → 搜索聚焦订单/渗透率 |
| Step 4 | `prosperity.type` | supply_shock → 走供给冲击推演路径; demand_explosion → 走需求爆发推演路径 |
| Step 4 | `cycle_position.phase` | bottleneck_formation → 走资源挤占+瓶颈迁移模板 |
| Step 4 | `propagation.chain` | 沿链条做 system_dynamics 推演 |
| Step 6 | `payoff.asymmetry` | 强非对称 → 提高 top_picks 权重 |
| Step 8 | `cycle_position.phase` | theme_emergence→PS; bottleneck_formation→EV/EBITDA; commoditization→PB |
| Step 9 | `prosperity.demand_quality` | policy_pull_forward → 加大预期差审查 |
| 报告 Section 1 | `cycle_position` + `prosperity` + `payoff` | 行业景气全景描述 |

---

## 6. 实现

### 6.1 修改文件

`backend/app/domain/research/agents/market_scanner.py`

### 6.2 改动内容

| 改动 | 说明 |
|------|------|
| `analyze()` 重构 | 新增 `mode` + `hypothesis_sectors` + `target_industry` 参数 |
| 新增 `_scan_auto()` | auto 模式: 候选行业 → 2 轮搜索 → LLM → 排序 |
| 新增 `_deep_dive_manual()` | manual 模式: 指定行业 → 4 轮搜索 → LLM → 深度全景 |
| Prompt 重写 | 按 6 阶段 × 6 类型的矩阵组织提问, 强制输出定性标签 |

### 6.3 改动量

~80 行

---

## 7. 验收

1. `python -m py_compile market_scanner.py` 通过
2. curl `POST /research/scan` 返回的 `hot_industries` 包含 `cycle_position` 和 `prosperity` 块
3. curl `POST /research/scan` (manual, industry="SOFC") 返回单个深度全景
4. 输出的 `verdict.priority` 为定性标签（"高"/"中"等）, 不出现数字分数
