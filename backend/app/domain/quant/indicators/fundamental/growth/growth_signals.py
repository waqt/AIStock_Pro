"""增长信号 — 单季营收同比 / R&D增长"""
from ..base import FinancialIndicator, register, _pct, _safe_div


@register
class RevenueYoY(FinancialIndicator):
    name = "revenue_yoy"
    label = "营收同比(%)"
    description = "单季度营收同比增速。相比TTM更敏感的增速指标,能更快捕捉拐点。"
    judgment = "加速增长=景气上行; 减速但正增长=景气高位; 转负=拐点信号。"
    category = "growth"
    indicator_type = "prosperity"
    applicable_stages = ["inflection", "growth"]
    params = {}
    output = ["revenue_yoy"]
    requires = ["revenue"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if len(financials) < 5:
            return {"revenue_yoy": None}
        rev = float(financials[0].get("revenue", 0) or 0)
        rev_4q = float(financials[4].get("revenue", 0) or 0)
        return {"revenue_yoy": _pct(rev, rev_4q)}


@register
class RDGrowth(FinancialIndicator):
    name = "rd_growth"
    label = "研发费用同比(%)"
    description = "研发费用同比增速。高研发增长预示公司在积极构建技术护城河。"
    judgment = ">30%=激进投入; 15~30%=稳健投入; 0~15%=正常维持; <0%=削减研发(需关注原因)。"
    category = "growth"
    indicator_type = "moat"
    applicable_stages = ["startup", "inflection", "growth"]
    params = {}
    output = ["rd_growth"]
    requires = ["rd_expense"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if len(financials) < 5:
            return {"rd_growth": None}
        rd = float(financials[0].get("rd_expense", 0) or 0)
        rd_4q = float(financials[4].get("rd_expense", 0) or 0)
        return {"rd_growth": _pct(rd, rd_4q)}
