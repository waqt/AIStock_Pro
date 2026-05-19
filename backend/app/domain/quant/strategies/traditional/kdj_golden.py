from ..base import TimingStrategy, SignalResult, register_strategy

@register_strategy
class KDJGoldenCrossStrategy(TimingStrategy):
    name = "kdj_golden"
    description = "KDJ低位金叉买入, 高位死叉卖出"
    required_indicators = ["kdj"]

    async def analyze(self, stock_code: str) -> SignalResult:
        ind = await self.load_indicators(stock_code)
        if not ind or "k" not in ind:
            return SignalResult.create(stock_code, self.name, self.category, "HOLD", 0.3, "数据不足")

        k, d, j = ind.get("k", 50), ind.get("d", 50), ind.get("j", 50)
        prev_k, prev_d = ind.get("_prev_k", k), ind.get("_prev_d", d)
        cross_up = prev_k < prev_d and k > d
        cross_down = prev_k > prev_d and k < d

        if cross_up and k < 40:
            return SignalResult.create(stock_code, self.name, self.category, "BUY", 0.78, f"KDJ低位金叉(K={k:.1f})")
        elif cross_down and k > 70:
            return SignalResult.create(stock_code, self.name, self.category, "SELL", 0.72, f"KDJ高位死叉(K={k:.1f})")
        elif j > 100:
            return SignalResult.create(stock_code, self.name, self.category, "SELL", 0.65, f"KDJ超买(J={j:.1f})")
        elif j < 0:
            return SignalResult.create(stock_code, self.name, self.category, "BUY", 0.62, f"KDJ超卖(J={j:.1f})")
        return SignalResult.create(stock_code, self.name, self.category, "HOLD", 0.50, f"KDJ中性(K={k:.1f})")
