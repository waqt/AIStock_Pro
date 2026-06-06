"""PEG 分析 — PE / EPS 增长率, 衡量估值与成长匹配度"""
from app.domain.quant.valuation.base import ValuationMethod, register_valuation


@register_valuation
class PEGAnalysisMethod(ValuationMethod):
    name = "peg_analysis"
    label = "PEG 分析"
    category = "relative"
    description = "PEG = PE(TTM) / EPS 近 3 年复合增速。PEG<1 低估, 1-2 合理, >2 泡沫"
    output = ["peg_ratio", "peg_verdict"]
    requires = ["pe_ttm", "eps_growth_3y"]
    text_output = ["peg_verdict"]
    judgment = "peg_ratio<1→可能低估, 1-2→合理, >2→可能高估。peg_ratio<0.5→显著低估, >3→显著高估。PEG结合growth_quality使用更可靠"
    applicable_scenarios = "适用于有利润且EPS增速稳定的成长公司; 适合消费/科技/医药等持续增长行业"
    limitations = "eps_growth_3y缺失时无法计算; 增速剧烈波动的公司PEG失真; 未区分内生增长和并购增长"

    @classmethod
    def compute(cls, pe_ttm: float = None, eps_growth_3y: float = None, **kwargs) -> dict:
        if pe_ttm is None or pe_ttm <= 0:
            return {"peg_ratio": None, "peg_verdict": None}
        if eps_growth_3y is None or eps_growth_3y <= 0:
            return {"peg_ratio": None, "peg_verdict": "增速不足, PEG 不适用"}

        peg = pe_ttm / eps_growth_3y
        if peg < 1:
            verdict = "低估"
        elif peg <= 2:
            verdict = "合理"
        else:
            verdict = "泡沫"

        return {"peg_ratio": round(peg, 2), "peg_verdict": verdict}
