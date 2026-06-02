"""经营杠杆 — 利润增速/营收增速"""
from ..base import FinancialIndicator, register


@register
class OperatingLeverage(FinancialIndicator):
    name = "operating_leverage"
    label = "经营杠杆"
    description = "经营杠杆 = 利润增速/营收增速。衡量利润对营收变化的敏感度。"
    judgment = ">2.0=高经营杠杆(固定成本高); 1.5~2.0=中等; 1.0~1.5=低; <1.0或负=利润增速落后营收。"
    category = "growth"
    indicator_type = "prosperity"
    applicable_stages = ["growth"]
    params = {}
    output = ["operating_leverage"]
    requires = ["revenue", "parent_profit"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if len(financials) < 8:
            return {"operating_leverage": None}
        rev_t = sum(float(q.get("revenue", 0) or 0) for q in financials[:4])
        rev_t1 = sum(float(q.get("revenue", 0) or 0) for q in financials[4:8])
        profit_t = sum(float(q.get("profit", q.get("parent_profit", 0)) or 0) for q in financials[:4])
        profit_t1 = sum(float(q.get("profit", q.get("parent_profit", 0)) or 0) for q in financials[4:8])
        if not rev_t1 or not profit_t1 or abs(profit_t1) < 1e7 or abs(rev_t1) < 1e7:
            return {"operating_leverage": None}
        rev_growth = (rev_t - rev_t1) / abs(rev_t1)
        profit_growth = (profit_t - profit_t1) / abs(profit_t1)
        if abs(rev_growth) < 0.001:
            return {"operating_leverage": None}
        return {"operating_leverage": round(profit_growth / rev_growth, 2)}
