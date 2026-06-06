"""剪刀差转折点估值 (Scissor Gap Inflection Valuation)

核心逻辑:
  利润增速 - 营收增速 = 剪刀差, 反映盈利质量拐点。
  - 剪刀差为正 + expanding → 进入盈利收获期 → PE 重估溢价
  - 剪刀差从负转正 → 盈利拐点 → PE 上调
  - 剪刀差为负 + 营收减速 → 双弱 → PE 折价

适用: 处于盈利转折点的成长公司, 互联网/科技/医药等先投入后收获的行业
"""
from app.domain.quant.valuation.base import ValuationMethod, register_valuation


@register_valuation
class ScissorGapInflectionMethod(ValuationMethod):
    name = "scissor_inflection"
    label = "剪刀差转折点估值"
    category = "dynamic"
    description = "利用利润增速-营收增速的剪刀差判断盈利阶段, 动态调整目标 PE 倍数"
    output = [
        "scissor_phase_label", "scissor_phase_score",
        "scissor_target_pe", "scissor_target_price",
        "scissor_upside_pct", "scissor_re_rating_pct", "scissor_verdict",
    ]
    text_output = ["scissor_phase_label", "scissor_verdict"]
    requires = ["pe_ttm", "mcap_yi", "total_shares"]
    requires_financial_data = True
    requires_financial_indicators = True

    judgment = "scissor_re_rating_pct≥15→盈利改善阶段PE有望重估, ≥5→关注拐点, ≥-5→PE维持, else→PE下行风险。scissor_phase_score>70→盈利质量拐点已确认"
    applicable_scenarios = "处于盈利拐点附近的成长公司; 互联网/科技/医药等先投入后收获模式; 利润增速从负转正阶段"
    limitations = "依赖财务指标剪刀差数据的及时性; 仅调整PE倍数未纳入FCF折现; 营收和利润增速不同的会计处理可能导致误判"

    _field_labels = {
        "scissor_phase_label": "剪刀差阶段",
        "scissor_phase_score": "阶段评分(0-100)",
        "scissor_target_pe": "目标 PE(倍)",
        "scissor_target_price": "转折目标价(¥)",
        "scissor_upside_pct": "上行空间(%)",
        "scissor_re_rating_pct": "PE 重估幅度(%)",
        "scissor_verdict": "判断结论",
    }

    @classmethod
    def compute(cls, **kwargs) -> dict:
        pe_ttm = kwargs.get("pe_ttm")
        mcap_yi = kwargs.get("mcap_yi")
        total_shares = kwargs.get("total_shares")
        scissor_gap = kwargs.get("scissor_gap")  # 百分点
        is_expanding = kwargs.get("scissor_is_expanding")
        rev_accel = kwargs.get("revenue_acceleration") or "stable"
        op_margin = kwargs.get("operating_margin_pct") or 0

        if pe_ttm is None or not mcap_yi or not total_shares:
            return {k: None for k in cls.output}

        pe_ttm = float(pe_ttm)
        current_price = (mcap_yi * 1e8) / total_shares if total_shares > 0 else 0
        eps_ttm = current_price / pe_ttm if pe_ttm > 0 else 0

        # 判定阶段
        gap = float(scissor_gap) if scissor_gap is not None else 0
        expanding = str(is_expanding).lower() == "true" if is_expanding else False
        accelerating = rev_accel == "accelerating"
        decelerating = rev_accel == "decelerating"

        # 评分和 PE 调整
        if gap > 3 and expanding:
            # 盈利改善: 利润增长持续快于营收
            phase_label = "盈利改善 (Harvest)"
            phase_score = 85
            pe_adjust_pct = 20  # +20%
        elif gap > 0 and not expanding:
            # 盈利拐点: 剪刀差刚转正
            phase_label = "盈利拐点 (Inflection)"
            phase_score = 70
            pe_adjust_pct = 10  # +10%
        elif gap < -3 and accelerating:
            # 投入扩张: 利润增速低于营收(在投入), 但营收加速增长
            phase_label = "投入扩张 (Invest)"
            phase_score = 50
            pe_adjust_pct = 0  # 维持
        elif gap < -3 and decelerating:
            # 双弱: 利润减速 + 营收减速
            phase_label = "双弱 (Weak)"
            phase_score = 25
            pe_adjust_pct = -15  # -15%
        elif gap < 0:
            phase_label = "盈利承压 (Pressure)"
            phase_score = 35
            pe_adjust_pct = -5
        else:
            phase_label = "平稳 (Stable)"
            phase_score = 60
            pe_adjust_pct = 0

        # 利润率修正: 利润率太低的公司 PE 要打折
        op_margin_f = float(op_margin)
        margin_discount = 0
        if op_margin_f < 5:
            margin_discount = -10
        elif 5 <= op_margin_f < 10:
            margin_discount = -5

        total_adjust = pe_adjust_pct + margin_discount
        target_pe = pe_ttm * (1 + total_adjust / 100.0)
        target_pe = max(5.0, target_pe)

        target_price = eps_ttm * target_pe
        upside = ((target_price / current_price) - 1) * 100 if current_price > 0 and target_price > 0 else 0

        # 结论
        if total_adjust >= 15:
            verdict = "盈利质量改善中, PE 有望重估"
        elif total_adjust >= 5:
            verdict = "盈利拐点出现, 关注 PE 修复"
        elif total_adjust >= -5:
            verdict = "剪刀差平稳, PE 维持"
        else:
            verdict = "盈利承压, PE 有下行风险"

        return {
            "scissor_phase_label": phase_label,
            "scissor_phase_score": round(phase_score, 0),
            "scissor_target_pe": round(target_pe, 2),
            "scissor_target_price": round(target_price, 2),
            "scissor_upside_pct": round(upside, 1),
            "scissor_re_rating_pct": round(float(total_adjust), 1),
            "scissor_verdict": verdict,
        }
