"""ROIIC — 增量资本回报率"""
from ..base import FinancialIndicator, register
from app.framework.finance.roiic import compute_roiic as _compute_roiic


@register
class ROIICIndicator(FinancialIndicator):
    name = "roiic"
    label = "ROIIC(%)"
    description = "增量投资资本回报率 = ΔNOPAT/ΔIC。衡量新投入资本的边际回报，判断成长质量的关键指标。"
    judgment = ">30%=高效扩张; 15~30%=健康扩张; 8~15%=可接受; 0~8%=低效; <0=价值毁灭。ROIIC>ROIC=边际改善中。"
    category = "profitability"
    indicator_type = "prosperity"
    applicable_stages = ["growth"]
    params = {"capitalize_rd": False}
    output = ["roiic", "roiic_pct", "roiic_quality", "roiic_interpretation"]
    requires = ["revenue", "operate_cost", "sale_expense", "manage_expense",
                "total_assets", "current_assets"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if len(financials) < 8:
            return {"roiic": None, "roiic_pct": None}
        r = _compute_roiic(financials, capitalize_rd=False)
        return {
            "roiic": r.get("roiic"), "roiic_pct": r.get("roiic_pct"),
            "roiic_quality": r.get("quality"), "roiic_interpretation": r.get("interpretation"),
        }
