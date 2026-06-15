"""OCF健康度 — OCF/净利润 + OCF趋势"""
from ..base import FinancialIndicator, register, _safe_div


@register
class OCFHealth(FinancialIndicator):
    name = "ocf_health"
    label = "OCF健康度"
    description = "近4Q经营现金流/近4Q净利润。衡量利润是否真实转化为现金,是识别纸面利润的核心指标。"
    judgment = ">1.0=高(OCF覆盖净利润有余); 0.7~1.0=中高; 0.5~0.7=中等; <0.5=低(OCF不足净利润一半); loss_making_but_cash_positive=净利润为负但OCF为正; loss_making_with_negative_ocf=净利润为负且OCF为负。ocf_profit_ratio=近4Q经营现金流/近4Q净利润(倍),正大=现金创造能力强,负=净利润亏损。"
    category = "health"
    indicator_type = "moat"
    applicable_stages = ["growth", "mature"]
    concepts = ["financial_health"]
    params = {}
    output = ["ocf_health", "ocf_profit_ratio"]
    text_output = ["ocf_health"]
    requires = ["op_cashflow", "profit"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if not financials:
            return {"ocf_health": None, "ocf_profit_ratio": None}
        ocf = sum(float(q.get("op_cashflow", 0) or 0) for q in financials[:4])
        profit = sum(float(q.get("profit", q.get("parent_profit", 0)) or 0) for q in financials[:4])

        ratio = round(ocf / profit, 2) if profit != 0 else (None if ocf == 0 else 999.0)

        if profit > 0:
            if ratio > 1.0:
                return {"ocf_health": "healthy", "ocf_profit_ratio": ratio}
            if ratio >= 0.7:
                return {"ocf_health": "normal", "ocf_profit_ratio": ratio}
            if ratio >= 0.5:
                return {"ocf_health": "low", "ocf_profit_ratio": ratio}
            return {"ocf_health": "poor", "ocf_profit_ratio": ratio}
        else:
            if ocf > 0:
                return {"ocf_health": "loss_making_but_cash_positive", "ocf_profit_ratio": ratio}
            return {"ocf_health": "loss_making_with_negative_ocf", "ocf_profit_ratio": ratio}
