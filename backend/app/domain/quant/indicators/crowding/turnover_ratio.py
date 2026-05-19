"""拥挤度: 20日/120日换手率比值"""
from ..base import BaseIndicator, register

@register
class TurnoverRatioIndicator(BaseIndicator):
    name = "turnover_ratio"
    category = "crowding"
    params = {"short": 20, "long": 120}
    output = ["turnover_20d", "turnover_120d", "crowding_ratio"]
    requires = ["volume"]

    @classmethod
    def compute(cls, df):
        # 换手率近似: 成交量 / 成交量MA (无总股本数据时, 用相对比例)
        v20 = df["volume"].rolling(cls.params["short"]).mean()
        v120 = df["volume"].rolling(cls.params["long"]).mean()
        return {
            "turnover_20d": v20,
            "turnover_120d": v120,
            "crowding_ratio": (v20 / (v120 + 1e-9)),
        }
