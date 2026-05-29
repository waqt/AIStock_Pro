"""
财务指标基类 — 与价量类技术指标完全平行的独立体系
数据源: FinancialStatement (季报) 而非 MarketData (日线)
计算: 外部触发 (Step 6), 不在 IndicatorRunner 管线内
"""
from typing import Dict, Any


class FinancialIndicator:
    """财务指标基类 — 季度频率, 基于财报数据"""

    name: str = ""           # 唯一标识, 全小写+下划线
    label: str = ""          # 中文显示名
    category: str = "fundamental"
    params: dict = {}        # 可调参数
    output: list = []        # 输出字段名列表
    requires: list = []      # 依赖的 FinancialStatement 字段

    @classmethod
    def compute(cls, financials: list) -> dict:
        """计算财务指标值
        输入: FinancialStatement 季度数据列表 (由调用方从 DB/akshare 加载后传入)
        返回: dict of {field_name: value}
        """
        raise NotImplementedError


# 财务指标注册表 (独立于 INDICATOR_REGISTRY)
FINANCIAL_REGISTRY: Dict[str, type] = {}


def register_financial(cls):
    """注册财务指标到 FINANCIAL_REGISTRY"""
    FINANCIAL_REGISTRY[cls.name] = cls
    return cls
