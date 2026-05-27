# Step 1b: 全球资本流向扫描 (CapitalFlowScanner)

> **定位**: 不是做宏观分析，而是寻找全球资本正在挤压产业系统的位置。
> **分析哲学**: 产业景气不是概念驱动，而是现金流驱动。谁在花钱？花在哪？约束在哪？
> **V1.1**: 搜索链由用户指定行业动态生成，不预设任何赛道。

---

## 与 Step 1a 的关系

```
Step 1a (GlobalCapexScanner)     Step 1b (CapitalFlowScanner)
  宏观周期分析                      全球资本流向扫描
  ↓                                ↓
  利率/流动性/PMI/通胀              谁在花钱？花在哪？约束在哪？
  ↓                                ↓
  macro_report.json               pressure_vectors + constraint_vectors
  (独立于 pipeline)                (pipeline 的起点)
```

Step 1a 独立运行，提供宏观周期参考。Step 1b 是 pipeline 的实际起跑线——资本流向扫描从这里开始。

---

## I/O 合约

### 输入

| 来源 | 用途 |
|------|------|
| 用户指定 `industry` | **驱动搜索链生成** — 搜索聚焦该行业的全球/中国资本流向 |
| Step 1a 宏观报告 | 参考用（非必需），regime 提示 |
| 5 轮自适应 Web 搜索 | 由 `_build_search_chains(industry)` 动态生成 |

### 输出

```json
{
  "capital_flow_summary": "一句话: 全球资本正集中流向[用户关注的行业方向]..., [系统节点]正在承压",

  "pressure_vectors": [
    {
      "capital_source": "资本来源",
      "source_region": "global/domestic/both",
      "system_node": "承压的系统节点 (infrastructure/equipment/natural_resource/certification/policy)",
      "pressure_type": "infrastructure_bottleneck",
      "pressure_signals": ["具体压力信号1", "信号2", "信号3"],
      "intensity": "high",
      "duration": "3_5_years",
      "transmission_direction": "upstream",
      "evidence": [
        {"fact": "具体事实", "from": "search[X.Y]·来源",
         "quality": {"level": "high", "source_type": "company_filing"}}
      ]
    }
  ],

  "constraint_vectors": [
    {
      "node": "约束节点",
      "constraint_type": "equipment_lead_time",
      "severity": "extreme",
      "lead_time": "over_24m",
      "trigger": "什么需求触发了这个约束",
      "evidence": [...]
    }
  ]
}
```

---

## 搜索策略 (V1.1 — 行业驱动)

搜索链由用户指定的 `industry` 动态生成，**不预设任何赛道**：

### 有行业指定 (如 "AI电力基础设施" / "生物制药")

| 轮次 | 维度 | 搜索词模板 |
|------|------|-----------|
| 1 | 全球 CAPEX 流向 | `{industry} 全球 资本开支 CAPEX 投资 龙头 2026` → 简中 → English |
| 2 | 产业约束 | `{industry} 产业链 瓶颈 产能 供给约束 短缺 2026` → 简中 → English |
| 3 | 中国财政方向 | `中国 {industry} 专项债 财政 投资 扩产 2026` → 简中 → English |
| 4 | 受益方/供应商 | `{industry} 受益方 供应商 产业链 上游 设备 材料 2026` → 简中 → English |
| 5 | 中国国内 CAPEX | `中国 央企 国企 {industry} 资本开支 布局 投资 2026` → 简中 → English |

### 无行业指定 (宽泛扫描)

| 轮次 | 维度 | 搜索词 |
|------|------|--------|
| 1 | 全球 CAPEX 趋势 | `2026 全球 资本开支 CAPEX 投资 趋势 行业` |
| 2 | 全球供应链约束 | `2026 全球 供应链 瓶颈 产能 短缺 制约` |
| 3 | 中国财政方向 | `中国 专项债 财政支出 产业投资 投向 2026` |
| 4 | 受益方 | `全球 资本流向 产业 受益方 供应商 2026` |
| 5 | 中国国内 CAPEX | `中国 央企 国企 资本开支 扩产 投资 方向 2026` |

### 关键原则

```
✅ 搜索链由用户行业驱动 — 用户说"生物制药"就搜生物制药的资本流向
✅ 不预设赛道 — 不在搜索词中硬编码 AI/电力/芯片
✅ 同时覆盖全球 + 中国 — 每链有中文和英文降级
✅ 系统节点输出保持通用 — infrastructure_bottleneck/equipment_lead_time/natural_resource...
❌ 禁止在搜索词中限定具体产业名称 — 如"变压器""液冷""HBM"
```

---

## pressure_type 枚举

| 值 | 含义 |
|----|------|
| `infrastructure_bottleneck` | 基础设施瓶颈（电力/散热/网络/用地） |
| `equipment_lead_time` | 设备交期约束 |
| `natural_resource` | 自然资源稀缺 |
| `certification_barrier` | 认证壁垒 |
| `policy_restriction` | 政策/出口管制 |

## constraint_type 枚举

| 值 | 含义 |
|----|------|
| `equipment_lead_time` | 设备交期约束 |
| `natural_resource` | 自然资源稀缺 |
| `certification_barrier` | 认证壁垒 |
| `policy_restriction` | 政策/出口管制 |
| `infrastructure_bottleneck` | 基础设施瓶颈 |

---

## 与下游的接口

| 方向 | 步骤 | 传递内容 |
|------|------|---------|
| ← 消费 | 用户 | `industry` → 驱动搜索链生成 |
| → 提供 | Step 2 | `pressure_vectors[]` + `constraint_vectors[]` → 帮助 Step 2 判断哪些产业环节承压 |

---

## 当前实现

| 属性 | 值 |
|------|------|
| 文件 | `domain/research/agents/capital_flow_scanner.py` |
| 版本 | V1.1 |
| API | `POST /api/research/capital-flow` |
| LLM | `chat_flash` (deepseek-v4-flash, timeout=60s) |
| 搜索 | 5 链 × 3 级降级 × 4 条 = 最多 60 条结果 |
| Trace | 5 轮搜索 + 1 次 LLM 调用 |
| Cache | 当天有效，过期自动重跑 |
| 偏向控制 | 搜索词由用户行业动态生成，无预设赛道 |

---

## 验证

```bash
# 有行业指定
curl -X POST http://127.0.0.1:8000/api/research/capital-flow \
  -H "Content-Type: application/json" \
  -d '{"industry":"生物制药"}'

# 无行业指定（宽泛扫描）
curl -X POST http://127.0.0.1:8000/api/research/capital-flow

# 检查: pressure_vectors 非空, constraint_vectors 非空
# 检查: system_node 是通用系统节点 (不出现产业名称)
# 检查: 每条 evidence 带 quality
# 检查: pressure_type 在枚举范围内
```
