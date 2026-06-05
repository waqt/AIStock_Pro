"""
TechnicalQueryService — Agent/Strategy 可调用的技术指标查询与组装服务

设计目的:
  价量指标目前只能通过低阶 indicator_store 函数直接查询 (get_latest/get_history)。
  本服务提供更灵活的模式:
    1. 暴露数据字典 (指标注册表分组 + 字段 unit/meaning)
    2. 按指标名查询 (自动展开至 output 字段)
    3. 格式化文本供 LLM prompt 注入 (供后续择时智能体使用)

API 端点:
    GET  /api/quant/indicators/catalog   — 数据字典 (已缓存)
    POST /api/quant/indicators/query     — 按需查询

用法:
    svc = TechnicalQueryService()
    catalog = svc.get_catalog()
    data = svc.query("600519", indicators=["macd_cross"])
    series = svc.get_time_series("600519", ["macd_cross"], days=120)
    prompt = svc.format_catalog_for_prompt()
"""
from typing import List, Dict, Optional, Any
from app.framework.logger import logger


# ═══ 字段含义标注 ═══
_FIELD_MEANINGS: Dict[str, str] = {
    # price
    "price": "收盘价",
    # trend
    "ma5": "5日均线", "ma10": "10日均线", "ma20": "20日均线",
    "ma60": "60日均线", "ma120": "120日均线", "ma250": "250日均线",
    "macd": "MACD快线(DIF)", "macd_signal": "MACD慢线(DEA)",
    "macd_hist": "MACD柱状图",
    "k": "KDJ指标K值", "d": "KDJ指标D值", "j": "KDJ指标J值",
    # momentum
    "rsi": "相对强弱指标RSI", "atr": "平均真实波幅ATR",
    "cci": "商品通道指标CCI",
    # volatility
    "bb_upper": "布林上轨", "bb_mid": "布林中轨", "bb_lower": "布林下轨",
    "bb_width": "布林带宽",
    # volume
    "obv": "能量潮OBV",
    "v_ma5": "5日均量", "v_ma10": "10日均量", "v_ma20": "20日均量",
    "vwap": "成交量加权均价",
    # crowding
    "turnover_20d": "20日换手率", "turnover_120d": "120日换手率",
    "crowding_ratio": "拥挤度", "sharpe_60d": "60日夏普比率",
    # chip
    "chip_concentration": "筹码集中度", "chip_peak_price": "筹码峰值价格",
    "chip_avg_cost": "筹码平均成本", "chip_is_single_peak": "是否单峰",
    "chip_pattern": "筹码形态", "chip_signal": "筹码信号",
    # fib
    "fib_high": "斐波那契参考高点", "fib_low": "斐波那契参考低点",
    "fib_23_6": "斐波那契23.6%", "fib_38_2": "斐波那契38.2%",
    "fib_50_0": "斐波那契50.0%", "fib_61_8": "斐波那契61.8%",
    "fib_78_6": "斐波那契78.6%",
}

_CATEGORY_LABELS: Dict[str, str] = {
    "trend": "趋势", "momentum": "动量", "volatility": "波动",
    "volume": "量能", "crowding": "拥挤度", "chip": "筹码",
}

# 缓存
_catalog_cache: Optional[Dict[str, Any]] = None


class TechnicalQueryService:

    @staticmethod
    def get_catalog() -> Dict[str, Any]:
        """返回全量数据字典: 按 category 分组的已注册指标, 含字段元信息"""
        global _catalog_cache
        if _catalog_cache is not None:
            return _catalog_cache

        from app.domain.quant.indicators import INDICATOR_REGISTRY

        indicators = {}
        for name, cls in INDICATOR_REGISTRY.items():
            output_fields = []
            text_set = set(getattr(cls, 'text_output', []))
            for f in getattr(cls, 'output', []):
                output_fields.append({
                    "field": f,
                    "unit": _infer_unit(f),
                    "meaning": _FIELD_MEANINGS.get(f, ""),
                    "is_text": f in text_set,
                })
            indicators[name] = {
                "label": getattr(cls, 'label', name),
                "category": getattr(cls, 'category', 'other'),
                "params": getattr(cls, 'params', {}),
                "output_fields": output_fields,
                "output_field_names": getattr(cls, 'output', []),
                "requires": getattr(cls, 'requires', []),
            }

        # 按 category 分组
        grouped = {}
        for name, meta in indicators.items():
            cat = meta.get("category", "other")
            grouped.setdefault(cat, []).append(name)

        _catalog_cache = {
            "indicators": indicators,
            "summary": {
                "total_indicators": len(indicators),
                "categories": {cat: grouped[cat] for cat in sorted(grouped.keys())},
            },
        }
        return _catalog_cache

    @staticmethod
    def format_catalog_for_prompt() -> str:
        """格式化数据字典为纯文本, 供 LLM prompt 注入"""
        catalog = TechnicalQueryService.get_catalog()
        lines = ["## 可用技术指标 (价量)", ""]
        lines.append("可通过 indicators 参数按需请求以下指标。")
        lines.append("")

        grouped = catalog["summary"]["categories"]
        for cat in sorted(grouped.keys()):
            label = _CATEGORY_LABELS.get(cat, cat)
            lines.append(f"### {label}")
            lines.append("")
            for name in grouped[cat]:
                meta = catalog["indicators"][name]
                fields_str = ", ".join(
                    f"`{f['field']}` ({f['unit']})"
                    for f in meta["output_fields"]
                )
                lines.append(f"- **{meta['label']}** ({name}): {fields_str}")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def query(code: str, indicators: Optional[List[str]] = None) -> Dict[str, Any]:
        """按指标名查询最新值. indicators=None 返回全部字段"""
        from app.domain.quant.engine import indicator_store
        row = indicator_store.get_latest(code)
        if not row:
            return {"stock_code": code, "error": "No indicator data"}

        result = {"stock_code": code, "trade_date": row.get("trade_date")}
        if indicators:
            from app.domain.quant.indicators import INDICATOR_REGISTRY
            for name in indicators:
                cls = INDICATOR_REGISTRY.get(name)
                if cls:
                    for f in getattr(cls, 'output', []):
                        if f in row:
                            result[f] = row[f]
        else:
            for k, v in row.items():
                if k not in ("stock_code", "trade_date"):
                    result[k] = v
        return result

    @staticmethod
    def query_batch(codes: List[str],
                    indicators: Optional[List[str]] = None) -> Dict[str, Dict]:
        """批量查询多只股票的最新指标值"""
        from app.domain.quant.engine import indicator_store
        rows = indicator_store.get_latest_for_codes(codes)
        if not rows:
            return {}

        from app.domain.quant.indicators import INDICATOR_REGISTRY
        result = {}
        for row in rows:
            code = row.get("stock_code")
            if not code:
                continue
            data = {"stock_code": code, "trade_date": row.get("trade_date")}
            if indicators:
                for name in indicators:
                    cls = INDICATOR_REGISTRY.get(name)
                    if cls:
                        for f in getattr(cls, 'output', []):
                            if f in row:
                                data[f] = row[f]
            else:
                for k, v in row.items():
                    if k not in ("stock_code", "trade_date"):
                        data[k] = v
            result[code] = data
        return result

    @staticmethod
    def get_time_series(code: str, indicators: List[str],
                        days: int = 120) -> Dict[str, Any]:
        """获取时间序列数据"""
        from app.domain.quant.engine import indicator_store
        from app.domain.quant.indicators import INDICATOR_REGISTRY

        fields = []
        for name in indicators:
            cls = INDICATOR_REGISTRY.get(name)
            if cls:
                fields.extend(getattr(cls, 'output', []))
        if not fields:
            return {"stock_code": code, "dates": [], "fields": {}}
        return indicator_store.get_history(code, fields, days)


def _infer_unit(field: str) -> str:
    """从字段名推断展示单位"""
    price_fields = {"price", "bb_upper", "bb_mid", "bb_lower", "vwap",
                    "chip_peak_price", "chip_avg_cost", "atr",
                    "fib_high", "fib_low"}
    pct_fields = {"crowding_ratio", "turnover_20d", "turnover_120d",
                  "chip_concentration", "bb_width",
                  "fib_23_6", "fib_38_2", "fib_50_0", "fib_61_8", "fib_78_6"}
    index_fields = {"rsi", "k", "d", "j"}
    ratio_fields = {"sharpe_60d", "chip_is_single_peak"}

    if field in price_fields:
        return "price"  # 价格(元)
    if field in pct_fields:
        return "%"
    if field in index_fields:
        return "index"  # 无量纲指数
    if field in ratio_fields:
        return "ratio"  # 比率
    if field.startswith("ma") or field in ("macd", "macd_signal", "macd_hist"):
        return "price"
    if field.startswith("v_"):
        return "volume"
    return "?"
