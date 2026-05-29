"""
成长质量/利润质量指标
适用于 Growth/Inflection 和 Mature 阶段
"""
from .base import FinancialIndicator, register_financial


@register_financial
class RDIntensity(FinancialIndicator):
    name = "rd_intensity"
    label = "研发费用率(%)"
    category = "fundamental"
    indicator_type = "moat"
    applicable_stages = ["startup", "inflection"]
    params = {}
    output = ["rd_intensity"]
    requires = ["rd_expense", "revenue"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if not financials:
            return {"rd_intensity": None}
        rd = sum(float(q.get("rd_expense", 0) or 0) for q in financials[:4])
        rev = sum(float(q.get("revenue", 0) or 0) for q in financials[:4])
        if not rev:
            return {"rd_intensity": None}
        return {"rd_intensity": round(rd / rev * 100, 1)}


@register_financial
class GrossMargin(FinancialIndicator):
    name = "gross_margin"
    label = "毛利率(%)"
    category = "fundamental"
    indicator_type = "moat"
    applicable_stages = ["inflection", "growth", "mature"]
    params = {}
    output = ["gross_margin"]
    requires = ["revenue", "operate_cost"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if not financials:
            return {"gross_margin": None}
        rev = sum(float(q.get("revenue", 0) or 0) for q in financials[:4])
        cost = sum(float(q.get("operate_cost", 0) or 0) for q in financials[:4])
        if not rev:
            return {"gross_margin": None}
        return {"gross_margin": round((rev - cost) / rev * 100, 1)}


@register_financial
class GrossMarginTrend(FinancialIndicator):
    name = "gross_margin_trend"
    label = "毛利率趋势"
    category = "fundamental"
    indicator_type = "moat"
    applicable_stages = ["inflection", "growth", "mature"]
    params = {}
    output = ["gross_margin_trend"]
    requires = ["revenue", "operate_cost"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        """判断毛利率连续趋势: rising/stable/declining"""
        if len(financials) < 4:
            return {"gross_margin_trend": None}
        gms = []
        for q in financials[:4]:
            rev = float(q.get("revenue", 0) or 0)
            cost = float(q.get("operate_cost", 0) or 0)
            gms.append((rev - cost) / rev * 100 if rev else 0)
        if len(gms) >= 3 and gms[0] > gms[1] > gms[2]:
            return {"gross_margin_trend": "declining"}
        if len(gms) >= 3 and gms[0] < gms[1] < gms[2]:
            return {"gross_margin_trend": "rising"}
        return {"gross_margin_trend": "stable"}


@register_financial
class OperatingLeverage(FinancialIndicator):
    name = "operating_leverage"
    label = "经营杠杆"
    category = "fundamental"
    indicator_type = "prosperity"
    applicable_stages = ["growth"]
    params = {}
    output = ["operating_leverage"]
    requires = ["revenue", "parent_profit"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        """经营杠杆 = (Δprofit/profit) / (Δrevenue/revenue)"""
        if len(financials) < 8:
            return {"operating_leverage": None}
        rev_t = sum(float(q.get("revenue", 0) or 0) for q in financials[:4])
        rev_t1 = sum(float(q.get("revenue", 0) or 0) for q in financials[4:8])
        profit_t = sum(float(q.get("profit", q.get("parent_profit", 0)) or 0) for q in financials[:4])
        profit_t1 = sum(float(q.get("profit", q.get("parent_profit", 0)) or 0) for q in financials[4:8])
        if not rev_t1 or not profit_t1:
            return {"operating_leverage": None}
        rev_growth = (rev_t - rev_t1) / abs(rev_t1)
        profit_growth = (profit_t - profit_t1) / abs(profit_t1) if abs(profit_t1) > 0 else 0
        if abs(rev_growth) < 0.001:
            return {"operating_leverage": None}
        return {"operating_leverage": round(profit_growth / rev_growth, 2)}


@register_financial
class FCFConversion(FinancialIndicator):
    name = "fcf_conversion"
    label = "现金流转化率"
    category = "fundamental"
    indicator_type = "moat"
    applicable_stages = ["growth", "mature"]
    params = {}
    output = ["fcf_conversion"]
    requires = ["op_cashflow", "parent_profit"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        """经营性现金流/净利润。>1 = 利润是真金白银"""
        if not financials:
            return {"fcf_conversion": None}
        ocf = sum(float(q.get("op_cashflow", 0) or 0) for q in financials[:4])
        profit = sum(float(q.get("profit", q.get("parent_profit", 0)) or 0) for q in financials[:4])
        if not profit or profit <= 0:
            return {"fcf_conversion": None}
        return {"fcf_conversion": round(ocf / profit, 2)}
