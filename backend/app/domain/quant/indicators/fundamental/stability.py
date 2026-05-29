"""
稳定性指标 — 适用于 Mature/Cash Cow 阶段
验证护城河是否还在, 利润是否稳定
"""
from .base import FinancialIndicator, register_financial
from app.framework.finance.roiic import compute_roic as _compute_roic


@register_financial
class ROICStability(FinancialIndicator):
    name = "roic_stability"
    label = "ROIC稳定性"
    category = "fundamental"
    indicator_type = "moat"
    applicable_stages = ["mature"]
    params = {}
    output = ["roic_stability"]
    requires = ["revenue", "operate_cost", "sale_expense", "manage_expense",
                "total_assets", "current_assets"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        """最近4Q的ROIC变异系数 (std/mean), 越小越稳定"""
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


@register_financial
class InventoryRevenueTrend(FinancialIndicator):
    name = "inventory_revenue_ratio"
    label = "存货/营收比趋势"
    category = "fundamental"
    indicator_type = "both"
    applicable_stages = ["growth", "mature"]
    params = {}
    output = ["inventory_revenue_ratio"]
    requires = ["inventory", "revenue"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        """存货/营收比 — 连续上升=过度扩张风险, 连续下降=景气"""
        if len(financials) < 4:
            return {"inventory_revenue_ratio": None}
        ratios = []
        for i in range(min(4, len(financials))):
            inv = float(financials[i].get("inventory", 0) or 0)
            rev = float(financials[i].get("revenue", 0) or 0)
            ratios.append(inv / rev if rev else 0)
        if len(ratios) >= 3 and ratios[0] > ratios[1] > ratios[2]:
            return {"inventory_revenue_ratio": "rising_alert"}
        if len(ratios) >= 3 and ratios[0] < ratios[1] < ratios[2]:
            return {"inventory_revenue_ratio": "declining_bullish"}
        return {"inventory_revenue_ratio": "stable"}


@register_financial
class OperatingMarginStability(FinancialIndicator):
    name = "operating_margin_stability"
    label = "营业利润率稳定性"
    category = "fundamental"
    indicator_type = "moat"
    applicable_stages = ["mature"]
    params = {}
    output = ["operating_margin_stability"]
    requires = ["revenue", "operate_cost", "sale_expense", "manage_expense"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        """近8Q营业利润率的标准差 (百分点)。<1pp=护城河牢固; >3pp=盈利不稳"""
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
