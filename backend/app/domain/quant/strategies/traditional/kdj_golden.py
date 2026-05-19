from ..base import TimingStrategy, SignalResult, register_strategy

@register_strategy
class KDJGoldenCrossStrategy(TimingStrategy):
    name = "kdj_golden"
    description = "KDJ低位金叉买入, 高位死叉卖出"
    required_indicators = ["kdj"]

    async def analyze(self, stock_code: str) -> SignalResult:
        ind = await self.load_indicators(stock_code)
        kdj = ind.get("kdj", {})
        k = kdj.get("k", [])
        d = kdj.get("d", [])
        j = kdj.get("j", [])
        if len(k) < 3:
            return SignalResult.create(stock_code, self.name, self.category,
                "HOLD", 0.3, "数据不足")

        cur_k, prev_k = k[-1], k[-2]
        cur_d, prev_d = d[-1], d[-2]
        cur_j = j[-1] if j else 0

        cross_up = prev_k < prev_d and cur_k > cur_d
        cross_down = prev_k > prev_d and cur_k < cur_d

        if cross_up and cur_k < 40:
            return SignalResult.create(stock_code, self.name, self.category,
                "BUY", 0.78, f"KDJ低位金叉 (K={cur_k:.1f})")
        elif cross_up and cur_j < 0:
            return SignalResult.create(stock_code, self.name, self.category,
                "BUY", 0.60, f"KDJ金叉+J值超卖 (J={cur_j:.1f})")
        elif cross_down and cur_k > 70:
            return SignalResult.create(stock_code, self.name, self.category,
                "SELL", 0.72, f"KDJ高位死叉 (K={cur_k:.1f})")
        elif cur_j > 100:
            return SignalResult.create(stock_code, self.name, self.category,
                "SELL", 0.65, f"KDJ J值超买 (J={cur_j:.1f})")
        return SignalResult.create(stock_code, self.name, self.category,
            "HOLD", 0.50, f"KDJ中性 (K={cur_k:.1f})")
