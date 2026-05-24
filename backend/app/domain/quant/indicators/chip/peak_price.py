"""筹码峰值定位 — COST算法 + numba加速 (经通达信对比验证)"""
from ..base import BaseIndicator, register
import numpy as np
import pandas as pd
from numba import jit

# 复用 concentration 的 numba COST 函数
from .concentration import _cost_chip

@jit(nopython=True, cache=True)
def _peak_detect(chip_norm, p_min, bw, threshold, bins, p_max):
    """numba加速: 从归一化分布检测峰值和谷值"""
    peaks = []
    valleys = []
    for j in range(1, bins - 1):
        if chip_norm[j] > threshold and chip_norm[j] > chip_norm[j-1] and chip_norm[j] >= chip_norm[j+1]:
            peaks.append(float(p_min + j * bw))
        if j > 1 and j < bins - 2:
            if chip_norm[j] < chip_norm[j-1] and chip_norm[j] < chip_norm[j+1] and chip_norm[j] < 0.3:
                valleys.append(float(p_min + j * bw))
    # 合并去重
    merged = []
    for p in peaks:
        if not merged or p - merged[-1] > (p_max - p_min) * 0.05:
            merged.append(p)
    return merged, valleys


@register
class ChipPeakPriceIndicator(BaseIndicator):
    name = "chip_peak_detect"
    label = "筹码峰值定位"
    category = "chip"
    params = {"window": 0, "decay_half": 45, "min_peak_height": 0.05, "bins": 400}
    output = ["chip_peaks", "chip_valleys", "chip_is_single_peak"]
    requires = ["high", "low", "close", "volume"]

    @classmethod
    def compute(cls, df):
        w = cls.params["window"]
        bins = cls.params["bins"]
        hl = cls.params["decay_half"]
        threshold = cls.params["min_peak_height"]
        close = df["close"].values.astype(np.float64)
        high = df["high"].values.astype(np.float64)
        low = df["low"].values.astype(np.float64)
        volume = df["volume"].values.astype(np.float64)
        n = len(df)
        decay = np.float64(0.5 ** (1.0 / hl))

        peaks_series = pd.Series([[] for _ in range(n)], index=df.index, dtype=object)
        valleys_series = pd.Series([[] for _ in range(n)], index=df.index, dtype=object)
        is_single_series = pd.Series(False, index=df.index, dtype=bool)

        if n < w:
            return {"chip_peaks": peaks_series, "chip_valleys": valleys_series, "chip_is_single_peak": is_single_series}

        for i in range(max(w, 60), n):
            if w > 0:
                lo_w = low[i-w:i]; hi_w = high[i-w:i]; cl_w = close[i-w:i]; vol_w = volume[i-w:i]; actual_w = w
            else:
                lo_w = low[0:i]; hi_w = high[0:i]; cl_w = close[0:i]; vol_w = volume[0:i]; actual_w = i

            p_min = float(np.min(lo_w))
            p_max = float(np.max(hi_w))
            cur = float(cl_w[-1])
            if cur > p_max: p_max = cur
            if cur < p_min: p_min = cur
            if p_max <= p_min:
                is_single_series.iloc[i] = True
                continue

            margin = (p_max - p_min) * 0.05
            p_min -= margin; p_max += margin
            bw = (p_max - p_min) / bins

            chip = _cost_chip(cl_w, hi_w, lo_w, vol_w, p_min, p_max, bins, decay, actual_w)
            mx = float(chip.max())
            if mx <= 0.0:
                is_single_series.iloc[i] = True
                continue

            chip_norm = chip / mx
            peaks, valleys = _peak_detect(chip_norm, p_min, bw, threshold, bins, p_max)

            peaks_series.iloc[i] = [round(p, 4) for p in peaks[:5]]
            valleys_series.iloc[i] = [round(v, 4) for v in valleys[:5]]
            is_single_series.iloc[i] = len(peaks) == 1

        return {
            "chip_peaks": peaks_series,
            "chip_valleys": valleys_series,
            "chip_is_single_peak": is_single_series,
        }
