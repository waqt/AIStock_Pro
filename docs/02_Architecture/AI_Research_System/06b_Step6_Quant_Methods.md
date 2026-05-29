# Step 6b: 核心资产筛选 — 量化方法 + 数据底座

> **定位**: Step 6 中所有不需要 LLM 推理的计算逻辑。纯函数、纯数据。
> **设计来源**: Gemini 生命周期分轨 + ROIIC + 研发资本化调整
> **姊妹文档**: [06a 智能体设计](06a_Step6_Agent_Design.md)

---

## 一、生命周期分轨 (Lifecycle Gate)

### 设计原则

不同产业生命周期的公司，用不同的财务门槛。避免用成熟期标准误杀成长期公司。

### 分轨逻辑

```python
# domain/research/services/screening_gate.py

GATE_RULES = {
    "growth": {
        "label": "成长期/瓶颈爆发期",
        "trigger_cycle": ["bottleneck_formation", "supply_shock", "capacity_release"],
        "prescreen": "宽松 — 保护成长股不被财务指标误杀",
        "rules": {
            "revenue_yoy_min_pct": 15,       # 营收同比增速最低门槛
            "allow_negative_fcf": True,       # 负自由现金流不排除
            "require_roiic": True,            # 必须计算增量ROIC
            "rd_ratio_check": True,           # 研发费率是否行业前列
            "audit_fail_action": "mark",      # 审计FAIL→标记(不排除)
            "gross_margin_check": "optional",  # 毛利率检查可选
        }
    },
    "mature": {
        "label": "成熟期/现金牛",
        "trigger_cycle": ["cash_cow", "oligopoly_stable"],
        "prescreen": "严格 — 成熟期必须有已验证的财务回报",
        "rules": {
            "roic_min_pct": 8,                # ROIC最低要求
            "fcf_positive_required": True,     # FCF必须为正
            "gross_margin_stable": True,       # 毛利率不能持续下滑(>4Q)
            "audit_fail_action": "exclude",    # 审计FAIL→排除
            "rd_ratio_check": False,           # 不检查研发费率
        }
    },
    "recovery": {
        "label": "周期反转/出清期",
        "trigger_cycle": ["crisis_recovery", "oversupply"],
        "prescreen": "中等 — 关注反转信号而非当前盈利",
        "rules": {
            "revenue_stabilizing": True,       # 营收不再加速下滑
            "inventory_declining": True,       # 库存去化进行中
            "audit_fail_action": "mark",       # 审计FAIL→标记
        }
    },
}

def get_gate_mode(step3_output: dict) -> str:
    """从 Step 3 的 cycle_position 推断筛选模式"""
    cycle = step3_output.get("cycle_position", "")
    for mode, config in GATE_RULES.items():
        if any(t in cycle for t in config["trigger_cycle"]):
            return mode
    return "growth"  # 默认: 保守偏成长
```

### 输入来源

Step 2 的 `cycle_position` 字段决定生命周期阶段:

```
Step 2 → cycle_position → Step 3 传入 → Step 6 读取
```

---

## 二、ROIIC 计算 (增量投资资本回报率)

### 为什么用 ROIIC 而非 ROIC

对于成长期公司，静态 ROIC 可能很低（因为近期大量 CAPEX 还未产生回报）。ROIIC 衡量的是**新增投入的每一块钱能产生多少回报**——这才是判断"它在烧钱还是在投资"的关键。

### 公式

$$ROIIC = \frac{NOPAT_{t} - NOPAT_{t-4}}{InvestedCapital_{t-1} - InvestedCapital_{t-5}}$$

其中:
- NOPAT = 营业利润 × (1 - 有效税率), 取最近4Q滚动
- InvestedCapital = 总资产 - 现金 - 无息流动负债
- t 与 t-4 间隔 4 个季度 (YoY 比较, 消除季节性)

### 实现

```python
# framework/finance/roiic.py

def compute_roiic(financials: List[Dict]) -> dict:
    """
    输入: 最近 8Q 财务数据 (从 FinancialStatement 表)
    返回: {roiic, nopat_current, nopat_prev, ic_current, ic_prev, interpretation}
    """
    if len(financials) < 8:
        return {"roiic": None, "error": "insufficient data (need 8Q)"}

    # 分组: 最近 4Q vs 前 4Q
    recent_4q = financials[:4]
    prior_4q = financials[4:8]

    # NOPAT = sum(operate_profit) * (1 - tax_rate)
    # 简化: 用 parent_profit 替代, tax_rate 用 15% (高新技术企业)
    TAX_RATE = 0.15
    nopat_current = sum(q.get("parent_profit", 0) or 0 for q in recent_4q) * (1 - TAX_RATE)
    nopat_prev = sum(q.get("parent_profit", 0) or 0 for q in prior_4q) * (1 - TAX_RATE)

    # InvestedCapital = total_assets - cash - non_interest_current_liabilities
    # 简化: total_assets - current_assets * 0.3 (近似无息流动负债)
    def invested_capital(q):
        ta = q.get("total_assets", 0) or 0
        ca = q.get("current_assets", 0) or 0
        return ta - ca * 0.3

    ic_current = invested_capital(recent_4q[0])   # 最新季度
    ic_prev = invested_capital(prior_4q[0])       # 4Q前的季度

    if ic_current == ic_prev:
        return {"roiic": None, "error": "no change in invested capital"}

    roiic = (nopat_current - nopat_prev) / (ic_current - ic_prev)

    interpretation = _interpret_roiic(roiic)
    return {
        "roiic": round(roiic, 4),
        "roiic_pct": round(roiic * 100, 1),
        "nopat_current": round(nopat_current, 2),
        "nopat_prev": round(nopat_prev, 2),
        "ic_current": round(ic_current, 2),
        "ic_prev": round(ic_prev, 2),
        "delta_nopat": round(nopat_current - nopat_prev, 2),
        "delta_ic": round(ic_current - ic_prev, 2),
        "interpretation": interpretation,
    }

def _interpret_roiic(roiic: float) -> str:
    if roiic > 0.30:  return "高效扩张 — 每1元新投入产生>0.3元回报, 成长质量极高"
    if roiic > 0.15:  return "健康扩张 — 新增资本回报率良好"
    if roiic > 0.08:  return "可接受 — 刚覆盖资本成本"
    if roiic > 0:     return "低效扩张 — 新投入回报尚不足以覆盖WACC, 需观察"
    return "价值毁灭 — 新投入在亏钱, 应停止扩张"
```

### 使用方式

```
成长期公司: ROIIC > 15% → 高质量成长, 优先关注
            ROIIC 0-15% → 正常成长, 需配合其他指标
            ROIIC < 0 → 红灯, 仅在有明确拐点信号时保留

成熟期公司: 不适用 ROIIC, 用静态 ROIC
```

---

## 三、研发资本化调整

### 问题

GAAP 会计准则将研发支出全额计入当期费用，导致高研发投入的科技公司：
- 账面利润被压低
- ROE/ROIC 被低估
- 资产负债表不反映研发形成的无形资产

### 调整方法

```python
# framework/finance/rd_adjustment.py

def adjust_rd_capitalization(financials: List[Dict], amort_years: int = 5) -> dict:
    """
    将研发支出资本化并摊销, 还原真实的盈利能力和资产回报率。

    参数:
      financials: 最近 8Q 财务数据
      amort_years: 研发资本化摊销年限 (默认5年)
    返回:
      {adjusted_profit, adjusted_assets, rd_asset, rd_amortization, adjustment_note}
    """
    rd_expenses = [q.get("rd_expense", 0) or 0 for q in financials]

    # 计算研发资产 (未摊销部分)
    rd_asset = 0
    annual_amort = 1.0 / amort_years
    for i, rd in enumerate(rd_expenses):
        quarters_remaining = max(0, amort_years * 4 - i)
        unamortized_pct = quarters_remaining / (amort_years * 4)
        rd_asset += rd * unamortized_pct * annual_amort

    # 当期摊销 = 研发资产 / 剩余年限
    rd_amortization = rd_asset / amort_years

    # 调整后利润 = 报告利润 + 当期研发费用 - 研发摊销
    reported_profit = sum(q.get("parent_profit", 0) or 0 for q in financials[:4])
    current_rd = sum(rd_expenses[:4])
    adjusted_profit = reported_profit + current_rd - rd_amortization

    # 调整后总资产 = 报告总资产 + 研发资产净值
    reported_assets = financials[0].get("total_assets", 0) or 0
    adjusted_assets = reported_assets + rd_asset

    return {
        "reported_profit": round(reported_profit, 2),
        "adjusted_profit": round(adjusted_profit, 2),
        "profit_adjustment_pct": round((adjusted_profit / reported_profit - 1) * 100, 1) if reported_profit else 0,
        "rd_asset": round(rd_asset, 2),
        "rd_amortization": round(rd_amortization, 2),
        "adjusted_roe": round(adjusted_profit / adjusted_assets * 100, 1) if adjusted_assets else 0,
        "note": f"研发资本化摊销{amort_years}年: 利润上调{round((adjusted_profit/reported_profit-1)*100, 1)}%"
               if reported_profit and adjusted_profit > reported_profit else "研发资本化无显著影响"
    }
```

### 使用场景

```
成长期公司 + 研发费率 > 10%:
  → 必须做研发资本化调整
  → 调整后的 ROE 才是真实的盈利能力
  → 在 moat_profile 中标注 "财务数据为研发资本化调整后值"

成熟期公司:
  → 可选, 不强制
```

---

## 四、财务健康快速筛查 (Prescreen)

### 硬性排除 (所有模式通用)

```python
HARD_EXCLUDE = {
    "st_delisted": "已退市或 ST",
    "daily_turnover_below_10m": "日均成交额 < 1000万 (流动性不足)",
}

# 注意: 不设统一 PE/ROE 阈值 — 由生命周期分轨决定
```

### 生命周期分轨的 Prescreen

```python
def prescreen(candidates: List[Dict], gate_mode: str, stock_info: Dict, financials: Dict) -> tuple:
    """
    返回: (passed, filtered) — 通过和过滤的候选
    """
    rules = GATE_RULES[gate_mode]["rules"]
    passed, filtered = [], []

    for c in candidates:
        code = c["code"]
        info = stock_info.get(code, {})
        fin = financials.get(code, {})

        # 硬性排除
        if info.get("is_st"): filtered.append({**c, "filter": "st_delisted"}); continue

        if gate_mode == "growth":
            # 营收增速 (从 financials 的 yoy 算)
            rev_yoy = _calc_revenue_yoy(fin)
            if rev_yoy < rules["revenue_yoy_min_pct"]:
                filtered.append({**c, "filter": f"revenue_yoy={rev_yoy}%<{rules['revenue_yoy_min_pct']}%"})
                continue

            # 负 FCF → 标记但不排除
            if not rules["allow_negative_fcf"]:
                fcf = _calc_fcf(fin)
                if fcf < 0:
                    filtered.append({**c, "filter": "fcf_negative"})
                    continue

            c["flags"] = c.get("flags", [])
            if _calc_fcf(fin) < 0:
                c["flags"].append("capex_expansion")

        elif gate_mode == "mature":
            roiic_data = compute_roiic(fin)
            if roiic_data.get("roiic_pct", 0) < rules["roic_min_pct"]:
                filtered.append({**c, "filter": f"ROIIC={roiic_data.get('roiic_pct',0)}%<{rules['roic_min_pct']}%"})
                continue

            if rules["fcf_positive_required"] and _calc_fcf(fin) < 0:
                filtered.append({**c, "filter": "fcf_negative_mature"})
                continue

        passed.append(c)

    return passed, filtered
```

---

## 五、数据依赖清单

### 已有数据 (可直接用)

| 数据 | 表/来源 | 用途 |
|------|---------|------|
| PE/PB/ROE/市值/行业 | StockInfo | prescreen + 基数 |
| 8Q 营收/利润/资产/负债/现金流 | FinancialStatement | ROIIC + 研发资本化 + FCF |
| 日均成交额 | MarketData (volume×close) | 流动性过滤 |
| cycle_position | Step 2/3 checkpoint | 生命周期分轨 |

### 需要新增的计算

| 计算 | 输入 | 实现位置 |
|------|------|---------|
| ROIIC | FinancialStatement 8Q | `framework/finance/roiic.py` |
| 研发资本化调整 | FinancialStatement 8Q rd_expense | `framework/finance/rd_adjustment.py` |
| 营收同比增速 | FinancialStatement revenue yoy | prescreen 内联 |
| 自由现金流 | FinancialStatement op_cashflow - capex | prescreen 内联 |
| 毛利率稳定性 | FinancialStatement (revenue-cost)/revenue 方差 | prescreen 内联 |

### 待建设的数据 (V7.0)

| 数据 | 用途 | 优先级 |
|------|------|--------|
| 行业平均毛利率 | 毛利率优势 = 公司 - 行业均值 | P2 |
| 行业平均 ROIC | 超额回报 = ROIC - WACC | P2 |
| 专利数据 | 认证权 evidence | V7.0 |
| 客户/供应商合同 | 卡位权/认证权 evidence | V7.0 |
| 招聘数据 | 资源权/认知权 evidence | V7.0 |

---

## 六、与 FinancialAuditor 的分工

```
FinancialAuditor (被 Step 6 调用):
  - 7 项深度检查 (剪刀差/四连击/库存/合同负债/OCF/Beneish)
  - 输出: PASS / CAUTION / FAIL + 详细指标 + 分数
  - ★ 角色: 财务标注器 (Annotator), 不是过滤器
  - 审计结论永远不排除公司, 仅标注在 risk_tags 中
  - 例如: audit_verdict=FAIL → risk_tags 加 "audit_fail", 但公司仍在候选池

Step 6 Prescreen (本地函数):
  - 轻量快速筛查: 营收增速 / ROIIC / FCF / 毛利率趋势
  - 作用: 做基本门禁 (流动性/退市/停牌), 不做质量判断

分工原则:
  Prescreen = 硬门禁 (流动性不足/已退市 → 排除)
  FinancialAuditor = 软标注 (财务质量诊断 → 标记, 不排除)
  六维权力画像 = 质量判断 (产业权力/利润捕获 → 分类)
  
为什么审计不排除:
  1. 成长期公司 CAPEX 高峰期必然审计差, 但恰是爆发前夜
  2. 周期反转公司底部财务最难看, 但恰是拐点
  3. "差"本身就是信号 — 标注出来让 Step 11 综合判断
  4. 排除后不可回溯, 标记后下游全链路可见
```

---

## 七、当前数据底座现状

### 已有且可靠的数据

| 数据 | 表 | 覆盖范围 | 可靠性 |
|------|-----|---------|--------|
| PE/PB/市值/换手率 | StockInfo | 持仓+自选股 (通过腾讯行情) | ✅ 实时更新 |
| 日线 OHLCV | MarketData | 所有同步过的股票 | ✅ 历史完整 |
| 8Q 利润表 (营收/利润/成本/费用) | FinancialStatement | A股 (通过 akshare) | ✅ 按季度 |
| 8Q 现金流 (经营CF) | FinancialStatement | A股 | ✅ |
| 8Q 资产负债表 (存货/应收/资产/负债) | FinancialStatement | A股 | ✅ |
| 指标 (换手率/拥挤度/动量/筹码) | indicators.db | 持仓+自选股 (计算后) | ✅ |
| 行业分类 | StockInfo.industry | 触发过 sync_stock_info 的 | ⚠️ 部分覆盖 |

### 数据缺口及补齐方案

| 缺口 | 严重度 | 补齐方案 | 优先级 |
|------|--------|---------|--------|
| **`dividend_yield` 全局为空** | 🔴 高 | akshare `stock_financial_analysis_indicator` 返回股息率, 在 `sync_financial_factors` 中补加一行写入。代码改动 <10 行。 | P0 |
| **`roe`/`eps_growth_3y` 仅覆盖持仓+自选股** | 🟡 中 | 在 Step 6 候选池确定后, 对覆盖外的股票补调 `sync_financial_factors`。或: 从 FinancialStatement 直接算 ROE (parent_profit/total_equity), 不需要额外 API。 | P0 |
| **`total_equity` 在 DB 路径缺失** | 🟡 中 | `load_financial_statements` 的 DB 映射少映射了 `total_equity`。补一行映射即可。 | P0 |
| **`rd_expense` 某些公司可能为 0** | 🟡 中 | akshare 利润表有此字段, 但部分公司会计科目名不一致。无法补齐时 → 标记"研发数据不可用", 研发资本化调整跳过。 | P1 |
| **行业平均毛利率/ROIC** | 🟠 低 | 当前无行业聚合数据。Step 6 V1 不做行业对比, 仅做公司自身时间序列判断。V2 再建。 | P2 |
| **WACC 计算所需数据** | 🟠 低 | 无风险利率 + beta + 股权风险溢价。V1 使用固定阈值 (ROIC>8%) 替代 WACC 对比。 | P2 |
| **`announce_date` 未被填充** | 🟢 低 | 下游未使用, 暂不补齐。 | P3 |

### P0 补齐详细方案

**1. dividend_yield**

```python
# 在 sync_financial_factors() 中补加:
df = ak.stock_financial_analysis_indicator(symbol=symbol)
if "股利支付率" in df.columns or "股息率" in df.columns:
    div_col = next((c for c in df.columns if "股息" in c or "股利" in c), None)
    if div_col:
        stock_info.dividend_yield = float(df[div_col].iloc[-1])
```

**2. ROE from FinancialStatement (不依赖 sync_financial_factors)**

```python
# 直接从现有数据计算, 不需要额外 API
def compute_roe_from_db(financials):
    """ROE = 最近4Q归母净利润合计 / 最新总权益"""
    profit_4q = sum(q.get("profit", q.get("parent_profit", 0)) for q in financials[:4])
    equity = financials[0].get("total_equity", 0)
    return (profit_4q / equity * 100) if equity else None
```

**3. total_equity 映射修复**

```python
# 在 load_financial_statements 的 DB 返回 dict 中补加:
"total_equity": float(r.total_equity or 0),  # 此行当前缺失
```

### 搜索替代方案 (无法从本地DB获取时)

| 场景 | 搜索方案 |
|------|---------|
| 候选股票不在 StockInfo (未同步过) | `search_web("{股票代码} PE PB ROE 市值")` → LLM 从片段提取 |
| 财务数据少于 4Q | `search_web("{股票代码} 2025年报 营收 利润 毛利率")` → LLM 提取 |
| 行业分类缺失 | `search_web("{股票代码} 主营业务 所属行业")` |
| 研发费率异常 (为0但公司应属科技) | `search_web("{股票代码} 研发费用 2025年报")` |

---

## 验证

```python
# temp_lab/test_step6_quant.py
import asyncio, sys
sys.path.insert(0, 'backend')

from app.framework.finance.roiic import compute_roiic
from app.domain.research.services.data_loader import data_loader

async def test():
    # 1. 加载真实财务数据
    fin = await data_loader.load_financial_statements("688012", periods=8)
    
    # 2. 算 ROIIC
    roiic = compute_roiic(fin.get("quarters", []))
    print(f"ROIIC: {roiic}")
    assert "roiic" in roiic
    
    # 3. 研发资本化调整
    from app.framework.finance.rd_adjustment import adjust_rd_capitalization
    adj = adjust_rd_capitalization(fin.get("quarters", []))
    print(f"研发调整: 报告利润={adj['reported_profit']}, 调整后={adj['adjusted_profit']}")
    
    # 4. 验证分轨逻辑
    from app.domain.research.services.screening_gate import get_gate_mode
    mode = get_gate_mode({"cycle_position": "bottleneck_formation"})
    assert mode == "growth"

asyncio.run(test())
```
