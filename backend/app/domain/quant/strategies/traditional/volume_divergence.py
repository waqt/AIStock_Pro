from ..base import TimingStrategy, SignalResult, register_strategy

@register_strategy
class VolumeDivergenceStrategy(TimingStrategy):
    name = "volume_divergence"
    description = "量价背离检测"
    required_indicators = ["ma", "volume_ma"]

    async def analyze(self, stock_code: str) -> SignalResult:
        ind = await self.load_indicators(stock_code)
        if not ind or "ma5" not in ind or "v_ma5" not in ind:
            return SignalResult.create(stock_code, self.name, self.category, "HOLD", 0.3, "数据不足")

        v5 = ind.get("v_ma5", 0)
        v20 = ind.get("v_ma20", 0)
        v10 = ind.get("v_ma10", 0)

        # 量价关系判断
        if v5 > v20 * 2:
            return SignalResult.create(stock_code, self.name, self.category, "BUY", 0.55, "成交量异常放大, 关注方向")
        elif v5 < v10 * 0.5:
            return SignalResult.create(stock_code, self.name, self.category, "HOLD", 0.50, "成交量萎缩, 观望")
        elif v5 > v20 * 1.3:
            return SignalResult.create(stock_code, self.name, self.category, "BUY", 0.62, "成交量温和放大")
        return SignalResult.create(stock_code, self.name, self.category, "HOLD", 0.50, "量价正常")
