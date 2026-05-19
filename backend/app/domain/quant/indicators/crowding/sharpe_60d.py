"""拥挤度: 60日夏普比率"""
from ..base import BaseIndicator, register
import numpy as np

@register
class Sharpe60dIndicator(BaseIndicator):
    name = "sharpe_60d"
    category = "crowding"
    params = {"period": 60, "rf": 0.02}
    output = ["sharpe_60d"]
    requires = ["close"]

    @classmethod
    def compute(cls, df):
        returns = df["close"].pct_change()
        excess = returns - cls.params["rf"] / 252
        roll_mean = excess.rolling(cls.params["period"]).mean()
        roll_std = excess.rolling(cls.params["period"]).std()
        return {"sharpe_60d": roll_mean / (roll_std + 1e-9) * np.sqrt(252)}
