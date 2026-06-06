"""剩余收益模型 (Residual Income Model / RIM) — P/B = 1 + (ROE - r) / (r - g)

比 DCF 更稳健: 不需要预测自由现金流, 只需要 ROE 和净资产。
"""
from app.domain.quant.valuation.base import ValuationMethod, register_valuation


@register_valuation
class ResidualIncomeMethod(ValuationMethod):
    name = "residual_income"
    label = "剩余收益估值"
    category = "absolute"
    description = "RIM = BVPS + (ROE - r) / (r - g) × BVPS。基于净资产和超额收益的估值, 适合金融/稳定公司"
    output = ["rim_value", "rim_vs_price_pct"]
    requires = ["roe", "pb", "mcap_yi", "total_shares", "total_equity"]
    requires_financial_data = True
    judgment = "rim_vs_price_pct>0%→股价低于剩余收益模型价值(低估)。ROE>r时创造价值, ROE<r时摧毁价值。ROE<r+g时增长反而毁损价值"
    applicable_scenarios = "适用于有形资产比重大的公司(银行/保险/制造); ROE稳定可预测的成熟公司效果最好"
    limitations = "权益成本率(r)取固定值9%, 未按个股β调整; g取3%偏低, 可能低估成长期公司; 依赖BVPS准确性(受会计政策影响)"

    @classmethod
    def compute(cls, roe: float = None, pb: float = None,
                mcap_yi: float = None, total_shares: float = None,
                total_equity: float = None, **kwargs) -> dict:
        if not all([roe, total_shares, total_equity]) or total_shares <= 0:
            return {k: None for k in cls.output}

        bvps = total_equity / total_shares
        price = (mcap_yi * 1e8) / total_shares if mcap_yi and total_shares > 0 else None

        # 权益成本 r: 5 年期国债收益率(~2.5%) + 股权风险溢价(~4%)
        r = 6.5  # % 或直接用 0.065

        # 稳定增速 g: 保守假设 = GDP 增速 4%
        g = 4.0  # %

        # RIM = BVPS + (ROE - r) / (r - g) * BVPS
        roe_pct = roe  # ROE 已是百分比
        if roe_pct <= g:
            # ROE 低于增长假设, 没有超额收益, 按账面价值估值
            rim = bvps
        else:
            excess = (roe_pct / 100 - r / 100) / ((r - g) / 100)
            rim = bvps * (1 + excess)

        rim_per_share = rim / total_shares if total_shares > 0 else rim

        vs_price = None
        if price and price > 0:
            vs_price = round((rim_per_share - price) / price * 100, 1)

        return {
            "rim_value": round(rim_per_share, 2) if rim_per_share else None,
            "rim_vs_price_pct": vs_price,
        }
