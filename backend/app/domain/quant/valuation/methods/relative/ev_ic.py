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
    judgment = "ev_ic_ratio<1→极度低估, 1-2→合理, >3→可能高估。ROIC>10%且EV/IC<2→价值创造型公司(类巴菲特标准)"
    applicable_scenarios = "适用于重资产制造业、基础设施、公用事业等资本密集型公司; 适合与ROIC指标配合使用"
    limitations = "投入资本(IC)的计算涉及较多假设; 轻资产公司IC被低估导致EV/IC偏高; 资本化研发费用的处理方式影响可比性"

    @classmethod
    def compute(cls, mcap_yi: float = None, total_liabilities: float = None,
                cash: float = None, total_equity: float = None,
                **kwargs) -> dict:
        if mcap_yi is None or total_liabilities is None:
            return {k: None for k in cls.output}

        # total_liabilities / total_equity / cash 来自 FinancialStatement (原始元)
        # 统一转换为亿元
        tl_yi = (total_liabilities or 0) / 1e8
        cash_yi = (cash or 0) / 1e8
        te_yi = (total_equity or 0) / 1e8

        # EV = 市值 + 总负债 - 现金 (亿元)
        ev = mcap_yi + tl_yi - cash_yi

        # IC = 总权益 + 总负债 - 现金 (简化, 类似 invested capital)
        ic = te_yi + tl_yi - cash_yi
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
