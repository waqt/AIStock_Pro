"""
财务指标模块 — 独立于价量类技术指标的注册体系
自动发现 fundamental/ 下所有 .py 文件, @register_financial 自注册
"""
import os, pkgutil, importlib

from .base import (
    FinancialIndicator,
    FINANCIAL_REGISTRY,
    register_financial,
)

# 自动发现并导入本目录下所有模块 (触发 @register_financial)
__path__ = [os.path.dirname(__file__)]
for _, module_name, _ in pkgutil.iter_modules(__path__):
    if module_name not in ("base", "__init__"):
        importlib.import_module(f".{module_name}", package=__package__)
