from ..base import TimingStrategy, SignalResult, register_strategy

@register_strategy
class BollingerBreakStrategy(TimingStrategy):
    name = "bollinger_break"
    description = "Bollinger带突破策略"
    required_indicators = ["bollinger", "volume_ma"]

    async def analyze(self, stock_code: str) -> SignalResult:
        ind = await self.load_indicators(stock_code)
        if not ind or "bb_upper" not in ind:
            return SignalResult.create(stock_code, self.name, self.category, "HOLD", 0.3, "数据不足")

        price = ind.get("price", 0)
        upper = ind["bb_upper"]
        mid = ind["bb_mid"]
        lower = ind["bb_lower"]
        v20 = ind.get("v_ma20", 0)
        v10 = ind.get("v_ma10", 0)

        if price > upper and v20 > v10 * 1.2:
            return SignalResult.create(stock_code, self.name, self.category, "BUY", 0.72, "放量突破Bollinger上轨")
        elif price < lower:
            return SignalResult.create(stock_code, self.name, self.category, "BUY", 0.55, "触及Bollinger下轨(超跌)")
        elif price < mid:
            return SignalResult.create(stock_code, self.name, self.category, "SELL", 0.60, "跌破Bollinger中轨")
        return SignalResult.create(stock_code, self.name, self.category, "HOLD", 0.50, "Bollinger带内运行")
