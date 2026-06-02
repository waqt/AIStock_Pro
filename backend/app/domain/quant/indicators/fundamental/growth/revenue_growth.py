"""营收增长 — YoY + 4Q平均"""
from ..base import FinancialIndicator, register, _pct


@register
class RevenueGrowth(FinancialIndicator):
    name = "revenue_growth"
    label = "营收增长"
    description = "近4Q营收YoY增速 + 近4Q平均增速。衡量公司收入扩张的核心指标。"
    judgment = ">30%=高速增长; 15~30%=稳健增长; 5~15%=低速增长; 0~5%=停滞; <0=衰退。连续4Q>20%是高成长股特征。"
    category = "growth"
    indicator_type = "prosperity"
    applicable_stages = ["startup", "inflection", "growth"]
    params = {}
    output = ["rev_yoy_latest", "avg_rev_yoy_4q", "rev_yoy_ttm", "revenue_4q_yi"]
    requires = ["revenue"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if len(financials) < 8:
            return {"rev_yoy_latest": None, "avg_rev_yoy_4q": None, "rev_yoy_ttm": None, "revenue_4q_yi": None}
        revs = [float(q.get("revenue", 0) or 0) for q in financials]
        latest_ttm = sum(revs[:4])
        prior_ttm = sum(revs[4:8])
        yoy_list = []
        for i in range(4):
            if i + 4 < len(revs):
                yoy_list.append(_pct(revs[i], revs[i + 4]))
        return {
            "rev_yoy_latest": yoy_list[0] if yoy_list else None,
            "avg_rev_yoy_4q": round(sum(y for y in yoy_list if y is not None) / max(len([y for y in yoy_list if y is not None]), 1), 1) if yoy_list else None,
            "rev_yoy_ttm": round((latest_ttm - prior_ttm) / prior_ttm * 100, 1) if prior_ttm else None,
            "revenue_4q_yi": round(latest_ttm / 1e8, 2),
        }
