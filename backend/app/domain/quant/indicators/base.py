"""指标算子基类 — 类属性即元信息, @register 装饰器自动注册"""
import pandas as pd
from typing import Dict

_registry: Dict[str, type] = {}


def register(cls):
    """装饰器: 将指标类自动注册到 _registry"""
    _registry[cls.name] = cls
    return cls


def get_registry() -> dict:
    return _registry


class BaseIndicator:
    """指标算子基类 — 纯函数, 向量化, 无状态"""
    name: str = ""
    label: str = ""     # 中文名称
    category: str = ""
    params: dict = {}
    output: list = []
    requires: list = []

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
        }
