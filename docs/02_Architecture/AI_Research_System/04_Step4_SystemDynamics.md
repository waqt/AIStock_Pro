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
| `core_stocks` | 各环节对应的 A 股标的 |
| `sales_chain` / `expansion_chain` | 景气传导时序 |

### 输出

```json
{
  "system_dynamics": {
    "bottleneck_migration": {
      "current": "CoWoS封装",
      "next_12m": "ABF基板",
      "next_24m": "HBM3E",
      "next_36m": "数据中心电力",
      "migration_drivers": [
        {"from": "CoWoS", "to": "ABF基板", "trigger": "台积电扩产→封装产能释放→基板成为新瓶颈",
         "evidence": [...]}
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
        "china_stocks": ["待确认"],
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
        "visibility": "低 — 市场注意力集中在MLCC成品和粉体",
        "china_stocks": ["待确认"],
        "evidence": [...]
      }
    ]
  }
}
```

---

## 推演方法论 (嵌入 System Prompt)

### 六步链式推演

```
需求变化 → 资源变化 → 供给变化 → 价格变化 → 利润变化 → CAPEX变化 → 再平衡

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

---

## 搜索策略

2 轮自适应搜索，聚焦"二阶传导"和"被忽视的受益者"：

| 轮次 | 维度 | 降级 chain |
|------|------|-----------|
| 1 | 瓶颈迁移 + 资源挤占 | `{industry} 扩产 瓶颈迁移 新瓶颈 2026` → `{industry} 产能扩张 新制约` → `{industry} supply chain bottleneck shift` |
| 2 | 隐藏受益者 + 受损方 | `{industry} 供应链 意外受益 被忽视 标的` → `{industry} 产业链 受益方 受损方` |

---

## 与上下游的接口

| 方向 | 步骤 | 传递内容 |
|------|------|---------|
| ← 消费 | Step 3 | supply_chain_map (瓶颈结构) + scarcity_ranking (稀缺排序) |
| → 提供 | Step 6 | hidden_beneficiaries (补漏: DB筛选以外的标的) |
| → 提供 | Step 9 | thesis_breakers (预期差验证的基准) |
| → 提供 | Step 10 | bottleneck_migration (风险分析: 瓶颈会不会突然解除) |
| → 提供 | Step 11 | system_dynamics 全量 → 报告"产业推演"章节 |

---

## 证据要求

所有结论必须带结构化证据，对齐 Step 2/3 标准：

```json
"evidence": [
  {"fact": "台积电CoWoS产能2026年120K wpm, 2028年目标250K",
   "from": "search[1.2]·台积电法说会",
   "quality": {"level": "high", "source_type": "company_filing"}}
]
```

- quality.level: high/medium/low
- quality.source_type: company_filing / industry_data / official_policy / sell_side_report / news_media
- self_media/ai_summary 仅参考，不得单独支撑关键推演

---

## 枚举约束

| 字段 | 可选值 |
|------|--------|
| profit_pool_shift.confidence | high / medium / low / speculative |
| hidden_beneficiaries.visibility | very_low / low / moderate — 越低 Alpha 越大 |
| bottleneck_migration 时间窗 | next_12m / next_24m / next_36m |

**禁止数值评分**。Step 3 的 scarcity_ranking 已做定性排序，Step 4 不再重复。

---

## 当前实现

| 属性 | 值 |
|------|------|
| 文件 | `domain/research/agents/system_dynamics_agent.py` (📋 新建) |
| API | `POST /api/research/system-dynamics` (📋 新建) |
| 输入 | Step 3 checkpoint JSON |
| LLM | `chat_pro` (需要深度推演) |
| 搜索 | 2 轮自适应 |
| 状态 | 📋 设计完成，待实现 |

---

## 验证

```bash
# 先跑 Step 3 得到 supply_chain_map
curl .../supply-chain-hacker -d '{"industry":"MLCC"}'

# Step 4 消费 Step 3 输出
curl .../system-dynamics -d '{"industry":"MLCC","step3_output":{...}}'

# 检查
# - bottleneck_migration 是否有 current/next_12m/next_24m
# - resource_crowding 是否每个条目有 evidence
# - hidden_beneficiaries.visibility 是否为 very_low/low/moderate
# - thesis_breakers 是否有 watch_signal
# - 无 scarcity_score 等数值评分
```
