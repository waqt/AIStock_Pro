"""营运资本效率 — (AR+存货-AP)/TTM营收"""
from ..base import FinancialIndicator, register


@register
class WorkingCapitalEfficiency(FinancialIndicator):
    name = "working_capital_efficiency"
    label = "营运资本效率(%)"
    description = "(应收账款+存货-应付账款)/TTM营收。衡量公司对上下游的议价能力和渠道控制力。"
    judgment = "<5%=低(营运资本需求小,占用上下游资金); 5~10%=较低; 10~20%=中等; >30%=高(扩张时资金占用大)。负值=净占用上下游资金,但需确认非拖欠供应商。"
    category = "profitability"
    indicator_type = "moat"
    concepts = ["capital_return_efficiency"]
    applicable_stages = ["growth", "mature"]
    params = {}
    output = ["working_capital_efficiency"]
    requires = ["accounts_receivable", "inventory", "accounts_payable", "revenue"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if not financials:
            return {"working_capital_efficiency": None}
        ar = float(financials[0].get("accounts_receivable", 0) or 0)
        inv = float(financials[0].get("inventory", 0) or 0)
        ap = float(financials[0].get("accounts_payable", 0) or 0)
        nwc = ar + inv - ap
        revenue_ttm = sum(float(q.get("revenue", 0) or 0) for q in financials[:4])
        if not revenue_ttm:
            return {"working_capital_efficiency": None}
        return {"working_capital_efficiency": round(nwc / revenue_ttm * 100, 1)}
