"""存货/营收比趋势"""
from ..base import FinancialIndicator, register


@register
class InventoryRevenueTrend(FinancialIndicator):
    name = "inventory_revenue_trend"
    label = "存货/营收比趋势"
    description = "存货余额/营收的连续变化趋势分类。"
    judgment = "rising_alert=存货占比连续上升; declining_bullish=持续下降; stable=经营健康。"
    category = "health"
    indicator_type = "both"
    applicable_stages = ["growth", "mature"]
    params = {}
    output = ["inventory_revenue_trend"]
    requires = ["inventory", "revenue"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if len(financials) < 4:
            return {"inventory_revenue_trend": None}
        ratios = []
        for i in range(min(4, len(financials))):
            inv = float(financials[i].get("inventory", 0) or 0)
            rev = float(financials[i].get("revenue", 0) or 0)
            ratios.append(inv / rev if rev else 0)
        if len(ratios) >= 3 and ratios[0] > ratios[1] > ratios[2]:
            return {"inventory_revenue_trend": "rising_alert"}
        if len(ratios) >= 3 and ratios[0] < ratios[1] < ratios[2]:
            return {"inventory_revenue_trend": "declining_bullish"}
        return {"inventory_revenue_trend": "stable"}
