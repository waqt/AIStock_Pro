from ..base import BaseIndicator, register

@register
class CCIIndicator(BaseIndicator):
    name = "cci"
    label = "CCI商品通道"
    category = "momentum"
    params = {"period": 20}
    output = ["cci"]
    requires = ["high", "low", "close"]

    @classmethod
    def compute(cls, df):
        tp = (df["high"] + df["low"] + df["close"]) / 3
        ma = tp.rolling(cls.params["period"]).mean()
        md = tp.rolling(cls.params["period"]).apply(lambda x: (x - x.mean()).abs().mean())
        return {"cci": (tp - ma) / (0.015 * md + 1e-9)}
