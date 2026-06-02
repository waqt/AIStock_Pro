"""营收规模分类"""
from ..base import FinancialIndicator, register


@register
class RevenueScale(FinancialIndicator):
    name = "revenue_scale"
    label = "营收规模"
    description = "TTM营收规模分类: mega/large/medium/small/micro。判定公司体量和市场地位。"
    judgment = "mega=千亿级(大盘蓝筹); large=百亿级(中盘成长); medium=十亿级(小盘); small=亿级(微型); micro=千万级(初创)。阈值基于A股标准(RMB计价),港股/美股需按汇率换算后参考。"
    category = "profile"
    indicator_type = "both"
    applicable_stages = ["startup", "inflection", "growth", "mature"]
    params = {}
    output = ["revenue_scale"]
    text_output = ["revenue_scale"]
    requires = ["revenue"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if not financials:
            return {"revenue_scale": "unknown"}
        rev = sum(float(q.get("revenue", 0) or 0) for q in financials[:4])
        if rev >= 1e11:
            return {"revenue_scale": "mega"}
        if rev >= 1e10:
            return {"revenue_scale": "large"}
        if rev >= 1e9:
            return {"revenue_scale": "medium"}
        if rev >= 1e8:
            return {"revenue_scale": "small"}
        return {"revenue_scale": "micro"}
