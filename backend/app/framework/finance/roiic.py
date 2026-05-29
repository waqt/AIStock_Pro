"""
ROIIC (Return On Incremental Invested Capital) — 增量投资资本回报率
ROIC  (Return On Invested Capital)           — 静态投资资本回报率

ROIIC 衡量新增投入资本的边际回报效率。成长期公司静态ROIC可能很低(CAPEX高峰期),
ROIIC才是判断"它在烧钱还是投资"的关键指标。
ROIC 用于成熟期公司, 衡量现有资本存量的回报效率。

公式:
  NOPAT = sum(operating_profit, 4Q) * (1 - tax_rate)
  operating_profit = revenue - operate_cost - sale_expense - manage_expense
  IC = total_assets - current_assets * 0.3  (近似: 扣除估计的无息流动负债)

  ROIC  = NOPAT / IC
  ROIIC = (NOPAT_t - NOPAT_t-4) / (IC_t-1 - IC_t-5)
"""
from typing import List, Dict, Optional

TAX_RATE = 0.15  # 高新技术企业通用


def _nopat_4q(quarters: List[Dict]) -> float:
    """NOPAT = sum(operating_profit) * (1 - tax_rate), 最近4Q"""
    op_total = 0.0
    for q in quarters[:4]:
        rev = float(q.get("revenue", 0) or 0)
        cost = float(q.get("operate_cost", 0) or 0)
        sga = float(q.get("sale_expense", 0) or 0) + float(q.get("manage_expense", 0) or 0)
        op = rev - cost - sga
        op_total += op
    return op_total * (1 - TAX_RATE)


def _invested_capital(q: Dict) -> float:
    """InvestedCapital = total_assets - cash - NIBCL
    NIBCL (无息流动负债) ≈ current_liabilities - short_loan - noncurrent_liab_1year
    如果有新字段则精确计算, 否则回退到 30% 近似"""
    ta = float(q.get("total_assets", 0) or 0)
    cash = float(q.get("cash", 0) or 0)
    cl = float(q.get("current_liabilities", 0) or 0)
    sl = float(q.get("short_loan", 0) or 0)
    ncl1y = float(q.get("noncurrent_liab_1year", 0) or 0)

    if cl > 0:
        # 精确公式: IC = TA - cash - (CL - short_loan - 1year_LTD)
        nibcl = max(cl - sl - ncl1y, 0)  # 无息流动负债
        return ta - cash - nibcl
    # 回退: 近似公式 (旧数据无新字段)
    ca = float(q.get("current_assets", 0) or 0)
    return ta - ca * 0.3


# ═══ 公开 API ═══════════════════════════════

def compute_roic(financials: List[Dict]) -> dict:
    """
    ROIC = NOPAT / InvestedCapital (静态, 基于最近4Q)
    用于成熟期公司的现有资本回报效率判断。

    返回: {roic, roic_pct, nopat_yi, ic_yi, interpretation}
    """
    if not financials or len(financials) < 4:
        return {"roic": None, "error": "insufficient_data", "available_quarters": len(financials)}

    nopat = _nopat_4q(financials)
    ic = _invested_capital(financials[0])

    if not ic:
        return {"roic": None, "error": "ic_zero"}

    roic = nopat / ic

    return {
        "roic": round(roic, 4),
        "roic_pct": round(roic * 100, 1),
        "nopat_yi": round(nopat / 1e8, 2),
        "ic_yi": round(ic / 1e8, 2),
        "interpretation": _interpret_roic(roic),
        "quality": "high" if roic > 0.15 else "medium" if roic > 0.08 else "low",
    }


def compute_roiic(financials: List[Dict]) -> dict:
    """
    ROIIC = (NOPAT_t - NOPAT_t-4) / (IC_t-1 - IC_t-5)
    衡量新增投入资本的边际回报。成长期公司的核心判断指标。

    输入: 最近 8Q 财务数据 (report_date DESC)
    返回: {roiic, roiic_pct, nopat_current, nopat_prev, ic_current, ic_prev, ...}
    """
    if len(financials) < 8:
        return {"roiic": None, "error": "insufficient_data", "available_quarters": len(financials)}

    recent_4q = financials[:4]
    prior_4q = financials[4:8]

    nopat_current = _nopat_4q(recent_4q)
    nopat_prev = _nopat_4q(prior_4q)

    ic_current = _invested_capital(recent_4q[0])
    ic_prev = _invested_capital(prior_4q[0])

    if ic_current == ic_prev:
        return {"roiic": None, "error": "no_change_in_ic", "ic_current_yi": round(ic_current / 1e8, 2)}

    delta_nopat = nopat_current - nopat_prev
    delta_ic = ic_current - ic_prev
    roiic = delta_nopat / delta_ic

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


def compute_roe_from_financials(financials: List[Dict]) -> Optional[float]:
    """ROE = 最近4Q归母净利润 / 最新总权益"""
    if not financials:
        return None
    profit_4q = sum(float(q.get("profit", q.get("parent_profit", 0)) or 0) for q in financials[:4])
    equity = float(financials[0].get("total_equity", 0) or 0)
    if not equity:
        return None
    return round(profit_4q / equity * 100, 1)


# ═══ 内部 ═══════════════════════════════

def _interpret_roic(roic: float) -> str:
    if roic > 0.20:  return "优秀: 现有资本回报率>20%, 护城河深厚"
    if roic > 0.12:  return "良好: 显著高于资本成本"
    if roic > 0.08:  return "可接受: 覆盖资本成本"
    if roic > 0:     return "偏低: 资本效率不足, 需关注改善趋势"
    return "亏损: 资本在毁灭价值"


def _interpret_roiic(roiic: float) -> str:
    if roiic > 0.30:  return "高效扩张: 每1元新投入产生>0.3元回报, 成长质量极高"
    if roiic > 0.15:  return "健康扩张: 新增资本回报率良好"
    if roiic > 0.08:  return "可接受: 覆盖资本成本线"
    if roiic > 0:     return "低效: 新增回报不足, 需观察拐点信号"
    return "价值毁灭: 新增投入在亏损, 除非有明确拐点否则应警惕"


def _quality_roiic(roiic: float) -> str:
    if roiic > 0.15: return "high"
    if roiic > 0: return "medium"
    return "low"
