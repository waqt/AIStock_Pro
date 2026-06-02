"""盈利能力 — 毛利率/净利率/营业利润率"""
from ..base import FinancialIndicator, register


@register
class MarginIndicator(FinancialIndicator):
    name = "margin"
    label = "综合利润率"
    description = "毛利率、净利率、营业利润率。衡量公司盈利能力和定价权的核心指标。"
    judgment = "毛利率>70%=极强定价权; 50~70%=强护城河; 30~50%=中等; <30%=竞争激烈。净利率>20%=优秀。"
    category = "profitability"
    indicator_type = "moat"
    applicable_stages = ["inflection", "growth", "mature"]
    params = {}
    output = ["gross_margin_pct", "net_margin_pct", "operating_margin_pct"]
    requires = ["revenue", "operate_cost", "profit", "sale_expense", "manage_expense"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if not financials or len(financials) < 4:
            return {"gross_margin_pct": None, "net_margin_pct": None, "operating_margin_pct": None}
        rev_ttm = sum(float(q.get("revenue", 0) or 0) for q in financials[:4])
        cost_ttm = sum(float(q.get("operate_cost", 0) or 0) for q in financials[:4])
        profit_ttm = sum(float(q.get("profit", 0) or 0) for q in financials[:4])
        sga = sum(float(q.get("sale_expense", 0) or 0) + float(q.get("manage_expense", 0) or 0) for q in financials[:4])
        if not rev_ttm:
            return {"gross_margin_pct": None, "net_margin_pct": None, "operating_margin_pct": None}
        gm = (rev_ttm - cost_ttm) / rev_ttm * 100
        nm = profit_ttm / rev_ttm * 100
        om = (rev_ttm - cost_ttm - sga) / rev_ttm * 100
        return {"gross_margin_pct": round(gm, 1), "net_margin_pct": round(nm, 1), "operating_margin_pct": round(om, 1)}


@register
class ROEIndicator(FinancialIndicator):
    name = "roe"
    label = "ROE(%)"
    description = "净资产收益率 = 归母净利润/净资产。巴菲特的选股金标准，衡量股东权益的回报效率。"
    judgment = ">20%=优秀(10年长牛股门槛); 15~20%=良好; 10~15%=一般; 5~10%=偏低; <5%=资本利用效率差。连续5年>15%是优质白马特征。"
    category = "profitability"
    indicator_type = "moat"
    applicable_stages = ["mature"]
    params = {}
    output = ["roe"]
    requires = ["profit", "total_equity"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if not financials or len(financials) < 4:
            return {"roe": None}
        profit = sum(float(q.get("profit", q.get("parent_profit", 0)) or 0) for q in financials[:4])
        equity = float(financials[0].get("total_equity", 0) or 0)
        if not equity:
            return {"roe": None}
        return {"roe": round(profit / equity * 100, 1)}
