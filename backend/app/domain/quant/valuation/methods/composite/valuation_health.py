"""估值健康评分 — 综合多个估值方法的合成指标

汇总全部估值维度的结论, 输出 0-100 综合评分 + 文字 verdict。
"""
from app.domain.quant.valuation.base import ValuationMethod, register_valuation


@register_valuation
class ValuationHealthMethod(ValuationMethod):
    name = "valuation_health"
    label = "估值健康评分"
    category = "composite"
    description = "综合 PE/PB/PS 百分位、PEG、FCF Yield、格雷厄姆数等多维度得出 0-100 估值健康评分"
    output = ["valuation_score", "valuation_verdict", "valuation_summary"]
    text_output = ["valuation_verdict", "valuation_summary"]

    # 依赖所有其他方法的输出
    requires = ["pe_percentile", "pb_percentile", "peg_ratio"]
    judgment = "valuation_score<30→低估(绿色), 30-60→合理(黄色), >60→高估(红色)。valuation_verdict 提供文字结论。各维度(PE/PB/PS/PEG/FCF)得分详情见valuation_summary"
    applicable_scenarios = "适用于有完整估值数据覆盖的公司(PE/PB/PS/PEG/FCF等维度齐全); 作为快速估值体检工具使用"
    limitations = "数据维度越多评分越准确; 某些维度数据缺失时评分可能片面; 综合加权平均可能平滑掉局部极端信号; 建议结合具体维度明细而非仅看总分"

    @classmethod
    def compute(cls, **kwargs) -> dict:
        scores = []

        # 1. PE 百分位评分 (0-100, 20-80 分位内得分高)
        pe_pct = kwargs.get("pe_percentile")
        if pe_pct is not None:
            if 30 <= pe_pct <= 70:
                scores.append(80)
            elif 20 <= pe_pct <= 80:
                scores.append(60)
            elif pe_pct < 20 or pe_pct > 80:
                scores.append(30)

        # 2. PB 百分位评分
        pb_pct = kwargs.get("pb_percentile")
        if pb_pct is not None:
            if 30 <= pb_pct <= 70:
                scores.append(80)
            elif 20 <= pb_pct <= 80:
                scores.append(60)
            else:
                scores.append(30)

        # 3. PEG 评分
        peg = kwargs.get("peg_ratio")
        if peg is not None:
            if peg < 1:
                scores.append(85)
            elif peg <= 2:
                scores.append(60)
            else:
                scores.append(25)

        # 4. FCF Yield 评分
        fcf = kwargs.get("fcf_yield_pct")
        if fcf is not None:
            if fcf > 5:
                scores.append(85)
            elif fcf > 3:
                scores.append(65)
            elif fcf > 0:
                scores.append(45)
            else:
                scores.append(20)

        # 5. 格雷厄姆安全边际
        safety = kwargs.get("safety_margin_pct")
        if safety is not None:
            if safety > 30:
                scores.append(90)
            elif safety > 10:
                scores.append(70)
            elif safety > 0:
                scores.append(55)
            else:
                scores.append(25)

        # 6. 三情景非对称性
        asymmetry = kwargs.get("asymmetry")
        if asymmetry is not None:
            if "强非对称" in str(asymmetry):
                scores.append(80)
            elif "对称" in str(asymmetry):
                scores.append(50)
            else:
                scores.append(30)

        if not scores:
            return {"valuation_score": None, "valuation_verdict": None,
                    "valuation_summary": "数据不足, 无法评分"}

        score = sum(scores) / len(scores)

        if score >= 75:
            verdict = "低估"
            summary = "多个估值维度表明当前价格低于内在价值"
        elif score >= 55:
            verdict = "合理"
            summary = "估值与内在价值基本匹配"
        elif score >= 35:
            verdict = "合理偏贵"
            summary = "部分估值维度显示溢价, 需关注成长性能否支撑"
        else:
            verdict = "高估"
            summary = "多个估值维度均显示显著溢价, 安全边际不足"

        return {
            "valuation_score": round(score, 0),
            "valuation_verdict": verdict,
            "valuation_summary": summary,
        }
