"""斐波那契回调位 — 基于 N 日滚动高/低点"""
import numpy as np
import pandas as pd
from ..base import BaseIndicator, register

@register
class FibonacciRetracement(BaseIndicator):
    name = "fib_retracement"
    label = "斐波那契回调"
    description = "基于滚动窗口最高/最低价计算斐波那契回调位(23.6%/38.2%/50%/61.8%/78.6%)，上升趋势从高向下回调，下降趋势从低向上反弹。"
    category = "trend"
    params = {"window": 60}
    output = ["fib_high", "fib_low",
              "fib_23_6", "fib_38_2", "fib_50_0", "fib_61_8", "fib_78_6"]
    requires = ["close", "high", "low"]

    FIB_LEVELS = [(0.236, "fib_23_6"), (0.382, "fib_38_2"),
                  (0.5, "fib_50_0"), (0.618, "fib_61_8"),
                  (0.786, "fib_78_6")]

    @classmethod
    def compute(cls, df):
        window = cls.params["window"]
        rolling_high = df["high"].rolling(window, min_periods=window).max()
        rolling_low = df["low"].rolling(window, min_periods=window).min()
        diff = rolling_high - rolling_low

        # 趋势方向: SMA20 过滤, 避免噪音
        sma20 = df["close"].rolling(20).mean()
        up_trend = df["close"] > sma20

        result = {"fib_high": rolling_high, "fib_low": rolling_low}
        for ratio, key in cls.FIB_LEVELS:
            fib_up = rolling_high - diff * ratio       # 上升→回调向下
            fib_down = rolling_low + diff * ratio      # 下降→反弹向上
            result[key] = pd.Series(np.where(up_trend, fib_up, fib_down), index=df.index)
        return result
