"""指标算子基类 — 类属性即元信息, @register 装饰器自动注册"""
import pandas as pd
from typing import Dict
from app.framework.logger import logger

_registry: Dict[str, type] = {}

# 所有指标共知的 OHLCV 基础列, 用于 requires 校验
BASE_FIELDS = {'open', 'high', 'low', 'close', 'volume', 'amount', 'trade_date'}


def register(cls):
    """装饰器: 将指标类自动注册到 _registry, 含导入时校验"""
    if not cls.name:
        raise ValueError(f"[IndicatorRegistry] Indicator {cls.__name__} has empty 'name'")
    if cls.name in _registry:
        raise ValueError(
            f"[IndicatorRegistry] Duplicate indicator name '{cls.name}' "
            f"(existing: {_registry[cls.name].__name__}, new: {cls.__name__})"
        )
    _registry[cls.name] = cls
    return cls


def get_registry() -> dict:
    """返回注册表, 并在首次调用时校验依赖完整性"""
    if not hasattr(get_registry, '_validated'):
        _validate_registry()
        get_registry._validated = True
    return _registry


def _validate_registry():
    """校验所有已注册指标的 requires 字段是否存在上游产出"""
    known_fields = set()
    for cls in _registry.values():
        known_fields.update(cls.output)
    for name, cls in _registry.items():
        for req in cls.requires:
            if req not in known_fields and req not in BASE_FIELDS and not req.startswith('_'):
                logger.warning(
                    f"[IndicatorRegistry] '{name}' requires '{req}' — "
                    f"not produced by any registered indicator (may be loaded later)"
                )


class BaseIndicator:
    """指标算子基类 — 纯函数, 向量化, 无状态"""
    name: str = ""
    label: str = ""     # 中文名称
    category: str = ""
    params: dict = {}
    output: list = []
    requires: list = []
    text_output: list = []   # output 中属于文本/枚举类型的字段名, 存储为 TEXT 列

    @classmethod
    def compute(cls, df: pd.DataFrame) -> dict:
        raise NotImplementedError

    @classmethod
    def meta(cls) -> dict:
        return {
            "name": cls.name, "label": cls.label,
            "category": cls.category,
            "params": cls.params, "output": cls.output,
            "requires": cls.requires,
            "text_output": cls.text_output,
        }
