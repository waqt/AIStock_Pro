"""DDM 戈登增长模型 — 适用于稳定派息公司的绝对估值

P = DPS / (r - g)
  DPS = 股息每股, r = 权益成本, g = 永续增长率
"""
from app.domain.quant.valuation.base import ValuationMethod, register_valuation


@register_valuation
class GordonGrowthMethod(ValuationMethod):
    name = "gordon_growth"
    label = "DDM 戈登模型"
    category = "absolute"
    description = "戈登增长模型: P = DPS / (r - g)。适用于稳定派息、可预测增长的成熟公司"
    output = ["ddm_value", "ddm_vs_price_pct", "dps_est", "implied_growth_rate"]
    requires = ["dividend_yield", "mcap_yi", "total_shares"]

    @classmethod
    def compute(cls, dividend_yield: float = None, mcap_yi: float = None,
                total_shares: float = None, **kwargs) -> dict:
        if dividend_yield is None or mcap_yi is None or not total_shares or total_shares <= 0:
            return {k: None for k in cls.output}

        # 当前股价
        price = (mcap_yi * 1e8) / total_shares
        if price <= 0:
            return {k: None for k in cls.output}

        # DPS = 股价 × 股息率%
        dps = price * (dividend_yield / 100)

        # 权益成本 r: 5 年期国债(~2.5%) + 股权风险溢价(~4%)
        r = 0.065

        # 永续增长率 g: 保守假设 3%
        g = 0.03

        if r <= g:
            return {"ddm_value": None, "ddm_vs_price_pct": None,
                    "dps_est": round(dps, 3), "implied_growth_rate": None}

        ddm_value = dps / (r - g)
        vs_price = round((ddm_value - price) / price * 100, 1) if price > 0 else None

        # 反推: 当前价格隐含的增长率
        implied_g = None
        if price > 0 and dps > 0:
            implied_g = r - dps / price

        return {
            "ddm_value": round(ddm_value, 2),
            "ddm_vs_price_pct": vs_price,
            "dps_est": round(dps, 3),
            "implied_growth_rate": round(implied_g * 100, 2) if implied_g else None,
        }
