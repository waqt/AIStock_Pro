"""
DEPRECATED — 此文件仅保留向后兼容, 所有财务指标已迁移至
  domain/quant/indicators/fundamental/

使用方式 (旧代码仍可导入):
  from app.framework.finance.indicators.base import (
      BaseFinancialIndicator, register, get_registry,
      FINANCIAL_INDICATOR_REGISTRY,
      _pct, _safe_div,
  )
  等效于 domain 版本。将在 V6 中移除。
"""
from app.domain.quant.indicators.fundamental.base import (
    FinancialIndicator as BaseFinancialIndicator,
    register,
    FINANCIAL_REGISTRY as FINANCIAL_INDICATOR_REGISTRY,
    _pct,
    _safe_div,
)


def get_registry() -> dict:
    return FINANCIAL_INDICATOR_REGISTRY


# 标注 deprecation —— 通知下游调用方
import warnings
warnings.warn(
    "framework/finance/indicators/base.py is DEPRECATED. "
    "Use domain/quant/indicators/fundamental/ instead.",
    DeprecationWarning, stacklevel=2,
)
