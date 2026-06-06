"""三阶段增长估值 (Three-Stage Growth Valuation)

核心逻辑:
  经典三阶段 DCF 变种, 专门为成长公司设计:
  Stage 1 (高增期, 3年): 按当前营收增速增长, 利润率逐年改善
  Stage 2 (过渡期, 5年): 增速线性衰减至行业终端增速
  Stage 3 (成熟期): 永续增长, 终端价值

  所有 FCF + TV 折现 → 每股内在价值。

适用: 高成长公司(营收增速>15%), 处于规模扩张中期
"""
from app.domain.quant.valuation.base import ValuationMethod, register_valuation


@register_valuation
class ThreeStageGrowthMethod(ValuationMethod):
    name = "three_stage_growth"
    label = "三阶段增长估值"
    category = "dynamic"
    description = "经典三阶段 DCF: 高增(3年)→过渡(5年)→成熟永续, 适用于营收增速>15%的成长公司"
    output = [
        "three_stage_value", "three_stage_upside_pct",
        "three_stage_terminal_fcf", "three_stage_assumed_wacc",
        "three_stage_phase1_years", "three_stage_margin_target",
        "three_stage_implied_pe", "three_stage_verdict",
    ]
    text_output = ["three_stage_verdict"]
    requires = ["mcap_yi", "total_shares"]
    requires_financial_data = True
    requires_financial_indicators = True

    _field_labels = {
        "three_stage_value": "三阶段价值(¥)",
        "three_stage_upside_pct": "上行空间(%)",
        "three_stage_terminal_fcf": "终端FCF(亿元)",
        "three_stage_assumed_wacc": "折现率(%)",
        "three_stage_phase1_years": "高增阶段(年)",
        "three_stage_margin_target": "目标利润率(%)",
        "three_stage_implied_pe": "隐含 PE(倍)",
        "three_stage_verdict": "判断结论",
    }

    @classmethod
    def compute(cls, **kwargs) -> dict:
        rev_ttm_yi = kwargs.get("revenue_4q_yi")
        rev_growth = kwargs.get("rev_yoy_ttm") or kwargs.get("avg_rev_yoy_4q")
        op_margin = kwargs.get("operating_margin_pct") or kwargs.get("net_margin_pct") or 5.0
        mcap_yi = kwargs.get("mcap_yi")
        total_shares = kwargs.get("total_shares")
        gm_pct = kwargs.get("gross_margin_pct") or 30.0

        if not rev_ttm_yi or not rev_growth or not mcap_yi or not total_shares:
            return {k: None for k in cls.output}

        rev_growth = float(rev_growth)
        rev_growth = max(5.0, min(rev_growth, 80.0))
        op_margin = float(op_margin)

        # 参数
        p1_years = 3      # 高增期
        p2_years = 5      # 过渡期
        terminal_growth = 3.0
        wacc = 9.0
        tax_rate = 0.25
        reinvest_rate = 0.30  # 再投资率(营收增量资本密集度)

        # 利润率目标: 趋向行业均值 12%
        current_margin = op_margin / 100.0
        target_margin = max(current_margin, 0.12)

        current_rev = float(rev_ttm_yi)

        # Stage 1: 高增期
        p1_fcf = []
        for yr in range(p1_years):
            decay = yr / p1_years
            yr_growth = rev_growth * (1 - decay * 0.35)  # 线性衰减35%
            next_rev = current_rev * (1 + yr_growth / 100.0)
            rev_inc = next_rev - current_rev

            # 利润率线性改善
            margin_improve = (target_margin - current_margin) * ((yr + 1) / p1_years)
            yr_margin = current_margin + margin_improve
            yr_ebit = next_rev * yr_margin
            yr_fcf = yr_ebit * (1 - tax_rate) - rev_inc * reinvest_rate
            pv = yr_fcf / ((1 + wacc / 100.0) ** (yr + 1))
            p1_fcf.append(pv)
            current_rev = next_rev

        # Stage 2: 过渡期
        p2_start_growth_rate = rev_growth * (1 - 0.35)  # 前期末的增速
        p2_fcf = []
        for yr in range(p2_years):
            t = yr + 1
            # 增速从 p2_start_growth_rate 线性衰减至 terminal_growth
            yr_growth = p2_start_growth_rate + (terminal_growth - p2_start_growth_rate) * ((yr + 1) / p2_years)
            next_rev = current_rev * (1 + yr_growth / 100.0)
            rev_inc = next_rev - current_rev

            yr_margin = target_margin
            yr_ebit = next_rev * yr_margin
            yr_fcf = yr_ebit * (1 - tax_rate) - rev_inc * reinvest_rate
            pv = yr_fcf / ((1 + wacc / 100.0) ** (p1_years + t))
            p2_fcf.append(pv)
            current_rev = next_rev

        # Stage 3: 终端价值
        terminal_rev = current_rev * (1 + terminal_growth / 100.0)
        terminal_ebit = terminal_rev * target_margin
        terminal_fcf = terminal_ebit * (1 - tax_rate)
        tv = terminal_fcf / ((wacc - terminal_growth) / 100.0)
        pv_tv = tv / ((1 + wacc / 100.0) ** (p1_years + p2_years))

        # 内在价值
        total_fcf_pv = sum(p1_fcf) + sum(p2_fcf) + pv_tv

        # 加现金减负债的简化: 用净资产近似
        total_equity = kwargs.get("total_equity")
        cash = kwargs.get("cash")
        if total_equity:
            equity_value = total_fcf_pv + float(cash or 0) * 0.5 / 1e8
        else:
            equity_value = total_fcf_pv

        per_share_value = (equity_value * 1e8) / total_shares if total_shares > 0 else 0
        current_price = (mcap_yi * 1e8) / total_shares if total_shares > 0 else 0

        upside = ((per_share_value / current_price) - 1) * 100 if current_price > 0 else 0

        # 隐含 PE
        implied_pe = 0
        if per_share_value > 0 and current_price > 0 and mcap_yi > 0:
            implied_eps = (op_margin * rev_ttm_yi * (1 - tax_rate) * 1e8) / total_shares / 1e8 if total_shares > 0 else 0
            implied_eps_actual = implied_eps * 1e8 if rev_ttm_yi > 0 else 0
            pe_ttm_val = kwargs.get("pe_ttm")
            if current_price > 0 and pe_ttm_val:
                implied_pe = per_share_value / (current_price / pe_ttm_val) if (current_price / pe_ttm_val) > 0 else 0

        if upside > 20:
            verdict = "低估, 三阶段增长折现价值显著高于市价"
        elif upside > 5:
            verdict = "略低估, 成长性未完全定价"
        elif upside > -10:
            verdict = "合理, 成长性已反映在价格中"
        else:
            verdict = "高估, 当前价格已透支未来增长"

        return {
            "three_stage_value": round(per_share_value, 2),
            "three_stage_upside_pct": round(upside, 1),
            "three_stage_terminal_fcf": round(terminal_fcf, 2),
            "three_stage_assumed_wacc": wacc,
            "three_stage_phase1_years": p1_years,
            "three_stage_margin_target": round(target_margin * 100, 1),
            "three_stage_implied_pe": round(implied_pe, 2) if implied_pe else None,
            "three_stage_verdict": verdict,
        }
