"""
研发资本化调整后的 ROIC/ROIIC
解决了因会计处理差异导致横向对比失效的问题
"""
from .base import FinancialIndicator, register_financial


@register_financial
class ROICAdjusted(FinancialIndicator):
    name = "roic_adjusted"
    label = "ROIC(研发调整后)"
    category = "fundamental"
    indicator_type = "moat"
    applicable_stages = ["growth", "mature"]
    params = {}
    output = ["roic_adjusted", "roic_pct_adjusted"]
    requires = []

    @classmethod
    def compute(cls, financials: list) -> dict:
        """由 compute 端点统一计算, 此处返回空 (端点中处理)"""
        return {}


@register_financial
class ROIICAdjusted(FinancialIndicator):
    name = "roiic_adjusted"
    label = "ROIIC(研发调整后)"
    category = "fundamental"
    indicator_type = "prosperity"
    applicable_stages = ["growth"]
    params = {}
    output = ["roiic_adjusted", "roiic_pct_adjusted"]
    requires = []

    @classmethod
    def compute(cls, financials: list) -> dict:
        """由 compute 端点统一计算, 此处返回空 (端点中处理)"""
        return {}
