# AI 投研系统 V5.7 → V6.0 升级设计文档

> 对标 GPT 投研提示词 V2（11 步系统动力学增强版），在现有 6 Agent + DAG Pipeline 架构上渐进增强。

---

## 系统定位

**AIStock Pro 产业链分析专家** — 针对投资驱动的供给侧行业分析系统。


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



