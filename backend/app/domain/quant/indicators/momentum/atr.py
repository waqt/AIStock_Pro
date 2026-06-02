import pandas as pd
from ..base import BaseIndicator, register

@register
class ATRIndicator(BaseIndicator):
    name = "atr"
    label = "ATR真实波幅"
    category = "momentum"
    params = {"period": 14}
    output = ["atr"]
    requires = ["high", "low", "close"]

    @classmethod
    def compute(cls, df):
        high, low, close = df["high"], df["low"], df["close"]
        tr = pd.concat([
            (high - low).abs(),
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)
        return {"atr": tr.ewm(span=cls.params["period"], adjust=False).mean()}
