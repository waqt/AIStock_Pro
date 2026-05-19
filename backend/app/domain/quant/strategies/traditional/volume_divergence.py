from ..base import TimingStrategy, SignalResult, register_strategy

@register_strategy
class VolumeDivergenceStrategy(TimingStrategy):
    name = "volume_divergence"
    description = "量价背离检测"
    required_indicators = ["ma", "volume_ma"]

    async def analyze(self, stock_code: str) -> SignalResult:
        ind = await self.load_indicators(stock_code)
        ma_data = ind.get("ma", {})
        vol_data = ind.get("volume_ma", {})
        ma5 = ma_data.get("ma5", [])
        v5 = vol_data.get("v_ma5", [])
        v20 = vol_data.get("v_ma20", [])
        if len(ma5) < 6:
            return SignalResult.create(stock_code, self.name, self.category,
                "HOLD", 0.3, "数据不足")

        # 近5日趋势
        price_rising = ma5[-1] > ma5[-5]
        vol_rising = (v5[-1] + v5[-2]) / 2 > (v5[-5] + v5[-4]) / 2

        if price_rising and not vol_rising:
            return SignalResult.create(stock_code, self.name, self.category,
                "SELL", 0.68, "价涨量缩, 顶背离")
        elif not price_rising and vol_rising:
            return SignalResult.create(stock_code, self.name, self.category,
                "BUY", 0.62, "价跌量增, 底背离")
        elif v5[-1] > v20[-1] * 2:
            return SignalResult.create(stock_code, self.name, self.category,
                "BUY", 0.55, "成交量异常放大, 关注方向选择")

        return SignalResult.create(stock_code, self.name, self.category,
            "HOLD", 0.50, "量价关系正常")
