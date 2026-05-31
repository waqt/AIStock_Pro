# Step 3: 产业链系统拆解 (SupplyChainHacker)

> **分析哲学**: 寻找核心利润池和产业瓶颈 — 谁拥有定价权? 谁控制供给? 核心利润池在哪?

## 文档版本

| 版本 | 日期 | 说明 | 作者 |
|------|------|------|------|
| V5.10 | 2026-04 | 初版: 定性枚举 + confidence + margin_estimated | - |
| V5.11a | 2026-05 | sub_processes 基础版: 瓶颈节点内部工艺拆解 + a_stock_mapping 下沉 | Claude |
| V5.11b | 2026-05 | 三层抽象模型: value_magnitude + value_owners + pricing_behavior 纳入 sub_processes, 9条设计规则, P0-P4优先排序表 | Claude |

---

## I/O 合约

### 输入 (来自 Step 2)

| 字段 | 用途 |
|------|------|
| `cycle_position` | 决定搜索聚焦点: bottleneck_formation→找瓶颈环节, capacity_release→找成本最低者 |
| `prosperity_type` | 决定分析框架: supply_shock→找供给约束源头, demand_explosion→找产能扩张瓶颈 |
| `propagation_depth` | 决定分析深度: 深→走满 L4, 浅→L2 即可 |
| `payoff_asymmetry` | 传递给 Step 6 资产筛选 |
| `verdict.enter_step3` | 若 false 则**降权标记** (不硬跳过, 用户可超驰) |

### 输出

```json
{
  "confidence": "high",
  "confidence_note": "搜索覆盖充分: 3轮15条有效结果, 瓶颈环节数据完整。以下 margin_level/share_of_profit 为LLM基于搜索片段估计, 待Step 6财务验证后回写修正。",

  "supply_chain_map": [
    {
      "level": 1,
      "name": "先进封装 CoWoS",
      "bottleneck_narrative": "台积电独家供应, 扩产需18个月, 无替代方案可量产",
      "confidence": "high",

      "supply_rigidity": {
        "severity": "extreme",
        "root_cause": "equipment_constraint",
        "expand_cycle": "over_12m",
        "substitutability": "none_short_term",
        "concentration": "monopoly_single_supplier",
        "alpha_narrative": "独家供给刚性=定价权极高, 景气窗口精确可算"
      },

      "profit_pool": {
        "share_of_industry_profit": "dominant_30_50pct",
        "margin_level": "very_high_above_40pct",
        "margin_estimated": true,
        "margin_data_source": "LLM估计, 基于搜索片段中的研报引用",
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
      ],

      "evidence": [
        {"fact": "关键事实", "from": "search[1.3]·来源", "quality": {"level": "high", "source_type": "industry_data"}}
      ],

      // ═══ V5.11: 瓶颈节点内部工艺拆解 ═══
      // 当瓶颈节点（如"封装"）内部包含多个刚性差异巨大的子工艺时,
      // 展开 sub_processes 以便 Step 6 做精确的资产映射.
      // Optional: 仅 L1-L2 且 severity≥high 时使用, 最多 5 个.
      "sub_processes": [
        {
          "name": "TSV深硅刻蚀",
          "confidence": "high",
          "chokepoint_score": 85,
          "supply_rigidity": {
            "severity": "high",
            "root_cause": "equipment_constraint",
            "expand_cycle": "over_24m",
            "substitutability": "partial_emerging",
            "concentration": "oligopoly"
          },

          // ★ V5.11 三层抽象模型:
          //   维度1: 价值量级 — 该子工艺所在市场的绝对规模
          "value_magnitude": {
            "order_of_magnitude": "1B_10B",
            "unit_economics_hint": "TSV刻蚀设备全球市场约$5-8B/年, 国产化率20-50%",
            "margin_level": "very_high_above_40pct"
          },

          //   维度2: 价值归属 — 谁捕获了这部分价值
          "value_owners": [
            {"name": "应用材料", "public_market": "NASDAQ:AMAT",
             "captures_value_in": ["TSV深硅刻蚀", "薄膜沉积"],
             "value_share": "dominant", "investable_in_a_share": false},
            {"name": "泛林半导体", "public_market": "NASDAQ:LRCX",
             "captures_value_in": ["TSV深硅刻蚀"],
             "value_share": "major", "investable_in_a_share": false},
            {"name": "中微公司", "public_market": "SH:688012",
             "captures_value_in": ["TSV深硅刻蚀"],
             "value_share": "challenger", "investable_in_a_share": true,
             "investment_logic": "卖水人逻辑: TSV刻蚀设备国产替代唯一龙头"}
          ],

          "profit_pool": {
            "share_of_industry_profit": "dominant_30_50pct",
            "margin_level": "very_high_above_40pct",
            "margin_estimated": true,
            "margin_data_source": "LLM估计"
          },

          //   维度3 (修饰因子): 竞争行为模式
          "competitive_landscape": {
            "structure": "oligopoly_CR3_above_70",
            "pricing_behavior": "collusive_oligopoly",
            "global_leaders": ["应用材料", "泛林半导体", "东京电子"],
            "china_substitution_rate": "20_50pct",
            "china_players": {"tier1": ["中微公司"], "tier2": [], "tier3": []}
          },
          "future_outlook": {
            "next_2_3_years": "bottleneck_persists"
          },
          "a_stock_mapping": [
            {"code": "688012", "name": "中微公司", "code_ts": "688012.SH",
             "logic": "TSV深硅刻蚀设备国产替代唯一龙头"}
          ],
          "value_node_tags": ["TSV刻蚀设备国产替代", "HBM制造核心设备"],
          "evidence": [
            {"fact": "关键事实", "from": "search[1.3]·来源",
             "quality": {"level": "high", "source_type": "industry_data"}}
          ]
        }
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

### 关键字段说明 (V5.10 新增)

| 字段 | 类型 | 说明 |
|------|------|------|
| `confidence` | enum | 整体分析置信度: `high`(搜索覆盖充分) / `medium`(部分数据缺失) / `low`(数据严重不足, 以下结论可能偏差较大) |
| `confidence_note` | string | 置信度说明, 明确指出数据缺口在哪 |
| `supply_chain_map[].confidence` | enum | 单节点置信度, 同上 |
| `profit_pool.margin_estimated` | bool | ★ 标记为 LLM 估计值 (`true`=LLM估计, `false`=Step6回写后修正) |
| `profit_pool.margin_data_source` | string | 数据来源说明 ("LLM估计, 基于搜索片段" / "Step6财务验证: 2025Q4毛利率=42.3%") |
| `supply_chain_map[].sub_processes` | array | ★ V5.11 新增, 详见 §sub_processes 设计
| `supply_chain_map[].sub_processes[].a_stock_mapping` | array | ★ 子工艺级别的 A 股映射, 每项含 `code` / `name` / `code_ts` / `logic`, 供 Step 6 直接消费 |
| `supply_chain_map[].sub_processes[].value_magnitude` | object | ★ 该子工艺所在市场的价值量级估算, 含 `order_of_magnitude` / `unit_economics_hint` / `margin_level`, 解决"毛利率vs绝对利润"的偏差 |
| `supply_chain_map[].sub_processes[].value_owners[]` | array | ★ 该子工艺的价值归属方列表, 每项含 `name` / `public_market` / `value_share` / `investable_in_a_share` / `investment_logic` |
| `supply_chain_map[].sub_processes[].competitive_landscape.pricing_behavior` | enum | ★ 竞争行为模式: `collusive_oligopoly` / `capacity_war` / `monopoly` / `price_taker`, 修正"结构=垄断≠利润高"的简单化假设 |

### sub_processes 设计 (V5.11 新增)

#### 设计动机

Step 3 的瓶颈节点（如"HBM 先进封装"）在实际产业链中包含多个刚性差异巨大的子工艺（TSV 刻蚀 / 微凸块 / 堆叠键合 / ABF 基板 / TIM 散热 / 测试探针等）。将这些子工艺聚合成一个节点打分（如 chokepoint_score=92）会丢失关键粒度 —— 不同子工艺的供给刚性、竞争格局、国产化率、A 股可投资性完全不同，Step 6 无法据此做出精确的资产筛选。

更深层的问题：当前框架隐含了一个错误映射 —— **"垄断=利润最高, oligopoly=利润中, fragmented=利润低"**。现实是：
- 台积电在 CoWoS 环节 **monopoly**，但该环节市场总量约 $10B，绝对利润约 $5B
- 海力士/三星在 HBM 制造环节 **oligopoly**，但该环节市场总量 **$100B+**，绝对利润 **$20B+**

**结构 ≠ 利润。需要拆成三个正交维度。**

#### 三层抽象模型

一个子工艺的实际投资价值由三个独立维度决定，Step 3 做定性标签，Step 6 做精确财务验证：

```
维度1: 价值量级 (value_magnitude)
  该子工艺所在市场的绝对规模。
  解决: 毛利率高 ≠ 利润池大的偏差。
  Step 3 输出: LLM 基于搜索做量级估算 (<1B / 1B_10B / 10B_100B / 100B+)
  Step 6 回写: 财务验证后修正为精确数值

维度2: 价值归属 (value_owners)
  谁真正捕获了这个子工艺的价值？同一公司可能横跨多个子工艺。
  解决: "台积电是垄断但只占低价值环节" vs "海力士是寡头但占高价值环节"
  Step 3 输出: 列出了工艺的价值所有者及其上市地
  Step 6 消费: 区分"可直接买"/"卖水人逻辑"/"不可投资"

修饰因子: 竞争行为模式 (pricing_behavior)
  同一 oligopoly 结构下，定价行为可能完全不同：
  - 合谋寡头 (海力士/三星/美光) → 产能协同控量 → 接近垄断定价权
  - 产能竞赛 (光伏/面板) → 大家都在扩产 → 定价权恶化中
  - 价格接受者 (封测代工) → 充分竞争 → 无定价权
  解决: 结构(一数) ≠ 行为(另一数)。同一结构不同行为的公司不应同等对待。
```

#### 核心规则

| # | 规则 | 说明 |
|---|------|------|
| 1 | **Optional 展开** | 仅 L1-L2 瓶颈节点且 `severity≥high` 时才需要展开 `sub_processes`。非瓶颈节点或严重性低的节点不要展开 |
| 2 | **上限 5 个** | 单个节点的 `sub_processes` 最多 5 个，防止输出爆炸 |
| 3 | **定性枚举复用** | 每个子工艺复用 `supply_rigidity` / `profit_pool` / `competitive_landscape` / `future_outlook` 的完整枚举体系 |
| 4 | **A 股映射下沉** | A 股标的映射放在子工艺级别的 `a_stock_mapping[]` 中，而非父节点级别。父节点的 `a_stock_transmission` 保留为整体描述 |
| 5 | **零映射也保留** | 如果某子工艺完全没有 A 股标的（如台积电独家垄断环节），仍列出该子工艺并标注 `a_stock_mapping: []`，供 Step 6 知悉此环节在 A 股无敞口 |
| 6 | **证据闭环** | 每个子工艺的 `evidence[]` 必须包含至少 1 条支撑其 rigidity 判断的事实 |
| 7 | **价值量级锚定** | 每个子工艺必须估算 `value_magnitude.order_of_magnitude`，基于搜索中的营收/利润数据，不做精确数字，只估量级。零搜索结果时标注 `unknown` |
| 8 | **价值归属标注** | 每个子工艺必须列出至少 1 个 `value_owners[]`，无法识别时标注 `["unknown"]`。同一公司跨多个子工艺时在每个子工艺重复出现。`investable_in_a_share` 标记是否可直接投资 |
| 9 | **竞争行为判定** | 每个子工艺必须标注 `pricing_behavior`，且不能与 `structure` 自动关联 — 必须基于搜索中的实际定价行为推断 |

#### 投资映射粒度 (三层模型完整版)

```
父节点: HBM晶圆制造+TSV+堆叠 (chokepoint_score=85)
│ value_magnitude: 100B+    ← 最大市场
│ value_owners: [海力士, 三星, 美光]  ← 价值在此，但不在A股
│
├── DRAM晶圆制造
│   ├ value_magnitude: 100B+, margin=very_high_above_40pct
│   ├ value_owners: [海力士(KOSPI), 三星(KRX), 美光(NASDAQ)]
│   │   investable_in_a_share = false (三家均非A股)
│   ├ pricing_behavior: collusive_oligopoly (三大寡头合谋控量提价)
│   └ a_stock_mapping: [] (无A股映射, 仅卖水人逻辑: 设备/材料)
│
├── TSV硅通孔制备
│   ├ value_magnitude: 1B_10B, margin=very_high_above_40pct
│   ├ value_owners: [海力士(自研), 三星(自研)]  ← 价值主要被存储厂自研消化
│   ├ pricing_behavior: collusive_oligopoly
│   └ a_stock_mapping: [中微公司 688012]  ← 卖水人: 设备供应商
│
├── 堆叠键合(MR-MUF/TC-NCF)
│   ├ value_magnitude: 1B_10B
│   ├ value_owners: [海力士(MR-MUF), 三星(TC-NCF)]  ← 核心know-how, 不外放
│   ├ pricing_behavior: differentiated_duopoly (技术路线不同, 非直接价格竞争)
│   └ a_stock_mapping: [] (核心know-how在韩国)

父节点: CoWoS 2.5D系统级封装 (chokepoint_score=92)
│ value_magnitude: 10B_100B   ← 比HBM制造小一个量级
│ value_owners: [台积电]      ← 价值在此，也不在A股
│
├── 硅中介层+倒装键合 (CoW阶段)
│   ├ value_magnitude: 1B_10B
│   ├ value_owners: [台积电(台股)]  ← CoW阶段台积电自研不外放
│   ├ pricing_behavior: monopoly (独家)
│   └ a_stock_mapping: [] (台积电台股, 非A股)
│
├── ABF基板贴装 (oS阶段)
│   ├ value_magnitude: 1B_10B
│   ├ value_owners: [味之素(东京), IBIDEN(东京)]
│   ├ pricing_behavior: collusive_oligopoly (ABF膜: 味之素96%垄断)
│   └ a_stock_mapping: [深南电路 002916, 兴森科技 002436]  ← 国产替代受益
│
├── TIM散热材料
│   ├ value_magnitude: <1B, margin=high_25_40pct
│   ├ value_owners: [信越化学(东京), Honeywell(NYSE)]
│   ├ pricing_behavior: price_taker (多种替代方案)
│   └ a_stock_mapping: [德邦科技 688035]  ← 小众标的
│
└── 探针测试
    ├ value_magnitude: <1B
    ├ value_owners: [FormFactor(NASDAQ), 和林微纳(SH)]
    ├ pricing_behavior: fragmented
    └ a_stock_mapping: [和林微纳 688661, 精测电子 300567]
```

#### Step 6 优先级的复合判定

Step 6 消费 `sub_processes` 后，按以下优先级组合筛选：

| 优先级 | 组合条件 | 含义 | 示例 |
|--------|---------|------|------|
| **P0** | `value_magnitude`≥10B+ *AND* `investable_in_a_share=true` | 大市场且 A 股可投 | 暂无(海力士/三星都不在A股) |
| **P1** | `value_magnitude`≥1B *AND* `a_stock_mapping` 非空 *AND* `pricing_behavior`≠price_taker | 中等以上市场 + 有 A 股标的 + 有定价权 | 深南电路(ABF), 中微公司(刻蚀) |
| **P2** | `china_substitution_rate`≥20_50pct *AND* `a_stock_mapping` 非空 | 国产替代逻辑清晰 | 北方华创, 华海清科 |
| **P3** | `value_magnitude`≥1B *AND* `a_stock_mapping` 非空 *AND* `pricing_behavior`=price_taker | 有市场但竞争激烈 | 德邦科技(TIM), 和林微纳(探针) |
| **P4** | `a_stock_mapping` 为空但 `value_owners` 有跨环节协同效应 | 不可直接买但产业链有联动 | 台积电涨价→国内封测厂受益 |

#### 父节点与子工艺的关系

- 父节点的 `chokepoint_score` 是整体评分（聚合值）
- 子工艺的 `chokepoint_score` 是独立评分，可与父节点不同（如封装整体 92 分，但内部 TIM 散热可能只有 70 分）
- 父节点的 `a_stock_transmission` 保留为整体投资叙事，`value_node_tags` 保留为整体标签
- `sales_chain` / `expansion_chain` / `chain_timeline` 仍然是产业链级别的分析，不受 sub_processes 影响
- **sub_processes 不替换父节点的 chokepoint 评分** — 两者供下游不同用途：父节点评分决定"产业链瓶颈排序"，子工艺的 value_magnitude+value_owners 决定"具体的资产映射"

### 过滤规则 (V5.10 修正)

| 规则 | 旧行为 | 新行为 |
|------|--------|--------|
| `verdict.enter_step3=false` | 硬跳过, 不可恢复 | **降权标记**, 用户可超驰继续 |
| `severity=low/oversupply` | 不被 Step 4/5 重点推演 | **仍纳入推演**, 但标记 `severity_low` 供下游知悉 |
| 搜索 3 轮无有效结果 | 硬输出, 无质量标记 | 输出 `confidence=low` + `confidence_note` 说明数据缺口 |

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

### supply_rigidity.expand_cycle (V5.10 改为三档, 与 Step 4/5 对齐)

| 值 | 含义 |
|----|------|
| `under_12m` | 12个月内可扩产 |
| `12_24m` | 12-24个月 |
| `over_24m` | 超过24个月 |

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

**注意**: `share_of_industry_profit` 和 `margin_level` 均为 LLM 基于搜索估计值, 字段 `margin_estimated=true` 标记。Step 6 财务审计后回写真实数据, 将 `margin_estimated` 改为 `false` 并更新 `margin_data_source`。

### value_capture.attention_quality

| 值 | 含义 |
|----|------|
| `profit_real` | 热度高且利润确实集中 — 稀缺溢价合理 |
| `profit_diverted` | 热度高但利润被上游抽走 — 警惕炒作 |
| `under_the_radar` | 关注度低但利润捕获好 — 预期差最大 |
| `deservedly_low` | 关注度低且确实不赚钱 — 合理回避 |

**注意**: `attention_quality` 是关键分叉标签。`profit_diverted` 会让下游降权, `profit_real` 会让下游侧重。LLM 必须基于搜索证据判断, 不可空判。证据不足时标记 `confidence=low` 并附说明。

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

### confidence 枚举

| 值 | 含义 | 下游动作 |
|----|------|---------|
| `high` | 搜索覆盖充分, 关键数据有多个独立来源交叉验证 | 正常推演 |
| `medium` | 部分数据缺失或依赖单一来源 | 推演时标注不确定性 |
| `low` | 数据严重不足, LLM 基于有限信息推断 | 降低该结论在 Step 11 综合报告中的权重 |
| `insufficient_data` | 几乎无可用数据 (新兴/极冷门行业) | 标记, 不丢弃, 等待数据补全后重跑 |

### competitive_landscape.pricing_behavior (V5.11 新增)

| 值 | 含义 | 典型例子 | 等同于 |
|----|------|---------|--------|
| `monopoly` | 独家垄断 — 完全定价权 | 台积电 CoWoS | 传统 monopoly |
| `collusive_oligopoly` | 寡头合谋 — 产能协同/人为控量 | 海力士/三星/美光 HBM 制造 | 事实上的垄断定价权 |
| `capacity_war` | 产能竞赛 — 大家都在扩产, 定价权恶化 | 光伏硅片/面板/LED | 恶化中的 oligopoly |
| `price_taker` | 价格接受者 — 充分竞争, 无定价权 | 封测代工/低端材料 | fragmented |

**注意**: `pricing_behavior` 与 `competitive_landscape.structure` 是正交的。同是 oligopoly, `collusive_oligopoly` 和 `capacity_war` 的投资价值完全不同。LLM 必须基于搜索中的**实际定价行为**推断, 不能从 structure 自动映射。

### value_magnitude.order_of_magnitude (V5.11 新增)

| 值 | 含义 |
|----|------|
| `100B+` | 千亿美元级市场 (如 HBM 制造) |
| `10B_100B` | 百亿美元级市场 (如 CoWoS 封装) |
| `1B_10B` | 十亿美元级市场 (如 TSV 设备、ABF 基板) |
| `<1B` | 十亿美元以下 (如 TIM 散热、探针卡) |
| `unknown` | 无搜索结果, 无法估算 |

**注意**: `order_of_magnitude` 是量级估算, 不是精确数值。基于搜索中出现的营收数据或行业市场规模数据做粗略分类。零搜索结果时标注 `unknown` 而非猜测。Step 6 拿到真实财务数据后回写修正。

### value_owners[].value_share (V5.11 新增)

| 值 | 含义 |
|----|------|
| `dominant` | 主导地位 (>50% 份额) |
| `major` | 重要参与者 (15-50%) |
| `challenger` | 挑战者 (<15%, 但增速快或有技术突破) |
| `niche` | 小众/边缘参与者 |

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

搜索 3 轮仍无有效结果时: 不丢弃, 输出 `confidence=insufficient_data` + 说明, 等数据补全后可重跑。

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
| → 提供 | Step 6 | core_stocks + scarcity_ranking → 核心资产筛选; Step 6 回写 margin_level 真实数据 |
| → 提供 | Step 6 | **sub_processes[].a_stock_mapping** → V5.11 子工艺级 A 股映射, Step 6 按 `severity` + `china_substitution_rate` + `a_stock_mapping` 组合做优先级筛选 |
| ← 回写 | Step 6 | margin_estimated → false, margin_data_source → "财务验证: 2025Q4毛利率=XX%" |
| → 提供 | Step 8 | profit_pool + competitive_landscape → 估值模型选择 |
| → 提供 | Step 11 | 全量 supply_chain_map + confidence → 报告"产业链图谱"章节 |

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

**改动内容 (V5.10)**:
- `_structure_output()` prompt: 新增 `confidence` + `margin_estimated` + `margin_data_source` 字段
- Prompt 末尾: 注入"数据不足时输出 confidence=insufficient_data"规则
- 不改: `analyze_level()`, `_extract_stocks_simple()`, `_second_level_analysis()`, `_hack_supply_chain()`

**改动量 (V5.10)**: ~30 行 prompt 调整, 零新增文件。

**改动内容 (V5.11a — sub_processes 基础版)**:
- Prompt 中 `supply_chain_map[]` 节点模板: 新增可选的 `sub_processes[]` 结构
- LLM 规则: 注入 sub_processes 展开规则（仅 L1-L2 severity≥high、最多 5 个、证据闭环）
- LLM 规则: 每个子工艺的 `a_stock_mapping` 须标注具体公司代码 + 投资逻辑
- 不改: `sales_chain` / `expansion_chain` / `chain_timeline` — 保持产业链级别不变

**改动量 (V5.11a)**: ~20 行 prompt 调整, 零新增文件。

**改动内容 (V5.11b — 三层抽象模型增强)**:
- `sub_processes[]` 节点模板: 新增 `value_magnitude` (order_of_magnitude + unit_economics_hint)
- `sub_processes[]` 节点模板: 新增 `value_owners[]` (name + public_market + value_share + investable_in_a_share + investment_logic)
- `competitive_landscape` 模板: 新增 `pricing_behavior` 枚举 (collusive_oligopoly / monopoly / capacity_war / price_taker)
- LLM 规则: 注入三层抽象模型规则 — 每个子工艺必须标注价值量级、价值归属、竞争行为，且不能从 structure 自动推导 pricing_behavior
- LLM 规则: 零搜索结果时 `order_of_magnitude` 标注 `unknown`, 不猜测
- 不改: `sales_chain` / `expansion_chain` / `chain_timeline` — 保持产业链级别不变
- 不改: 父节点 `chokepoint_score` — sub_processes 不替换父节点评分

**改动量 (V5.11b)**: ~30 行 prompt 调整, 零新增文件。

---

## 验证标准

1. `curl POST /api/research/supply-chain-hacker -d '{"industry":"SOFC"}'` 返回新 schema
2. 输出含 `confidence` 字段 (high/medium/low/insufficient_data)
3. `margin_estimated` 为 `true` (LLM 估计标记)
4. value_capture.attention_quality 是有效枚举值之一
5. 搜索 3 轮无结果时 confidence 为 `low` 或 `insufficient_data` (不丢数据)
6. supply_chain_map 每个环节的 supply_rigidity.severity 是枚举值 (不是数字)
7. `expand_cycle` 为 under_12m / 12_24m / over_24m (三档对齐)
8. V5.11: supply_chain_map 中 severity≥high 的 L1-L2 节点可选地包含 `sub_processes[]`
9. V5.11: 每个 sub_process 包含完整的 `supply_rigidity` / `profit_pool` / `competitive_landscape` / `value_magnitude` / `value_owners` 枚举
10. V5.11: 每个 sub_process 的 `competitive_landscape.pricing_behavior` 是有效枚举值, 且不与 `structure` 相同
11. V5.11: 每个 sub_process 的 `value_magnitude.order_of_magnitude` 已标注（`unknown` 也可接受）
12. V5.11: 每个 sub_process 的 `a_stock_mapping[]` 标注了具体公司代码和投资逻辑（零映射时为空数组）
13. V5.11: `sub_processes` 数量 ≤ 5
