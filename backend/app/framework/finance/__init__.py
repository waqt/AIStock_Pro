"""
framework/finance — 基础金融工具包
纯函数, 零 I/O, Agent 和策略可复用的定价引擎
"""
from app.framework.finance.valuation import (
    pe_valuation,
    pb_valuation,
    ps_valuation,
    ev_ebitda_valuation,
    peg_valuation,
    fcf_yield_valuation,
    scenario_weighted,
    apply_pricing_power_premium,
    apply_quality_adjustment,
    apply_financial_risk_discount,
)
from app.framework.finance.model_map import (
    VALUATION_MODEL_MAP,
    CYCLE_VALUATION_GUIDE,
    match_asset_type,
    get_valuation_method,
)
from app.framework.finance.roiic import (
    compute_roic,
    compute_roiic,
    compute_roe_from_financials,
)
