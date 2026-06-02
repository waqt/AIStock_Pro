"""
财务指标库 — 透传层

DDD EXCEPTION: framework 层 re-export domain/quant 的注册表,
用于 pipeline (domain/research) 通过 framework 路径访问财务指标。

V6 计划: 将 financial_data_view.py 移至 domain 层, 此文件即移除。
"""
from app.domain.quant.indicators.fundamental import (
    FINANCIAL_REGISTRY as FINANCIAL_INDICATOR_REGISTRY,
    register,
    FinancialIndicator,
)
