"""OCF/利润比(TTM) — 经营现金流/净利润 数值版"""
from ..base import FinancialIndicator, register, _safe_div


@register
class OCFProfitRatio(FinancialIndicator):
    name = "ocf_profit_ratio_ttm"
    label = "经营现金流/净利润(TTM)"
    description = "近4Q经营现金流净额 / 近4Q归母净利润。衡量利润的现金保障程度, 是ocf_health指标的数值版, 支持阈值筛选和趋势跟踪。"
    judgment = ">1.0=现金保障充足; 0.7~1.0=正常; 0.5~0.7=偏低; 0~0.5=较差; <0=利润无现金支撑(或亏损)。"
    category = "health"
    indicator_type = "both"
    applicable_stages = ["growth", "mature", "inflection"]
    concepts = ["financial_health"]
    params = {}
    output = ["ocf_profit_ratio_ttm"]
    text_output = []  # 纯数值，无文本输出
    requires = ["op_cashflow", "parent_profit"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if len(financials) < 4:
            return {"ocf_profit_ratio_ttm": None}
        ocf_ttm = sum(float(q.get("op_cashflow", 0) or 0) for q in financials[:4])
        profit_ttm = sum(float(q.get("parent_profit", 0) or 0) for q in financials[:4])
        return {"ocf_profit_ratio_ttm": _safe_div(ocf_ttm, profit_ttm)}
