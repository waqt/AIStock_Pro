# Step 3: 产业链系统拆解 (SupplyChainHacker)

> **分析哲学**: 寻找核心利润池和产业瓶颈 — 谁拥有定价权? 谁控制供给? 核心利润池在哪?

---

## I/O 合约

### 输入 (来自 Step 2)

| 字段 | 用途 |
|------|------|
| `cycle_position` | 决定搜索聚焦点: bottleneck_formation→找瓶颈环节, capacity_release→找成本最低者 |
| `prosperity_type` | 决定分析框架: supply_shock→找供给约束源头, demand_explosion→找产能扩张瓶颈 |
| `propagation_depth` | 决定分析深度: 深→走满 L4, 浅→L2 即可 |
| `payoff_asymmetry` | 传递给 Step 6 资产筛选 |
| `verdict.enter_step3` | 若 false 则跳过本 Step |

### 输出

```json
{
  "supply_chain_map": [
    {
      "level": 1,
      "name": "先进封装 CoWoS",
      "bottleneck_narrative": "台积电独家供应, 扩产需18个月, 无替代方案可量产",

      "supply_rigidity": {
        "severity": "extreme",
        "root_cause": "equipment_constraint",
        "expand_cycle": "18_24_months",
        "substitutability": "none_short_term",
        "concentration": "monopoly_single_supplier",
        "alpha_narrative": "独家供给刚性=定价权极高, 景气窗口精确可算"
      },

      "profit_pool": {
        "share_of_industry_profit": "dominant_30_50pct",
        "margin_level": "very_high_above_40pct",
        "pricing_power_narrative": "卖方市场, 价格持续上涨中, 下游无议价能力"
      },

      "value_capture": {
        "market_attention": "very_high",
        "attention_quality": "profit_real",
        "gap_narrative": "市场高度关注但利润确实集中在这里 — 稀缺溢价合理, 非泡沫",
        "who_captures_value": ["台积电(封装)", "AMAT(设备)", "ABF基板(材料)"]
      },

      "competitive_landscape": {
        "structure": "oligopoly_CR3_above_70",
        "global_leaders": ["台积电", "三星"],
        "china_substitution_rate": "below_5pct",
        "china_players": {"tier1": [], "tier2": ["长电科技"], "tier3": ["通富微电"]}
      },

      "future_outlook": {
        "next_2_3_years": "bottleneck_persists",
        "potential_relief": "台积电2028新厂投产但远水不解近渴",
        "emerging_bottleneck": "ABF基板可能成为下一个瓶颈"
      },

      "assets": [
        {"code": "688012", "name": "中微公司", "role": "刻蚀设备", "market_position": "tier2_challenger"}
      ]
    }
  ],

  "core_stocks": [
    {"code": "688012", "name": "中微公司", "segment": "刻蚀设备", "role": "龙头", "moat": "技术垄断"}
  ],

  "sales_chain": [
    {"segment": "直接受益环节", "companies": ["688xxx"], "reason": "下游订单爆发→最先感知", "lead_months": "1-3"}
  ],

  "expansion_chain": [
    {"segment": "滞后受益环节", "companies": ["688yyy"], "reason": "上游扩产→设备/材料滞后受益", "lag_months": "6-12"}
  ],

  "chain_timeline": {
    "sales_lead_months": "1-3",
    "expansion_lag_months": "6-12",
    "rotation_strategy": "先配销售链路标的, 3-6个月后转配扩产链路标的"
  },

  "scarcity_ranking": [
    {"rank": 1, "segment": "CoWoS封装", "rigidity_narrative": "台积电垄断, 零替代, 18个月扩产周期", "beneficiary_stocks": ["688012"]}
  ]
}
```

---

## 枚举定义 (注入 glossary)

所有数值型评分已替换为定性枚举, LLM 从搜索文本推理标签而非猜测数字。

### supply_rigidity.severity

| 值 | 含义 |
|----|------|
| `extreme` | 供给完全刚性 — 独家供应, 零替代, 扩产>18个月 |
| `high` | 供给严重受限 — CR2垄断, 替代方案不成熟, 扩产>12个月 |
| `moderate` | 供给偏紧 — CR3-5竞争, 扩产6-12个月, 有替代但成本高 |
| `low` | 供给充裕 — 充分竞争, 扩产<6个月, 多替代方案 |
| `oversupply` | 供给过剩 — 产能严重过剩, 价格战风险 |

### supply_rigidity.root_cause

| 值 | 含义 | 典型例子 |
|----|------|---------|
| `equipment_constraint` | 设备交期约束 | EUV光刻机, CoWoS封装设备 |
| `natural_resource` | 自然资源稀缺 | 高纯石英砂, 稀土, 锂矿 |
| `certification_barrier` | 客户认证壁垒 | 车规芯片认证(3-5年), 航空认证 |
| `policy_restriction` | 政策/出口管制 | 美国设备禁令, 日本材料限制 |
| `capital_scale` | 资本规模门槛 | 晶圆厂($10B+), 面板厂 |

### supply_rigidity.expand_cycle

| 值 | 含义 |
|----|------|
| `under_6_months` | 6个月内可扩产 |
| `6_12_months` | 6-12个月 |
| `12_18_months` | 12-18个月 |
| `18_24_months` | 18-24个月 |
| `over_24_months` | 超过24个月 |

### supply_rigidity.substitutability

| 值 | 含义 |
|----|------|
| `none_short_term` | 短期无替代方案 |
| `partial_high_cost` | 有替代但成本显著更高/性能显著更差 |
| `partial_emerging` | 替代方案正在验证中 |
| `multiple_options` | 存在多个可用的替代方案 |

### supply_rigidity.concentration

| 值 | 含义 |
|----|------|
| `monopoly_single_supplier` | 独家供应 (>90%份额) |
| `duopoly` | 双寡头 (CR2>80%) |
| `oligopoly` | 寡头 (CR3-5>60%) |
| `fragmented` | 分散竞争 (CR5<40%) |

### profit_pool.share_of_industry_profit

| 值 | 含义 |
|----|------|
| `dominant_30_50pct` | 占据行业30-50%利润 |
| `significant_15_30pct` | 占据15-30% |
| `moderate_5_15pct` | 占据5-15% |
| `marginal_below_5pct` | 不足5% |

### profit_pool.margin_level

| 值 | 含义 |
|----|------|
| `very_high_above_40pct` | 毛利率>40% |
| `high_25_40pct` | 毛利率25-40% |
| `moderate_15_25pct` | 毛利率15-25% |
| `low_below_15pct` | 毛利率<15% |

### value_capture.attention_quality

| 值 | 含义 |
|----|------|
| `profit_real` | 热度高且利润确实集中 — 稀缺溢价合理 |
| `profit_diverted` | 热度高但利润被上游抽走 — 警惕炒作 |
| `under_the_radar` | 关注度低但利润捕获好 — 预期差最大 |
| `deservedly_low` | 关注度低且确实不赚钱 — 合理回避 |

### competitive_landscape.china_substitution_rate

| 值 | 含义 |
|----|------|
| `below_5pct` | 国产化率<5% — 几乎完全依赖进口 |
| `5_20pct` | 国产化率5-20% — 开始替代但差距大 |
| `20_50pct` | 国产化率20-50% — 快速追赶中 |
| `above_50pct` | 国产化率>50% — 已具备竞争力 |

### future_outlook.next_2_3_years

| 值 | 含义 |
|----|------|
| `bottleneck_persists` | 瓶颈持续 — 2-3年内无实质性缓解 |
| `bottleneck_easing` | 瓶颈缓解 — 新增产能/替代方案正在落地 |
| `bottleneck_resolved` | 瓶颈解除 — 供给将追上需求 |
| `new_bottleneck_emerging` | 新瓶颈形成 — 当前宽松但2-3年内收紧 |

---

## 搜索策略

### Step 2 输出驱动搜索聚焦

搜索策略由 Step 2 的定性标签决定, 不搞一刀切:

| Step 2 标签 | 搜索聚焦 | 典型 query |
|------------|---------|-----------|
| `cycle_position=bottleneck_formation` | 产能/交期/缺口数据 | "{industry} 产能 交期 瓶颈 缺口 2026" |
| `cycle_position=capacity_release` | 成本曲线/出清节奏 | "{industry} 成本优势 产能过剩 出清 2026" |
| `prosperity_type=supply_shock` | 供给约束源头 | "{industry} 设备禁令 资源稀缺 认证壁垒" |
| `prosperity_type=demand_explosion` | 产能扩张瓶颈 | "{industry} 扩产计划 新增产能 CAPEX 2026" |
| `propagation_depth=深` | L1-L4 全链路下钻 | 每层单独搜一轮 |
| `propagation_depth=浅` | L1-L2 即可 | 减少到2轮搜索 |

### 3 轮迭代搜索

```
Round 1: 产业链全景 + 瓶颈定位
  query = f"{industry} 产业链 核心瓶颈 产能 技术壁垒 龙头公司 市占率"
  → LLM 分析 + 自检缺口

Round 2: 缺口补搜 (基于 Round 1 的 gaps)
  query = f"{industry} {gaps[:3]}"
  → LLM 校验 + 判断是否需要 Round 3

Round 3 (条件触发): 深度数据补搜
  query = f"{industry} {remaining_gaps} 最新 2026"
  → 最终校验
```

每轮搜索 5 条结果, 最大 3 轮, 条件终止 (need_more_search=false 且 round>1)。

---

## Prompt 注入

### glossary 注入

Step 3 prompt 末尾调用 `step3_glossary()` 注入 `cycle_phase` + `prosperity_type` 术语定义, 确保 Step 2 的标签被正确理解。

### Step 2 标签注入

```
## 上游决策 (来自 Step 2 看门人, 请据此调整分析框架)

行业周期位置: {cycle_position.phase} {cycle_position.sub_phase}
  → {cycle_position.phase 对应的分析聚焦}

景气类型: {prosperity_type}
  → {prosperity_type 对应的分析框架}

传导深度: {propagation_depth}
  → {propagation_depth 对应的下钻层级要求}
```

---

## 与上下游的接口

| 方向 | Step | 传递内容 |
|------|------|---------|
| ← 消费 | Step 2 | cycle_position, prosperity_type, propagation_depth → 驱动搜索策略 |
| → 提供 | Step 4+5 | supply_chain_map (瓶颈结构) → SystemDynamicsAgent 推演基础 |
| → 提供 | Step 6 | core_stocks + scarcity_ranking → 核心资产筛选 |
| → 提供 | Step 8 | profit_pool + competitive_landscape → 估值模型选择 |
| → 提供 | Step 11 | 全量 supply_chain_map → 报告"产业链图谱"章节 |

---

## 现有能力保留

以下现有 `supply_chain_hacker.py` 的能力**不做减法**, 仅增强:

- `sales_chain` + `expansion_chain` 双链模型 — 保留, 纳入最终输出
- `chain_timeline` 轮动策略 — 保留
- `analyze_level()` 单层深钻 — 保留, 独立调试用
- 股票代码三层提取 (正则→LLM→重试) — 保留, 不需要改
- `second_order_effects` — 移交给 Step 4 SystemDynamicsAgent (但 Step 3 不删除, 等 Step 4 接入后再切)
- `thesis_breakers` — 保留, 从 Step 2 移入的输出字段

---

## 改动范围

**文件**: `backend/app/domain/research/agents/supply_chain_hacker.py`

**改动内容**:
- `_hack_supply_chain()` prompt: 替换旧 schema → 新定性标签 schema
- `_structure_output()` prompt: 替换旧 schema → 新定性标签 schema + 注入 Step 2 标签
- 搜索策略: 在 `_hack_supply_chain()` 开头加 Step 2 标签驱动的 query 选择逻辑
- Prompt 末尾注入 `step3_glossary()` + Step 2 标签
- 不改: `analyze_level()`, `_extract_stocks_simple()`, `_second_level_analysis()`

**改动量**: ~80 行 prompt 替换, ~15 行搜索策略调整, 零新增文件。

---

## 验证标准

1. `curl POST /api/research/supply-chain-hacker -d '{"industry":"SOFC"}'` 返回新 schema
2. supply_chain_map 每个环节的 supply_rigidity.severity 是 `extreme/high/moderate/low/oversupply` (不是数字)
3. value_capture.attention_quality 是 `profit_real/profit_diverted/under_the_radar/deservedly_low` 之一
4. 枚举值全部在 glossary 定义范围内 (不出现 `"medium"`, `"type_a"` 等自创值)
5. 传入不同 cycle_position, 搜索 query 不同 (验证 Step 2 标签驱动)
6. sales_chain + expansion_chain 双链仍正常输出
