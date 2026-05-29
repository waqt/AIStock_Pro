"""
ROIIC 指标 — 增量投资资本回报率
公式: ROIIC = (NOPAT_t - NOPAT_t-4) / (IC_t-1 - IC_t-5)
"""
from .base import FinancialIndicator, register_financial
from app.framework.finance.roiic import compute_roiic


@register_financial
class ROIICIndicator(FinancialIndicator):
    name = "roiic"
    label = "增量资本回报率(ROIIC)"
    category = "fundamental"
    indicator_type = "prosperity"
    applicable_stages = ["growth"]
    params = {}
    output = ["roiic", "roiic_pct"]
    requires = ["revenue", "operate_cost", "sale_expense", "manage_expense",
                "total_assets", "current_assets", "cash", "current_liabilities",
                "short_loan", "noncurrent_liab_1year"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        result = compute_roiic(financials)
        return {
            "roiic": result.get("roiic"),
            "roiic_pct": result.get("roiic_pct"),
        }
