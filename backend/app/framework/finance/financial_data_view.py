"""
Financial Data View — 全方位财务数据视图构建器
V5.16: 底层计算委托给 FINANCIAL_INDICATOR_REGISTRY 中的 15 个注册指示器

后向兼容导出:
  build_financial_data_view  — 结构化视图 (StageClassifier 使用)
  compute_quarterly_metrics  — 逐季度中间数据 (FinancialAuditor 使用)
  compute_beneish_m_score   — M-Score (FinancialAuditor 使用)
  compute_audit             — 综合审计判定 (FinancialAuditor 使用)
  compute_all_indicators    — ★ 注册表所有指示器的扁平结果
"""
from typing import List, Dict, Optional
from app.framework.finance.indicators import FINANCIAL_INDICATOR_REGISTRY
from app.framework.logger import logger


# ═══ 内部工具 ═══════════════════════════════════════

def _pct(current: float, base: float) -> Optional[float]:
    """计算百分比变化"""
    if base and base != 0:
        return round((current - base) / abs(base) * 100, 2)
    return None


# ═══ 逐季度指标计算 (中间数据, 非指示器) ═══════════

def compute_quarterly_metrics(quarters: List[Dict]) -> List[Dict]:
    """为每个季度计算中间指标（仅保留未被注册指标覆盖的计算）

    已由注册指标覆盖的计算（通过 compute_all_indicators 获取）:
      rev_qoq    → revenue_qoq 指标
      rev_yoy    → revenue_yoy / revenue_growth 指标
      profit_yoy → profit_growth 指标
      scissor_gap → scissor_gap 指标

    仍保留的手算（单季度视角，无直接指标对应或仅作降级用）:
      profit_qoq       — 利润环比（波动大，指标系统无直接对应）
      net_margin       — 单季度净利率（与指标 TTM 口径不同）
      ocf_profit_ratio — 单季度 OCF/利润（指标是 TTM 版）
      inventory_revenue_ratio — 单季度库存/营收（指标是 TTM/营收）

    输入: newest-first (i=0=最新季度)
    输出: 同样 newest-first 顺序
    """
    results = []
    for i, q in enumerate(quarters):
        rev = float(q.get("revenue", 0) or 0)
        profit = float(q.get("profit", 0) or 0)
        inv = float(q.get("inventory", 0) or 0)
        ocf = float(q.get("op_cashflow", 0) or 0)

        m = {"report_date": q.get("report_date", ""),
             "revenue": rev, "profit": profit, "op_cashflow": ocf,
             "inventory": inv}

        # profit QoQ: vs 上一季度 (保留: 无直接指标对应)
        if i + 1 < len(quarters):
            m["profit_qoq"] = _pct(profit, float(quarters[i + 1].get("profit", 0) or 0))
        else:
            m["profit_qoq"] = None

        # 单季度净利率 (保留: TTM 口径与单季口径不同)
        m["net_margin"] = round(profit / rev * 100, 1) if rev > 0 else 0.0

        # 单季度 OCF/利润比 (保留: 指标是 TTM, 此处是单季)
        m["ocf_profit_ratio"] = round(ocf / profit, 2) if profit and profit > 0 else None

        # 单季度库存/营收 (保留: 指标是 TTM/营收)
        m["inventory_revenue_ratio"] = round(inv / rev, 2) if rev > 0 else None

        results.append(m)

    return results


# ═══ 后向兼容: 委托注册指示器 ═══════════════════════

def compute_beneish_m_score(quarters: List[Dict]) -> Dict:
    """后向兼容: 委托至 beneish_m_score 注册指示器"""
    cls = FINANCIAL_INDICATOR_REGISTRY.get("beneish_m_score")
    if cls:
        return cls.compute(quarters)
    return {"m_score": None, "error": "beneish_m_score not registered"}


def compute_audit(metrics: List[Dict], quarters: List[Dict]) -> Dict:
    """审计 — 已被移除注册表, 返回默认值; 审计逻辑由 pipeline 的 FinancialAuditor agent 承担"""
    return {"verdict": "SKIP", "score": 0, "metrics": metrics}


# ═══ 注册表全量计算 ════════════════════════════════

def compute_all_indicators(quarters: List[Dict]) -> Dict:
    """遍历 FINANCIAL_INDICATOR_REGISTRY, 返回所有已注册指示器的扁平结果

    Returns:
        {output_field: value, ...}  — 所有指示器 output 字段的并集
        {"_errors": {name: error}}  — 计算失败的指示器
    """
    if not quarters:
        return {"_error": "no_quarters"}

    result = {}
    errors = {}
    for name, cls in sorted(FINANCIAL_INDICATOR_REGISTRY.items()):
        try:
            output = cls.compute(quarters)
            if isinstance(output, dict):
                # 扁平化: m_score_components → 保持嵌套但 prefix 避免冲突
                result.update(output)
        except Exception as e:
            errors[name] = str(e)
            logger.warning(f"[FinDataView] {name} failed: {e}")

    if errors:
        result["_indicator_errors"] = errors
    return result


# ═══ 结构化视图组装 ════════════════════════════════

def _company_profile(quarters: List[Dict], ir: Dict) -> Dict:
    """公司画像 (优先用注册指示器结果 ir, 降级自算)"""
    return {
        "revenue_4q_yi": ir.get("revenue_4q_yi") or (
            round(sum(float(q.get("revenue", 0) or 0) for q in quarters[:4]) / 1e8, 2)
            if quarters else None),
        "profit_4q_yi": ir.get("profit_4q_yi") or (
            round(sum(float(q.get("profit", 0) or 0) for q in quarters[:4]) / 1e8, 2)
            if quarters else None),
        "revenue_scale": ir.get("revenue_scale", "unknown"),
        "rd_intensity_pct": ir.get("rd_intensity"),
        "gross_margin_pct": ir.get("gross_margin_pct"),
        "net_margin_pct": ir.get("net_margin_pct"),
        "quarters_available": len(quarters) if quarters else 0,
    }


def _growth_trajectory(metrics: List[Dict], ir: Dict) -> Dict:
    """增长轨迹 (优先用注册指示器, 降级自算)"""
    if ir.get("rev_yoy_latest") is not None:
        return {
            "rev_yoy_latest": ir.get("rev_yoy_latest"),
            "profit_yoy_latest": ir.get("profit_yoy_latest"),
            "rev_qoq_latest": ir.get("rev_qoq_latest"),
            "profit_qoq_latest": ir.get("profit_qoq_latest"),
            "avg_rev_yoy_4q": ir.get("avg_rev_yoy_4q"),
            "avg_profit_yoy_4q": ir.get("avg_profit_yoy_4q"),
        }
    # 降级: 从 metrics 自算
    if not metrics:
        return {}
    yoy_q = [m for m in metrics if m.get("rev_yoy") is not None]
    if not yoy_q:
        return {}
    latest = metrics[0]
    recent = yoy_q[:4] if len(yoy_q) >= 4 else yoy_q
    return {
        "rev_yoy_latest": latest.get("rev_yoy"),
        "profit_yoy_latest": latest.get("profit_yoy"),
        "rev_qoq_latest": latest.get("rev_qoq"),
        "profit_qoq_latest": latest.get("profit_qoq"),
        "avg_rev_yoy_4q": round(sum(m.get("rev_yoy", 0) or 0 for m in recent) / len(recent), 1) if recent else None,
        "avg_profit_yoy_4q": round(sum(m.get("profit_yoy", 0) or 0 for m in recent) / len(recent), 1) if recent else None,
    }


def _scissor_analysis(ir: Dict) -> Dict:
    """剪刀差分析"""
    return {
        "latest_gap_pct": ir.get("scissor_gap"),
        "is_expanding": ir.get("scissor_is_expanding", False),
        "scissor_quarters_count": ir.get("scissor_quarters_count", 0),
    }


def _profitability_block(ir: Dict) -> Dict:
    """盈利能力块"""
    return {
        "roic": {
            "roic_pct": ir.get("roic_pct"),
            "roic_quality": ir.get("roic_quality"),
            "roic_interpretation": ir.get("roic_interpretation"),
        },
        "roiic": {
            "roiic_pct": ir.get("roiic_pct"),
            "roiic_quality": ir.get("roiic_quality"),
            "roiic_interpretation": ir.get("roiic_interpretation"),
        },
        "roe": ir.get("roe"),
        "adjusted_roe": ir.get("adjusted_roe"),
        "rd_adjustment": {
            "adjusted_profit_yi": ir.get("rd_adjusted_profit_yi"),
            "profit_impact_pct": ir.get("rd_profit_impact_pct"),
            "material": ir.get("rd_material", False),
        },
    }


def _rd_impact(ir: Dict) -> Dict:
    """研发影响块"""
    return {
        "rd_intensity_pct": ir.get("rd_intensity"),
        "profit_impact_pct": ir.get("rd_profit_impact_pct"),
        "material": ir.get("rd_material", False),
        "adjusted_profit_yi": ir.get("rd_adjusted_profit_yi"),
    }


def _financial_health(audit: Dict, ir: Dict) -> Dict:
    """财务健康块"""
    return {
        "audit": {
            "verdict": audit.get("audit_verdict"),
            "score": audit.get("audit_score"),
            "flags": audit.get("audit_flags", []),
            "inventory_trend": ir.get("inventory_trend", "unknown"),
            "contract_liability_trend": ir.get("contract_liability_trend", "unknown"),
            "ocf_health": ir.get("ocf_health", "unknown"),
        },
        "beneish": {
            "m_score": ir.get("m_score"),
            "interpretation": ir.get("m_score_interpretation"),
        },
    }


def _data_quality_block(quarters: List[Dict]) -> Dict:
    """数据质量 — 直接从原始 quarters 检查字段可用性"""
    any_q = quarters[0] if quarters else {}
    return {
        "all_8q_available": len(quarters) >= 8 if quarters else False,
        "has_rd_expense": float(any_q.get("rd_expense", 0) or 0) > 0,
        "has_op_cashflow": float(any_q.get("op_cashflow", 0) or 0) > 0,
        "has_inventory": float(any_q.get("inventory", 0) or 0) > 0,
        "has_contract_liability": float(any_q.get("contract_liability", 0) or 0) > 0,
        "has_accounts_receivable": float(any_q.get("accounts_receivable", 0) or 0) > 0,
    }


# ═══ 主构造器 ═══════════════════════════════════════

def build_financial_data_view(quarters: List[Dict]) -> Dict:
    """构建全方位财务数据视图

    基于 FINANCIAL_INDICATOR_REGISTRY 中 15 个注册财务量化指示器,
    组装为结构化视图 (后向兼容 V5.15 格式).

    Args:
        quarters: 8Q 财务数据 (report_date DESC, 最新在前)

    Returns:
        结构化财务数据视图 dict
    """
    if not quarters:
        return {"error": "no_quarters", "quarters_count": 0}

    # 1. 逐季度中间数据
    metrics = compute_quarterly_metrics(quarters)

    # 2. 全量注册指示器计算结果
    ir = compute_all_indicators(quarters)

    # 3. 审计 (委托注册指示器, 补充 metrics)
    audit = compute_audit(metrics, quarters)

    return {
        "company_profile": _company_profile(quarters, ir),
        "growth_trajectory": _growth_trajectory(metrics, ir),
        "profitability": _profitability_block(ir),
        "scissor_analysis": _scissor_analysis(ir),
        "rd_impact": _rd_impact(ir),
        "financial_health": _financial_health(audit, ir),
        "quarterly_metrics": metrics,
        "data_quality": _data_quality_block(quarters),
    }
