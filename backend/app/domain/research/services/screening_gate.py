"""
Hard Filter Gate — 硬性门禁过滤器
只保留不可逾越的硬性排除条件, 所有软性财务判断交给 StageClassifier + FinancialAuditor

V5.16 简化: 删除了 GATE_RULES / get_gate_mode 及 5 个软标记函数。
生命周期分轨判断由 StageClassifier (LLM) 取代, 不再用 rule-based 决策树。
"""
from typing import List, Dict, Tuple


# ═══ 硬性排除规则 ═══════════════════════════════════

HARD_FILTERS = {
    "st_delisted": "已退市或ST",
    "daily_turnover_below_10m": "日均成交额<1000万",
}


def hard_filter(
    candidates: List[Dict],
    stock_info_map: Dict[str, Dict],
) -> Tuple[List[Dict], List[Dict]]:
    """
    硬性门禁过滤 — 只排除明确不合格的候选

    排除条件:
      1. ST / 退市
      2. 日均成交额 < 1000万 (流动性不足)

    返回: (passed, filtered)
      passed 中的候选保留了 flags 和 gate_mode 字段的兼容性
    """
    passed, filtered = [], []

    for c in candidates:
        code = c.get("code", "")
        info = stock_info_map.get(code, {})

        # ── 硬性排除: ST / 退市 ──
        if info.get("is_st") or info.get("is_delisted"):
            filtered.append({**c, "filter_reason": "st_delisted"})
            continue

        # ── 流动性检查: 日均成交额 < 1000万 ──
        try:
            avg_amount = _estimate_daily_amount(code)
            if avg_amount is not None and avg_amount < 10_000_000:
                filtered.append({**c, "filter_reason": f"daily_turnover_below_10m ({avg_amount/1e4:.0f}万)"})
                continue
        except Exception:
            pass  # 指标不可用不阻塞

        passed.append(c)

    return passed, filtered


# ═══ 内部工具 ═══════════════════════════════════════

def _estimate_daily_amount(stock_code: str) -> float:
    """估算日均成交额 ≈ 最新价 × 20日均量 (从指标库)"""
    from app.domain.quant.engine import indicator_store
    indicator = indicator_store.get_latest(stock_code)
    if not indicator:
        return None
    price = float(indicator.get("price", 0) or 0)
    v_ma20 = float(indicator.get("v_ma20", 0) or 0)
    if price and v_ma20:
        return price * v_ma20
    return None
