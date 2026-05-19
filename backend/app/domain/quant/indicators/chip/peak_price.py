"""筹码峰值定位 — 识别筹码分布中的主要峰值和多峰状态"""
from ..base import BaseIndicator, register
import numpy as np

@register
class ChipPeakPriceIndicator(BaseIndicator):
    name = "chip_peak_price"
    category = "chip"
    params = {"window": 90, "min_peak_height": 0.05}
    output = ["chip_peaks", "chip_valleys", "chip_is_single_peak"]
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
            return {"chip_peaks": [], "chip_valleys": [], "chip_is_single_peak": False}

        price_bins = 200
        price_min = np.min(low[-w:])
        price_max = np.max(high[-w:])
        if price_max <= price_min:
            return {"chip_peaks": [], "chip_valleys": [], "chip_is_single_peak": True}

        bin_width = (price_max - price_min) / price_bins
        chip = np.zeros(price_bins)
        for i in range(max(0, n - w), n):
            if volume[i] <= 0: continue
            lo = max(0, int((low[i] - price_min) / bin_width))
            hi = min(price_bins - 1, int((high[i] - price_min) / bin_width) + 1)
            if hi <= lo: hi = lo + 1
            mid = int((close[i] - price_min) / bin_width)
            mid = max(lo, min(hi - 1, mid))
            for j in range(lo, hi):
                weight = 1.0 - 0.7 * abs(j - mid) / max(hi - lo, 1)
                chip[j] += volume[i] * max(0, weight)

        if chip.max() <= 0: return {"chip_peaks": [], "chip_valleys": [], "chip_is_single_peak": True}

        chip_norm = chip / chip.max()

        # 简单峰值检测: 比左右邻居都高的点
        peaks = []
        valleys = []
        threshold = cls.params["min_peak_height"]
        for j in range(1, price_bins - 1):
            if chip_norm[j] > threshold and chip_norm[j] > chip_norm[j - 1] and chip_norm[j] >= chip_norm[j + 1]:
                peaks.append(round(float(price_min + j * bin_width), 2))
            if j > 1 and j < price_bins - 2:
                if chip_norm[j] < chip_norm[j - 1] and chip_norm[j] < chip_norm[j + 1] and chip_norm[j] < 0.3:
                    valleys.append(round(float(price_min + j * bin_width), 2))

        # 去重: 合并相邻峰值
        merged_peaks = []
        for p in peaks:
            if not merged_peaks or p - merged_peaks[-1] > (price_max - price_min) * 0.05:
                merged_peaks.append(p)

        is_single = len(merged_peaks) == 1

        return {
            "chip_peaks": merged_peaks[:5],
            "chip_valleys": valleys[:5],
            "chip_is_single_peak": is_single,
        }
