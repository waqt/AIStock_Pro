"""PS 估值 — 市销率 TTM + 百分位判断"""
import numpy as np
from app.domain.quant.valuation.base import ValuationMethod, register_valuation


@register_valuation
class PSValuationMethod(ValuationMethod):
    name = "ps_valuation"
    label = "PS 估值"
    category = "relative"
    description = "市销率 = 市值 / 营收 TTM, 用于高成长/亏损公司的估值判断"
    output = ["ps_ttm", "ps_percentile", "ps_status"]
    requires = ["mcap_yi", "total_shares", "revenue_ttm"]
    text_output = ["ps_status"]
    requires_financial_data = True
    judgment = "ps_percentile<20→低估, 20-80→合理, >80→高估。ps_ttm < 1 可能低估, > 10 可能高估(TMT行业正常范围可能更高)"
    applicable_scenarios = "适用于营收稳定但利润波动大的公司(如成长初期); 适合周期性行业和亏损公司"
    limitations = "PS不考虑成本结构和利润率差异; 高毛利和低毛利公司的PS不可直接比较; 营收操控风险低于利润但依然存在"

    @classmethod
    def compute(cls, mcap_yi: float = None, total_shares: float = None,
                revenue_ttm: float = None, price_history: list = None, **kwargs) -> dict:
        if mcap_yi is None or revenue_ttm is None or revenue_ttm <= 0:
            return {k: None for k in cls.output}

        ps_ttm = mcap_yi / (revenue_ttm / 1e8) if revenue_ttm > 0 else None
        if ps_ttm is None:
            return {k: None for k in cls.output}

        # 简单行业参考: PS<2=低估, 2-8=合理, >8=高估 (成长行业)
        status = "高估" if ps_ttm > 8 else ("低估" if ps_ttm < 2 else "合理")

        # 有历史价格时算百分位
        ps_pct = None
        if price_history and len(price_history) > 20 and total_shares:
            rev_per_share = (revenue_ttm / 1e8) / total_shares if total_shares > 0 else 0
            if rev_per_share > 0:
                ps_seq = [(p or 0) / rev_per_share for p in price_history if (p or 0) > 0]
                if ps_seq:
                    arr = np.array(ps_seq)
                    ps_pct = round(float(np.sum(arr <= ps_ttm) / len(arr) * 100), 1)

        return {
            "ps_ttm": round(ps_ttm, 2),
            "ps_percentile": ps_pct,
            "ps_status": status,
        }
