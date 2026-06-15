"""存货/营收比趋势"""
from ..base import FinancialIndicator, register
from ..profitability.profit_quality import _is_strictly_monotonic


@register
class InventoryRevenueTrend(FinancialIndicator):
    name = "inventory_revenue_trend"
    label = "存货/营收比趋势"
    description = "存货余额/营收的连续变化趋势分类。"
    judgment = "rising_alert=存货占比连续上升; declining_bullish=持续下降; stable=窄幅波动。inv_rev_ratio_chg=最新季与4季前存货/营收比差值,正值=占比上升。"
    category = "health"
    indicator_type = "both"
    applicable_stages = ["growth", "mature"]
    concepts = ["financial_health"]
    params = {}
    output = ["inventory_revenue_trend", "inv_rev_ratio_chg"]
    text_output = ["inventory_revenue_trend"]
    requires = ["inventory", "revenue"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if len(financials) < 4:
            return {"inventory_revenue_trend": None, "inv_rev_ratio_chg": None}
        ratios = []
        for i in range(min(4, len(financials))):
            inv = float(financials[i].get("inventory", 0) or 0)
            rev = float(financials[i].get("revenue", 0) or 0)
            ratios.append(inv / rev if rev else 0)
        chg = round(ratios[0] - ratios[-1], 4) if len(ratios) >= 4 else None
        if len(ratios) >= 3 and _is_strictly_monotonic(ratios[:3]):
            if ratios[0] > ratios[-1]:
                return {"inventory_revenue_trend": "rising_alert", "inv_rev_ratio_chg": chg}
            return {"inventory_revenue_trend": "declining_bullish", "inv_rev_ratio_chg": chg}
        return {"inventory_revenue_trend": "stable", "inv_rev_ratio_chg": chg}
