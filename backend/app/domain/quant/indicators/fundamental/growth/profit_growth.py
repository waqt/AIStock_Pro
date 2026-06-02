"""利润增长 — YoY + 4Q平均"""
from ..base import FinancialIndicator, register, _pct


@register
class ProfitGrowth(FinancialIndicator):
    name = "profit_growth"
    label = "利润增长"
    description = "近4Q归母净利润YoY增速。衡量公司盈利能力的提升速度。"
    judgment = ">30%=高增长; 15~30%=稳健; 5~15%=低速; 0~5%=停滞; <0=利润衰退。利润增速>营收增速=利润率扩张(好信号)。"
    category = "growth"
    indicator_type = "prosperity"
    applicable_stages = ["startup", "inflection", "growth"]
    params = {}
    output = ["profit_yoy_latest", "avg_profit_yoy_4q", "profit_yoy_ttm", "profit_4q_yi"]
    requires = ["profit"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if len(financials) < 8:
            return {"profit_yoy_latest": None, "avg_profit_yoy_4q": None, "profit_yoy_ttm": None, "profit_4q_yi": None}
        profits = [float(q.get("profit", q.get("parent_profit", 0)) or 0) for q in financials]
        latest_ttm = sum(profits[:4])
        prior_ttm = sum(profits[4:8])
        yoy_list = []
        for i in range(4):
            if i + 4 < len(profits):
                yoy_list.append(_pct(profits[i], profits[i + 4]))
        return {
            "profit_yoy_latest": yoy_list[0] if yoy_list else None,
            "avg_profit_yoy_4q": round(sum(y for y in yoy_list if y is not None) / max(len([y for y in yoy_list if y is not None]), 1), 1) if yoy_list else None,
            "profit_yoy_ttm": round((latest_ttm - prior_ttm) / prior_ttm * 100, 1) if prior_ttm else None,
            "profit_4q_yi": round(latest_ttm / 1e8, 2),
        }
