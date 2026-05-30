"""
营运资本效率指标 — 适用于高速成长期
衡量公司对上下游的议价能力和渠道控制力
"""
from .base import FinancialIndicator, register_financial


@register_financial
class WorkingCapitalEfficiency(FinancialIndicator):
    name = "working_capital_efficiency"
    label = "营运资本效率(%)"
    description = "(应收账款+存货-应付账款)/TTM营收。衡量公司营运资本占用营收的比例,反映对上下游的议价能力和渠道控制力。"
    judgment = "<5%=极强渠道力(占用别人资金经营,如茅台); 5~10%=强势; 10~20%=正常水平; 20~30%=偏弱,资金被上下游占用; >30%=渠道弱势,扩张质量差。负值=完全占用上下游资金(顶级)。"
    category = "fundamental"
    indicator_type = "moat"
    applicable_stages = ["growth", "mature"]
    params = {}
    output = ["working_capital_efficiency"]
    requires = ["accounts_receivable", "inventory", "accounts_payable", "revenue"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        """(应收账款+存货-应付账款) / TTM营收 × 100
        <10%: 强渠道控制力 (占用上下游资金)
        10-20%: 正常
        20-30%: 偏弱, 被占用资金
        >30%: 渠道弱势, 扩张质量差
        """
        if not financials:
            return {"working_capital_efficiency": None}
        ar = float(financials[0].get("accounts_receivable", 0) or 0)
        inv = float(financials[0].get("inventory", 0) or 0)
        ap = float(financials[0].get("accounts_payable", 0) or 0)
        nwc = ar + inv - ap
        revenue_ttm = sum(float(q.get("revenue", 0) or 0) for q in financials[:4])
        if not revenue_ttm:
            return {"working_capital_efficiency": None}
        pct = nwc / revenue_ttm * 100
        return {"working_capital_efficiency": round(pct, 1)}
