"""经营杠杆调整估值 (Operating Leverage Adjusted Valuation)

核心逻辑:
  经营杠杆 (DOL) 将营收增长转换为利润增长的放大器。
  高 DOL + 高营收增长 → 未来利润弹性极大, 应赋予更高 PEG。
  低 DOL → 增长转化效率低 → PEG 折价。

适用: 固定成本占比高/规模效应强的公司 (制造/互联网/平台)
"""
from app.domain.quant.valuation.base import ValuationMethod, register_valuation


@register_valuation
class DOLAdjustedValuationMethod(ValuationMethod):
    name = "dol_adjusted"
    label = "经营杠杆调整估值"
    category = "dynamic"
    description = "基于经营杠杆(DOL)将营收增速转换为前向利润增速, 动态调整 PEG/P E 倍数"
    output = [
        "dol_adjusted_pe", "dol_base_pe",
        "dol_forward_growth_est",
        "dol_target_price", "dol_upside_pct", "dol_verdict",
    ]
    text_output = ["dol_verdict"]
    requires = ["pe_ttm", "mcap_yi", "total_shares"]
    requires_financial_data = True
    requires_financial_indicators = True

    _field_labels = {
        "dol_adjusted_pe": "DOL调整后PE(倍)",
        "dol_base_pe": "当前PE(倍)",
        "dol_forward_growth_est": "前向利润增速(%)",
        "dol_target_price": "DOL目标价(¥)",
        "dol_upside_pct": "上行空间(%)",
        "dol_verdict": "判断结论",
    }

    @classmethod
    def compute(cls, **kwargs) -> dict:
        pe_ttm = kwargs.get("pe_ttm")
        mcap_yi = kwargs.get("mcap_yi")
        total_shares = kwargs.get("total_shares")
        dol = kwargs.get("operating_leverage")
        avg_rev_growth = kwargs.get("avg_rev_yoy_4q") or 0
        rev_latest = kwargs.get("rev_yoy_latest") or avg_rev_growth
        op_margin = kwargs.get("operating_margin_pct") or 0

        if pe_ttm is None or not mcap_yi or not total_shares:
            return {k: None for k in cls.output}

        pe_ttm = float(pe_ttm)
        current_price = (mcap_yi * 1e8) / total_shares if total_shares > 0 else 0
        eps_ttm = current_price / pe_ttm if pe_ttm > 0 else 0

        dol_f = float(dol) if dol and 1.0 <= float(dol) <= 5.0 else 1.5
        avg_rev = min(float(avg_rev_growth), float(rev_latest))
        avg_rev = max(avg_rev, 3.0)  # 最低 3%

        # 1. 前向利润增速 = DOL × 营收增速
        forward_growth = dol_f * avg_rev
        forward_growth = max(5.0, min(forward_growth, 100.0))  # 限制范围

        # 2. 根据 DOL + 营收增速确定 PEG 目标
        if dol_f > 3.0 and avg_rev > 20:
            peg_target = 1.5
            peg_reason = "高DOL+高增长→溢价"
        elif dol_f > 2.0 and avg_rev > 15:
            peg_target = 1.2
            peg_reason = "中高DOL+较好增长→小幅溢价"
        elif dol_f > 1.5:
            peg_target = 1.0
            peg_reason = "正常DOL→中性"
        else:
            peg_target = 0.8
            peg_reason = "低DOL→折价"

        # 利润率修正: 低利润率降低 PEG 目标
        op_margin_f = float(op_margin)
        if op_margin_f < 5:
            peg_target *= 0.85
            peg_reason += " 低利润率折价15%"
        elif op_margin_f > 20:
            peg_target *= 1.1
            peg_reason += " 高利润率溢价10%"

        # 3. Justified PE = PEG_target × forward_growth
        justified_pe = peg_target * forward_growth
        justified_pe = max(8.0, min(justified_pe, 80.0))

        # 4. 目标价
        target_price = eps_ttm * justified_pe
        upside = ((target_price / current_price) - 1) * 100 if current_price > 0 and target_price > 0 else 0

        # 结论
        if upside > 20:
            verdict = f"经营杠杆支撑强 (DOL={dol_f:.1f}), 低估"
        elif upside > 5:
            verdict = f"适度低估 (DOL={dol_f:.1f})"
        elif upside > -10:
            verdict = f"经营杠杆反映在股价中 (DOL={dol_f:.1f})"
        else:
            verdict = f"高估, DOL 尚未转化为利润 ({peg_reason})"

        return {
            "dol_adjusted_pe": round(justified_pe, 2),
            "dol_base_pe": round(pe_ttm, 2),
            "dol_forward_growth_est": round(forward_growth, 1),
            "dol_target_price": round(target_price, 2),
            "dol_upside_pct": round(upside, 1),
            "dol_verdict": verdict,
        }
