"""三情景估值 — Bull/Base/Bear 情景下的目标价分析

基于当前 EPS 和不同的 PE 倍数假设, 给出三种情景的目标价。
调用 framework/finance/valuation.py 的 scenario_weighted 函数。
"""
from app.domain.quant.valuation.base import ValuationMethod, register_valuation
from app.framework.finance.valuation import scenario_weighted


@register_valuation
class ScenarioEstimateMethod(ValuationMethod):
    name = "scenario_estimate"
    label = "三情景估值"
    category = "advanced"
    description = "基于 EPS 和 PE 倍数区间, 构建牛市/基准/熊市三情景估值, 输出概率加权目标价和非对称性"
    output = ["bull_target", "base_target", "bear_target", "weighted_target",
              "upside_pct", "downside_pct", "asymmetry"]
    requires = ["pe_ttm", "mcap_yi", "total_shares"]

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

        scenario = scenario_weighted(bull, base, bear)

        return {
            "bull_target": round(bull, 2),
            "base_target": round(base, 2),
            "bear_target": round(bear, 2),
            "weighted_target": scenario["weighted_price"],
            "upside_pct": scenario["upside_pct"],
            "downside_pct": scenario["downside_pct"],
            "asymmetry": scenario["asymmetry"],
        }
