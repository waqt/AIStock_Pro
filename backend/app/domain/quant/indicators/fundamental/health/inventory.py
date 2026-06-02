"""存货分析 — 存货占比、存货周转、存货趋势"""
from ..base import FinancialIndicator, register, _pct


@register
class InventoryIndicator(FinancialIndicator):
    name = "inventory"
    label = "存货分析"
    description = "存货余额/TTM营收占比 + 同比增速。存货过高有跌价风险,过低可能丧失销售机会。"
    judgment = "存货/营收<10%=低(存货占营收比重小); 10~20%=中等; 20~40%=较高; >40%=高(存货占比大)。存货增速>营收增速=存货累积速度快于营收确认速度。"
    category = "health"
    indicator_type = "both"
    applicable_stages = ["growth", "mature"]
    params = {}
    output = ["inventory_revenue_ratio", "inventory_yoy"]
    requires = ["inventory", "revenue"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if not financials or len(financials) < 5:
            return {"inventory_revenue_ratio": None, "inventory_yoy": None}
        inv = float(financials[0].get("inventory", 0) or 0)
        rev_ttm = sum(float(q.get("revenue", 0) or 0) for q in financials[:4])
        inv_4q = float(financials[4].get("inventory", 0) or 0)
        return {
            "inventory_revenue_ratio": round(inv / rev_ttm * 100, 1) if rev_ttm else None,
            "inventory_yoy": _pct(inv, inv_4q),
        }
