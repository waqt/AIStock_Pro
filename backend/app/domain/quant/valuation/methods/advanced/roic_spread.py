"""ROIC-WACC 价差 — 衡量企业价值创造能力

ROIC - WACC > 0 → 创造价值
ROIC - WACC < 0 → 毁灭价值
"""
from app.domain.quant.valuation.base import ValuationMethod, register_valuation


@register_valuation
class ROICSpreadMethod(ValuationMethod):
    name = "roic_spread"
    label = "ROIC-WACC 价差"
    category = "advanced"
    description = "ROIC - WACC。正价差表示公司创造价值, 负价差表示毁灭价值。价差越大, 护城河越宽"
    output = ["roic_spread_pct", "wacc_est", "value_creation_label"]
    requires = ["roe", "pe_ttm"]
    requires_financial_data = True
    text_output = ["value_creation_label"]

    @classmethod
    def compute(cls, roe: float = None, pe_ttm: float = None, **kwargs) -> dict:
        # 获取 ROIC (由 runner 从 indicators 模块注入)
        roic_pct = kwargs.get("roic_pct") or roe  # 兜底用 ROE

        if roic_pct is None:
            return {k: None for k in cls.output}

        # WACC 估计: 基于 PE 反推权益成本
        if pe_ttm and pe_ttm > 0:
            earnings_yield = 1 / pe_ttm * 100  # 盈利收益率 %
            # WACC ≈ 盈利收益率 × 0.7 + 债务成本 × 0.3
            wacc = earnings_yield * 0.7 + 3.0 * 0.3  # 债务成本 ~3%
        else:
            wacc = 8.0  # 默认 WACC

        spread = roic_pct - wacc

        if spread > 5:
            label = "强价值创造"
        elif spread > 0:
            label = "价值创造"
        elif spread > -5:
            label = "价值中性"
        else:
            label = "价值毁灭"

        return {
            "roic_spread_pct": round(spread, 2),
            "wacc_est": round(wacc, 2),
            "value_creation_label": label,
        }
