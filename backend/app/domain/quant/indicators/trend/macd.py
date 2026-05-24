from ..base import BaseIndicator, register

@register
class MACDIndicator(BaseIndicator):
    name = "macd"
    label = "MACD指标"
    category = "trend"
    params = {"fast": 12, "slow": 26, "signal": 9}
    output = ["macd", "macd_signal", "macd_hist"]
    requires = ["close"]

    @classmethod
    def compute(cls, df):
        ema_fast = df["close"].ewm(span=cls.params["fast"], adjust=False).mean()
        ema_slow = df["close"].ewm(span=cls.params["slow"], adjust=False).mean()
        macd = ema_fast - ema_slow
        signal = macd.ewm(span=cls.params["signal"], adjust=False).mean()
        return {"macd": macd, "macd_signal": signal, "macd_hist": macd - signal}
