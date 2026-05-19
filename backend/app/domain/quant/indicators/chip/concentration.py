"""筹码集中度 — 成本分布峰值的筹码占比"""
from ..base import BaseIndicator, register
import numpy as np

@register
class ChipConcentrationIndicator(BaseIndicator):
    name = "chip_concentration"
    category = "chip"
    params = {"window": 90, "peak_band_pct": 10}
    output = ["chip_concentration", "chip_peak_price", "chip_avg_cost"]
    requires = ["high", "low", "close", "volume"]

    @classmethod
    def compute(cls, df):
        w = cls.params["window"]
        close = df["close"].values
        high = df["high"].values
        low = df["low"].values
        volume = df["volume"].values
        n = len(df)
        if n < w:
            return {"chip_concentration": None, "chip_peak_price": None, "chip_avg_cost": None}

        # COST算法: 模拟筹码分布
        # 对每日, 将成交量分配在 [low, high] 区间
        price_bins = 200
        price_min = np.min(low[-w:])
        price_max = np.max(high[-w:])
        if price_max <= price_min:
            return {"chip_concentration": 0.0, "chip_peak_price": close[-1], "chip_avg_cost": close[-1]}

        bin_width = (price_max - price_min) / price_bins
        chip = np.zeros(price_bins)

        for i in range(max(0, n - w), n):
            if volume[i] <= 0:
                continue
            # 将当日成交量分布到 [low, high] (简化: 三角分布, 峰值在close)
            lo = max(0, int((low[i] - price_min) / bin_width))
            hi = min(price_bins - 1, int((high[i] - price_min) / bin_width) + 1)
            if hi <= lo:
                hi = lo + 1
            # 三角分布: close处权重最高
            mid = int((close[i] - price_min) / bin_width)
            mid = max(lo, min(hi - 1, mid))
            for j in range(lo, hi):
                weight = 1.0 - 0.7 * abs(j - mid) / max(hi - lo, 1)
                chip[j] += volume[i] * max(0, weight)

        if chip.sum() <= 0:
            return {"chip_concentration": 0.0, "chip_peak_price": close[-1], "chip_avg_cost": close[-1]}

        # 筹码集中度: 最高峰附近±5% 范围内的筹码占比
        peak_idx = np.argmax(chip)
        band = int(price_bins * cls.params["peak_band_pct"] / 100)
        band_lo = max(0, peak_idx - band)
        band_hi = min(price_bins, peak_idx + band + 1)
        concentration = float(chip[band_lo:band_hi].sum() / chip.sum() * 100)

        # 峰值价格
        peak_price = float(price_min + peak_idx * bin_width)

        # 平均成本
        bin_centers = np.array([price_min + (j + 0.5) * bin_width for j in range(price_bins)])
        avg_cost = float(np.average(bin_centers, weights=chip)) if chip.sum() > 0 else float(close[-1])

        return {
            "chip_concentration": round(concentration, 2),
            "chip_peak_price": round(peak_price, 2),
            "chip_avg_cost": round(avg_cost, 2),
        }
