"""格雷厄姆数 — Benjamin Graham 防御型价值投资公式"""
from app.domain.quant.valuation.base import ValuationMethod, register_valuation


@register_valuation
class GrahamNumberMethod(ValuationMethod):
    name = "graham_number"
    label = "格雷厄姆数"
    category = "absolute"
    description = "Graham Number = √(22.5 × EPS × BVPS)。价格低于 Graham Number 的 2/3 时有显著安全边际"
    output = ["graham_number", "graham_vs_price_pct", "safety_margin_pct"]
    requires = ["pe_ttm", "pb", "mcap_yi", "total_shares", "total_equity"]
    requires_financial_data = True

    @classmethod
    def compute(cls, pe_ttm: float = None, pb: float = None,
                mcap_yi: float = None, total_shares: float = None,
                total_equity: float = None, **kwargs) -> dict:
        if not all([pe_ttm, pb, total_shares, total_equity]):
            return {k: None for k in cls.output}

        # EPS = 净利润 / 总股本, 从 PE 反推: EPS = price / PE
        # BVPS = 净资产 / 总股本
        if total_shares <= 0:
            return {k: None for k in cls.output}
        bvps = (total_equity or 0) / total_shares

        # 从 PE 和 PB 反推 EPS: EPS = (PE × BVPS) / (PB × 总股本) 的变形
        # 更直接: price = mcap_yi * 1e8 / total_shares, eps = price / pe_ttm
        price = (mcap_yi * 1e8) / total_shares if mcap_yi and total_shares > 0 else None
        if not price or price <= 0:
            return {k: None for k in cls.output}
        eps = price / pe_ttm

        graham = (22.5 * eps * bvps) ** 0.5
        vs_price = (graham - price) / price * 100
        safety = vs_price  # 正数 = 安全边际

        return {
            "graham_number": round(graham, 2),
            "graham_vs_price_pct": round(vs_price, 1),
            "safety_margin_pct": round(safety, 1),
        }
