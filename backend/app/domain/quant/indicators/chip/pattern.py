"""筹码形态识别 — 单峰/双峰/多峰 + 高低位判定 (对齐行业标准)"""
from ..base import BaseIndicator, register
import numpy as np
import pandas as pd

@register
class ChipPatternIndicator(BaseIndicator):
    name = "chip_pattern"
    label = "筹码形态识别"
    category = "chip"
    params = {"window": 0, "conc_dense": 0.12, "conc_dispersed": 0.20, "peak_dominance": 0.5}
    output = ["chip_pattern", "chip_signal"]
    requires = ["close", "chip_concentration", "chip_peak_price", "chip_peaks", "chip_is_single_peak"]

    @classmethod
    def compute(cls, df):
        n = len(df)
        min_days = 60
        c_dense = cls.params["conc_dense"]
        c_dispersed = cls.params["conc_dispersed"]
        peak_dom = cls.params["peak_dominance"]

        pattern_series = pd.Series("insufficient_data", index=df.index, dtype=str)
        signal_series = pd.Series("HOLD", index=df.index, dtype=str)

        if n < min_days:
            return {"chip_pattern": pattern_series, "chip_signal": signal_series}

        conc_col = df["chip_concentration"].values
        peak_price_col = df["chip_peak_price"].values
        peaks_col = df["chip_peaks"].values
        is_single_col = df["chip_is_single_peak"].values
        close = df["close"].values
        high = df["high"].values
        low = df["low"].values

        for i in range(min_days, n):
            conc = conc_col[i]
            if conc is None or (isinstance(conc, float) and pd.isna(conc)):
                continue

            conc = float(conc)
            cl = float(close[i])
            pk = float(peak_price_col[i]) if peak_price_col[i] is not None and not (isinstance(peak_price_col[i], float) and pd.isna(peak_price_col[i])) else cl

            peaks_val = peaks_col[i]
            peaks = peaks_val if isinstance(peaks_val, list) else []
            n_peaks = len(peaks)

            # 250日价格区间分位
            price_250_low = float(np.min(low[max(0, i-250):i+1])) if i >= 50 else float(np.min(low[:i+1]))
            price_250_high = float(np.max(high[max(0, i-250):i+1])) if i >= 50 else float(np.max(high[:i+1]))
            price_range = price_250_high - price_250_low if price_250_high > price_250_low else 1.0
            peak_pct = (pk - price_250_low) / price_range  # 峰值在250日区间的分位(0~1)

            pattern = "多峰密集"
            signal = "HOLD"

            if conc <= c_dense and n_peaks == 1:
                # 单峰密集: 高位 or 低位
                if peak_pct <= 0.35:
                    pattern = "低位单峰密集"
                    signal = "BUY"
                elif peak_pct >= 0.65:
                    pattern = "高位单峰密集"
                    signal = "SELL"
                else:
                    pattern = "单峰密集"
                    signal = "HOLD"

            elif conc <= c_dispersed and n_peaks >= 2:
                # 双峰或多峰: 判断价格靠近哪个峰
                if n_peaks == 2:
                    p1, p2 = peaks[0], peaks[1]
                    d1, d2 = abs(cl - p1), abs(cl - p2)
                    if d1 < d2:
                        pattern = "双峰密集(近下峰)"
                        signal = "BUY" if cl < p2 * 1.05 else "HOLD"
                    else:
                        pattern = "双峰密集(近上峰)"
                        signal = "SELL" if cl > p1 * 0.95 else "HOLD"
                else:
                    # 多峰 (>2): 找最近的两个主峰
                    sorted_peaks = sorted(peaks, key=lambda p: abs(cl - p))
                    nearest = sorted_peaks[:2]
                    if len(nearest) == 2 and abs(nearest[0] - nearest[1]) > price_range * 0.03:
                        p_low = min(nearest)
                        p_high = max(nearest)
                        d_low, d_high = abs(cl - p_low), abs(cl - p_high)
                        if d_low < d_high:
                            pattern = "双峰密集(近下峰)"
                            signal = "BUY"
                        else:
                            pattern = "双峰密集(近上峰)"
                            signal = "SELL"
                    else:
                        pattern = "多峰密集"
                        signal = "HOLD"

            elif conc > c_dispersed:
                # 筹码发散
                pattern = "多峰密集"
                signal = "HOLD"

            if n_peaks == 0:
                pattern = "筹码分散"
                signal = "HOLD"

            pattern_series.iloc[i] = pattern
            signal_series.iloc[i] = signal

        return {"chip_pattern": pattern_series, "chip_signal": signal_series}
