"""策略库 — 自动发现 + 导出 STRATEGY_REGISTRY"""
import importlib, pkgutil, os

_pkg_dir = os.path.dirname(__file__)
for _cat in ["traditional", "ai_chain"]:
    _cat_dir = os.path.join(_pkg_dir, _cat)
    if os.path.isdir(_cat_dir):
        for _, _name, _ in pkgutil.iter_modules([_cat_dir]):
            importlib.import_module(f".{_cat}.{_name}", __package__)

from .base import get_registry
STRATEGY_REGISTRY = get_registry()
