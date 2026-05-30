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
    description = "ROIIC = ΔNOPAT / ΔIC。衡量公司每新增投入一元资本带来的边际回报，是判断成长质量的核心指标。回答了新投的钱是否比旧钱赚得多的核心问题。"
    judgment = "ROIIC>20%=增长创造价值,新投资回报丰厚; 10~20%=合理增长; 5~10%=增长效率一般; <5%=增长不创造价值,净烧钱。持续>30%为爆发前夜信号。"
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
