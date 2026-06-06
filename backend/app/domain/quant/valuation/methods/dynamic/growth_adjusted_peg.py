"""成长调整 PEG (Growth-Adjusted PEG Valuation)

核心逻辑:
  传统 PEG = PE/Growth 太单一。引入多因子动态调整 PEG 目标值:
  - 营收加速/减速 → 调整 PEG 目标
  - 毛利率上升/下降 → 调整 PEG 目标
  - 经营杠杆 DOL → 调整 PEG 目标
  - ROE 质量 → 调整 PEG 目标

适用: 有利润的成长公司 (PE>0, EPS 增速>0)
"""
from app.domain.quant.valuation.base import ValuationMethod, register_valuation


@register_valuation
class GrowthAdjustedPEGMethod(ValuationMethod):
    name = "growth_peg"
    label = "成长调整 PEG"
    category = "dynamic"
    description = "多因子动态调整 PEG 目标值(营收趋势/毛利率/经营杠杆/ROE), 比传统 PEG 更精准"
    output = [
        "growth_peg_target", "growth_peg_adjusted_pe",
        "growth_peg_forward_growth",
        "growth_peg_target_price", "growth_peg_upside_pct",
        "growth_adjustment_detail", "growth_peg_verdict",
    ]
    text_output = ["growth_adjustment_detail", "growth_peg_verdict"]
    requires = ["pe_ttm", "eps_growth_3y", "mcap_yi", "total_shares"]
    requires_financial_data = True
    requires_financial_indicators = True

    judgment = "growth_peg_upside_pct>20%→显著低估, >5%→略微低估, >-10%→合理, else→高估。growth_peg_target<0.7→极端打折可能过度悲观; growth_adjustment_detail显示各因子调整明细"
    applicable_scenarios = "有利润(PE>0)且EPS增速>0的成长公司; 适合营收趋势/毛利率/经营杠杆变化敏感的公司"
    limitations = "eps_growth_3y数据缺失时无法计算(需从StockValuation获取); 多因子调整幅度(0.3/0.2)为经验值; 净利润率转换营收增速为利润增速有近似误差"

    _field_labels = {
        "growth_peg_target": "调整后PEG目标",
        "growth_peg_adjusted_pe": "调整后PE(倍)",
        "growth_peg_forward_growth": "前向增速(%)",
        "growth_peg_target_price": "PEG目标价(¥)",
        "growth_peg_upside_pct": "上行空间(%)",
        "growth_adjustment_detail": "调整明细",
        "growth_peg_verdict": "判断结论",
    }

    @classmethod
    def compute(cls, **kwargs) -> dict:
        pe_ttm = kwargs.get("pe_ttm")
        eps_growth = kwargs.get("eps_growth_3y")  # 3年复合EPS增速
        mcap_yi = kwargs.get("mcap_yi")
        total_shares = kwargs.get("total_shares")

        # 动态因子
        avg_rev_growth = kwargs.get("avg_rev_yoy_4q") or 0
        rev_accel = kwargs.get("revenue_acceleration") or "stable"
        gm_trend = kwargs.get("gross_margin_trend") or "stable"
        dol = kwargs.get("operating_leverage")
        roe = kwargs.get("roe") or 0

        if pe_ttm is None or eps_growth is None or not mcap_yi or not total_shares:
            return {k: None for k in cls.output}

        pe_ttm = float(pe_ttm)
        eps_growth = float(eps_growth)
        current_price = (mcap_yi * 1e8) / total_shares if total_shares > 0 else 0
        eps_ttm = current_price / pe_ttm if pe_ttm > 0 else 0

        # 1. Base PEG = 1.0
        base_peg = 1.0
        adjustments = []
        total_adj = 0.0

        # 2. 营收趋势调整
        if rev_accel == "accelerating":
            total_adj += 0.3
            adjustments.append("加速+0.3")
        elif rev_accel == "decelerating":
            total_adj -= 0.2
            adjustments.append("减速-0.2")

        # 3. 毛利率趋势调整
        if gm_trend == "rising":
            total_adj += 0.3
            adjustments.append("毛利上升+0.3")
        elif gm_trend == "declining":
            total_adj -= 0.3
            adjustments.append("毛利下降-0.3")

        # 4. 经营杠杆调整
        dol_f = float(dol) if dol else 1.5
        avg_rev_f = float(avg_rev_growth)
        if dol_f > 3.0 and avg_rev_f > 20:
            total_adj += 0.2
            adjustments.append("高DOL+高增长+0.2")
        elif dol_f < 1.5:
            total_adj -= 0.1
            adjustments.append("低DOL-0.1")

        # 5. ROE 质量调整
        if roe and float(roe) > 15:
            total_adj += 0.2
            adjustments.append(f"高ROE({float(roe):.0f}%)+0.2")

        adjusted_peg = base_peg + total_adj
        adjusted_peg = max(0.4, min(adjusted_peg, 2.5))  # 限制范围

        # 6. 前向增速: 加权平均 EPS 增速和营收增速
        avg_rev_for_growth = min(float(avg_rev_growth), 60.0)
        # 用净利率将营收增速转化为利润增速近似
        net_margin = kwargs.get("net_margin_pct") or 8.0
        margin_ratio = max(0.3, min(float(net_margin) / 15.0, 2.0))
        rev_to_profit_growth = avg_rev_for_growth * margin_ratio
        forward_growth = max(5.0, eps_growth * 0.6 + rev_to_profit_growth * 0.4)

        # 7. Justified PE = PEG × forward_growth
        justified_pe = adjusted_peg * forward_growth
        justified_pe = max(5.0, min(justified_pe, 80.0))

        target_price = eps_ttm * justified_pe
        upside = ((target_price / current_price) - 1) * 100 if current_price > 0 and target_price > 0 else 0

        # 结论
        adj_detail = f"Base PEG=1.0 | " + " | ".join(adjustments) + f" | final={adjusted_peg:.2f}"

        if upside > 20:
            verdict = "成长性超越估值, 显著低估"
        elif upside > 5:
            verdict = "成长支撑估值, 略微低估"
        elif upside > -10:
            verdict = "成长性-估值匹配"
        else:
            verdict = "成长性溢价过高, 高估"

        return {
            "growth_peg_target": round(adjusted_peg, 2),
            "growth_peg_adjusted_pe": round(justified_pe, 2),
            "growth_peg_forward_growth": round(forward_growth, 1),
            "growth_peg_target_price": round(target_price, 2),
            "growth_peg_upside_pct": round(upside, 1),
            "growth_adjustment_detail": adj_detail,
            "growth_peg_verdict": verdict,
        }
