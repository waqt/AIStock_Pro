from ..base import TimingStrategy, SignalResult, register_strategy

@register_strategy
class MAAlignmentStrategy(TimingStrategy):
    name = "ma_alignment"
    description = "均线多头/空头排列"
    required_indicators = ["ma"]

    async def analyze(self, stock_code: str) -> SignalResult:
        ind = await self.load_indicators(stock_code)
        ma = ind.get("ma", {})
        m5 = ma.get("ma5", [])
        m10 = ma.get("ma10", [])
        m20 = ma.get("ma20", [])
        m60 = ma.get("ma60", [])
        if len(m5) < 2:
            return SignalResult.create(stock_code, self.name, self.category,
                "HOLD", 0.3, "数据不足")

        # 多头排列: MA5 > MA10 > MA20 > MA60
        bullish = m5[-1] > m10[-1] > m20[-1] > m60[-1]
        bearish = m5[-1] < m10[-1] < m20[-1] < m60[-1]
        was_bullish = m5[-2] > m10[-2] > m20[-2] > m60[-2]

        if bullish and not was_bullish:
            return SignalResult.create(stock_code, self.name, self.category,
                "BUY", 0.80, "均线多头排列形成")
        elif bullish:
            return SignalResult.create(stock_code, self.name, self.category,
                "BUY", 0.65, "均线多头排列持续")
        elif bearish:
            return SignalResult.create(stock_code, self.name, self.category,
                "SELL", 0.70, "均线空头排列")
        return SignalResult.create(stock_code, self.name, self.category,
            "HOLD", 0.45, "均线交织, 方向不明")
