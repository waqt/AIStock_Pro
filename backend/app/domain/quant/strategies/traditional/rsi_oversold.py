from ..base import TimingStrategy, SignalResult, register_strategy

@register_strategy
class RSIOverSoldStrategy(TimingStrategy):
    name = "rsi_oversold"
    description = "RSI超买超卖判断"
    required_indicators = ["rsi"]

    async def analyze(self, stock_code: str) -> SignalResult:
        ind = await self.load_indicators(stock_code)
        rsi = ind.get("rsi") if ind else None
        if rsi is None:
            return SignalResult.create(stock_code, self.name, self.category, "HOLD", 0.3, "数据不足")

        if rsi < 30:
            return SignalResult.create(stock_code, self.name, self.category, "BUY", 0.70, f"RSI={rsi:.1f}, 超卖")
        elif rsi < 25:
            return SignalResult.create(stock_code, self.name, self.category, "BUY", 0.80, f"RSI={rsi:.1f}, 深度超卖")
        elif rsi > 80:
            return SignalResult.create(stock_code, self.name, self.category, "SELL", 0.75, f"RSI={rsi:.1f}, 超买")
        elif rsi > 70:
            return SignalResult.create(stock_code, self.name, self.category, "SELL", 0.60, f"RSI={rsi:.1f}, 偏贵")
        return SignalResult.create(stock_code, self.name, self.category, "HOLD", 0.50, f"RSI={rsi:.1f}, 中性")
