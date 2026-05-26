# Step 1b: 全球资本流向扫描 (CapitalFlowScanner)

> **定位**: 不是做宏观分析，而是寻找全球资本正在挤压产业系统的位置。
> **分析哲学**: 产业景气不是概念驱动，而是现金流驱动。谁在花钱？花在哪？约束在哪？

---

## 与 Step 1a 的关系

```
Step 1a (GlobalCapexScanner)     Step 1b (CapitalFlowScanner)
  宏观周期分析                      全球资本流向扫描
  ↓                                ↓
  利率/流动性/PMI/通胀              谁在花钱？花在哪？约束在哪？
  ↓                                ↓
  macro_report.json               capex_vectors + constraint_vectors
  (独立于 pipeline)                (pipeline 的起点)
```

Step 1a 独立运行，提供宏观周期参考。Step 1b 是 pipeline 的实际起跑线——全局扫描和资本流向扫描都从这里开始。

---

## I/O 合约

### 输入

| 来源 | 用途 |
|------|------|
| 4 轮自适应 Web 搜索 | 全球 CAPEX 流向、产业约束、财政方向、受益方 |
| Step 1a 宏观报告 | 参考用（非必需） |

### 输出

```json
{
  "capital_flow_summary": "一句话: 全球资本正集中流向AI数据中心和电网升级, 电力约束已成瓶颈",

  "capex_vectors": [
    {
      "initiator": "MAG7",
      "initiator_region": "global",
      "target": "AI数据中心",
      "capex_scale": "3200亿美元+ (2025财年)",
      "growth": "high",
      "duration": "3_5_years",
      "constraints": ["电力接入", "变压器交期", "液冷散热", "HBM供给"],
      "china_exposure": "high",
      "china_beneficiary": ["电网设备", "液冷散热", "光模块", "先进封装"],
      "theme_type": "industrial_capex",
      "evidence": [
        {"fact": "MAG7 2025 capex指引$320B", "from": "search[1.3]·财报汇总",
         "quality": {"level": "high", "source_type": "company_filing"}}
      ]
    }
  ],

  "constraint_vectors": [
    {
      "node": "变压器",
      "constraint_type": "equipment_lead_time",
      "severity": "extreme",
      "lead_time": "18_24_months",
      "upstream_trigger": "AI数据中心+电网升级双驱动",
      "downstream_impact": ["数据中心交付延迟", "铜需求激增"],
      "evidence": [...]
    }
  ],

  "theme_type_distribution": {
    "industrial_capex": 3,
    "commodity_cycle": 1,
    "macro_asset": 0,
    "policy_theme": 0
  }
}
```

---

## 搜索策略

5 轮自适应搜索，每轮带 3 级降级 chain（精准→简化→英文）：

| 轮次 | 维度 | 降级 chain |
|------|------|-----------|
| 1 | 全球 CAPEX 流向 | `MAG7 科技巨头 CAPEX 2025 2026` → `大型科技企业 资本开支 AI 2026` → `global tech capex spending AI` |
| 2 | 产业约束 | `AI数据中心 电力 变压器 液冷 交期 瓶颈 2026` → `数据中心 电力瓶颈 变压器短缺` → `data center power constraint transformer` |
| 3 | 中国财政方向 | `中国 专项债 财政支出 投向 算力 电网 2026` → `专项债 基建 新质生产力 半导体` → `china fiscal spending infrastructure` |
| 4 | 国产受益方 | `AI芯片 光模块 液冷 先进封装 国产替代 受益 A股 2026` → `算力产业链 国产化 受益标的` → `china AI supply chain beneficiary` |
| 5 | **中国国内 CAPEX** | `国家电网 中芯国际 三大运营商 国企 CAPEX 资本开支 2026` → `央企 国企 资本开支 投资 算力 电网 半导体` → `china state grid SMIC telecom capex` |

> 注：第 5 条链确保覆盖国内资本开支主体（国家电网/中芯国际/运营商等），不遗漏中国内部的产业投资驱动力。

---

## theme_type 分类

| 值 | 含义 | 是否进入 Step 2 |
|----|------|---------------|
| `industrial_capex` | 实体产业资本开支（AI数据中心/电网/先进封装） | ✅ YES |
| `commodity_cycle` | 商品周期（铜/锂） | ✅ 部分 |
| `policy_theme` | 政策/财政主题（需拆分为具体产业） | ⚠️ 拆分后可用 |
| `macro_asset` | 宏观交易资产（黄金/REITs） | ❌ NO |

---

## constraint_type 枚举

| 值 | 含义 |
|----|------|
| `equipment_lead_time` | 设备交期约束 |
| `natural_resource` | 自然资源稀缺 |
| `certification_barrier` | 认证壁垒 |
| `policy_restriction` | 政策/出口管制 |
| `infrastructure_bottleneck` | 基础设施瓶颈（电网/土地） |

---

## 与下游的接口

| 方向 | 步骤 | 传递内容 |
|------|------|---------|
| → 提供 | Step 2 (auto_scan/capital_flow) | `capex_vectors[theme_type=industrial_capex].china_beneficiary` → hypothesis_sectors |
| → 提供 | Step 2 (手动) | 用户在宏观参考 + 资本流向结果后，手动选择分析产业 |

---

## 当前实现

| 属性 | 值 |
|------|------|
| 文件 | `domain/research/agents/capital_flow_scanner.py` |
| 版本 | V1.0 |
| API | `POST /api/research/capital-flow` |
| LLM | `chat_pro` (deepseek-v4-pro, timeout=120s) |
| Trace | 4 轮搜索 + 1 次 LLM 调用 |
| Cache | 当天有效，过期自动重跑 |

---

## 验证

```bash
# 独立运行
curl -X POST http://127.0.0.1:8000/api/research/capital-flow

# 检查 capex_vectors 是否有 initiator/target/constraints/evidence
# 检查 theme_type 是否在枚举范围内
# 检查 evidence 是否有 quality 标注
```
