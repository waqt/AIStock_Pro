"""稳定性 — ROIC稳定性 / 营业利润率稳定性"""
from ..base import FinancialIndicator, register
from app.framework.finance.roiic import compute_roic as _compute_roic


@register
class ROICStability(FinancialIndicator):
    name = "roic_stability"
    label = "ROIC稳定性"
    description = "ROIC的变异系数(标准差/均值)。越小越稳定,护城河越牢固。"
    judgment = "<0.1=极稳定; 0.1~0.3=正常波动; >0.3=ROIC不稳定。高均值+低变异=最优质资产。"
    category = "quality"
    indicator_type = "moat"
    applicable_stages = ["mature"]
    params = {}
    output = ["roic_stability"]
    requires = ["revenue", "operate_cost", "sale_expense", "manage_expense", "total_assets", "current_assets"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if len(financials) < 8:
            return {"roic_stability": None}
        roics = []
        for i in range(min(4, len(financials) - 3)):
            win = financials[i:i+4]
            r = _compute_roic(win)
            v = r.get("roic_pct")
            if v is not None:
                roics.append(v)
        if len(roics) < 2:
            return {"roic_stability": None}
        import statistics
        mean = statistics.mean(roics)
        stdev = statistics.stdev(roics) if len(roics) > 1 else 0
        return {"roic_stability": round(stdev / mean, 3) if mean else None}


@register
class OperatingMarginStability(FinancialIndicator):
    name = "operating_margin_stability"
    label = "营业利润率稳定性"
    description = "近8Q营业利润率的标准差(百分点)。衡量盈利能力稳定性。"
    judgment = "<1pp=护城河牢固; 1~3pp=正常波动; >3pp=盈利不稳。"
    category = "quality"
    indicator_type = "moat"
    applicable_stages = ["mature"]
    params = {}
    output = ["operating_margin_stability"]
    requires = ["revenue", "operate_cost", "sale_expense", "manage_expense"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if len(financials) < 8:
            return {"operating_margin_stability": None}
        margins = []
        for i in range(min(8, len(financials))):
            rev = float(financials[i].get("revenue", 0) or 0)
            cost = float(financials[i].get("operate_cost", 0) or 0)
            sga = float(financials[i].get("sale_expense", 0) or 0) + float(financials[i].get("manage_expense", 0) or 0)
            if rev:
                margins.append((rev - cost - sga) / rev * 100)
        if len(margins) < 4:
            return {"operating_margin_stability": None}
        import statistics
        return {"operating_margin_stability": round(statistics.stdev(margins), 1)}
