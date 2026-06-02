"""
财务指标模块 — 统一注册表
自动发现 fundamental/ 下所有子目录中的 .py 文件, @register 自注册

所有财务指标算子统一放在以下子目录中:
  profitability/  — 利润率/ROE/ROIC/ROIIC/R&D
  growth/         — 营收/利润/剪刀差增长
  health/         — 合同负债/存货/OCF健康度
  quality/        — Beneish M-Score/审计
  profile/        — 公司画像 (数据质量/营收规模)

数据方向: 所有 compute() 输入均为 newest-first (index 0 = 最新季度)
"""
import os, pkgutil, importlib

from .base import (
    FinancialIndicator,
    FINANCIAL_REGISTRY,
    register,
    register_financial,
    _pct,
    _safe_div,
)

# 递归自动发现所有子目录的 .py 模块 (fundamental/ 根目录自身被跳过)
__path__ = [os.path.dirname(__file__)]
for root, dirs, files in os.walk(__path__[0]):
    rel = os.path.relpath(root, __path__[0])
    if rel == ".":
        continue  # 跳过根目录自身
    pkg = f".{rel.replace(os.sep, '.')}"
    for _, name, _ in pkgutil.iter_modules([root]):
        importlib.import_module(f"{pkg}.{name}", __package__)
