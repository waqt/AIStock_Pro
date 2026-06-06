"""营收增长框架估值 (Revenue Growth Framework Valuation)

核心逻辑:
  成长公司估值的核心——营收增长轨迹 + 利润率演变路径。
  利用 operating_leverage 将营收增长映射为 EBIT 增长,
  做简化 DCF 折现后与当前市值对比。

  升级(V3): CCF 连续折现模式 (e^{-rt}) + 动态 WACC (高增期/终端分阶段)

适用: 营收增速>10% 的成长型公司, 有利润或即将盈利
"""
import math
from app.domain.quant.valuation.base import ValuationMethod, register_valuation


@register_valuation
class RevenueGrowthFrameworkMethod(ValuationMethod):
    name = "rev_growth_framework"
    label = "营收增长框架估值"
    category = "dynamic"
    description = "基于营收增长轨迹 + 经营杠杆 + 利润率改善路径的简化DCF估值, 适合成长型公司"
    output = [
        "rgv_target_price", "rgv_upside_pct", "rgv_fair_value_yi",
        "rgv_phase1_years", "rgv_phase1_growth", "rgv_terminal_growth",
        "rgv_assumed_wacc", "rgv_verdict",
    ]
    text_output = ["rgv_verdict"]
    requires = ["mcap_yi", "total_shares"]
    requires_financial_data = True
    requires_financial_indicators = True
    params = {
        "use_continuous_compounding": False,
        "wacc_phase1": 10.0,
        "wacc_terminal": 8.0,
    }

    judgment = "rgv_upside_pct>20%→显著低估, >5%→略微低估, >-5%→合理, >-20%→略微高估, else→显著高估。营收增速>30%时框架更可靠"
    applicable_scenarios = "营收增速>10%的成长型公司, 有利润或即将盈利; 适合科技/医药/消费等规模效应强的行业"
    limitations = "假设条件较多(增速衰减路径/利润改善节奏/WACC), 营收增速剧烈波动时误差大; 不适用于亏损恶化阶段的公司"

    _field_labels = {
        "rgv_target_price": "框架目标价(¥)",
        "rgv_upside_pct": "上行空间(%)",
        "rgv_fair_value_yi": "公允价值(亿元)",
        "rgv_phase1_years": "高增阶段(年)",
        "rgv_phase1_growth": "高增阶段增速(%)",
        "rgv_terminal_growth": "终值增速(%)",
        "rgv_assumed_wacc": "终端折现率(%)",
        "rgv_verdict": "判断结论",
    }

    @classmethod
    def _discount_factor(cls, t_years: float, r_pct: float, use_ccf: bool) -> float:
        """折现因子

        Args:
            t_years: 折现年数
            r_pct: 折现率(%)
            use_ccf: True=连续复利 e^{-rt}, False=离散 1/(1+r)^t
        """
        r = r_pct / 100.0
        if use_ccf:
            r_cont = math.log(1.0 + r)
            return math.exp(-r_cont * t_years)
        else:
            return 1.0 / ((1.0 + r) ** t_years)

    @classmethod
    def compute(cls, **kwargs) -> dict:
        rev_growth = kwargs.get("rev_yoy_ttm") or kwargs.get("avg_rev_yoy_4q")
        op_margin = kwargs.get("operating_margin_pct") or 8.0
        dol = kwargs.get("operating_leverage")
        rev_ttm_yi = kwargs.get("revenue_4q_yi")
        mcap_yi = kwargs.get("mcap_yi")
        total_shares = kwargs.get("total_shares")
        gm_pct = kwargs.get("gross_margin_pct") or 30.0

        # 数据不足时返回 None
        if not rev_growth or not rev_ttm_yi or not mcap_yi or not total_shares:
            return {k: None for k in cls.output}

        # 保守取增速 (min of latest vs avg)
        rev_latest = kwargs.get("rev_yoy_latest")
        growth_rate = min(float(rev_growth), float(rev_latest or rev_growth))
        growth_rate = max(growth_rate, 5.0)  # 最低 5%
        growth_rate = min(growth_rate, 80.0)  # 封顶 80%

        # 参数设定
        phase1_years = 3
        terminal_growth = 3.0
        tax_rate = 0.25
        reinvest_pct = 0.35  # 营收增量的再投资比例

        # ★ CCF 连续折现模式
        use_ccf = bool(kwargs.get("use_continuous_compounding", False))

        # ★ 动态 WACC: 高增期 vs 终端
        wacc_p1 = float(kwargs.get("wacc_phase1", 10.0))
        wacc_term = float(kwargs.get("wacc_terminal", 8.0))
        single_wacc = kwargs.get("wacc")
        if single_wacc is not None:
            wacc_p1 = wacc_term = float(single_wacc)

        # 经营杠杆调整: DOL 将营收增速映射到 EBIT 增速
        eff_dol = float(dol) if dol and 1.0 <= float(dol) <= 5.0 else 1.5

        # 逐年计算 FCF
        cum_fcf = 0.0
        current_rev = float(rev_ttm_yi)
        current_op_margin = float(op_margin) / 100.0

        # 利润率改善: 从当前向目标(12%)线性过渡
        target_op_margin = max(current_op_margin, 0.12)
        margin_step = (target_op_margin - current_op_margin) / phase1_years if phase1_years > 0 else 0

        for yr in range(1, phase1_years + 1):
            decay = yr / phase1_years
            yr_growth = growth_rate * (1 - decay * 0.5)  # 线性衰减
            next_rev = current_rev * (1 + yr_growth / 100.0)
            rev_increment = next_rev - current_rev

            # 利润率线性改善
            yr_margin = current_op_margin + margin_step * yr
            yr_ebit = next_rev * yr_margin
            yr_fcf = yr_ebit * (1 - tax_rate) - rev_increment * reinvest_pct

            # FCF 折现 (高增期用 wacc_p1)
            cum_fcf += yr_fcf * cls._discount_factor(yr, wacc_p1, use_ccf)
            current_rev = next_rev

        # 终端价值 (第4年起的永续, 用 wacc_term)
        terminal_rev = current_rev * (1 + terminal_growth / 100.0)
        terminal_op_margin = target_op_margin
        terminal_ebit = terminal_rev * terminal_op_margin
        terminal_fcf = terminal_ebit * (1 - tax_rate)
        terminal_value = terminal_fcf / ((wacc_term - terminal_growth) / 100.0)
        # TV 折现: 先折过 phase1_years (用 wacc_p1), 因 TV 在第 phase1_years+1 年
        pv_tv = terminal_value * cls._discount_factor(phase1_years, wacc_p1, use_ccf)

        fair_value_yi = cum_fcf + pv_tv
        current_value_yi = float(mcap_yi)

        upsides = []
        if current_value_yi > 0:
            upsides.append((fair_value_yi / current_value_yi - 1) * 100)

        avg_upside = sum(upsides) / len(upsides) if upsides else 0.0
        target_price = 0.0
        if total_shares > 0 and current_value_yi > 0:
            current_price = (current_value_yi * 1e8) / total_shares
            target_price = round(current_price * (1 + avg_upside / 100.0), 2)

        # 判断结论
        if avg_upside > 20:
            verdict = "显著低估"
        elif avg_upside > 5:
            verdict = "略微低估"
        elif avg_upside > -5:
            verdict = "合理"
        elif avg_upside > -20:
            verdict = "略微高估"
        else:
            verdict = "显著高估"

        return {
            "rgv_target_price": round(target_price, 2),
            "rgv_upside_pct": round(avg_upside, 1),
            "rgv_fair_value_yi": round(fair_value_yi, 2),
            "rgv_phase1_years": phase1_years,
            "rgv_phase1_growth": round(growth_rate, 1),
            "rgv_terminal_growth": terminal_growth,
            "rgv_assumed_wacc": wacc_term,
            "rgv_verdict": verdict,
        }
