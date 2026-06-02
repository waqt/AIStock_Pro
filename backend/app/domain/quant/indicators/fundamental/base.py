"""
财务指标基类 — 与价量类技术指标完全平行的独立体系
数据源: FinancialStatement (季报) 而非 MarketData (日线)
计算: 外部触发 (Step 6 / 异步任务), 不在 IndicatorRunner 管线内
"""
from typing import Dict, Any, List, Optional


# ═══ 共享工具 ═══════════════════════════════════════
def _pct(current: float, base: float) -> Optional[float]:
    """计算百分比变化"""
    if base and base != 0:
        return round((current - base) / abs(base) * 100, 2)
    return None


def _safe_div(a: float, b: float) -> float:
    """安全除法, 分母为0 返回 0"""
    return a / b if b and b != 0 else 0


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
    text_output: list = []   # 输出字段中属于文本/枚举类型 (非数值) 的字段名
                             # 存储时作为 TEXT 列, 查询时不参与数值计算

    # 字段单位/含义速查表 (所有注册指标的 output + text_output 综合推导)
    # key=field_name → {"unit": "...", "meaning": "..."}
    _FIELD_META_CACHE = None

    @classmethod
    def compute(cls, financials: list) -> dict:
        """计算财务指标值
        输入: FinancialStatement 季度数据列表 (newest-first, 由调用方从 DB/akshare 加载后传入)
        返回: dict of {field_name: value}
        """
        raise NotImplementedError

    @classmethod
    def _infer_unit(cls, field: str) -> str:
        """根据字段名模式推断单位"""
        text_set = set(cls.text_output)
        if field in text_set:
            return "枚举" if field in ("enum",) else "文本"
        # numeric patterns
        if field.endswith("_pct") or field.endswith("_yoy") or field.endswith("_qoq"):
            return "%"
        if field.endswith("_yi") or "_4q_yi" in field:
            return "亿元"
        if field.endswith("_months"):
            return "月"
        if field in ("roe", "rd_intensity", "gross_margin_pct", "net_margin_pct", "operating_margin_pct",
	                     "working_capital_efficiency"):
            return "%"
        if field in ("m_score",):
            return "分"
        if field in ("scissor_gap", "operating_margin_stability"):
            return "百分点"
        if field == "rd_to_opex":
            return "%"
        if field == "burn_rate_months":
            return "月"
        if "roic" in field or "roiic" in field:
            if field in ("roic", "roiic", "roic_adjusted", "roiic_adjusted"):
                return "小数"
            return "%"
        return "?"

    @classmethod
    def meta(cls) -> dict:
        """序列化元信息, 供 /registry API 使用"""
        per_field = {}
        for f in cls.output:
            per_field[f] = {
                "unit": cls._infer_unit(f),
                "meaning": "",
                "is_text": f in cls.text_output,
            }
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
            "text_output": cls.text_output,
            "output_fields": per_field,
        }


def build_financial_field_registry() -> dict:
    """从 FINANCIAL_REGISTRY 全局推导全部字段的 unit/meaning/is_text 信息。
    供 FinancialQueryService 使用, 替代手写 FIELD_ANNOTATIONS。
    """
    from app.domain.quant.indicators.fundamental import FINANCIAL_REGISTRY
    result = {}
    for name, cls in FINANCIAL_REGISTRY.items():
        for f in cls.output:
            if f not in result:
                result[f] = {
                    "unit": cls._infer_unit(f),
                    "meaning": cls.description[:80] if cls.description else "",
                    "is_text": f in cls.text_output,
                    "source_indicator": name,
                }
    return result


# 财务指标注册表 (独立于 INDICATOR_REGISTRY)
FINANCIAL_REGISTRY: Dict[str, type] = {}


def register_financial(cls):
    """注册财务指标到 FINANCIAL_REGISTRY"""
    FINANCIAL_REGISTRY[cls.name] = cls
    return cls


# 向后兼容别名 (新版统一使用 @register)
register = register_financial
