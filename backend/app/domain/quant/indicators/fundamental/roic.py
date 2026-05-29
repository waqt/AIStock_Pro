"""
ROIC 指标 — 静态投资资本回报率
公式: ROIC = NOPAT / InvestedCapital
"""
from .base import FinancialIndicator, register_financial
from app.framework.finance.roiic import compute_roic


@register_financial
class ROICIndicator(FinancialIndicator):
    name = "roic"
    label = "投资资本回报率(ROIC)"
    category = "fundamental"
    params = {}
    output = ["roic", "roic_pct"]
    requires = ["revenue", "operate_cost", "sale_expense", "manage_expense",
                "total_assets", "current_assets", "cash", "current_liabilities",
                "short_loan", "noncurrent_liab_1year"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        result = compute_roic(financials)
        return {
            "roic": result.get("roic"),
            "roic_pct": result.get("roic_pct"),
        }
