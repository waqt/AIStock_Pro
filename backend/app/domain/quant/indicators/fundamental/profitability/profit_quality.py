"""成长质量 — 毛利率趋势 / 研发费用率"""
from ..base import FinancialIndicator, register


@register
class GrossMarginTrend(FinancialIndicator):
    name = "gross_margin_trend"
    label = "毛利率趋势"
    description = "判断毛利率连续4Q的变化方向: rising/stable/declining。"
    judgment = "rising=定价权增强; stable=竞争均衡; declining=定价权削弱。连续3Q下降是预警信号。"
    category = "profitability"
    indicator_type = "moat"
    applicable_stages = ["inflection", "growth", "mature"]
    params = {}
    output = ["gross_margin_trend"]
    requires = ["revenue", "operate_cost"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if len(financials) < 4:
            return {"gross_margin_trend": None}
        gms = []
        for q in financials[:4]:
            rev = float(q.get("revenue", 0) or 0)
            cost = float(q.get("operate_cost", 0) or 0)
            gms.append((rev - cost) / rev * 100 if rev else 0)
        if len(gms) >= 3 and gms[0] > gms[1] > gms[2]:
            return {"gross_margin_trend": "rising"}
        if len(gms) >= 3 and gms[0] < gms[1] < gms[2]:
            return {"gross_margin_trend": "declining"}
        return {"gross_margin_trend": "stable"}


@register
class RDIntensity(FinancialIndicator):
    name = "rd_intensity"
    label = "研发费用率(%)"
    description = "研发费用占营收比例。衡量公司对技术/创新的投入力度。"
    judgment = ">15%=高强度研发投入; 8~15%=企业级软件/硬科技; 3~8%=稳健投入型; <3%=研发投入不足。"
    category = "profitability"
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
