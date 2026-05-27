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
  "cross_industry_linkages": [
    {
      "source_node": "高纯钛酸钡 (MLCC核心原料)",
      "linkage_type": "shared_constraint",
      "affected_sector": "压电陶瓷执行器",
      "impact_direction": "negative",
      "impact_narrative": "MLCC扩产大量消耗钛酸钡→压电陶瓷原料供给收缩→成本上升",
      "china_stocks": ["待确认"],
      "visibility": "low",
      "evidence": [...]
    },
    {
      "source_node": "HBM高带宽内存",
      "linkage_type": "crowding_out_beneficiary",
      "affected_sector": "二线DRAM厂商",
      "impact_direction": "positive", 
      "impact_narrative": "HBM消耗3x晶圆→挤占DDR产能→DDR涨价→未掌握HBM的DRAM厂被动受益",
      "china_stocks": ["待确认"],
      "visibility": "moderate",
      "evidence": [...]
    },
    {
      "source_node": "精密叠层机 (MLCC核心设备)",
      "linkage_type": "shared_equipment",
      "affected_sector": "LTCC低温共烧陶瓷滤波器",
      "impact_direction": "negative",
      "impact_narrative": "MLCC扩产抢购叠层机→LTCC滤波器扩产受阻",
      "china_stocks": ["待确认"],
      "visibility": "very_low",
      "evidence": [...]
    },
    {
      "source_node": "ABF基板 (先进封装材料)",
      "linkage_type": "byproduct_economics",
      "affected_sector": "低端PCB基板制造商",
      "impact_direction": "negative",
      "impact_narrative": "ABF产能被高端封装抢占→低端PCB基板材料涨价",
      "china_stocks": ["待确认"],
      "visibility": "low",
      "evidence": [...]
    }
  ],

  "discovery_summary": "跨产业意外发现: 2个潜在受益方, 3个潜在受损方, 其中压电陶瓷和LTCC滤波器的关联度最被市场忽视"
}
```

---

## 五种推演方法

### 1. 产能挤出 (Crowding-out)
```
问: 这个瓶颈环节的高利润产品，正在挤占谁的产能/资源？
搜: "{稀缺资源} 产能分配 挤占" / "{瓶颈环节} 还用于哪些产品"
例: HBM消耗3x晶圆 → DDR供给收缩 → 二线DRAM厂受益
```

### 2. 副产品经济学 (Byproduct Economics)
```
问: 主产品供需剧变时，哪些副产品会受影响？
搜: "{主产品} 生产 副产品" / "{主产品} 减产 影响"
例: 炼油减产 → 硫磺断供 → 磷肥飞涨 → 化肥企业受益
```

### 3. 投入产出溢出 (Input-Output Spillover)
```
问: 一个环节扩产，上游设备/材料需求溢出到哪些其他行业？
搜: "{瓶颈设备} 应用领域" / "{稀缺材料} 下游 用途"
例: CoWoS扩产 → ABF基板紧缺 → 还有谁需要ABF?
```

### 4. 牛鞭效应 (Bullwhip Effect)
```
问: 终端需求小幅波动，上游哪个环节会被过度放大？
搜: "{行业} 库存 周期 补库 去库" / "{行业} 订单 波动"
例: 手机-5% → 芯片砍单-30% → 晶圆厂利用率骤降
```

### 5. 蛛网模型 (Cobweb Theorem)
```
问: 当前高利润吸引的CAPEX，τ时间后会不会形成供给洪峰？
输入: Step 3 的 expand_cycle 字段 (τ参数)
例: MLCC扩产τ=18月 → 2027H2可能出现供给洪峰 → 提前预警
```

---

## 搜索策略

对每个 bottleneck node（severity=extreme/high），执行 3 轮定向搜索：

| 轮次 | 维度 | 搜索词模板 |
|------|------|-----------|
| 1 | 共享约束 | `{稀缺资源} 还用于 哪些行业` / `{瓶颈设备} 下游 应用 领域` |
| 2 | 挤占/受益 | `{瓶颈环节} 产能 挤占 影响` / `{稀缺资源} 供应紧张 受益 标的` |
| 3 | 跨产业溢出 | `{瓶颈环节} 涨价 影响 下游 产业链` / `{稀缺原料} 国产替代 受益` |

---

## linkage_type 枚举

| 值 | 含义 | 方向 |
|----|------|------|
| `shared_constraint` | 共享稀缺资源/设备 | negative (受损) |
| `crowding_out_beneficiary` | 被挤出者的意外受益 | positive |
| `crowding_out_victim` | 被挤出者直接受损 | negative |
| `shared_equipment` | 共享核心设备 | negative |
| `byproduct_economics` | 副产品价格传导 | positive/negative |
| `bullwhip_amplification` | 牛鞭效应放大 | negative |
| `cobweb_oversupply` | 蛛网模型供给过剩 | negative (预警) |

## visibility 枚举

| 值 | 含义 |
|----|------|
| `very_low` | 几乎无人关注 → Alpha 最大 |
| `low` | 少数专业机构关注 |
| `moderate` | 已被部分市场参与者认知 |

---

## 与上下游的接口

| 方向 | 步骤 | 传递内容 |
|------|------|---------|
| ← 消费 | Step 3 | supply_chain_map 的 bottleneck 节点 |
| ← 消费 | Step 4 | resource_crowding |
| → 提供 | Step 6 | cross_industry 发现的隐藏标的 (补漏 DB 筛选) |
| → 提供 | Step 11 | 报告"跨产业关联"章节 |

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
# 每条有 linkage_type 和 visibility
# evidence 可追溯到搜索结果
```
