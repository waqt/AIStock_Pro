# Step 5: 跨产业关联分析 (CrossIndustryLinkageAgent)

> **定位**: 发现段的终点。回答"这个产业的瓶颈波动，还波及了哪些相邻系统？"——寻找被主流分析遗漏的跨产业意外受益方和受损方。
> **区别于 Step 4**: Step 4 推演同一产业链内部的变形，Step 5 搜索与主供应链**共享资源/设备/工艺**的相邻产业。

---

## I/O 合约

### 输入 (来自 Step 3 + Step 4)

| 字段 | 用途 |
|------|------|
| `supply_chain_map` (Step 3) | 瓶颈节点的稀缺资源/设备/技术名称 |
| `resource_crowding` (Step 4) | 已识别的资源挤占方向 |
| `bottleneck_migration` (Step 4) | 瓶颈迁移路径 |

### 输出

```json
{
  "confidence": "medium",
  "confidence_note": "跨产业关联分析本质上依赖推理而非硬数据, 所有 linkage 需经 Step 6 财务验证后方可确认。已反向校验 Step 3/4: 钛酸钡的稀缺性可能被夸大(Step 3 severity=extreme→Step 4 调整)。",

  "step3_step4_sanity_check": {
    "questioned": [
      {"source": "Step 3", "claim": "钛酸钡 supply_rigidity.severity=extreme", "doubt": "日系供应商(村田/堺化学)有扩产计划, severity 可能为 high"}
    ],
    "adjustment": "shared_constraint 中降低钛酸钡相关推演的确定性"
  },

  "cross_industry_linkages": [
    {
      "source_node": "高纯钛酸钡 (MLCC核心原料)",
      "linkage_type": "shared_constraint",
      "affected_sector": "压电陶瓷执行器",
      "sector_description": "压电陶瓷元件制造, 下游半导体设备/精密定位",
      "impact_direction": "negative",
      "impact_narrative": "MLCC扩产大量消耗钛酸钡→压电陶瓷原料供给收缩→成本上升",
      "target_profile": "主营压电陶瓷元件, 下游半导体设备/精密定位, 营收<50亿, 毛利率>35%, 钛酸钡占原料成本>30%",
      "time_to_impact": "medium_term",
      "impact_materiality": "high",
      "visibility": "low",
      "evidence": [...]
    },
    {
      "source_node": "HBM高带宽内存",
      "linkage_type": "crowding_out_beneficiary",
      "affected_sector": "二线DRAM厂商",
      "sector_description": "DRAM存储芯片制造, 缺乏HBM技术储备",
      "impact_direction": "positive",
      "impact_narrative": "HBM消耗3x晶圆→挤占DDR产能→DDR涨价→未掌握HBM的DRAM厂被动受益",
      "target_profile": "主营DRAM存储芯片, 无HBM技术储备, DDR4/DDR5收入占比>60%, 市值<500亿",
      "time_to_impact": "immediate",
      "impact_materiality": "high",
      "visibility": "moderate",
      "evidence": [...]
    },
    {
      "source_node": "精密叠层机 (MLCC核心设备)",
      "linkage_type": "shared_equipment",
      "affected_sector": "LTCC低温共烧陶瓷滤波器",
      "sector_description": "LTCC滤波器/天线制造, 依赖进口叠层机",
      "impact_direction": "negative",
      "impact_narrative": "MLCC扩产抢购叠层机→LTCC滤波器扩产受阻",
      "target_profile": "主营LTCC滤波器/天线, 依赖进口叠层机, 扩产计划受设备交期制约",
      "time_to_impact": "long_term",
      "impact_materiality": "medium",
      "visibility": "very_low",
      "evidence": [...]
    },
    {
      "source_node": "ABF基板 (先进封装材料)",
      "linkage_type": "byproduct_economics",
      "affected_sector": "低端PCB基板制造商",
      "sector_description": "低端PCB基板制造, 上游ABF材料涨价承压",
      "impact_direction": "negative",
      "impact_narrative": "ABF产能被高端封装抢占→低端PCB基板材料涨价",
      "target_profile": "主营低端PCB基板, ABF基板业务占比<10%, 对原材料涨价敏感",
      "time_to_impact": "medium_term",
      "impact_materiality": "low",
      "visibility": "low",
      "evidence": [...]
    }
  ],

  "discovery_summary": "跨产业意外发现: 2个潜在受益方, 3个潜在受损方, 其中压电陶瓷和LTCC滤波器的关联度最被市场忽视"
}
```

### 关键字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `affected_sector` | string | LLM 输出的细分行业名 (自由文本, 不需要对齐分类体系) |
| `sector_description` | string | 行业通俗描述 (如"做压电陶瓷元件的, 下游半导体设备"), 供 Step 6 程序化匹配分类 |
| `target_profile` | string | 该类企业的核心业务特征描述, 供 Step 6 web search 精确圈定股票, **禁止 LLM 直接输出股票代码** |
| `time_to_impact` | enum | `immediate`(<3月) / `medium_term`(3-12月) / `long_term`(12-36月) |
| `impact_materiality` | enum | `high`(跨界影响占营收>20%) / `medium`(10-20%) / `low`(<10%, 直接过滤) |

---

## 五种推演方法

### 1. 产能挤出 (Crowding-out)
```
问: 这个瓶颈环节的高利润产品，正在挤占谁的产能/资源？
搜: "{稀缺资源} 产能分配 挤占" / "{瓶颈环节} 还用于哪些产品"
例: HBM消耗3x晶圆 → DDR供给收缩 → 二线DRAM厂受益
传导周期: immediate (现货价格1-3月反映)
```

### 2. 副产品经济学 (Byproduct Economics)
```
问: 主产品供需剧变时，哪些副产品会受影响？
搜: "{主产品} 生产 副产品" / "{主产品} 减产 影响"
例: 炼油减产 → 硫磺断供 → 磷肥飞涨 → 化肥企业受益
传导周期: immediate~medium_term
```

### 3. 投入产出溢出 (Input-Output Spillover)
```
问: 一个环节扩产，上游设备/材料需求溢出到哪些其他行业？
搜: "{瓶颈设备} 应用领域" / "{稀缺材料} 下游 用途"
例: CoWoS扩产 → ABF基板紧缺 → 还有谁需要ABF?
传导周期: medium_term~long_term
```

### 4. 牛鞭效应 (Bullwhip Effect)
```
问: 终端需求小幅波动，上游哪个环节会被过度放大？
搜: "{行业} 库存 周期 补库 去库" / "{行业} 订单 波动"
例: 手机-5% → 芯片砍单-30% → 晶圆厂利用率骤降
传导周期: immediate (1-3月迅速反映现货价格)
```

### 5. 蛛网模型 (Cobweb Theorem)
```
问: 当前高利润吸引的CAPEX，τ时间后会不会形成供给洪峰？
输入: Step 3 的 expand_cycle 字段 (τ参数)
例: MLCC扩产τ=18月 → 2027H2可能出现供给洪峰 → 提前预警
传导周期: long_term (12-18月设备进场到产能开出)
```

---

## 搜索策略

对每个 bottleneck node（severity=extreme/high），执行 3 轮定向搜索：

| 轮次 | 维度 | 搜索词模板 |
|------|------|-----------|
| 1 | 共享约束 | `{稀缺资源} 还用于 哪些行业` / `{瓶颈设备} 下游 应用 领域` |
| 2 | 挤占/受益 + 业绩弹性 | `{瓶颈环节} 产能 挤占 影响` / `{稀缺资源} 供应紧张 受益 标的 营收占比` |
| 3 | 跨产业溢出 + 业绩弹性 | `{瓶颈环节} 涨价 影响 下游 产业链` / `{稀缺原料} 国产替代 受益 业绩弹性` |

第 2/3 轮搜索需额外关注: 跨界影响对相关公司营收/利润的实质性程度 (营收敞口 >20% 才有意义)。

---

## linkage_type 枚举

| 值 | 含义 | 方向 | 典型 time_to_impact |
|----|------|------|---------------------|
| `shared_constraint` | 共享稀缺资源/设备 | negative (受损) | medium_term |
| `crowding_out_beneficiary` | 被挤出者的意外受益 | positive | immediate |
| `crowding_out_victim` | 被挤出者直接受损 | negative | immediate |
| `shared_equipment` | 共享核心设备 | negative | long_term |
| `byproduct_economics` | 副产品价格传导 | positive/negative | immediate~medium_term |
| `bullwhip_amplification` | 牛鞭效应放大 | negative | immediate |
| `cobweb_oversupply` | 蛛网模型供给过剩 | negative (预警) | long_term |

## visibility 枚举

| 值 | 含义 |
|----|------|
| `very_low` | 几乎无人关注 |
| `low` | 少数专业机构关注 |
| `moderate` | 已被部分市场参与者认知 |

**注意**: visibility 与 Alpha 潜力没有必然关系。冷门行业可能确实无投资价值, 热门行业中也可能存在被忽视的细分环节。LLM 必须如实判断市场关注程度, 禁止因"低=Alpha大"而系统性压低评分。

## time_to_impact 枚举

| 值 | 含义 | Step 11 用途 |
|----|------|-------------|
| `immediate` | <3 个月传导 | 配动量交易策略 |
| `medium_term` | 3-12 个月传导 | 配中线配置策略 |
| `long_term` | 12-36 个月传导 | 配风控预警/观察池 |

## impact_materiality 枚举

| 值 | 含义 | 后续动作 |
|----|------|---------|
| `high` | 跨界影响占行业营收 >20% | 正常进入 Step 6 |
| `medium` | 10-20% | 标记降权, 进入 Step 6 |
| `low` | <10% | **标记 `materiality_low`, 仍进入 Step 6 但排序靠后** — 不删除, 因为营收占比小≠股价弹性小 (第二曲线/新业务可能被低估) |

**注意**: `impact_materiality=low` 改为标记而非删除。理由是: (1) 营收敞口小但边际变化大时, 股价弹性可能远超营收占比; (2) 新兴业务(第二曲线)的营收占比初期必然低, 但恰好是 Alpha 集中地; (3) 删除后无法回溯, 标记降权让 Step 11 综合所有标签做最终决策。

---

## 与上下游的接口

| 方向 | 步骤 | 传递内容 |
|------|------|---------|
| ← 消费 | Step 3 | supply_chain_map 的 bottleneck 节点 |
| ← 消费 | Step 4 | resource_crowding |
| → 提供 | Step 6 | affected_sector + target_profile → web search 圈定股票 → 财务清洗 |
| → 提供 | Step 9 | visibility + time_to_impact + impact_materiality → 叠加截面动量/换手率 |
| → 提供 | Step 11 | 报告"跨产业关联"章节, time_to_impact 决定策略路由 |

### 与 Step 9 (预期差+拥挤度) 的闭环

Step 5 输出的高 Alpha 候选 (visibility=very_low + materiality=high) 在 Step 9 需要叠加量价过滤:

| 情形 | 动作 |
|------|------|
| 跨界逻辑成立 + 换手率/资金流入温和放大 | **最佳介入窗口**, 触发买入信号 |
| 跨界逻辑成立 + 弱动量 + 极低关注度 | 入**观察池** (Watchlist), 等待催化剂 |
| 跨界逻辑成立 + 换手率已飙升 + 交易拥挤 | 标记"交易已拥挤", 降低优先级 |

---

## Prompt 关键约束

1. **禁止 LLM 直接输出股票代码**: LLM 只输出 `affected_sector` + `sector_description` + `target_profile` (业务特征描述)，具体股票由下游标的映射工作流圈定。
2. **必须输出 time_to_impact**: 基于推演方法类型判断传导速度 (crowding-out→immediate, cobweb→long_term)。
3. **必须输出 impact_materiality**: 评估跨界影响对行业利润表的实质性程度。`low` 标记降权但不删除。
4. **必须输出 confidence**: 整体分析置信度 (high/medium/low/insufficient_data)。跨产业关联本质上是推演, 大部分 linkage 置信度不超过 medium。
5. **visibility 如实判断**: 不因 "低=Alpha大" 而系统性压低 visibility。如实反映市场对该关联的认知程度。
6. **sector_description 不追求分类体系对齐**: 用自然语言描述行业, 不要编造申万分类名称。程序化匹配在 Step 6 做。
7. **LLM 定性, 程序化定量**: Step 5 做跨产业联想和归类, 下游做财务验证和量价过滤。

## 过滤规则 (V1.1 修正 — 标记代替删除)

| 规则 | 旧行为 | 新行为 |
|------|--------|--------|
| `impact_materiality=low` | **硬删除** | 标记 `materiality_low`, 进入 Step 6 但排序靠后 |
| `visibility=moderate` | 视为 Alpha 不足 | 如实标记, 不降权 (热门行业中也有细分盲点) |
| `confidence=insufficient_data` | 无此出口 | 标记, 不丢弃, 等数据补全后重跑 |
| 单个 linkage 证据不足 | 可能被忽略 | 保留, 标记 `confidence=low`, 注明缺什么数据 |

---

## 当前实现

| 属性 | 值 |
|------|------|
| 文件 | `domain/research/agents/cross_industry_linkage_agent.py` (📋 新建) |
| API | `POST /api/research/cross-industry` (📋 新建) |
| 输入 | Step 3 + Step 4 checkpoint |
| LLM | `chat_pro` (需要跨产业联想能力) |
| 搜索 | 3 轮 × bottleneck 节点数 |

---

## 验证

```bash
curl .../cross-industry -d '{"industry":"MLCC","step3_output":{...},"step4_output":{...}}'

# 检查: cross_industry_linkages >= 3 条
# 每条有 linkage_type, visibility, time_to_impact, impact_materiality
# 每条有 affected_sector + target_profile (无 china_stocks)
# evidence 可追溯到搜索结果
# impact_materiality=low 的条目应在后续被过滤
```
