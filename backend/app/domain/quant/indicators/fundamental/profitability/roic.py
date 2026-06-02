"""ROIC — 投资资本回报率"""
from ..base import FinancialIndicator, register
from .._roic_core import compute_roic as _compute_roic


@register
class ROICIndicator(FinancialIndicator):
    name = "roic"
    label = "ROIC(%)"
    description = "投资资本回报率 = NOPAT/IC。衡量公司占用资本的回报效率，不受资本结构影响，比ROE更纯净的护城河指标。"
    judgment = ">20%=高; 15~20%=较高; 10~15%=中等; 8~10%=偏低; <8%=低。ROIC>15%且稳定通常对应较强的竞争优势。"
    category = "profitability"
    indicator_type = "moat"
    applicable_stages = ["growth", "mature"]
    params = {"capitalize_rd": False}
    output = ["roic", "roic_pct", "roic_quality", "roic_interpretation"]
    text_output = ["roic_quality", "roic_interpretation"]
    requires = ["revenue", "operate_cost", "sale_expense", "manage_expense",
                "rd_expense", "total_assets", "current_assets", "cash",
                "current_liabilities", "short_loan", "noncurrent_liab_1year"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if len(financials) < 4:
            return {"roic": None, "roic_pct": None}
        # GAAP 标准模式: 研发费用作为营业费用扣除
        r = _compute_roic(financials, capitalize_rd=False, tax_rate=0.15)
        return {
            "roic": r.get("roic"), "roic_pct": r.get("roic_pct"),
            "roic_quality": r.get("quality"), "roic_interpretation": r.get("interpretation"),
        }
