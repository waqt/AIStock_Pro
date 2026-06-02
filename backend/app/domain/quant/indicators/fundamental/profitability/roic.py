"""ROIC — 投资资本回报率"""
from ..base import FinancialIndicator, register
from app.framework.finance.roiic import compute_roic as _compute_roic


@register
class ROICIndicator(FinancialIndicator):
    name = "roic"
    label = "ROIC(%)"
    description = "投资资本回报率 = NOPAT/IC。衡量公司占用资本的回报效率，不受资本结构影响，比ROE更纯净的护城河指标。"
    judgment = ">20%=极强护城河; 15~20%=优秀; 10~15%=良好; 8~10%=一般; <8%=平庸。ROIC>15%且稳定是顶级资产的核心特征。"
    category = "profitability"
    indicator_type = "moat"
    applicable_stages = ["growth", "mature"]
    params = {"capitalize_rd": False}
    output = ["roic", "roic_pct", "roic_quality", "roic_interpretation"]
    requires = ["revenue", "operate_cost", "sale_expense", "manage_expense",
                "total_assets", "current_assets"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if len(financials) < 4:
            return {"roic": None, "roic_pct": None}
        r = _compute_roic(financials, capitalize_rd=False)
        return {
            "roic": r.get("roic"), "roic_pct": r.get("roic_pct"),
            "roic_quality": r.get("quality"), "roic_interpretation": r.get("interpretation"),
        }
