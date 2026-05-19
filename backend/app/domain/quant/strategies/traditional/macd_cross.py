from ..base import TimingStrategy, SignalResult, register_strategy

@register_strategy
class MACDCrossStrategy(TimingStrategy):
    name = "macd_cross"
    description = "MACD金叉买入, 死叉卖出"
    required_indicators = ["macd"]

    async def analyze(self, stock_code: str) -> SignalResult:
        ind = await self.load_indicators(stock_code)
        if not ind or "macd" not in ind or "macd_signal" not in ind:
            return SignalResult.create(stock_code, self.name, self.category, "HOLD", 0.3, "数据不足")

        macd_val = ind["macd"]
        signal_val = ind["macd_signal"]
        prev_macd = ind.get("_prev_macd", macd_val)
        prev_signal = ind.get("_prev_signal", signal_val)

        if prev_macd < prev_signal and macd_val > signal_val and macd_val > 0:
            return SignalResult.create(stock_code, self.name, self.category, "BUY", 0.75, "MACD零轴上金叉")
        elif prev_macd < prev_signal and macd_val > signal_val:
            return SignalResult.create(stock_code, self.name, self.category, "BUY", 0.60, "MACD金叉(弱势)")
        elif prev_macd > prev_signal and macd_val < signal_val:
            return SignalResult.create(stock_code, self.name, self.category, "SELL", 0.70, "MACD死叉")
        return SignalResult.create(stock_code, self.name, self.category, "HOLD", 0.50, "MACD无信号")
