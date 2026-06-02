"""OCF健康度 — OCF/净利润 + OCF趋势"""
from ..base import FinancialIndicator, register


@register
class OCFHealth(FinancialIndicator):
    name = "ocf_health"
    label = "OCF健康度"
    description = "近4Q经营现金流/近4Q净利润。衡量利润是否真实转化为现金,是识别纸面利润的核心指标。"
    judgment = ">1.0=健康,利润是真金白银; 0.7~1.0=正常; 0.5~0.7=偏低; <0.5=利润质量差。持续<0.5需警惕财务操纵。"
    category = "health"
    indicator_type = "moat"
    applicable_stages = ["growth", "mature"]
    params = {}
    output = ["ocf_health"]
    requires = ["op_cashflow", "profit"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if not financials:
            return {"ocf_health": None}
        ocf = sum(float(q.get("op_cashflow", 0) or 0) for q in financials[:4])
        profit = sum(float(q.get("profit", q.get("parent_profit", 0)) or 0) for q in financials[:4])
        if not profit or profit <= 0:
            return {"ocf_health": None}
        ratio = ocf / profit
        if ratio > 1.0:
            return {"ocf_health": "healthy"}
        if ratio >= 0.7:
            return {"ocf_health": "normal"}
        if ratio >= 0.5:
            return {"ocf_health": "low"}
        return {"ocf_health": "poor"}
