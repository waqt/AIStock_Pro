from ..base import BaseIndicator, register

@register
class BollingerIndicator(BaseIndicator):
    name = "bollinger"
    category = "volatility"
    params = {"period": 20, "std": 2}
    output = ["bb_upper", "bb_mid", "bb_lower"]
    requires = ["close"]

    @classmethod
    def compute(cls, df):
        mid = df["close"].rolling(cls.params["period"]).mean()
        std = df["close"].rolling(cls.params["period"]).std()
        return {
            "bb_upper": mid + cls.params["std"] * std,
            "bb_mid": mid,
            "bb_lower": mid - cls.params["std"] * std,
        }
