from ..base import TimingStrategy, SignalResult, register_strategy

@register_strategy
class MAAlignmentStrategy(TimingStrategy):
    name = "ma_alignment"
    description = "均线多头/空头排列"
    required_indicators = ["ma"]

    async def analyze(self, stock_code: str) -> SignalResult:
        ind = await self.load_indicators(stock_code)
        if not ind or "ma5" not in ind:
            return SignalResult.create(stock_code, self.name, self.category, "HOLD", 0.3, "数据不足")

        m5, m10, m20, m60 = ind["ma5"], ind["ma10"], ind["ma20"], ind["ma60"]
        bullish = m5 > m10 > m20 > m60
        bearish = m5 < m10 < m20 < m60

        if bullish:
            return SignalResult.create(stock_code, self.name, self.category, "BUY", 0.72, "均线多头排列")
        elif bearish:
            return SignalResult.create(stock_code, self.name, self.category, "SELL", 0.68, "均线空头排列")
        return SignalResult.create(stock_code, self.name, self.category, "HOLD", 0.45, "均线交织")
