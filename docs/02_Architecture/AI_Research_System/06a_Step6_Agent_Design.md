# Step 6a: 核心资产筛选 — 智能体设计

> **定位**: 不是"选财务最好看的公司"，而是"找出最可能把产业利润变成自己利润的公司"。
> **设计来源**: GPT 六维权力画像 (骨架) + Gemini 生命周期分轨 (过滤逻辑)
> **姊妹文档**: [06b 量化方法+数据底座](06b_Step6_Quant_Methods.md)

---

## I/O 合约

### 输入 (来自 Step 3 + Step 4 + Step 5)

| 来源 | 字段 | 用途 |
|------|------|------|
| Step 3 | `supply_chain_map[].name / supply_rigidity / assets[]` | 瓶颈节点的权力属性 + 已有股票 |
| Step 3 | `core_stocks[]` | 直通候选池 (已验证的产业链标的) |
| Step 3 | `scarcity_ranking[]` | 稀缺环节排序, 锚定优先级 |
| Step 4 | `hidden_beneficiaries[].search_queries[] / sector` | 搜索词 → 标的映射 → 候选池 |
| Step 4 | `resource_crowding[].search_queries[] / hidden_beneficiary` | 资源挤占受益方 → 候选池 |
| Step 4 | `profit_pool_shift[].to_segment` | 利润迁移目标环节 |
| Step 5 | `cross_industry_linkages[].target_profile / affected_sector` | 跨产业波及行业 → 候选池 |
| Step 5 | `cross_industry_linkages[].impact_materiality / visibility` | 跨产业关联的实质性+关注度 |
| 本地DB | `StockInfo` 表 | PE/PB/ROE/行业/市值 |
| 本地DB | `FinancialStatement` 表 | 8Q 财务数据 (用于 ROIIC 计算) |

### 输出

```json
{
  "confidence": "high",
  "lifecycle_gate": {
    "cycle_position": "bottleneck_formation",
    "gate_mode": "growth",
    "gate_rules": "营收增速>30% + ROIIC高位 + 研发费率前列; 负FCF不排除"
  },

  "power_profile": {
    "industry_power_nodes": [
      {
        "node": "高纯钛酸钡粉体",
        "power_type": "supply_bottleneck",
        "why_power": "全球仅村田/堺化学可稳定供应, 扩产周期>24月, 下游MLCC厂绕不过去",
        "evidence": [...]
      }
    ]
  },

  "ranked_stocks": [
    {
      "code": "688012",
      "name": "中微公司",
      "category": "current_strong",

      "source": [
        {"step": "step3", "field": "core_stocks", "role": "龙头"}
      ],
      "exposure_type": "core_business",

      "moat_profile": {
        "position_power": "strong",
        "position_evidence": ["刻蚀设备是晶圆制造必经环节", "全球CR3>80%, 中微是唯一国产替代选项"],
        "pricing_power": "medium",
        "pricing_evidence": ["产品占客户CAPEX<5%但影响良率, 客户对价格不敏感", "毛利率稳定在42-45%"],
        "expansion_power": "strong",
        "expansion_evidence": ["在建工程同比+60%", "已锁定关键零部件长单"],
        "certification_power": "very_high",
        "certification_evidence": ["台积电/中芯国际认证周期>18个月", "已进入5nm产线"],
        "resource_power": "medium",
        "resource_evidence": ["核心工程师团队稳定, 行业人才稀缺"],
        "cognitive_power": "strong",
        "cognitive_evidence": ["2018年提前布局5nm刻蚀, 比国内同行早2年"]
      },

      "profit_capture_thesis": {
        "why_it_captures_profit": [
          "处于晶圆制造必经节点, 客户无法绕过",
          "全球供给集中, 国产替代唯一选项",
          "认证周期长→客户粘性高→份额不易流失"
        ],
        "future_profit_driver": [
          "国内晶圆厂扩产→刻蚀设备需求3年CAGR>40%",
          "从28nm向5nm升级→ASP提升3-5倍",
          "海外客户认证推进→TAM扩大"
        ]
      },

      "growth_asymmetry": {
        "growth_type": "nonlinear_breakout",
        "triggers": [
          "5nm刻蚀机通过验证→订单爆发",
          "海外客户突破→估值体系从'国产替代'切换为'全球竞争'"
        ],
        "current_stage": "订单加速但利润尚未完全释放 (CAPEX高峰)"
      },

      "risk_tags": [],
      "thesis_breakers": [
        "国内晶圆厂资本开支大幅缩减",
        "应用材料/泛林降价抢份额",
        "5nm验证失败或延迟"
      ]
    }
  ],

  "future_strong_candidates": [
    {
      "code": "688xxx",
      "name": "某新兴材料公司",
      "category": "future_strong",

      "moat_profile": {
        "position_power": "emerging",
        "position_evidence": ["ABF基板替代材料, 目前市占<5%但技术指标已追平日系"],
        "pricing_power": "weak",
        "pricing_evidence": ["当前需以价格换份额"],
        "expansion_power": "strong",
        "expansion_evidence": ["在建产能为现有3倍, 设备已锁单"],
        "certification_power": "medium",
        "certification_evidence": ["已通过2家PCB厂验证, 3家在测"],
        "resource_power": "medium",
        "resource_evidence": ["核心原料自给, 不受进口限制"],
        "cognitive_power": "strong",
        "cognitive_evidence": ["3年前布局替代材料, 比国内同行早2年"]
      },

      "profit_capture_thesis": {
        "why_it_captures_profit": [
          "一旦通过头部客户验证, 替代空间巨大",
          "ABF基板紧缺→国产替代窗口打开"
        ],
        "future_profit_driver": [
          "客户验证通过→从0到1的跃迁",
          "产能爬坡→规模效应→毛利率提升"
        ]
      },

      "growth_asymmetry": {
        "growth_type": "inflection_point",
        "triggers": [
          "通过头部PCB厂验证→标志性事件",
          "营收突破3亿→越过盈亏平衡点"
        ],
        "current_stage": "技术导入期, 财务数据尚未体现"
      },

      "catalyst_timeline": [
        {"event": "第3家客户验证结果", "expected": "2026Q3", "impact": "high"},
        {"event": "新产线投产", "expected": "2026Q4", "impact": "high"}
      ],

      "risk_tags": ["customer_concentration", "early_stage"],
      "thesis_breakers": [
        "头部客户验证失败",
        "日系供应商主动降价打压"
      ]
    }
  ],

  "filter_log": [
    {"code": "688yyy", "reason": "与 bottleneck 节点无实质业务关联, 纯概念", "filter": "business_mismatch"},
    {"code": "688zzz", "reason": "成熟期公司但ROIC连续4季<8%, 护城河消退", "filter": "moat_decline"}
  ],

  "step3_backfill": {
    "688012": {
      "segment": "刻蚀设备",
      "actual_margin": 42.5,
      "margin_estimated": false,
      "margin_data_source": "Step 6 财务验证: 2025Q4毛利率=42.5%"
    }
  }
}
```

---

## 处理流程

```
Step 6 主流程 (CoreScreeningAgent.analyze):

1. 候选池聚合
   ├─ Step 3 core_stocks + assets[] + sales_chain/expansion_chain companies[]
   ├─ Step 4 search_queries[] → 标的映射 A→B→C → 股票列表
   └─ Step 5 target_profile[] → 标的映射 A→B→C → 股票列表
   → 去重, 得到 unified_candidates[]

2. 生命周期分轨 (本地函数)
   ├─ 读 Step 3 cycle_position → gate_mode
   │   bottleneck_formation / capacity_release / supply_shock → "growth" 模式
   │   mature / cash_cow → "mature" 模式
   │   crisis_recovery / oversupply → "recovery" 模式
   └─ 确定每个候选的财务阈值

3. 权利节点映射 (LLM, 1次调用)
   └─ 从 supply_chain_map + scarcity_ranking 提取"哪些环节掌握定价权/最难绕过"
   → industry_power_nodes[]

4. 公司-节点匹配 + 六维权力画像 (LLM, 每公司1次 flash)
   对每个候选:
   ├─ 先判断: 是否踩在 power_node 上? (必经节点/关键配套/蹭概念?)
   │   蹭概念 → filter_log (排除)
   ├─ 六维权力判断 (基于搜索证据, 不是空想):
   │   position / pricing / expansion / certification / resource / cognitive
   │   每维: strong / medium / weak / emerging
   │   每维: 至少1条 evidence
   ├─ 利润捕获路径判断:
   │   current_holder / future_beneficiary / hidden_beneficiary / short_term_trade
   └─ 成长非线性判断:
       linear / cyclical_recovery / order_realization / tech_inflection / valuation_regime_shift

5. 财务验证 (本地函数) — ★ 标注不排除
   ├─ 调 FinancialAuditor → verdict + score + 详细指标
   ├─ verdict=FAIL → risk_tags 加 "audit_fail", 但公司仍在候选池
   ├─ verdict=CAUTION → risk_tags 加 "audit_caution"
   ├─ 成熟期: 额外计算 ROIC + FCF 稳定性 → 标注 maturity_quality
   └─ 成长期: 计算 ROIIC + 营收增速 + 研发费率 → 标注 growth_quality
   → 永远不因审计结论排除公司 (误杀成本 > 漏过成本)

6. 输出分级
   ├─ current_strong: 六维 power≥4项 strong, 利润捕获 current_holder
   └─ future_strong: 六维 power 有 emerging 项, 利润捕获 future_beneficiary
   → 不按综合分数排序, 按分类分组输出
   → 每只股票都有 audit 标注, 但不在 Step 6 做排除决策
```

---

## 六维权力画像 (LLM Prompt 核心)

每只候选公司在搜索证据支撑下，输出 6 个维度的定性判断：

| 维度 | 问的问题 | strong 的特征 |
|------|---------|-------------|
| **卡位权** | 是不是产业链必经节点？ | 不可替代, 客户绕不过去, 供给集中 |
| **定价权** | 能不能涨价客户还接受？ | 占客户成本低但影响大, 市场缺货, 无替代 |
| **扩产权** | 景气来了能不能吃下？ | 在建产能充足, 设备已锁单, 扩产不被卷 |
| **认证权** | 客户换供应商难不难？ | 认证周期>18月, 切换成本高, 已有头部客户背书 |
| **资源权** | 掌握稀缺资源吗？ | 独有产能/工程师/电力指标/GPU配额/关键原料 |
| **认知权** | 比市场更早看到未来？ | 提前押对技术路线, 提前布局产能, 提前拿下关键客户 |

**判断规则**:
- 每个维度的值: `strong` / `medium` / `weak` / `emerging` (萌芽期)
- 每个值至少 1 条 evidence 支撑, 来源标注 from 字段
- 没有搜索证据的维度 → 标记 `insufficient_data`
- 禁止 LLM 空想权力判断 (如 "它应该有定价权" 而无证据)

---

## 生命周期分轨 (本地函数)

```python
GATE_RULES = {
    "growth": {  # bottleneck_formation / supply_shock / capacity_release
        "prescreen": "宽松",
        "revenue_yoy_min": 15,      # 营收增速>15% (非强制的30%)
        "allow_negative_fcf": True,  # 负FCF不排除, 标记"CAPEX扩张期"
        "require_roiic": True,       # 必须算ROIIC
        "rd_ratio_check": True,      # 研发费率是否是行业前列
        "audit_on_fail": "mark",     # 审计FAIL→标记, 不排除
    },
    "mature": {  # cash_cow / oligopoly_stable
        "prescreen": "严格",
        "roic_min": 8,               # ROIC>8%
        "fcf_positive_required": True, # FCF必须为正
        "gross_margin_stable": True,  # 毛利率不能持续下滑
        "audit_on_fail": "mark",     # 审计FAIL→标记, 不排除 (成熟期FAIL可能是护城河消退信号, 需Step11综合判断)
    },
    "recovery": {  # crisis_recovery / oversupply
        "prescreen": "中等",
        "revenue_stabilizing": True,  # 营收不再下滑
        "inventory_declining": True,  # 库存去化中
        "audit_on_fail": "mark",      # 审计FAIL→标记
    },
}
```

---

## 当前实现

| 属性 | 值 |
|------|------|
| 文件 | `domain/research/agents/core_screening_agent.py` (📋 新建) |
| API | `POST /api/research/core-screening` (📋 新建) |
| 输入 | Step 3 + Step 4 + Step 5 checkpoint |
| LLM | `chat_flash` (六维判断, 每公司1次) + `chat_pro` (产业权力节点映射, 1次) |
| 搜索 | 标的映射 A→B→C (3轮×候选数) |
| 本地函数 | ROIIC / 生命周期分轨 / FinancialAuditor 调用 |

## 验证

```bash
curl -X POST http://127.0.0.1:8000/api/research/core-screening \
  -d '{"run_id": "xxx"}'

# 检查:
# - ranked_stocks 分组输出 (current_strong / future_strong)
# - 每只股票有完整的 moat_profile (6维, 每维有 evidence)
# - 每只股票有 profit_capture_thesis
# - lifecycle_gate 正确反映 cycle_position
# - filter_log 记录被排除的股票及原因
# - 没有综合数字分数 (不是打分排名, 是分类分组)
```
