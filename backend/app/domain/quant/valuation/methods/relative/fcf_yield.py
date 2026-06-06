"""FCF Yield — 自由现金流收益率, OCF 近似替代 FCF"""
from app.domain.quant.valuation.base import ValuationMethod, register_valuation


@register_valuation
class FCFYieldMethod(ValuationMethod):
    name = "fcf_yield"
    label = "FCF 收益率"
    category = "relative"
    description = "自由现金流收益率 = 估计 FCF / 市值。OCF 替代 FCF, 资本开支从固定资产变化估算。FCF Yield > 5% 有吸引力"
    output = ["fcf_yield_pct", "fcf_est_yi", "implied_value"]
    requires = ["mcap_yi", "ocf_ttm", "total_shares", "fixed_assets"]
    requires_financial_data = True

    @classmethod
    def compute(cls, mcap_yi: float = None, ocf_ttm: float = None,
                total_shares: float = None, fixed_assets: float = None,
                **kwargs) -> dict:
        if mcap_yi is None or mcap_yi <= 0 or ocf_ttm is None:
            return {k: None for k in cls.output}

        # 资本开支近似: fixed_assets 同比变化 (简单方法)
        # 无去年同期数据时用固定资产的 5% 作为维护性资本开支
        capex_est = fixed_assets * 0.05 if fixed_assets and fixed_assets > 0 else 0

        # 亿为单位
        fcf_est = ocf_ttm - capex_est
        if fcf_est <= 0:
            return {"fcf_yield_pct": round(ocf_ttm / (mcap_yi * 1e8) * 100, 2) if mcap_yi > 0 else 0,
                    "fcf_est_yi": 0,
                    "implied_value": None}

        fcf_yield = fcf_est / (mcap_yi * 1e8) * 100  # 收益率百分比

        # 隐含价值: 假设合理 FCF Yield = 4%
        implied = None
        if total_shares and total_shares > 0:
            target_yield = 0.04
            implied_ev = fcf_est / target_yield
            implied_value = implied_ev / total_shares  # 每股隐含价值
            implied = round(implied_value, 2)

        return {
            "fcf_yield_pct": round(fcf_yield, 2),
            "fcf_est_yi": round(fcf_est / 1e8, 2) if fcf_est > 1e8 else round(fcf_est, 2),
            "implied_value": implied,
        }
