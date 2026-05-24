# AI 投研系统 V5.7 → V6.0 升级设计文档

> 对标 GPT 投研提示词 V2（11 步系统动力学增强版），在现有 6 Agent + DAG Pipeline 架构上渐进增强。

---

## 系统定位

**AIStock Pro 产业链分析专家** — 针对投资驱动的供给侧行业分析系统。


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


