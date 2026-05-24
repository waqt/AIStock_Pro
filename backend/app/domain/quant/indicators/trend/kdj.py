from ..base import BaseIndicator, register

@register
class KDJIndicator(BaseIndicator):
    name = "kdj"
    label = "KDJ随机指标"
    category = "trend"
    params = {"n": 9, "m1": 3, "m2": 3}
    output = ["k", "d", "j"]
    requires = ["high", "low", "close"]

    @classmethod
    def compute(cls, df):
        low_n = df["low"].rolling(cls.params["n"]).min()
        high_n = df["high"].rolling(cls.params["n"]).max()
        rsv = (df["close"] - low_n) / (high_n - low_n + 1e-9) * 100
        k = rsv.ewm(com=cls.params["m1"] - 1, adjust=False).mean()
        d = k.ewm(com=cls.params["m2"] - 1, adjust=False).mean()
        j = 3 * k - 2 * d
        return {"k": k, "d": d, "j": j}
