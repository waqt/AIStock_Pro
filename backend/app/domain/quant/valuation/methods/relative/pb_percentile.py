"""PB 估值百分位 — 当前 PB 在近 3 年历史中的分位"""
import numpy as np
from app.domain.quant.valuation.base import ValuationMethod, register_valuation


@register_valuation
class PBPercentileMethod(ValuationMethod):
    name = "pb_percentile"
    label = "PB 估值百分位"
    category = "relative"
    description = "计算当前 PB 在近 3 年历史序列中的百分位, 判断市净率高低"
    output = ["pb_percentile", "pb_median", "pb_min", "pb_max", "pb_status"]
    requires = ["pb"]
    text_output = ["pb_status"]
    params = {"lookback_years": 3}
    requires_market_data = True

    @classmethod
    def compute(cls, pb: float = None, pb_history: list = None, **kwargs) -> dict:
        if pb is None or not pb_history or len(pb_history) < 20:
            return {k: None for k in cls.output}
        arr = np.array(pb_history)
        pct = float(np.sum(arr <= pb) / len(arr) * 100)
        return {
            "pb_percentile": round(pct, 1),
            "pb_median": round(float(np.median(arr)), 2),
            "pb_min": round(float(arr.min()), 2),
            "pb_max": round(float(arr.max()), 2),
            "pb_status": "高估" if pct > 80 else ("低估" if pct < 20 else "合理"),
        }
