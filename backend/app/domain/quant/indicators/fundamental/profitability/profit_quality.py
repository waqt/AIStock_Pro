"""成长质量 — 毛利率趋势 / 研发费用率"""
from ..base import FinancialIndicator, register


@register
class GrossMarginTrend(FinancialIndicator):
    name = "gross_margin_trend"
    label = "毛利率趋势"
    description = "判断毛利率连续3Q的变化方向: rising/stable/declining。"
    judgment = "rising=毛利率持续上升; stable=窄幅波动; declining=毛利率持续下降。gross_margin_chg_pp=最新季与4季前毛利率差值(百分点)。"
    category = "profitability"
    indicator_type = "moat"
    concepts = ["profit_quality"]
    applicable_stages = ["inflection", "growth", "mature"]
    params = {}
    output = ["gross_margin_trend", "gross_margin_chg_pp"]
    text_output = ["gross_margin_trend"]
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
        chg_pp = round(gms[0] - gms[-1], 2) if len(gms) >= 4 else None
        if len(gms) >= 3 and _is_strictly_monotonic(gms[:3]):
            if gms[0] > gms[-1]:
                return {"gross_margin_trend": "rising", "gross_margin_chg_pp": chg_pp}
            return {"gross_margin_trend": "declining", "gross_margin_chg_pp": chg_pp}
        return {"gross_margin_trend": "stable", "gross_margin_chg_pp": chg_pp}


def _is_strictly_monotonic(values: list, tolerance_pct: float = 0.5) -> bool:
    """检查列表是否严格单调 (允许容差 < tolerance_pct 的微小波动)。"""
    if len(values) < 2:
        return True
    increasing = values[0] < values[-1]
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        if increasing:
            if diff < -tolerance_pct:
                return False
        else:
            if diff > tolerance_pct:
                return False
    return True


@register
class RDIntensity(FinancialIndicator):
    name = "rd_intensity"
    label = "研发费用率(%)"
    description = "研发费用占营收比例。衡量公司对技术/创新的投入力度。"
    judgment = ">15%=高(生物医药/软件行业常见); 8~15%=中高; 3~8%=中等; <3%=低。高低本身无绝对好坏,需结合行业特征和研发资本化政策综合判断。"
    category = "profitability"
    indicator_type = "moat"
    concepts = ["profit_quality"]
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
