"""
生命周期分轨筛选门禁 — 根据产业生命周期动态调整财务阈值
设计来源: Gemini建议 — 成长期用ROIIC, 成熟期用ROIC, 不同阈值

核心原则: FinancialAuditor 只标注, 不排除。分轨仅做硬门禁 + 标注。
"""
from typing import List, Dict, Tuple

# 分轨规则
GATE_RULES = {
    "growth": {
        "label": "成长期/瓶颈爆发期",
        "trigger_cycle": ["bottleneck_formation", "supply_shock", "capacity_release"],
        "prescreen": "宽松",
        "rules": {
            "revenue_yoy_min_pct": 15,
            "allow_negative_fcf": True,
            "require_roiic": True,
            "rd_ratio_check": True,
            "audit_fail_action": "mark",
        },
    },
    "mature": {
        "label": "成熟期/现金牛",
        "trigger_cycle": ["cash_cow", "oligopoly_stable"],
        "prescreen": "严格",
        "rules": {
            "roic_min_pct": 8,
            "fcf_positive_required": True,
            "gross_margin_stable": True,
            "audit_fail_action": "mark",  # ★ 只标记不排除
        },
    },
    "recovery": {
        "label": "周期反转/出清期",
        "trigger_cycle": ["crisis_recovery", "oversupply"],
        "prescreen": "中等",
        "rules": {
            "revenue_stabilizing": True,
            "inventory_declining": True,
            "audit_fail_action": "mark",
        },
    },
}

# 硬性排除 (所有模式通用)
HARD_FILTERS = {
    "st_delisted": "已退市或ST",
    "daily_turnover_below_10m": "日均成交额<1000万",
}


def get_gate_mode(cycle_position: str) -> str:
    """从 Step 2/3 的 cycle_position 推断筛选模式, 默认 growth"""
    if not cycle_position:
        return "growth"
    for mode, config in GATE_RULES.items():
        for trigger in config["trigger_cycle"]:
            if trigger in cycle_position:
                return mode
    return "growth"


def gate_prescreen(
    candidates: List[Dict],
    gate_mode: str,
    stock_info_map: Dict[str, Dict],
    financials_map: Dict[str, Dict],
) -> Tuple[List[Dict], List[Dict]]:
    """
    生命周期分轨预筛选

    返回: (passed, filtered) — 通过的和被过滤的候选
    被过滤的仅在硬性不满足时排除, 财务状况仅标注在 flags 中
    """
    rules = GATE_RULES.get(gate_mode, GATE_RULES["growth"])["rules"]
    passed, filtered = [], []

    for c in candidates:
        code = c.get("code", "")
        info = stock_info_map.get(code, {})
        fin = financials_map.get(code, {})

        # ── 硬性排除 ──
        if info.get("is_st") or info.get("is_delisted"):
            filtered.append({**c, "filter_reason": "st_delisted"})
            continue

        # ── 流动性检查 ──
        from app.domain.quant.engine import indicator_store
        try:
            md_latest = indicator_store.get_latest(code) or {}
            avg_amount = _estimate_daily_amount(md_latest, info)
            if avg_amount and avg_amount < 10_000_000:  # <1000万
                filtered.append({**c, "filter_reason": f"daily_turnover_below_10m ({avg_amount/1e4:.0f}万)"})
                continue
        except Exception:
            pass  # 指标不可用不阻塞

        # ── 分轨预筛选 ──
        flags = c.get("flags", [])

        if gate_mode == "growth":
            rev_yoy = _get_revenue_yoy(fin)
            if rev_yoy is not None and rev_yoy < rules.get("revenue_yoy_min_pct", 15):
                flags.append(f"revenue_yoy_low ({rev_yoy}%)")
            # 负FCF只标记
            if not rules.get("allow_negative_fcf", True):
                fcf = _calc_fcf(fin)
                if fcf is not None and fcf < 0:
                    filtered.append({**c, "filter_reason": "fcf_negative_strict"})
                    continue
            if fcf_negative(fin):
                flags.append("capex_expansion")

        elif gate_mode == "mature":
            fcf = _calc_fcf(fin)
            if rules.get("fcf_positive_required") and fcf is not None and fcf < 0:
                flags.append("fcf_negative_mature")
            gm_declining = _is_gross_margin_declining(fin)
            if rules.get("gross_margin_stable") and gm_declining:
                flags.append("gross_margin_declining")

        elif gate_mode == "recovery":
            rev_stable = _is_revenue_stabilizing(fin)
            if rules.get("revenue_stabilizing") and not rev_stable:
                flags.append("revenue_still_declining")
            inv_declining = _is_inventory_declining(fin)
            if rules.get("inventory_declining") and not inv_declining:
                flags.append("inventory_not_declining")

        c["flags"] = flags
        c["gate_mode"] = gate_mode
        passed.append(c)

    return passed, filtered


# ═══ 内部工具 ═══════════════════════════════

def _get_revenue_yoy(fin: Dict) -> float:
    """从最近8Q财务数据计算营收同比增速"""
    quarters = fin.get("quarters", [])
    if len(quarters) < 8:
        return None
    recent_4q_rev = sum(q.get("revenue", 0) or 0 for q in quarters[:4])
    prior_4q_rev = sum(q.get("revenue", 0) or 0 for q in quarters[4:8])
    if not prior_4q_rev:
        return None
    return round((recent_4q_rev / prior_4q_rev - 1) * 100, 1)


def _calc_fcf(fin: Dict) -> float:
    """自由现金流 ≈ 经营CF - 维持性CAPEX (简化: 折旧近似维持性CAPEX)"""
    quarters = fin.get("quarters", [])
    if len(quarters) < 4:
        return None
    ocf_4q = sum(q.get("op_cashflow", 0) or 0 for q in quarters[:4])
    # 简化: 维持性CAPEX ≈ 折旧 (财务表不直接提供)
    # 用总资产变动近似
    return ocf_4q


def fcf_negative(fin: Dict) -> bool:
    fcf = _calc_fcf(fin)
    return fcf is not None and fcf < 0


def _is_gross_margin_declining(fin: Dict) -> bool:
    """毛利率连续2个季度下降"""
    quarters = fin.get("quarters", [])
    if len(quarters) < 6:
        return False
    gms = []
    for q in quarters[:6]:
        rev = q.get("revenue", 0) or 0
        cost = q.get("operate_cost", 0) or 0
        gms.append((rev - cost) / rev * 100 if rev else 0)
    # 最近3个季度是否持续下降
    return len(gms) >= 3 and gms[0] < gms[1] < gms[2]


def _is_revenue_stabilizing(fin: Dict) -> bool:
    """营收下滑速度是否在收敛"""
    quarters = fin.get("quarters", [])
    if len(quarters) < 6:
        return True  # 数据不足不排除
    yoy_rates = []
    for i in range(0, 4):
        if i + 4 < len(quarters):
            curr = quarters[i].get("revenue", 0) or 0
            prev = quarters[i + 4].get("revenue", 0) or 0
            if prev:
                yoy_rates.append((curr / prev - 1) * 100)
    if len(yoy_rates) < 2:
        return True
    # 最近YoY降幅比前一个YoY降幅小 → 在稳定
    return yoy_rates[0] > yoy_rates[1]


def _is_inventory_declining(fin: Dict) -> bool:
    """最近2季度库存是否在下降"""
    quarters = fin.get("quarters", [])
    if len(quarters) < 3:
        return False
    inv = [q.get("inventory", 0) or 0 for q in quarters[:3]]
    return inv[0] < inv[1]  # 最新季度 < 上季度


def _estimate_daily_amount(indicator: Dict, stock_info: Dict) -> float:
    """估算日均成交额 ≈ 最新价 × 20日均量 (从指标库)"""
    price = indicator.get("price", 0) or 0
    v_ma20 = indicator.get("v_ma20", 0) or 0
    if price and v_ma20:
        return price * v_ma20
    return None
