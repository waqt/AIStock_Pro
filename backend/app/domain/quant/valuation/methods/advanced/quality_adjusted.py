"""质量调整估值 — 基于 ROE/股息/增速对 PE 倍数进行调整

调用 framework/finance/valuation.py 的质量调整函数。
"""
from app.domain.quant.valuation.base import ValuationMethod, register_valuation
from app.framework.finance.valuation import apply_quality_adjustment


@register_valuation
class QualityAdjustedMethod(ValuationMethod):
    name = "quality_adjusted"
    label = "质量调整估值"
    category = "advanced"
    description = "基于 ROE>15%、股息率>2%、EPS 增速>20% 对 PE 倍数进行质量溢价调整"
    output = ["adjusted_pe", "quality_detail", "quality_bonus_pct"]
    requires = ["pe_ttm", "roe", "dividend_yield", "eps_growth_3y"]

    @classmethod
    def compute(cls, pe_ttm: float = None, roe: float = None,
                dividend_yield: float = None, eps_growth_3y: float = None,
                **kwargs) -> dict:
        if pe_ttm is None:
            return {k: None for k in cls.output}

        adjusted, details = apply_quality_adjustment(
            pe_ttm, roe, dividend_yield, eps_growth_3y)

        bonus_pct = round((adjusted - pe_ttm) / pe_ttm * 100, 1) if pe_ttm > 0 else 0

        return {
            "adjusted_pe": adjusted,
            "quality_detail": "; ".join(details) if details else "无质量溢价",
            "quality_bonus_pct": bonus_pct,
        }
