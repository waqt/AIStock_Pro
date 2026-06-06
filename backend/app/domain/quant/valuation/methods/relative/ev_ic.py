"""EV/IC 倍数 — 企业价值 / 投入资本, 结合 ROIC 评估价值创造"""
from app.domain.quant.valuation.base import ValuationMethod, register_valuation


@register_valuation
class EVICMethod(ValuationMethod):
    name = "ev_ic"
    label = "EV/IC 倍数"
    category = "relative"
    description = "企业价值 / 投入资本。EV/IC < 2 且 ROIC > 10% 表示价值被低估, 类似 PB-ROE 框架的企业级版本"
    output = ["ev_yi", "ic_yi", "ev_ic_ratio", "ev_ic_verdict"]
    requires = ["mcap_yi", "total_liabilities", "cash", "total_equity"]
    text_output = ["ev_ic_verdict"]
    requires_financial_data = True

    @classmethod
    def compute(cls, mcap_yi: float = None, total_liabilities: float = None,
                cash: float = None, total_equity: float = None,
                **kwargs) -> dict:
        if mcap_yi is None or total_liabilities is None:
            return {k: None for k in cls.output}

        # EV = 市值 + 总负债 - 现金 (亿元)
        ev = mcap_yi + (total_liabilities or 0)
        if cash:
            ev -= cash / 1e8  # cash 是元, 转亿

        # IC = 总权益 + 总负债 - 现金 (简化, 类似 invested capital)
        ic = (total_equity or 0) / 1e8 + (total_liabilities or 0) - (cash or 0) / 1e8
        if ic <= 0:
            ic = ev  # 兜底

        ratio = ev / ic if ic > 0 else None

        verdict = None
        if ratio is not None:
            if ratio < 1.5:
                verdict = "低估"
            elif ratio < 3.0:
                verdict = "合理"
            else:
                verdict = "高估"

        return {
            "ev_yi": round(ev, 2),
            "ic_yi": round(ic, 2),
            "ev_ic_ratio": round(ratio, 2) if ratio else None,
            "ev_ic_verdict": verdict,
        }
