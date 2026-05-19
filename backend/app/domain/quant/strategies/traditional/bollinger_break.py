from ..base import TimingStrategy, SignalResult, register_strategy

@register_strategy
class BollingerBreakStrategy(TimingStrategy):
    name = "bollinger_break"
    description = "Bollinger带突破策略"
    required_indicators = ["bollinger", "volume_ma"]

    async def analyze(self, stock_code: str) -> SignalResult:
        ind = await self.load_indicators(stock_code)
        bb = ind.get("bollinger", {})
        vol = ind.get("volume_ma", {})
        upper = bb.get("bb_upper", [])
        mid = bb.get("bb_mid", [])
        lower = bb.get("bb_lower", [])
        v_ma20 = vol.get("v_ma20", [])
        if len(upper) < 2:
            return SignalResult.create(stock_code, self.name, self.category,
                "HOLD", 0.3, "数据不足")

        price = upper[-1]  # approximate close via upper value; real impl uses market_data
        prev_price = upper[-2]

        if prev_price < upper[-2] and price > upper[-1] and v_ma20[-1] > v_ma20[-2]:
            return SignalResult.create(stock_code, self.name, self.category,
                "BUY", 0.72, "放量突破Bollinger上轨")
        elif price < mid[-1] and prev_price > mid[-2]:
            return SignalResult.create(stock_code, self.name, self.category,
                "SELL", 0.65, "跌破Bollinger中轨")
        elif price < lower[-1]:
            return SignalResult.create(stock_code, self.name, self.category,
                "BUY", 0.55, "触及Bollinger下轨(超跌)")
        return SignalResult.create(stock_code, self.name, self.category,
            "HOLD", 0.50, "Bollinger带内运行")
