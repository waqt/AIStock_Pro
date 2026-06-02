"""ROIIC — 增量资本回报率 + 研发资本化调整（产出 adjusted ROIC/ROIIC）"""
from ..base import FinancialIndicator, register
from .._roic_core import compute_roic as _compute_roic, compute_roiic as _compute_roiic
from .._roic_core import adjust_rd_capitalization


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
    output = [
        "roiic", "roiic_pct", "roiic_quality", "roiic_interpretation",
        "roic_adjusted", "roic_pct_adjusted",
        "roiic_adjusted", "roiic_pct_adjusted",
    ]
    text_output = ["roiic_quality", "roiic_interpretation"]
    requires = ["revenue", "operate_cost", "sale_expense", "manage_expense",
                "rd_expense",
                "total_assets", "current_assets", "cash",
                "current_liabilities", "short_loan", "noncurrent_liab_1year"]

    @classmethod
    def compute(cls, financials: list) -> dict:
        if len(financials) < 8:
            return {"roiic": None, "roiic_pct": None}
        # GAAP 标准模式: 研发费用作为营业费用扣除
        r = _compute_roiic(financials, capitalize_rd=False, tax_rate=0.15)
        result = {
            "roiic": r.get("roiic"), "roiic_pct": r.get("roiic_pct"),
            "roiic_quality": r.get("quality"), "roiic_interpretation": r.get("interpretation"),
        }

        # 研发资本化调整 → 当调整影响 >10% 时产出 adjusted 字段
        try:
            adj = adjust_rd_capitalization(financials[:8])
            if adj.get("material"):
                reported = adj.get("reported_profit_yi", 0)
                adjusted = adj.get("adjusted_profit_yi", 0)
                adj_factor = adjusted / max(reported, 0.01) if reported > 0 else 1.0
                if adj_factor > 1.01:
                    # 调整 ROIC (用资本化模式重新计算)
                    roic_adj = _compute_roic(financials[:4], capitalize_rd=True, tax_rate=0.15)
                    if roic_adj.get("roic_pct") is not None:
                        result["roic_adjusted"] = roic_adj.get("roic")
                        result["roic_pct_adjusted"] = roic_adj.get("roic_pct")
                    # 调整 ROIIC (用资本化模式重新计算)
                    roiic_adj = _compute_roiic(financials[:8], capitalize_rd=True, tax_rate=0.15)
                    if roiic_adj.get("roiic_pct") is not None:
                        result["roiic_adjusted"] = roiic_adj.get("roiic")
                        result["roiic_pct_adjusted"] = roiic_adj.get("roiic_pct")
        except Exception:
            pass

        return result
