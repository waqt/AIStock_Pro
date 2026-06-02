"""
[DEPRECATED] ROIC/ROIIC 核心计算

此文件已废弃，请使用 app.domain.quant.indicators.fundamental._roic_core 代替。
当前作为向后兼容的透传层保留。
"""
import warnings
from app.domain.quant.indicators.fundamental._roic_core import (
    compute_roic,
    compute_roiic,
    compute_roe_from_financials,
    compute_nopat,
    compute_invested_capital,
    adjust_rd_capitalization,
)

warnings.warn(
    "framework/finance/roiic.py is deprecated. "
    "Use domain/quant/indicators/fundamental/_roic_core instead.",
    DeprecationWarning, stacklevel=2,
)

__all__ = [
    "compute_roic",
    "compute_roiic",
    "compute_roe_from_financials",
    "compute_nopat",
    "compute_invested_capital",
    "adjust_rd_capitalization",
]
