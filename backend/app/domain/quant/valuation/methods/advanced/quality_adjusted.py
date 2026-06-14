"""质量调整估值 — 基于 ROE/股息/增速对 PE 倍数进行调整

内联实现 apply_quality_adjustment 逻辑，消除对旧 framework/finance/valuation.py 的依赖。
"""
from app.domain.quant.valuation.base import ValuationMethod, register_valuation


@register_valuation
class QualityAdjustedMethod(ValuationMethod):
    name = "quality_adjusted"
    label = "质量调整估值"
    category = "advanced"
    description = "基于 ROE>15%、股息率>2%、EPS 增速>20% 对 PE 倍数进行质量溢价调整"
    output = ["adjusted_pe", "quality_detail", "quality_bonus_pct"]
    text_output = ["quality_detail"]
    requires = ["pe_ttm", "roe", "dividend_yield", "eps_growth_3y"]
    judgment = "adjusted_pe 是经过质量调整后的合理PE上限。quality_detail 列出各项调整因子。质量调整幅度compounded可能过大, 建议参考各因子明细而非仅看最终值"
    applicable_scenarios = "适用于高质量公司(高ROE+稳定增长+良好治理); 质量因子的累加效应在蓝筹股中最明显"
    limitations = "多项调整叠加可能高估合理PE(compounding effect); ROE>15%阈值固定, 未考虑行业差异; 不考虑估值的安全边际"

    @classmethod
    def compute(cls, pe_ttm: float = None, roe: float = None,
                dividend_yield: float = None, eps_growth_3y: float = None,
                **kwargs) -> dict:
        if pe_ttm is None:
            return {k: None for k in cls.output}

        # 质量调整逻辑 (原 apply_quality_adjustment 内联)
        bonus = 0.0
        details = []
        if roe is not None and roe > 15:
            bonus += 0.05
            details.append(f"ROE={roe}%>15% (+5%)")
        if dividend_yield is not None and dividend_yield > 2:
            bonus += 0.03
            details.append(f"股息={dividend_yield}%>2% (+3%)")
        if eps_growth_3y is not None and eps_growth_3y > 20:
            bonus += 0.05
            details.append(f"EPS增速={eps_growth_3y}%>20% (+5%)")

        adjusted = round(pe_ttm * (1 + bonus), 2)
        bonus_pct = round((adjusted - pe_ttm) / pe_ttm * 100, 1) if pe_ttm > 0 else 0

        return {
            "adjusted_pe": adjusted,
            "quality_detail": "; ".join(details) if details else "无质量溢价",
            "quality_bonus_pct": bonus_pct,
        }
