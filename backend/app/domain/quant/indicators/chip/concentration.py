"""筹码集中度 — COST算法 + 指数衰减 (半衰期45天, numba加速)"""
from ..base import BaseIndicator, register
import numpy as np
import pandas as pd
from numba import jit

@jit(nopython=True, cache=True)
def _cost_chip(cl_w, hi_w, lo_w, vol_w, p_min, p_max, bins, decay, w):
    """numba加速: 计算窗口末日的筹码分布数组"""
    bw = (p_max - p_min) / bins
    chip = np.zeros(bins, dtype=np.float64)
    for j in range(w):
        for k in range(bins):
            chip[k] *= decay
        if vol_w[j] <= 0.0:
            continue
        lo = max(0, int((lo_w[j] - p_min) / bw))
        hi = min(bins - 1, int((hi_w[j] - p_min) / bw) + 1)
        if hi <= lo:
            continue
        mid_f = (cl_w[j] - p_min) / bw
        mid = int(mid_f)
        if mid < lo: mid = lo
        if mid >= hi: mid = hi - 1
        rng = max(hi - lo, 1.0)
        for k in range(lo, hi):
            weight = 1.0 - 0.7 * abs(k - mid) / rng
            if weight > 0.0:
                chip[k] += vol_w[j] * weight
    return chip

@jit(nopython=True, cache=True)
def _cost_percentile(chip, price_grid, pct, bins):
    """numba加速: 从筹码分布计算 N% 分位价格"""
    si = np.argsort(price_grid)
    chip_sorted = np.zeros(bins, dtype=np.float64)
    for i in range(bins):
        chip_sorted[i] = chip[si[i]]
    total = 0.0
    for i in range(bins):
        total += chip_sorted[i]
    cum = 0.0
    target = pct / 100.0
    idx = bins - 1
    for i in range(bins):
        cum += chip_sorted[i] / total
        if cum >= target:
            idx = si[i]
            break
    return price_grid[idx]

@jit(nopython=True, cache=True)
def _cost_avg(grid, chip, bins):
    """numba加速: 加权平均成本"""
    total = 0.0
    weighted = 0.0
    for i in range(bins):
        total += chip[i]
        weighted += grid[i] * chip[i]
    return weighted / total if total > 0 else 0.0

@jit(nopython=True, cache=True)
def _cost_peak_idx(chip, bins):
    """numba加速: 筹码峰值索引"""
    pk = 0
    pk_val = chip[0]
    for i in range(1, bins):
        if chip[i] > pk_val:
            pk_val = chip[i]
            pk = i
    return pk


@register
class ChipConcentrationIndicator(BaseIndicator):
    name = "chip_concentration"
    label = "筹码集中度"
    category = "chip"
    params = {"window": 0, "decay_half": 45, "bins": 400}  # window=0=全历史, 和temp_lab一致
    output = ["chip_concentration", "chip_peak_price", "chip_avg_cost"]
    requires = ["high", "low", "close", "volume"]

    @classmethod
    def compute(cls, df):
        w = cls.params["window"]
        bins = cls.params["bins"]
        hl = cls.params["decay_half"]
        close = df["close"].values.astype(np.float64)
        high = df["high"].values.astype(np.float64)
        low = df["low"].values.astype(np.float64)
        volume = df["volume"].values.astype(np.float64)
        n = len(df)
        decay = np.float64(0.5 ** (1.0 / hl))

        concentration = pd.Series(np.nan, index=df.index, dtype=float)
        peak_price = pd.Series(np.nan, index=df.index, dtype=float)
        avg_cost = pd.Series(np.nan, index=df.index, dtype=float)

        min_days = max(w, 60) if w > 0 else 60
        if n < min_days:
            return {"chip_concentration": concentration, "chip_peak_price": peak_price, "chip_avg_cost": avg_cost}

        for i in range(min_days, n):
            if w > 0:
                lo_w = low[i-w:i]; hi_w = high[i-w:i]; cl_w = close[i-w:i]; vol_w = volume[i-w:i]
                actual_w = w
            else:
                lo_w = low[0:i]; hi_w = high[0:i]; cl_w = close[0:i]; vol_w = volume[0:i]
                actual_w = i

            p_min = float(np.min(lo_w))
            p_max = float(np.max(hi_w))
            cur_p = float(cl_w[-1])
            if cur_p > p_max: p_max = cur_p
            if cur_p < p_min: p_min = cur_p
            if p_max <= p_min:
                concentration.iloc[i] = 0.0
                peak_price.iloc[i] = round(cur_p, 4)
                avg_cost.iloc[i] = round(cur_p, 4)
                continue

            margin = (p_max - p_min) * 0.05
            p_min -= margin
            p_max += margin
            bw = (p_max - p_min) / bins
            grid = np.array([p_min + (j + 0.5) * bw for j in range(bins)], dtype=np.float64)

            chip = _cost_chip(cl_w, hi_w, lo_w, vol_w, p_min, p_max, bins, decay, actual_w)
            total = float(chip.sum())
            if total <= 0:
                concentration.iloc[i] = 0.0
                peak_price.iloc[i] = round(cur_p, 4)
                avg_cost.iloc[i] = round(cur_p, 4)
                continue

            avg_cost.iloc[i] = round(float(_cost_avg(grid, chip, bins)), 4)
            pk_idx = _cost_peak_idx(chip, bins)
            peak_price.iloc[i] = round(float(grid[pk_idx]), 4)

            c10 = float(_cost_percentile(chip, grid, 10.0, bins))
            c50 = float(_cost_percentile(chip, grid, 50.0, bins))
            c90 = float(_cost_percentile(chip, grid, 90.0, bins))
            # 行业标准公式: (COST90-COST10)/(COST90+COST10), 越小越集中
            denom = c90 + c10
            if denom > 0:
                concentration.iloc[i] = round((c90 - c10) / denom, 4)
            else:
                concentration.iloc[i] = 0.0

        return {
            "chip_concentration": concentration,
            "chip_peak_price": peak_price,
            "chip_avg_cost": avg_cost,
        }
