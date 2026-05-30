"""
研发资本化调整后的 ROIC/ROIIC
解决了因会计处理差异导致横向对比失效的问题
"""
from .base import FinancialIndicator, register_financial


@register_financial
class ROICAdjusted(FinancialIndicator):
    name = "roic_adjusted"
    label = "ROIC(研发调整后)"
    description = "将研发支出资本化并摊销计入调整后的ROIC，解决轻资产高研发公司的会计扭曲。还原真实回报率，使高研发公司与传统公司的ROIC横向可比。"
    judgment = "调整后ROIC vs 原始ROIC:差值越大=研发资本化程度越高(研发是被隐藏的投资)。调整值>原始值说明研发是投资性支出而非费用。参考原始ROIC同等阈值判断。"
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
    description = "将研发支出资本化后重新计算的增量资本回报率。高研发公司新增投入中有大量属于隐性投资,调整后还原其真实边际回报。"
    judgment = "调整后ROIIC>原始ROIIC=研发投入在创造复利。调整后仍<原始ROIIC且均为负=新投入持续摧毁价值。参考原始ROIIC同等阈值判断。"
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
