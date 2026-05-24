from ..base import BaseIndicator, register

@register
class RSIIndicator(BaseIndicator):
    name = "rsi"
    label = "RSI相对强弱"
    category = "momentum"
    params = {"period": 14}
    output = ["rsi"]
    requires = ["close"]

    @classmethod
    def compute(cls, df):
        delta = df["close"].diff()
        gain = delta.clip(lower=0).rolling(cls.params["period"]).mean()
        loss = (-delta.clip(upper=0)).rolling(cls.params["period"]).mean()
        rs = gain / (loss + 1e-9)
        return {"rsi": 100 - (100 / (1 + rs))}
