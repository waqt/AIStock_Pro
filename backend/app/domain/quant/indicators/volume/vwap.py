from ..base import BaseIndicator, register

@register
class VWAPIndicator(BaseIndicator):
    name = "vwap"
    category = "volume"
    params = {}
    output = ["vwap"]
    requires = ["high", "low", "close", "volume"]

    @classmethod
    def compute(cls, df):
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        cum_pv = (typical_price * df["volume"]).cumsum()
        cum_vol = df["volume"].cumsum()
        return {"vwap": cum_pv / (cum_vol + 1e-9)}
