# Step 4: 系统动力学推演 (SystemDynamicsAgent)

> **定位**: 产业链静态结构 + 外部压力 → 动态推演结构如何变形。
> **区别于 Step 3**: Step 3 回答"产业链长什么样"，Step 4 回答"结构受压后怎么变形"。

---

## I/O 合约

### 输入 (来自 Step 3)

| 字段 | 用途 |
|------|------|
| `supply_chain_map` | L1-L4 瓶颈节点的供给刚性、利润池、竞争格局 |
| `scarcity_ranking` | 按供给刚性排序的稀缺环节列表 |
| `core_stocks` | 各环节对应的 A 股标的 (Step 3 已提取的, 非 LLM 直接输出) |
| `sales_chain` / `expansion_chain` | 景气传导时序 |

### 输出

```json
{
  "confidence": "high",
  "confidence_note": "Step 3 数据基础较好 + 2轮补充搜索覆盖充分。已反向校验 Step 3 的 severity=extreme 判断: 确认 CoWoS 垄断地位, 但 ABF 基板的替补方案可能被低估。",

  "step3_sanity_check": {
    "questioned": [
      {"claim": "ABF基板 supply_rigidity.severity=extreme", "doubt": "可能存在替代材料(如味之素以外的供应商), severity 可能应为 high 而非 extreme"}
    ],
    "adjustment": "在 resource_crowding 中保留 ABF 基板推演, 但降低确定性, 标记 confidence=medium"
  },
  "system_dynamics": {
    "bottleneck_migration": {
      "current": "CoWoS封装",
      "next_12m": "ABF基板",
      "next_24m": "HBM3E",
      "next_36m": "数据中心电力",
      "migration_drivers": [
        {
          "from": "CoWoS",
          "to": "ABF基板",
          "trigger": "台积电扩产→封装产能释放→基板成为新瓶颈",
          "monitoring_metric": "台积电CoWoS月产能 (wpm)",
          "trigger_threshold": "CoWoS月产能突破200K wpm时, ABF基板成为首要瓶颈",
          "evidence": [...]
        }
      ],
      "evidence": [...]
    },

    "resource_crowding": [
      {
        "resource": "ABF基板产能",
        "squeezed_from": "低端PCB基板",
        "squeezed_by": "先进封装基板",
        "victim_sector": "低端PCB制造商 — 被迫承受基板涨价",
        "hidden_beneficiary": "ABF替代材料供应商",
        "visibility": "low",
        "time_to_impact": "medium_term",
        "monitoring_metric": "ABF基板交期 (周)",
        "trigger_threshold": "交期突破26周时触发受益标的筛查",
        "search_queries": [
          "ABF基板 替代材料 A股 上市公司",
          "ABF基板 供应紧张 受益 标的 2026"
        ],
        "evidence": [...]
      }
    ],

    "profit_pool_shift": [
      {
        "from_segment": "MLCC成品制造",
        "to_segment": "陶瓷粉体",
        "trigger": "MLCC厂扩产→高端粉体需求激增→粉体供给刚性>成品",
        "timeline": "6-12个月",
        "confidence": "high",
        "monitoring_metric": "钛酸钡粉体价格指数 / 粉体厂产能利用率",
        "trigger_threshold": "粉体价格连续2季度上涨>15%",
        "evidence": [...]
      }
    ],

    "thesis_breakers": [
      {
        "thesis": "高端MLCC紧缺持续至2028",
        "break_condition": "村田/三星电机新产线提前投产 + 交期缩短至8周以下",
        "watch_signal": "MLCC原厂月度营收 + 交期数据",
        "evidence": [...]
      }
    ],

    "hidden_beneficiaries": [
      {
        "sector": "MLCC测试设备",
        "reason": "MLCC扩产→每新增一条产线需配测试设备→测试设备需求同步激增",
        "visibility": "very_low",
        "time_to_impact": "medium_term",
        "search_queries": [
          "MLCC 测试设备 A股 供应商",
          "MLCC 扩产 测试设备 受益 标的"
        ],
        "evidence": [...]
      }
    ]
  }
}
```

### 关键变更 (V1.1)

| 变更 | 旧 | 新 | 原因 |
|------|-----|-----|------|
| 股票映射 | `china_stocks: ["688525"]` | `search_queries: [...]` | LLM 幻觉严重, 改为输出搜索词, 下游三步工作流圈定 |
| 量化监控 | 无 | `monitoring_metric` + `trigger_threshold` | 支持自动抓取高频数据验证定性逻辑 |
| 证据类型 | `quality.level` only | + `evidence_type` | 区分传闻(试探仓) vs 硬数据(重仓) |
| 时间维度 | timeline 不统一 | `time_to_impact`: immediate/medium_term/long_term | 与 Step 5 枚举对齐 |

---

## 推演方法论 (嵌入 System Prompt)

### 六步链式推演

```
需求变化 → 资源变化 → 供给变化 → 价格变化 → 成本变化 → CAPEX变化 → 再平衡

1. 确定主驱动力 — 真正的驱动变量是什么？
2. 寻找约束条件 — 什么东西最先不够？
3. 分析资源迁移 — 高利润会吸走谁的资源？
4. 分析系统再平衡 — 什么时候供给会恢复？
5. 寻找利润池迁移 — 利润最终会流向谁？
6. 寻找最后被市场发现的人 — Alpha 来源
```

### 六个案例模板 (few-shot)

| # | 模式 | 推演链 |
|---|------|--------|
| 1 | 资源挤占 | HBM消耗3x晶圆 → 挤占DDR产能 → DRAM涨价 → 二线DRAM厂受益 |
| 2 | 联产经济学 | 炼油减产 → 硫磺供给收缩 → 磷肥飞涨 → 化肥企业受益 |
| 3 | 瓶颈迁移 | GPU短缺 → 云厂自研芯片 → CoWoS成新瓶颈 → 封装设备受益 |
| 4 | CAPEX错配 | 成熟制程CAPEX不足 → MCU缺货2年 → 成熟代工厂暴利 |
| 5 | 利润池迁移 | AI从硬件 → 软件 → 云服务 → 应用, 利润流向不同阶段 |
| 6 | 供给刚性 | 高纯石英砂只有北卡矿 → 光伏扩产 → 石英砂2年涨价10倍 |

### 推演十问 (每轮分析末尾强制自检)

```
1. 真正驱动力？  2. 哪个资源最稀缺？  3. 高利润会吸走谁的资源？
4. 谁会供给下降？  5. 谁会意外涨价？  6. 谁拥有定价权？
7. 哪个瓶颈最难扩产？  8. 利润会迁移到哪里？  9. 市场还没发现谁？
10. 什么信号会证伪我？
```

### Step 3 反向校验 (推演前强制 — P0)

在开始推演之前, 必须**先列出 Step 3 输出中 1-2 个可能错误的判断**:

```
## 反向校验: Step 3 输出质疑

对 Step 3 的 supply_chain_map 逐一审视:
1. 哪个瓶颈的 severity 可能被高估/低估？
2. 哪个 profit_pool 判断可能因搜索片段偏差而不准确？
3. 哪个环节的"零替代"断言可能有例外？

→ 质疑结论: [具体写出哪个判断可能错, 为什么]
→ 调整推演: [基于质疑, 调整后续推演的前提假设]
```

如果没有质疑出任何问题, 说明审视不够。每个行业至少找出 1 个"可能不准确"的判断。

---

## 搜索策略

2 轮自适应搜索，聚焦"二阶传导"和"被忽视的受益者"：

| 轮次 | 维度 | 降级 chain | 域名策略 |
|------|------|-----------|---------|
| 1 | 瓶颈迁移 + 资源挤占 | `{industry} 扩产 瓶颈迁移 新瓶颈 2026` → `{industry} 产能扩张 新制约` → `{industry} supply chain bottleneck shift` | 宽松 — 允许产业链媒体/研报 |
| 2 | 隐藏受益者 + 受损方 | `{industry} 供应链 意外受益 被忽视 标的` → `{industry} 产业链 受益方 受损方` | 宽松 — 需要跨产业联想 |

**注意**: Step 4 是推演环节，搜索目标是从真实世界的产业动态中找到推演锚点，域名范围不宜过窄。下游的三步标的映射工作流（A→B→C）中，步骤 C 的交叉验证阶段才使用白名单（公司公告/财报/交易所）。

---

## 标的映射工作流 (共享工具)

Step 4/5 不再直接输出股票代码。统一使用三步工作流：

```
A. Query Generation (LLM)
   → 输出 search_queries[] (精准搜索词)
   
B. Extraction (搜索+LLM)
   → 执行搜索, LLM 从 Top 5 结果提取候选股票名称

C. Cross-Validation (搜索+LLM)
   → 逐只搜索 "{股票名} 2025年报 主营业务构成"
   → LLM 阅读摘要, 确认主营业务匹配, 剔除不匹配标的
```

此工作流应实现在 `data_loader.py` 或 `framework/` 作为共享工具，供 Step 4/5/6 共用。

### 工作流示例

```
Step 4 输出 search_queries: ["ABF基板 替代材料 A股 上市公司"]

→ B. 执行搜索, 返回 Top 5 结果
→ LLM 提取: ["生益科技", "华正新材", "南亚新材"]

→ C. 逐只交叉验证:
   "生益科技 2025年报 主营业务构成" → 覆铜板/粘结片 ✅ 匹配
   "华正新材 2025年报 主营业务构成" → 覆铜板/绝缘材料 ✅ 匹配
   "南亚新材 2025年报 主营业务构成" → 覆铜板 ✅ 匹配

→ 最终输出: ["600183 生益科技", "603186 华正新材", "688519 南亚新材"]
→ 传入 Step 6 财务清洗
```

---

## 证据要求

所有结论必须带结构化证据，对齐 Step 2/3 标准：

```json
"evidence": [
  {
    "fact": "台积电CoWoS产能2026年120K wpm, 2028年目标250K",
    "from": "search[1.2]·台积电法说会",
    "quality": {"level": "high", "source_type": "company_filing"},
    "evidence_type": "hard_data_confirmation"
  }
]
```

### quality 字段

| 字段 | 可选值 | 说明 |
|------|--------|------|
| `quality.level` | high / medium / low | 来源可信度 |
| `quality.source_type` | company_filing / industry_data / official_policy / sell_side_report / news_media | 来源类型 |
| `evidence_type` | **forward_looking_rumor** / **hard_data_confirmation** | ★ 新增: 传闻 vs 硬数据 |

### evidence_type 枚举

| 值 | 含义 | 交易决策权重 |
|----|------|-------------|
| `forward_looking_rumor` | 产业链传闻/调研/Reddit/社交媒体前瞻信号 | 试探性建仓 (<2%仓位) |
| `hard_data_confirmation` | 财报/海关数据/公司公告/行业白皮书 | 重仓依据 (>5%仓位) |

**原则**: 两者不互斥。同一结论可以同时有传闻证据(前瞻)和硬数据证据(确认)。Step 11 综合报告需区分两种证据的支撑力度。

---

## 枚举约束 (V1.1)

| 字段 | 可选值 |
|------|--------|
| confidence | high / medium / low / insufficient_data |
| profit_pool_shift.confidence | high / medium / low / speculative |
| hidden_beneficiaries.visibility | very_low / low / moderate — 如实判断, 禁止因"低=Alpha大"而系统性压低 |
| bottleneck_migration 时间窗 | next_12m / next_24m / next_36m |
| resource_crowding.time_to_impact | immediate (<3月) / medium_term (3-12月) / long_term (12-36月) |
| hidden_beneficiaries.time_to_impact | immediate / medium_term / long_term |
| evidence.evidence_type | forward_looking_rumor / hard_data_confirmation |

**禁止事项**:
- ❌ 禁止 LLM 直接输出股票代码 (china_stocks 字段已删除)
- ❌ 禁止数值评分 (scarcity_score, alpha_score 等)
- ❌ 禁止模糊 timeline ("12-24个月" → 拆分为 12m 和 24m 两个条目)
- ❌ 禁止为追求 Alpha 而压低 visibility — 如实判断市场认知程度

---

## 与上下游的接口

| 方向 | 步骤 | 传递内容 |
|------|------|---------|
| ← 消费 | Step 3 | supply_chain_map (瓶颈结构) + scarcity_ranking (稀缺排序) |
| → 提供 | 标的映射 | search_queries → A→B→C 三步工作流 → 候选股票列表 |
| → 提供 | Step 6 | 验证后的股票列表 + 业务特征, 财务清洗 |
| → 提供 | Step 9 | thesis_breakers (预期差验证的基准) + monitoring_metric |
| → 提供 | Step 10 | bottleneck_migration (风险分析: 瓶颈会不会突然解除) |
| → 提供 | Step 11 | system_dynamics 全量 → 报告"产业推演"章节 |

---

## 当前实现

| 属性 | 值 |
|------|------|
| 文件 | `domain/research/agents/system_dynamics_agent.py` V1.0 → V1.1 |
| API | `POST /api/research/system-dynamics` |
| 输入 | Step 3 checkpoint JSON |
| LLM | `chat_pro` (需要深度推演) |
| 搜索 | 2 轮自适应 |
| 待改 | Prompt 剥离 china_stocks → search_queries, 新增 monitoring_metric + evidence_type |
| 待建 | 三步标的映射工作流 (共享工具, data_loader.py 或 framework/) |

---

## 验证

```bash
# 先跑 Step 3 得到 supply_chain_map
curl .../supply-chain-hacker -d '{"industry":"MLCC"}'

# Step 4 消费 Step 3 输出
curl .../system-dynamics -d '{"industry":"MLCC","step3_output":{...}}'

# 检查
# - bottleneck_migration 每个 driver 有 monitoring_metric + trigger_threshold
# - resource_crowding/hidden_beneficiaries 无 china_stocks, 有 search_queries
# - evidence 每条有 evidence_type (forward_looking_rumor / hard_data_confirmation)
# - time_to_impact 字段存在且值在枚举范围内
# - 无 scarcity_score 等数值评分
```
