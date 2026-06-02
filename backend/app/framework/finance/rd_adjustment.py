"""
[DEPRECATED] 研发资本化调整

此文件已废弃，请使用 app.domain.quant.indicators.fundamental._roic_core 代替。
当前作为向后兼容的透传层保留。
"""
import warnings
from app.domain.quant.indicators.fundamental._roic_core import adjust_rd_capitalization

warnings.warn(
    "framework/finance/rd_adjustment.py is deprecated. "
    "Use domain/quant/indicators/fundamental/_roic_core instead.",
    DeprecationWarning, stacklevel=2,
)

__all__ = ["adjust_rd_capitalization"]
