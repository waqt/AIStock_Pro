from ..base import BaseIndicator, register

@register
class MAIndicator(BaseIndicator):
    name = "ma"
    label = "移动均线"
    category = "trend"
    params = {"periods": [5, 10, 20, 60, 120, 250]}
    output = ["ma5", "ma10", "ma20", "ma60", "ma120", "ma250"]
    requires = ["close"]

    @classmethod
    def compute(cls, df):
        result = {}
        for p in cls.params["periods"]:
            result[f"ma{p}"] = df["close"].rolling(p).mean()
        return result
