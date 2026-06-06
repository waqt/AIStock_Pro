"""
定量估值模块 — ValuationMethod 基类 + @register_valuation 注册装饰器

与价量指标 (BaseIndicator) / 财务指标 (FinancialIndicator) 并列的注册体系。

每个估值方法继承 ValuationMethod，加 @register_valuation，
自动注册到 VALUATION_REGISTRY → 自动建 SQLite 列 → 自动暴露 API。

使用方（ValuationRunner）通过 VALUATION_REGISTRY 发现所有方法，
按需 gather_data → compute → store。
"""
from typing import ClassVar, Dict, List


_VALUATION_REGISTRY: Dict[str, type] = {}
"""name → class 的注册表"""


def register_valuation(cls):
    """装饰器: 将 ValuationMethod 子类注册到全局注册表"""
    name = getattr(cls, 'name', None)
    if not name:
        raise ValueError(f"ValuationMethod {cls.__name__} must have a `name` attribute")
    if name in _VALUATION_REGISTRY:
        raise ValueError(f"ValuationMethod name '{name}' already registered")
    _VALUATION_REGISTRY[name] = cls
    return cls


def get_registry() -> Dict[str, type]:
    """获取只读注册表副本"""
    return dict(_VALUATION_REGISTRY)


class ValuationMethod:
    """估值方法基类

    子类只需设置类属性 + 实现 compute()，其余全部自动完成。

    Class Attributes:
        name: 唯一标识，全小写+下划线 (如 "pe_percentile")
        label: 中文显示名 (如 "PE 估值百分位")
        category: relative | absolute | advanced | composite
        description: 方法说明 (60-100字, 可用于 LLM prompt)
        output: 输出字段名列表 (→ SQLite 列名, 自动推导)
        requires: 依赖的 StockValuation / 财务字段名列表
        text_output: output 中属于文本/枚举的字段名子集
        params: 可调参数字典 (可在 API 中覆盖)
        requires_market_data: 是否需要日线 PE/PB 历史序列
        requires_financial_data: 是否需要财务报表数据
    """
    name: ClassVar[str] = ""
    label: ClassVar[str] = ""
    category: ClassVar[str] = ""
    description: ClassVar[str] = ""
    output: ClassVar[List] = []
    requires: ClassVar[List] = []
    text_output: ClassVar[List] = []
    params: ClassVar[Dict] = {}
    requires_market_data: ClassVar[bool] = False
    requires_financial_data: ClassVar[bool] = False
    requires_financial_indicators: ClassVar[bool] = False
    """是否需要 financial_indicators (SQLite) 中的财务指标数据"""

    _field_labels: ClassVar[dict] = {}
    """字段名 → 中文标签映射, 用于前端/数据字典展示"""

    @classmethod
    def compute(cls, **kwargs) -> dict:
        """纯函数: 输入参数 → 输出 dict (字段名→值)

        由 ValuationRunner 调用，kwargs 包含:
        - 从 StockValuation / FinancialStatement / MarketData 加载的数据
        - params 中的可调参数（可通过 API 请求覆盖）

        Returns:
            dict[str, Any]: 与 output 字段一致，缺失返回 None
        """
        raise NotImplementedError

    @classmethod
    def meta(cls) -> dict:
        """返回注册元信息 (注册表 + 数据字典共用)"""
        return {
            "name": cls.name,
            "label": cls.label,
            "category": cls.category,
            "description": cls.description,
            "output": cls.output,
            "text_output": cls.text_output,
            "requires": cls.requires,
            "params": cls.params,
            "requires_market_data": cls.requires_market_data,
            "requires_financial_data": cls.requires_financial_data,
            "requires_financial_indicators": cls.requires_financial_indicators,
        }
