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
        category: relative | absolute | advanced | composite | dynamic
        description: 方法说明 (60-100字, 可用于 LLM prompt)
        judgment: 数据判读方法 — 阈值/结论判定指南 (如 "上行空间>20%→低估")
        applicable_scenarios: 适用场景 (如 "成熟稳定公司, 有持续派息记录")
        limitations: 局限性说明 (如 "不适用于亏损公司或不分红公司")
        output: 输出字段名列表 (→ SQLite 列名, 自动推导)
        requires: 依赖的 StockValuation / 财务字段名列表
        text_output: output 中属于文本/枚举的字段名子集
        params: 可调参数字典 (可在 API 中覆盖)
        requires_market_data: 是否需要日线 PE/PB 历史序列
        requires_financial_data: 是否需要财务报表数据
        requires_financial_indicators: 是否需要 financial_indicators SQLite 数据
    """
    name: ClassVar[str] = ""
    label: ClassVar[str] = ""
    category: ClassVar[str] = ""
    description: ClassVar[str] = ""
    judgment: ClassVar[str] = ""
    """判读指南: 如何解读输出值, 阈值说明 (如 "PE百分位<20→低估, >80→高估")"""
    applicable_scenarios: ClassVar[str] = ""
    """适用场景: 适合哪类公司/行业/发展阶段 (如 "成熟稳定派息公司")"""
    limitations: ClassVar[str] = ""
    """局限性: 该方法不适用的情况"""
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

    _field_meaning_overrides: ClassVar[dict] = {}
    """字段名 → 详细含义说明 (覆盖自动生成的默认含义)"""

    @classmethod
    def is_applicable(cls, **kwargs) -> bool:
        """判断该方法是否适用于当前股票 (Runner 在 compute 前调用)

        默认返回 True。特定情景方法 (如生物医药 rNPV) 可重写此方法
        在 kwargs 中检查行业/数据特征后选择性跳过。
        """
        return True

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
    def _infer_unit(cls, field: str) -> str:
        """根据字段名模式推断单位"""
        text_set = set(cls.text_output)
        if field in text_set:
            return "文本"
        # price / value / per share
        if field.endswith("_price") or field in ("graham_number", "nav_per_share",
            "ddm_value", "rim_value", "rgv_target_price", "gm_target_price",
            "scissor_target_price", "dol_target_price", "three_stage_value",
            "growth_peg_target_price"):
            return "¥"
        # percentage / rate / yield
        if field.endswith("_pct") or field.endswith("_yield") or field.endswith("_rate"):
            return "%"
        if field.endswith("_percentile"):
            return "% (百分位)"
        if field.endswith("_growth") or field.endswith("_upside"):
            return "%"
        if field.endswith("_discount") or field.endswith("_premium"):
            return "%"
        # PE / PB / PS / ratio (multiples)
        if field.endswith("_pe") or field.endswith("_pb") or field.endswith("_ps"):
            return "倍"
        if field.endswith("_ratio") or field.endswith("_mult"):
            return "倍"
        if field == "peg_ratio" or field == "growth_peg_target":
            return "倍"
        # "亿元" for _yi fields
        if field.endswith("_yi") or "_4q_yi" in field or "_value_yi" in field:
            return "亿元"
        if field.endswith("_value") and field not in ("ddm_value", "rim_value"):
            return "亿元"
        if field == "fcf_est_yi":
            return "亿元"
        if field == "ev_yi" or field == "ic_yi":
            return "亿元"
        # scores
        if field.endswith("_score") or field == "m_score":
            return "分"
        if field in ("valuation_score", "scissor_phase_score", "gm_quality_score"):
            return "分"
        # years
        if field.endswith("_years"):
            return "年"
        return "?"

    @classmethod
    def get_field_meaning(cls, field: str) -> str:
        """获取字段含义说明"""
        if field in cls._field_meaning_overrides:
            return cls._field_meaning_overrides[field]
        if field in cls._field_labels:
            return cls._field_labels[field]
        return ""

    @classmethod
    def meta(cls) -> dict:
        """返回注册元信息 (注册表 + 数据字典共用)"""
        per_field = {}
        for f in cls.output:
            per_field[f] = {
                "unit": cls._infer_unit(f),
                "meaning": cls.get_field_meaning(f),
                "is_text": f in cls.text_output,
            }
        return {
            "name": cls.name,
            "label": cls.label,
            "category": cls.category,
            "description": cls.description,
            "judgment": cls.judgment,
            "applicable_scenarios": cls.applicable_scenarios,
            "limitations": cls.limitations,
            "output": cls.output,
            "text_output": cls.text_output,
            "requires": cls.requires,
            "params": cls.params,
            "requires_market_data": cls.requires_market_data,
            "requires_financial_data": cls.requires_financial_data,
            "requires_financial_indicators": cls.requires_financial_indicators,
            "output_fields": per_field,
        }
