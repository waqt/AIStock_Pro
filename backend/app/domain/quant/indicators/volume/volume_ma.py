from ..base import BaseIndicator, register

@register
class VolumeMAIndicator(BaseIndicator):
    name = "volume_ma"
    label = "量能均线"
    category = "volume"
    params = {"periods": [5, 10, 20]}
    output = ["v_ma5", "v_ma10", "v_ma20"]
    requires = ["volume"]

    @classmethod
    def compute(cls, df):
        result = {}
        for p in cls.params["periods"]:
            result[f"v_ma{p}"] = df["volume"].rolling(p).mean()
        return result
