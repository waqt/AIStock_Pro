from ..base import BaseIndicator, register

@register
class OBVIndicator(BaseIndicator):
    name = "obv"
    label = "OBV能量潮"
    category = "volume"
    params = {}
    output = ["obv"]
    requires = ["close", "volume"]

    @classmethod
    def compute(cls, df):
        sign = df["close"].diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
        return {"obv": (sign * df["volume"]).cumsum()}
