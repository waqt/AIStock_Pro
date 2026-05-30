"""
财务指标基类 — 与价量类技术指标完全平行的独立体系
数据源: FinancialStatement (季报) 而非 MarketData (日线)
计算: 外部触发 (Step 6 / 异步任务), 不在 IndicatorRunner 管线内
"""
from typing import Dict, Any, List


class FinancialIndicator:
    """财务指标基类 — 季度频率, 基于财报数据"""

    name: str = ""           # 唯一标识, 全小写+下划线
    label: str = ""          # 中文显示名
    description: str = ""    # 指标含义说明
    judgment: str = ""       # 数据判断方法 (阈值/指南)
    category: str = "fundamental"
    indicator_type: str = "both"    # "moat"(护城河) / "prosperity"(高景气) / "both"
    applicable_stages: list = []    # ["startup","inflection","growth","mature","decline"]
    params: dict = {}        # 可调参数
    output: list = []        # 输出字段名列表
    requires: list = []      # 依赖的 FinancialStatement 字段

    @classmethod
    def compute(cls, financials: list) -> dict:
        """计算财务指标值
        输入: FinancialStatement 季度数据列表 (newest-first, 由调用方从 DB/akshare 加载后传入)
        返回: dict of {field_name: value}
        """
        raise NotImplementedError

    @classmethod
    def meta(cls) -> dict:
        """序列化元信息, 供 /registry API 使用"""
        return {
            "name": cls.name,
            "label": cls.label,
            "description": cls.description,
            "judgment": cls.judgment,
            "category": cls.category,
            "indicator_type": cls.indicator_type,
            "applicable_stages": cls.applicable_stages,
            "params": cls.params,
            "output": cls.output,
            "requires": cls.requires,
        }


# 财务指标注册表 (独立于 INDICATOR_REGISTRY)
FINANCIAL_REGISTRY: Dict[str, type] = {}


def register_financial(cls):
    """注册财务指标到 FINANCIAL_REGISTRY"""
    FINANCIAL_REGISTRY[cls.name] = cls
    return cls
