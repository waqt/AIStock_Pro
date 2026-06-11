"""FCF Yield — 自由现金流收益率, OCF 近似替代 FCF"""
from app.domain.quant.valuation.base import ValuationMethod, register_valuation


@register_valuation
class FCFYieldMethod(ValuationMethod):
    name = "fcf_yield"
    label = "FCF 收益率"
    category = "relative"
    description = "自由现金流收益率 = 估计 FCF / 市值。OCF 替代 FCF, 资本开支从固定资产估算"
    output = ["fcf_yield_pct", "fcf_est_yi", "implied_value"]
    requires = ["mcap_yi", "ocf_ttm", "total_shares", "fixed_assets", "cash", "total_liabilities"]
    requires_financial_data = True
    judgment = "fcf_yield_pct>5%→现金流充裕, >8%→优秀, 负值→经营现金流无法覆盖资本开支"
    applicable_scenarios = "适用于成熟稳定、现金流可预测的公司; 消费/公用事业/能源行业效果较好"
    limitations = "资本开支为经验估算(FixedAssets×5%), 实际可能偏差大; 高增长公司FCF通常为负导致yield无意义"

    @classmethod
    def compute(cls, mcap_yi: float = None, ocf_ttm: float = None,
                total_shares: float = None, fixed_assets: float = None,
                cash: float = None, total_liabilities: float = None,
                **kwargs) -> dict:
        if mcap_yi is None or mcap_yi <= 0 or ocf_ttm is None:
            return {k: None for k in cls.output}

        # 资本开支近似: 用固定资产的 5% 作为维护性资本开支
        capex_est = fixed_assets * 0.05 if fixed_assets and fixed_assets > 0 else 0

        fcf_est = ocf_ttm - capex_est

        # FCF 收益率 = FCF / 总市值 (始终计算真实值, 负FCF也如实反映)
        fcf_yield = fcf_est / (mcap_yi * 1e8) * 100

        # 隐含价值: EV = FCF / target_yield → Equity = EV - Net Debt → 每股价值
        implied = None
        if fcf_est > 0 and total_shares and total_shares > 0:
            target_yield = 0.04
            implied_ev = fcf_est / target_yield
            net_debt = (total_liabilities or 0) - (cash or 0)
            equity_value = implied_ev - net_debt
            if equity_value > 0:
                implied = round(equity_value / total_shares, 2)

        return {
            "fcf_yield_pct": round(fcf_yield, 2),
            "fcf_est_yi": round(fcf_est / 1e8, 2),  # 始终以亿为单位
            "implied_value": implied,
        }
