from ..base import TimingStrategy, SignalResult, register_strategy

@register_strategy
class RSIOverSoldStrategy(TimingStrategy):
    name = "rsi_oversold"
    description = "RSI超买超卖判断"
    required_indicators = ["rsi"]

    async def analyze(self, stock_code: str) -> SignalResult:
        ind = await self.load_indicators(stock_code)
        rsi_vals = ind.get("rsi", {}).get("rsi", [])
        if len(rsi_vals) < 2:
            return SignalResult.create(stock_code, self.name, self.category,
                "HOLD", 0.3, "数据不足")
        rsi = rsi_vals[-1]
        prev_rsi = rsi_vals[-2]
        if rsi < 30 and rsi > prev_rsi:
            return SignalResult.create(stock_code, self.name, self.category,
                "BUY", 0.70, f"RSI={rsi:.1f}, 超卖反弹")
        elif rsi < 25:
            return SignalResult.create(stock_code, self.name, self.category,
                "BUY", 0.60, f"RSI={rsi:.1f}, 深度超卖")
        elif rsi > 75:
            return SignalResult.create(stock_code, self.name, self.category,
                "SELL", 0.65, f"RSI={rsi:.1f}, 超买")
        elif rsi > 85:
            return SignalResult.create(stock_code, self.name, self.category,
                "SELL", 0.75, f"RSI={rsi:.1f}, 严重超买")
        return SignalResult.create(stock_code, self.name, self.category,
            "HOLD", 0.50, f"RSI={rsi:.1f}, 中性区间")
