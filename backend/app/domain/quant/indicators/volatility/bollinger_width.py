from ..base import BaseIndicator, register

@register
class BollingerWidthIndicator(BaseIndicator):
    name = "bollinger_width"
    category = "volatility"
    params = {"period": 20}
    output = ["bb_width"]
    requires = ["close"]

    @classmethod
    def compute(cls, df):
        mid = df["close"].rolling(cls.params["period"]).mean()
        std = df["close"].rolling(cls.params["period"]).std()
        return {"bb_width": (2 * 2 * std) / (mid + 1e-9) * 100}
