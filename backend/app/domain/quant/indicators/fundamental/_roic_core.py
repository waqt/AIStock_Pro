"""
ROIC/ROIIC 核心计算 — 指标体系内聚版本

将原本分散在 framework/finance/roiic.py 和 rd_adjustment.py 的逻辑内聚到指标体系内。
纯函数, 零 I/O, 作为 profitability/roic.py、profitability/roiic.py 等的共享后端。

所有函数输入: quarters list (newest-first, quarters[0] = 最新报告期)
"""
from typing import List, Dict, Optional


# ═══ 常量 ═══════════════════════════════════════════════

DEFAULT_TAX_RATE = 0.15  # 高新技术企业通用税率
STANDARD_TAX_RATE = 0.25  # 标准企业所得税税率


# ═══ NOPAT 计算 ════════════════════════════════════════

def compute_nopat(quarters: List[Dict], capitalize_rd: bool = False,
                  tax_rate: float = DEFAULT_TAX_RATE) -> float:
    """
    NOPAT = 营业利润 × (1 - 税率)

    营业利润计算:
      capitalize_rd=False (GAAP 标准): rev - cost - sga - rd_expense
        → 研发费用作为营业费用全额扣除, 与真实财报一致
      capitalize_rd=True (研发资本化): rev - cost - sga
        → 研发费用被视为投资而非费用, 不扣减 (但需加回研发资产到 IC)

    参数:
      quarters: newest-first 列表, 至少 4 期
      capitalize_rd: 是否将研发支出资本化
      tax_rate: 有效税率 (高新技术企业 0.15, 一般企业 0.25)
    """
    op_total = 0.0
    for q in quarters[:4]:
        rev = float(q.get("revenue", 0) or 0)
        cost = float(q.get("operate_cost", 0) or 0)
        sga = (float(q.get("sale_expense", 0) or 0) +
               float(q.get("manage_expense", 0) or 0))

        if capitalize_rd:
            # 研发资本化: 不扣减研发费用 (视为投资)
            op = rev - cost - sga
        else:
            # GAAP 标准: 研发费用作为营业费用扣除
            rd = float(q.get("rd_expense", 0) or 0)
            op = rev - cost - sga - rd

        op_total += op

    return op_total * (1 - tax_rate)


def compute_invested_capital(q: Dict) -> float:
    """
    Invested Capital (IC) = 总资产 - 货币资金 - 无息流动负债

    无息流动负债 (NIBCL) = 流动负债 - 短期借款 - 一年内到期非流动负债
    如果流动负债数据不可用, 回退到: TA - 流动资产 × 0.2

    回退系数 0.2 是对「无息流动负债 ≈ 流动资产 × 20%」的经验估计。
    精确值依赖行业特性 (零售偏高, 软件偏低), 但流动负债字段几乎总是可用的,
    此回退极少数情况会被触发。
    """
    ta = float(q.get("total_assets", 0) or 0)
    cash = float(q.get("cash", 0) or 0)
    cl = float(q.get("current_liabilities", 0) or 0)

    if cl > 0:
        sl = float(q.get("short_loan", 0) or 0)
        ncl1y = float(q.get("noncurrent_liab_1year", 0) or 0)
        nibcl = max(cl - sl - ncl1y, 0)
        return ta - cash - nibcl

    # 无流动负债字段的回退 (极罕见)
    ca = float(q.get("current_assets", 0) or 0)
    return ta - ca * 0.2


# ═══ 研发资本化调整 ═══════════════════════════════════

def adjust_rd_capitalization(financials: List[Dict], amort_years: int = 5) -> dict:
    """
    研发资本化调整 — 还原科技公司被会计准则压低的真实盈利能力。

    GAAP 将研发支出全额计入当期费用, 导致高研发投入的科技公司
    账面利润被大幅压低。此函数将研发支出视为无形资产, 按摊销年限资本化处理。

    公式:
      RD_Asset = Σ(RD_i × 未摊销比例_i)
      Adjusted_Profit = Reported_Profit + Current_RD - 摊销额
      Adjusted_Assets = Reported_Assets + RD_Asset

    参数:
      financials: 最近 8Q 财务数据 (含 rd_expense), newest-first
      amort_years: 研发资产摊销年限 (默认 5 年)

    返回:
      {reported_profit_yi, adjusted_profit_yi, profit_impact_pct,
       rd_asset_yi, rd_amortization_yi, adjusted_roe, material, ...}
    """
    rd_expenses = [float(q.get("rd_expense", 0) or 0) for q in financials]
    total_rd = sum(rd_expenses)

    if total_rd == 0:
        return _no_rd_result(financials)

    # 计算研发资产净值 (按摊销年限折余)
    rd_asset = 0.0
    quarters_per_year = 4.0
    annual_amort_rate = 1.0 / amort_years

    for i, rd in enumerate(rd_expenses):
        age_quarters = i  # i=0 是最新季度, i 越大越久远
        age_years = age_quarters / quarters_per_year
        if age_years >= amort_years:
            continue
        remaining_pct = 1.0 - (age_years / amort_years)
        rd_asset += rd * remaining_pct

    # 当期摊销
    rd_amortization = rd_asset / max(amort_years * 0.5, 1.0)

    # 报告利润 (最近4Q)
    reported_profit = sum(
        float(q.get("parent_profit", q.get("profit", 0)) or 0) for q in financials[:4])
    current_rd = sum(rd_expenses[:4])

    adjusted_profit = reported_profit + current_rd - rd_amortization

    # 调整后总资产
    reported_assets = float(financials[0].get("total_assets", 0) or 0)
    adjusted_assets = reported_assets + rd_asset

    profit_impact = ((adjusted_profit / reported_profit - 1) * 100) \
        if reported_profit and reported_profit > 0 else 0

    adjusted_roe = (adjusted_profit / adjusted_assets * 100) if adjusted_assets else None

    return {
        "reported_profit_yi": round(reported_profit / 1e8, 2),
        "adjusted_profit_yi": round(adjusted_profit / 1e8, 2),
        "profit_impact_pct": round(profit_impact, 1),
        "rd_asset_yi": round(rd_asset / 1e8, 2),
        "rd_amortization_yi": round(rd_amortization / 1e8, 2),
        "adjusted_roe": round(adjusted_roe, 1) if adjusted_roe else None,
        "rd_intensity_pct": round(current_rd / max(reported_profit, 1) * 100, 1)
        if reported_profit > 0 else None,
        "note": _make_rd_note(profit_impact, current_rd, rd_amortization),
        "material": profit_impact > 10,
    }


def _no_rd_result(financials: List[Dict]) -> dict:
    reported_profit = sum(
        float(q.get("parent_profit", q.get("profit", 0)) or 0) for q in financials[:4])
    return {
        "reported_profit_yi": round(reported_profit / 1e8, 2),
        "adjusted_profit_yi": round(reported_profit / 1e8, 2),
        "profit_impact_pct": 0.0,
        "rd_asset_yi": 0.0,
        "rd_amortization_yi": 0.0,
        "adjusted_roe": None,
        "rd_intensity_pct": 0.0,
        "note": "无研发支出数据或研发支出为0, 无需调整",
        "material": False,
    }


def _make_rd_note(impact: float, rd: float, amort: float) -> str:
    if impact > 20:
        return f"研发资本化后利润上调{impact:.0f}% — 该公司真实盈利能力远优于账面数据"
    if impact > 10:
        return f"研发资本化后利润上调{impact:.0f}%, 财报利润被研发投入显著压低"
    if impact > 5:
        return f"研发资本化后利润上调{impact:.0f}%, 略有影响"
    return "研发资本化调整影响不大"


# ═══ ROIC 计算 ════════════════════════════════════════

def compute_roic(financials: List[Dict], capitalize_rd: bool = False,
                 tax_rate: float = DEFAULT_TAX_RATE) -> dict:
    """
    ROIC = NOPAT / InvestedCapital (静态, 基于最近4Q)
    用于成熟期公司的现有资本回报效率判断。

    参数:
      financials: 财务数据列表 (newest-first), 至少 4 期
      capitalize_rd: 是否将研发支出资本化
      tax_rate: 有效税率

    返回:
      {roic, roic_pct, nopat_yi, ic_yi, interpretation, quality}
    """
    if not financials or len(financials) < 4:
        return {"roic": None, "error": "insufficient_data",
                "available_quarters": len(financials) if financials else 0}

    nopat = compute_nopat(financials, capitalize_rd, tax_rate)
    ic = compute_invested_capital(financials[0])

    if not ic or ic <= 0:
        return {"roic": None, "error": "ic_zero_or_negative"}

    roic = nopat / ic

    return {
        "roic": round(roic, 4),
        "roic_pct": round(roic * 100, 1),
        "nopat_yi": round(nopat / 1e8, 2),
        "ic_yi": round(ic / 1e8, 2),
        "interpretation": _interpret_roic(roic),
        "quality": "high" if roic > 0.15 else "medium" if roic > 0.08 else "low",
    }


def _interpret_roic(roic: float) -> str:
    if roic > 0.20:
        return "优秀: 现有资本回报率>20%, 护城河深厚"
    if roic > 0.12:
        return "良好: 显著高于资本成本"
    if roic > 0.08:
        return "可接受: 覆盖资本成本"
    if roic > 0:
        return "偏低: 资本效率不足, 需关注改善趋势"
    return "亏损: 资本在毁灭价值"


# ═══ ROIIC 计算 ═══════════════════════════════════════

def compute_roiic(financials: List[Dict], capitalize_rd: bool = False,
                  tax_rate: float = DEFAULT_TAX_RATE) -> dict:
    """
    ROIIC = (NOPAT_t - NOPAT_t-4) / (IC_current - IC_4Q_prev)
    衡量新增投入资本的边际回报。成长期公司的核心判断指标。

    参数:
      financials: 最近 8Q 财务数据 (newest-first)
      capitalize_rd: 是否将研发支出资本化
      tax_rate: 有效税率

    返回:
      {roiic, roiic_pct, nopat_current_yi, nopat_prev_yi,
       ic_current_yi, ic_prev_yi, delta_nopat_yi, delta_ic_yi,
       interpretation, quality}
    """
    if len(financials) < 8:
        return {"roiic": None, "error": "insufficient_data",
                "available_quarters": len(financials)}

    recent_4q = financials[:4]
    prior_4q = financials[4:8]

    nopat_current = compute_nopat(recent_4q, capitalize_rd, tax_rate)
    nopat_prev = compute_nopat(prior_4q, capitalize_rd, tax_rate)

    ic_current = compute_invested_capital(recent_4q[0])
    ic_prev = compute_invested_capital(prior_4q[0])

    if ic_current == ic_prev:
        return {"roiic": None, "error": "no_change_in_ic",
                "ic_current_yi": round(ic_current / 1e8, 2)}

    delta_nopat = nopat_current - nopat_prev
    delta_ic = ic_current - ic_prev
    roiic = delta_nopat / delta_ic if delta_ic != 0 else None

    if roiic is None:
        return {"roiic": None, "error": "delta_ic_zero"}

    return {
        "roiic": round(roiic, 4),
        "roiic_pct": round(roiic * 100, 1),
        "nopat_current_yi": round(nopat_current / 1e8, 2),
        "nopat_prev_yi": round(nopat_prev / 1e8, 2),
        "ic_current_yi": round(ic_current / 1e8, 2),
        "ic_prev_yi": round(ic_prev / 1e8, 2),
        "delta_nopat_yi": round(delta_nopat / 1e8, 2),
        "delta_ic_yi": round(delta_ic / 1e8, 2),
        "interpretation": _interpret_roiic(roiic),
        "quality": _quality_roiic(roiic),
    }


def _interpret_roiic(roiic: float) -> str:
    if roiic > 0.30:
        return "高效扩张: 每1元新投入产生>0.3元回报, 成长质量极高"
    if roiic > 0.15:
        return "健康扩张: 新增资本回报率良好"
    if roiic > 0.08:
        return "可接受: 覆盖资本成本线"
    if roiic > 0:
        return "低效: 新增回报不足, 需观察拐点信号"
    return "价值毁灭: 新增投入在亏损, 除非有明确拐点否则应警惕"


def _quality_roiic(roiic: float) -> str:
    if roiic > 0.15:
        return "high"
    if roiic > 0:
        return "medium"
    return "low"


# ═══ ROE 辅助计算 ═════════════════════════════════════

def compute_roe_from_financials(financials: List[Dict]) -> Optional[float]:
    """ROE = 最近4Q归母净利润 / 最新总权益"""
    if not financials:
        return None
    profit_4q = sum(
        float(q.get("profit", q.get("parent_profit", 0)) or 0) for q in financials[:4])
    equity = float(financials[0].get("total_equity", 0) or 0)
    if not equity:
        return None
    return round(profit_4q / equity * 100, 1)
