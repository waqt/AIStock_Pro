"""PE 估值百分位 — 当前 PE(TTM) 在近 3 年历史中的分位"""
import numpy as np
from app.domain.quant.valuation.base import ValuationMethod, register_valuation


@register_valuation
class PEPercentileMethod(ValuationMethod):
    name = "pe_percentile"
    label = "PE 估值百分位"
    category = "relative"
    description = "计算当前 PE(TTM) 在近 3 年历史序列中的百分位, 判断估值高低"
    output = ["pe_percentile", "pe_median", "pe_min", "pe_max", "pe_status"]
    requires = ["pe_ttm"]
    text_output = ["pe_status"]
    params = {"lookback_years": 3}
    requires_market_data = True

    @classmethod
    def compute(cls, pe_ttm: float = None, pe_history: list = None, **kwargs) -> dict:
        if pe_ttm is None or not pe_history or len(pe_history) < 20:
            return {k: None for k in cls.output}
        arr = np.array(pe_history)
        pct = float(np.sum(arr <= pe_ttm) / len(arr) * 100)
        return {
            "pe_percentile": round(pct, 1),
            "pe_median": round(float(np.median(arr)), 2),
            "pe_min": round(float(arr.min()), 2),
            "pe_max": round(float(arr.max()), 2),
            "pe_status": "高估" if pct > 80 else ("低估" if pct < 20 else "合理"),
        }
