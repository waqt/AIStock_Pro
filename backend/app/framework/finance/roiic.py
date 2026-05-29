"""
ROIIC (Return On Incremental Invested Capital) — 增量投资资本回报率
衡量新增投入资本的边际回报效率。成长期公司静态ROIC可能很低(CAPEX高峰期),
ROIIC才是判断"它在烧钱还是投资"的关键指标。

公式: ROIIC = (NOPAT_t - NOPAT_t-4) / (IC_t-1 - IC_t-5)
"""
from typing import List, Dict, Optional


def compute_roiic(financials: List[Dict]) -> dict:
    """
    输入: 最近 8Q 财务数据 (从 FinancialStatement 表按 report_date DESC 排列)
    返回: {roiic, roiic_pct, nopat_current, nopat_prev, ic_current, ic_prev, interpretation}

    若数据不足8Q或IC无变化, 返回 roiic=None
    """
    if len(financials) < 8:
        return {"roiic": None, "error": "insufficient_data", "available_quarters": len(financials)}

    recent_4q = financials[:4]
    prior_4q = financials[4:8]

    # NOPAT = sum(operating_profit) * (1 - tax_rate)
    TAX_RATE = 0.15  # 高新技术企业通用
    nopat_current = _sum_field(recent_4q, "parent_profit", "profit") * (1 - TAX_RATE)
    nopat_prev = _sum_field(prior_4q, "parent_profit", "profit") * (1 - TAX_RATE)

    ic_current = _invested_capital(recent_4q[0])
    ic_prev = _invested_capital(prior_4q[0])

    if ic_current == ic_prev:
        return {"roiic": None, "error": "no_change_in_ic", "ic_current": ic_current}

    delta_nopat = nopat_current - nopat_prev
    delta_ic = ic_current - ic_prev
    roiic = delta_nopat / delta_ic

    return {
        "roiic": round(roiic, 4),
        "roiic_pct": round(roiic * 100, 1),
        "nopat_current_yi": round(nopat_current / 1e8, 2),  # 亿
        "nopat_prev_yi": round(nopat_prev / 1e8, 2),
        "ic_current_yi": round(ic_current / 1e8, 2),
        "ic_prev_yi": round(ic_prev / 1e8, 2),
        "delta_nopat_yi": round(delta_nopat / 1e8, 2),
        "delta_ic_yi": round(delta_ic / 1e8, 2),
        "interpretation": _interpret(roiic),
        "quality": _quality(roiic),
    }


def compute_roe_from_financials(financials: List[Dict]) -> Optional[float]:
    """直接从 FinancialStatement 计算 ROE = 最近4Q归母净利润 / 最新总权益"""
    if not financials:
        return None
    profit_4q = _sum_field(financials[:4], "parent_profit", "profit")
    equity = financials[0].get("total_equity", 0) or 0
    if not equity:
        return None
    return round(profit_4q / equity * 100, 1)


# ═══ 内部工具 ═══════════════════════════════

def _sum_field(quarters: List[Dict], *field_names: str) -> float:
    total = 0.0
    for q in quarters:
        for name in field_names:
            v = q.get(name, 0)
            if v:
                total += float(v)
                break
    return total


def _invested_capital(q: Dict) -> float:
    """InvestedCapital ≈ total_assets - 30% * current_assets (近似无息流动负债)"""
    ta = float(q.get("total_assets", 0) or 0)
    ca = float(q.get("current_assets", 0) or 0)
    return ta - ca * 0.3


def _interpret(roiic: float) -> str:
    if roiic > 0.30:  return "高效扩张: 每1元新投入产生>0.3元回报, 成长质量极高"
    if roiic > 0.15:  return "健康扩张: 新增资本回报率良好"
    if roiic > 0.08:  return "可接受: 覆盖资本成本线"
    if roiic > 0:     return "低效: 新增回报不足, 需观察拐点信号"
    return "价值毁灭: 新增投入在亏损, 除非有明确拐点否则应警惕"


def _quality(roiic: float) -> str:
    if roiic > 0.15: return "high"
    if roiic > 0: return "medium"
    return "low"
