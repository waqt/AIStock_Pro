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
    description = "ROIC = NOPAT / 投入资本。衡量公司每投入一元资本能赚回多少利润，是判断护城河的核心指标。不受资本结构影响，比ROE更能反映经营质量。"
    judgment = "ROIC>15%=强护城河,定价权突出; 10~15%=良好,有竞争优势; 5~10%=一般,缺乏壁垒; <5%=脆弱需警惕。持续>20%为顶级复利机器。"
    category = "fundamental"
    indicator_type = "moat"
    applicable_stages = ["growth", "mature"]
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
