"""
定量估值模块 — VALUATION_REGISTRY 自动发现

与 INDICATOR_REGISTRY / FINANCIAL_REGISTRY 并列。
遍历 methods/ 下所有子目录，import 每个 .py 文件，
触发 @register_valuation 装饰器完成自动注册。
"""
import os as _os
import pkgutil as _pkgutil
import importlib as _importlib

_pkg_dir = _os.path.dirname(__file__)

# 遍历 methods/ 下所有子目录，import 每个模块 → 触发 @register_valuation
for _root, _dirs, _files in _os.walk(_os.path.join(_pkg_dir, "methods")):
    _rel = _os.path.relpath(_root, _pkg_dir)
    if _rel == ".":
        continue
    _pkg = f".{_rel.replace(_os.sep, '.')}"
    for _, _name, _ in _pkgutil.iter_modules([_root]):
        _importlib.import_module(f"{_pkg}.{_name}", __package__)

from app.domain.quant.valuation.base import get_registry, ValuationMethod

VALUATION_REGISTRY = get_registry()
"""dict[str, type]: 全部已注册的估值方法"""
