"""
基础估值工具包 — 纯函数, 零 I/O, 可复现
LLM 定性地选模型, 代码定量地算价格
"""
from typing import Optional


# ═══ 核心估值公式 ═══════════════════════════

def pe_valuation(eps: float, pe_multiple: float) -> float:
    """市盈率估值: 目标价 = EPS × PE 倍数
    Args:
        eps: 每股收益 (过去12个月或预期)
        pe_multiple: 目标PE倍数 (可比公司中位数或行业均值)
    Returns: 目标股价
    """
    return round(eps * pe_multiple, 2)


def pb_valuation(book_per_share: float, pb_multiple: float) -> float:
    """市净率估值: 目标价 = 每股净资产 × PB 倍数
    适用: 金融(银行/保险/券商)、强周期底部
    """
    return round(book_per_share * pb_multiple, 2)


def ps_valuation(revenue_per_share: float, ps_multiple: float) -> float:
    """市销率估值: 目标价 = 每股营收 × PS 倍数
    适用: 高成长无利润(SaaS/创新药)、早期主题阶段
    """
    return round(revenue_per_share * ps_multiple, 2)


def ev_ebitda_valuation(ebitda: float, net_debt: float, shares: float, multiple: float) -> float:
    """EV/EBITDA 估值
    目标价 = (EBITDA × 倍数 - 净债务) / 总股本
    Args:
        ebitda: 息税折旧摊销前利润 (亿元)
        net_debt: 净债务 = 总债务 - 现金 (亿元)
        shares: 总股本 (亿股)
        multiple: 目标 EV/EBITDA 倍数
    """
    ev = ebitda * multiple
    equity_value = ev - net_debt
    return round(equity_value / shares, 2) if shares > 0 else 0.0


def peg_valuation(eps: float, growth_rate_pct: float, peg_target: float = 1.0) -> float:
    """PEG 估值: 目标价 = EPS × 增速% × PEG
    PEG<1=低估, PEG=1=合理, PEG>2=泡沫
    Args:
        eps: 每股收益
        growth_rate_pct: 盈利增速% (如 25 表示 25%)
        peg_target: 目标 PEG 倍数
    """
    pe_implied = growth_rate_pct * peg_target
    return round(eps * pe_implied, 2)


def fcf_yield_valuation(fcf_per_share: float, target_yield_pct: float = 5.0) -> float:
    """自由现金流收益率估值: 目标价 = FCF每股 / 目标收益率%
    适用: 现金牛(水电/高速/港口), FCF远大于账面利润
    """
    return round(fcf_per_share / (target_yield_pct / 100), 2) if target_yield_pct > 0 else 0.0


# ═══ 情景分析 ═══════════════════════════

def scenario_weighted(bull: float, base: float, bear: float,
                      p_bull: float = 0.2, p_base: float = 0.6, p_bear: float = 0.2) -> dict:
    """三情景概率加权估值
    Returns: {weighted_price, range_low, range_high, asymmetry}
      asymmetry >1 = 上涨空间大于下跌空间 (强非对称)
    """
    weighted = bull * p_bull + base * p_base + bear * p_bear
    upside = (bull - weighted) / weighted * 100 if weighted else 0
    downside = (bear - weighted) / weighted * 100 if weighted else 0
    asymmetry = abs(upside / downside) if downside and downside < 0 else (99 if upside > 0 else 1)
    return {
        "weighted_price": round(weighted, 2),
        "range": [round(bear, 2), round(bull, 2)],
        "upside_pct": round(upside, 1),
        "downside_pct": round(downside, 1),
        "asymmetry": "强非对称" if asymmetry > 2 else ("对称" if asymmetry > 0.5 else "负非对称"),
    }


# ═══ 倍数调整 ═══════════════════════════

def apply_pricing_power_premium(base_multiple: float, supply_rigidity: str) -> float:
    """供给刚性 → 估值倍数溢价
    extreme → +30%, high → +20%, moderate → +10%, low/oversupply → 0
    """
    premiums = {"extreme": 0.30, "high": 0.20, "moderate": 0.10, "low": 0.0, "oversupply": -0.10}
    premium = premiums.get(supply_rigidity, 0.0)
    return round(base_multiple * (1 + premium), 2)


def apply_quality_adjustment(base_multiple: float, roe: Optional[float] = None,
                              dividend_yield: Optional[float] = None,
                              eps_growth: Optional[float] = None) -> tuple:
    """质量调整: ROE>15% +5%, 股息>2% +3%, EPS增速>20% +5%.
    Returns: (adjusted_multiple, bonus_detail_dict)
    """
    bonus = 0.0
    details = []
    if roe and roe > 15:
        bonus += 0.05
        details.append(f"ROE={roe}%>15% (+5%)")
    if dividend_yield and dividend_yield > 2:
        bonus += 0.03
        details.append(f"股息={dividend_yield}%>2% (+3%)")
    if eps_growth and eps_growth > 20:
        bonus += 0.05
        details.append(f"EPS增速={eps_growth}%>20% (+5%)")
    return round(base_multiple * (1 + bonus), 2), details


def apply_financial_risk_discount(base_multiple: float, audit_verdict: str) -> float:
    """财务风险折价: FAIL→-30%, CAUTION→-15%, PASS→0"""
    discounts = {"FAIL": 0.30, "CAUTION": 0.15, "PASS": 0.0}
    disc = discounts.get(audit_verdict, 0.0)
    return round(base_multiple * (1 - disc), 2)
