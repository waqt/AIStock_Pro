# Step 6b: 核心资产筛选 — 量化数据底座 (V5.16)

> **定位**: Step 6 的量化数据层。不再是预设阈值过滤器，而是作为 LLM 可调用的数据工具箱。
> **设计变迁**: V1.0 的 GATE_RULES/ROIIC/研发资本化预设阈值已被移除。LLM 在 `_verify_single` 中通过工具自主决定查什么、怎么判断。
> **姊妹文档**: [06a 智能体设计](06a_Step6_Agent_Design.md)

---

## 一、架构变迁: 从预设筛选 → LLM 数据工具箱

### V1.0 (已淘汰)
```
Prescreen(营收增速/ROIIC/FCF阈值) → StageClassifier(生命周期分轨)
  → FinancialAuditor(硬编码) → 六维权力画像
```

### V5.16 (当前)
```
hard_filter(ST/流动性) → [无预设阈值] → _verify_single(LLM自主调工具)
                                              ├─ query_financial_data()
                                              └─ web_search()
```

**关键变化**: 量化数据从"预设过滤器"变成了"LLM 自主查询的数据源"。不再有 `GATE_RULES`、`prescreen()`、`compute_roiic()` 等硬编码调用。

---

## 二、硬过滤器 (唯一预筛选)

`hard_filter` 是 Phase 2 结束后唯一的预筛选逻辑：

```python
# domain/research/services/screening_gate.py
def hard_filter(candidates, stock_info_map):
    """只排除 ST / 已退市 / 低流动性"""
    passed, filtered = [], []
    for c in candidates:
        code = c["code"]
        info = stock_info_map.get(code, {})
        if info.get("is_st"):
            filtered.append({**c, "filter": "st_delisted"})
            continue
        if (info.get("daily_turnover", 0) or 0) < 10_000_000:  # 日均成交额 < 1千万
            filtered.append({**c, "filter": "daily_turnover_below_10m"})
            continue
        passed.append(c)
    return passed, filtered
```

### 不设财务阈值的理由

| 旧 (V1.0) | 问题 | 解决方案 (V5.16) |
|-----------|------|-----------------|
| 营收增速 > 15% 最低门槛 | 拐点期公司可能营收刚启动，误杀 | LLM 自主判断营收是否合理 |
| ROIIC > 8% | CAPEX 高峰期 ROIIC 为负但恰是爆发前夜 | LLM 结合行业背景判断 |
| ROIC > 8% (成熟期) | 周期性底部 ROIC 低但可能反转 | LLM 看趋势而非绝对值 |
| FCF 必须为正 | 高成长公司必然负 FCF | LLM 识别是投资还是烧钱 |

---

## 三、FinancialQueryService — 财务数据工具箱

`_verify_single` 中 LLM 通过 `call_with_tools` 调用的核心工具。

### 调用方式

```python
# LLM 在 _verify_single 中自主调用
result = query_financial_data(
    code="688012",
    indicators=["roic_pct", "revenue_yoy", "gross_margin_trend", "operating_leverage"],
    raw_fields=["revenue", "rd_expense", "operate_cost", "total_assets"]
)
```

### 数据范围

**30+ 财务指标** (自动计算，不依赖 LLM):

| 分类 | 指标 | 单位 |
|------|------|------|
| 盈利能力 | `roe`, `roic_pct`, `gross_margin_trend`, `roiic`, `rd_intensity` | % |
| 成长性 | `revenue_yoy`, `revenue_acceleration`, `profit_growth`, `operating_leverage` | % |
| 现金流 | `ocf_health`, `burn_rate_months`, `working_capital_efficiency` | 枚举/倍 |
| 健康度 | `scissor_gap`, `contract_liability_yoy`, `inventory_revenue_ratio` | % |
| 质量 | `beneish_m_score`, `roic_stability`, `operating_margin_stability` | 分 |
| 规模 | `revenue_scale` | 枚举 |

**20+ 原始财务字段** (直接从 DB 加载):

| 字段 | 来源 |
|------|------|
| `revenue`, `operate_cost`, `gross_profit` | 利润表 |
| `rd_expense`, `sell_expense`, `manage_expense` | 利润表 |
| `parent_profit`, `operate_profit` | 利润表 |
| `total_assets`, `current_assets`, `total_equity` | 资产负债表 |
| `inventory`, `contract_liability`, `accounts_receivable` | 资产负债表 |
| `operate_cashflow`, `invest_cashflow`, `capex` | 现金流量表 |

### 数据字典注入

`FinancialQueryService.format_catalog_for_prompt()` 产出的字典在 `_build_competitive_analysis_prompt` 中通过 `{{FINANCIAL_CATALOG}}` 注入，LLM 据此了解可用字段及其含义。

---

## 四、数据依赖清单

### 已有数据

| 数据 | 表/来源 | 用途 |
|------|---------|------|
| PE/PB/ROE/市值/行业 | StockInfo | 硬过滤器 + LLM 查询 |
| 8Q 营收/利润/资产/负债/现金流 | FinancialStatement | LLM 自主分析 |
| 日均成交额 | MarketData (volume×close) | 硬过滤器 |
| cycle_position | Step 2/3 checkpoint | 输出元信息 |
| 30+ 财务指标 | financial_indicators (SQLite) | LLM 工具查询 |
| 估值数据 | StockInfo (PE/PB/市值) | LLM 工具查询 |

### 查询流程

```
_verify_single 中 LLM 调用 query_financial_data()
  → FinancialQueryService.query(code, indicators, raw_fields)
     → 优先查 financial_indicators SQLite 缓存
     → 缓存缺失时: load_financials(8Q) + 滑动窗口计算
     → 返回 {indicator_name: value, ...}
```

---

## 五、与 FinancialAuditor 的分工 (V5.16)

```
Step 6 V5.16:

hard_filter (本地函数):
  - 只排除 ST / 低流动性
  - 不设财务阈值

_verify_single (LLM 自主):
  - LLM 通过 query_financial_data 查财务数据
  - LLM 通过 web_search 查市场信息
  - 自主决定是否需要类似 FinancialAuditor 的深度分析
  - 自主决定分析维度 (不限于六维权力)

FinancialAuditor (独立步骤, 不在 Step 6 固定调用):
  - 8Q 剪刀差 + Beneish M-Score
  - 仅在 Path A (step2_only, DEPRECATED) 中保留调用
  - Path C 中由 _verify_single 的 LLM 自主决定是否做审计类推理

分工原则:
  hard_filter = 硬门禁 (流动性不足/已退市 → 排除)
  _verify_single = 综合判断 (LLM 自主调数据 → 分类)
  FinancialAuditor = 可选深度审计 (不固定调用)
```

### V1.0 对比 (已淘汰的特性)

| 特性 | 文件 | 状态 |
|------|------|------|
| `GATE_RULES` (生命周期分轨阈值) | `screening_gate.py` | V5.16 移除 |
| `get_gate_mode()` | `screening_gate.py` | V5.16 移除 |
| `prescreen()` (营收/ROIIC/FCF阈值) | `screening_gate.py` | V5.16 移除 |
| `compute_roiic()` | `framework/finance/roiic.py` | 未删除, 但 Step 6 不再调用 |
| `adjust_rd_capitalization()` | `framework/finance/rd_adjustment.py` | 未删除, 但 Step 6 不再调用 |
| `StageClassifier` | `framework/finance/stage_classifier.py` | V5.16 从 Step 6 移除 |

---

## 六、数据底座现状

### 已有且可靠的数据

| 数据 | 表 | 覆盖范围 | 可靠性 |
|------|-----|---------|--------|
| PE/PB/市值/换手率 | StockInfo | 持仓+自选股 (腾讯行情) | ✅ 实时更新 |
| 日线 OHLCV | MarketData | 所有同步过的股票 | ✅ 历史完整 |
| 8Q 利润表 (营收/利润/成本/费用) | FinancialStatement | A股 (akshare) | ✅ 按季度 |
| 8Q 现金流 (经营CF) | FinancialStatement | A股 | ✅ |
| 8Q 资产负债表 | FinancialStatement | A股 | ✅ |
| 30+ 财务指标 | financial_indicators.db | 持仓+自选股 (计算后) | ✅ |
| 技术指标 / 拥挤度 / 筹码 | indicators.db | 持仓+自选股 | ✅ |

### 搜索替代方案 (LLM 在 _verify_single 中使用)

当本地数据不足时，LLM 可通过 `web_search` 补充:

| 场景 | 搜索方案 |
|------|---------|
| 候选股票不在 StockInfo | `search_web("{股票代码} PE PB ROE 市值")` |
| 财务数据少于 4Q | `search_web("{股票代码} 2025年报 营收 利润 毛利率")` |
| 行业分类缺失 | `search_web("{股票代码} 主营业务 所属行业")` |
| 研发费率异常 | `search_web("{股票代码} 研发费用 2025年报")` |

---

## 验证

```python
# 验证硬过滤器
from app.domain.research.services.screening_gate import hard_filter

# 验证 hard_filter: ST/流动性排除
passed, filtered = hard_filter(candidates, stock_info_map)
assert all(c.get("code") for c in passed)

# 验证 FinancialQueryService 工具可用
from app.domain.quant.engine.financial_query_service import FinancialQueryService
catalog = FinancialQueryService.format_catalog_for_prompt()
assert "roic" in catalog

# 验证 catalog 可注入 prompt
from app.domain.research.agents.core_screening_agent import CoreScreeningAgent
agent = CoreScreeningAgent()
prompt = agent._build_competitive_analysis_prompt("公司", "688012", "AI", [])
prompt = prompt.replace("{{FINANCIAL_CATALOG}}", catalog)
assert "FINANCIAL_CATALOG" not in prompt
```
