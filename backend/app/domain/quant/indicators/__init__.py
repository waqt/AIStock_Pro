"""指标库 — 自动发现并导入所有算子, 导出 INDICATOR_REGISTRY"""
import importlib, pkgutil, os

# 递归自动发现: 扫描子目录, import 所有 .py 文件
_pkg_dir = os.path.dirname(__file__)
for _root, _dirs, _files in os.walk(_pkg_dir):
    _rel = os.path.relpath(_root, _pkg_dir)
    if _rel == ".":
        continue  # skip base dir itself (handled below)
    _pkg = f".{_rel.replace(os.sep, '.')}"
    for _, _name, _ in pkgutil.iter_modules([_root]):
        importlib.import_module(f"{_pkg}.{_name}", __package__)

from .base import get_registry
INDICATOR_REGISTRY = get_registry()
