"""三情景估值 — Bull/Base/Bear 情景下的目标价分析

基于当前 EPS 和不同的 PE 倍数假设, 给出三种情景的目标价。
内联实现 scenario_weighted 逻辑，消除对旧 framework/finance/valuation.py 的依赖。
"""
from app.domain.quant.valuation.base import ValuationMethod, register_valuation


@register_valuation
class ScenarioEstimateMethod(ValuationMethod):
    name = "scenario_estimate"
    label = "三情景估值"
    category = "advanced"
    description = "基于 EPS 和 PE 倍数区间, 构建牛市/基准/熊市三情景估值, 输出概率加权目标价和非对称性"
    output = ["bull_target", "base_target", "bear_target", "weighted_target",
              "upside_pct", "downside_pct", "asymmetry"]
    requires = ["pe_ttm", "mcap_yi", "total_shares"]
    judgment = "asymmetry = bull_target/bear_target - 1, 正值越大上行空间越大。base_target 是中性情景下的合理价值。asymmetry>2→上行远大于下行风险"
    applicable_scenarios = "适用于不确定性高的成长股/周期股/事件驱动型公司; 有明确EPS预测但市场观点分歧大的公司"
    limitations = "三情景EPS和PE为估算值, 依赖分析师判断精度; 概率权重主观(默认悲观25%/中性50%/乐观25%); 不适用于无法预测EPS的亏损公司"

    @classmethod
    def compute(cls, pe_ttm: float = None, mcap_yi: float = None,
                total_shares: float = None, **kwargs) -> dict:
        if pe_ttm is None or mcap_yi is None or not total_shares or total_shares <= 0:
            return {k: None for k in cls.output}

        # 计算 EPS
        price = (mcap_yi * 1e8) / total_shares
        if price <= 0:
            return {k: None for k in cls.output}
        eps = price / pe_ttm

        # 默认情景假设 (可通过 params 覆盖)
        bull_pe = pe_ttm * 1.3       # 牛市: PE 扩张 30%
        base_pe = pe_ttm * 1.0       # 基准: PE 不变
        bear_pe = pe_ttm * 0.7       # 熊市: PE 收缩 30%

        bull = eps * bull_pe
        base = eps * base_pe
        bear = eps * bear_pe

        # 情景概率加权 (原 scenario_weighted 内联)
        p_bull = 0.2
        p_base = 0.6
        p_bear = 0.2
        weighted = bull * p_bull + base * p_base + bear * p_bear
        upside = (bull - weighted) / weighted * 100 if weighted else 0
        downside = (bear - weighted) / weighted * 100 if weighted else 0
        asymmetry_ratio = abs(upside / downside) if (downside and downside < 0) else (99 if upside > 0 else 1)
        asymmetry_label = "强非对称" if asymmetry_ratio > 2 else ("对称" if asymmetry_ratio > 0.5 else "负非对称")

        return {
            "bull_target": round(bull, 2),
            "base_target": round(base, 2),
            "bear_target": round(bear, 2),
            "weighted_target": round(weighted, 2),
            "upside_pct": round(upside, 1),
            "downside_pct": round(downside, 1),
            "asymmetry": asymmetry_label,
        }
