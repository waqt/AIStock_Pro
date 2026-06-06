"""毛利率倍数修正估值 (Gross Margin Multiple Adjustment)

核心逻辑:
  毛利率是最强的可持续溢价信号。用毛利率水平和变化趋势调整 PS/PE 倍数。
  高毛利率 → 定价权强 → 高倍数; 毛利率上升 → 趋势加强 → 额外溢价。

适用: 消费/医药/TMT 等毛利率差异大的行业, 成长型公司
"""
from app.domain.quant.valuation.base import ValuationMethod, register_valuation


@register_valuation
class GrossMarginMultipleAdjustMethod(ValuationMethod):
    name = "gm_multiple_adjust"
    label = "毛利率倍数修正"
    category = "dynamic"
    description = "基于毛利率水平、变化趋势和营收增速动态调整 PS/PE 倍数, 适合毛利率驱动型成长公司"
    output = [
        "gm_adjusted_ps", "gm_base_ps", "gm_premium_breakdown",
        "gm_target_price", "gm_upside_pct", "gm_quality_score", "gm_verdict",
    ]
    text_output = ["gm_premium_breakdown", "gm_verdict"]
    requires = ["mcap_yi", "total_shares"]
    requires_financial_data = True
    requires_financial_indicators = True

    _field_labels = {
        "gm_adjusted_ps": "调整后 PS(倍)",
        "gm_base_ps": "基准 PS(倍)",
        "gm_premium_breakdown": "溢价分解",
        "gm_target_price": "毛利率目标价(¥)",
        "gm_upside_pct": "上行空间(%)",
        "gm_quality_score": "毛利率质量评分",
        "gm_verdict": "判断结论",
    }

    @classmethod
    def compute(cls, **kwargs) -> dict:
        gm_pct = kwargs.get("gross_margin_pct")  # %
        gm_trend = kwargs.get("gross_margin_trend") or "stable"
        gm_chg = kwargs.get("gross_margin_chg_pp") or 0
        rev_yoy = kwargs.get("rev_yoy_ttm") or kwargs.get("avg_rev_yoy_4q") or 0
        mcap_yi = kwargs.get("mcap_yi")
        total_shares = kwargs.get("total_shares")

        # 也有 pe_ttm 可用
        pe_ttm = kwargs.get("pe_ttm")

        if gm_pct is None or not mcap_yi or not total_shares:
            return {k: None for k in cls.output}

        gm_pct = float(gm_pct)
        rev_yoy = float(rev_yoy)
        current_price = (mcap_yi * 1e8) / total_shares if total_shares > 0 else 0

        # 1. 基准 PS: 行业中性 2.0, 根据毛利率水平调整
        base_ps = 2.0

        # GM调整因子: PS_mult = base_PS × (0.5 + gm_pct/100)
        # GM=30% → ×0.8, GM=60% → ×1.1, GM=80% → ×1.3
        gm_factor = 0.5 + gm_pct / 100.0
        ps_mult = base_ps * gm_factor

        # 2. 趋势溢价
        trend_premium = 0.0
        breakdown_parts = [f"base_PS={base_ps:.1f}", f"GM_factor={gm_factor:.2f}"]

        if gm_trend == "rising":
            trend_premium = 0.2 * base_ps
            breakdown_parts.append(f"GM_trend_rising+{trend_premium:.1f}")
        elif gm_trend == "declining":
            trend_premium = -0.15 * base_ps
            breakdown_parts.append(f"GM_trend_declining{trend_premium:.1f}")

        # 3. 增长协同
        growth_premium = 0.0
        if rev_yoy > 30:
            growth_premium = 0.15 * base_ps
            breakdown_parts.append(f"growth>30%+{growth_premium:.1f}")

        adjusted_ps = ps_mult + trend_premium + growth_premium
        adjusted_ps = max(0.5, adjusted_ps)

        # 4. 目标价 = PS × 每股营收
        rev_ttm_yi = kwargs.get("revenue_4q_yi")
        if rev_ttm_yi:
            rps = (rev_ttm_yi * 1e8) / total_shares
            target_price = adjusted_ps * rps
        elif pe_ttm:
            # 用 PE × EPS 估算
            if pe_ttm:
                eps = current_price / pe_ttm if pe_ttm > 0 else 0
                implied_pe = adjusted_ps * 2.0  # 粗估 PE/PS 比例
                target_price = eps * implied_pe
            else:
                target_price = 0
        else:
            target_price = 0

        upside = ((target_price / current_price) - 1) * 100 if current_price > 0 and target_price > 0 else 0

        # 毛利率质量评分 (0-100)
        quality = min(100, max(0,
            (gm_pct / 80.0) * 50 +                                    # 毛利率水平 0-50
            (gm_chg > 0 and 15 or (gm_chg < 0 and -10 or 0)) +        # 变化方向
            (rev_yoy / 50.0) * 20 +                                    # 增长协同 0-20
            (gm_trend == "rising" and 15 or gm_trend == "stable" and 10 or 0)  # 趋势稳定性
        ))

        # 结论
        if upside > 25:
            verdict = "毛利率支撑强, 显著低估"
        elif upside > 5:
            verdict = "毛利率合理偏低"
        elif upside > -10:
            verdict = "毛利率估值合理"
        else:
            verdict = "毛利率已透支定价"

        return {
            "gm_adjusted_ps": round(adjusted_ps, 2),
            "gm_base_ps": base_ps,
            "gm_premium_breakdown": " | ".join(breakdown_parts),
            "gm_target_price": round(target_price, 2),
            "gm_upside_pct": round(upside, 1),
            "gm_quality_score": round(quality, 0),
            "gm_verdict": verdict,
        }
