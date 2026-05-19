from ..base import TimingStrategy, SignalResult, register_strategy

@register_strategy
class MACDCrossStrategy(TimingStrategy):
    name = "macd_cross"
    description = "MACD金叉买入, 死叉卖出"
    required_indicators = ["macd"]

    async def analyze(self, stock_code: str) -> SignalResult:
        ind = await self.load_indicators(stock_code)
        macd_data = ind.get("macd", {})
        macd = macd_data.get("macd", [])
        signal_line = macd_data.get("macd_signal", [])
        if len(macd) < 3:
            return SignalResult.create(stock_code, self.name, self.category,
                "HOLD", 0.3, "数据不足")

        prev_m, cur_m = macd[-2], macd[-1]
        prev_s, cur_s = signal_line[-2], signal_line[-1]
        cross_up = prev_m < prev_s and cur_m > cur_s
        cross_down = prev_m > prev_s and cur_m < cur_s

        if cross_up and cur_m > 0:
            return SignalResult.create(stock_code, self.name, self.category,
                "BUY", 0.75, "MACD零轴上金叉")
        elif cross_up:
            return SignalResult.create(stock_code, self.name, self.category,
                "BUY", 0.60, "MACD零轴下金叉(弱势)")
        elif cross_down:
            return SignalResult.create(stock_code, self.name, self.category,
                "SELL", 0.70, "MACD死叉")
        return SignalResult.create(stock_code, self.name, self.category,
            "HOLD", 0.50, "MACD无明确信号")
