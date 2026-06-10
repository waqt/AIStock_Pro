"""Driver-Based Valuation — 从业务驱动因素出发的估值模型

核心链路:
  业务假设 (单价、销量、成本、费用率等)
  → 财务预测 (营收、利润、自由现金流)
  → DCF 估值 (企业价值、股权价值、每股价值)
  → Monte Carlo 敏感性分析

用途:
  - 适用于有明确量价模型的制造业/消费股/周期股
  - LLM Agent 可自主设定业务假设并调用工具估值
  - 情景分析: 对比乐观/基准/悲观三档假设下的估值差异

与 simulation.py (参数扰动) 的区别:
  simulation.py 对已有估值方法的参数(rev_yoy_ttm, wacc 等)做分布采样。
  driver_based.py 从更底层的业务驱动因素(价格、销量、成本结构)出发,
  先投影财务报表, 再做 DCF 估值。适合"先有业务假设, 再有估值"的场景。
"""
import math
import random
import statistics
from typing import Dict, Any, Optional, List


# ═══ 行业中性驱动因素定义 ═══════════════════════

DRIVER_FIELDS = [
    {"key": "product_price", "label": "产品单价", "unit": "元", "default": 100.0,
     "desc": "核心产品单件售价, 制造业/消费品的核心量价假设", "min": 1, "max": 100000},
    {"key": "sales_volume", "label": "年销量", "unit": "万件", "default": 1000.0,
     "desc": "年销售数量 (万件/万吨/万平米等)", "min": 1, "max": 1e8},
    {"key": "unit_cost", "label": "单位成本", "unit": "元", "default": 60.0,
     "desc": "每件产品的完全生产成本 (含直接材料+直接人工+制造费用)", "min": 0, "max": 100000},
    {"key": "sg_a_pct", "label": "销售管理费率", "unit": "%", "default": 15.0,
     "desc": "销售费用+管理费用占营收比例", "min": 0, "max": 100},
    {"key": "rd_pct", "label": "研发费用率", "unit": "%", "default": 5.0,
     "desc": "研发支出占营收比例", "min": 0, "max": 100},
    {"key": "tax_rate", "label": "有效税率", "unit": "%", "default": 15.0,
     "desc": "企业所得税有效税率", "min": 0, "max": 50},
    {"key": "annual_growth", "label": "营收年增速", "unit": "%", "default": 15.0,
     "desc": "增长期每年的营收增长率", "min": -50, "max": 200},
    {"key": "growth_years", "label": "增长期年数", "unit": "年", "default": 5.0,
     "desc": "高速增长阶段的年数, 之后进入永续增长", "min": 1, "max": 30},
    {"key": "terminal_growth", "label": "永续增长率", "unit": "%", "default": 3.0,
     "desc": "永续阶段的增长率 (通常 ≤ GDP 增速)", "min": -5, "max": 10},
    {"key": "wacc", "label": "折现率 (WACC)", "unit": "%", "default": 10.0,
     "desc": "加权平均资本成本, 取决于资本结构和风险", "min": 1, "max": 30},
    {"key": "total_shares", "label": "总股本", "unit": "亿股", "default": 10.0,
     "desc": "公司总股本, 用于计算每股价值", "min": 0.01, "max": 1e6},
    {"key": "net_debt", "label": "净负债", "unit": "亿元", "default": 0.0,
     "desc": "有息负债总额 - 现金及等价物 (正值=净负债, 负值=净现金)", "min": -1e6, "max": 1e6},
]

DRIVER_DICT = {f["key"]: f for f in DRIVER_FIELDS}

DEFAULT_DRIVERS = {f["key"]: f["default"] for f in DRIVER_FIELDS}


# ═══ 采样器 ═════════════════════════════════════

def _sample_normal(params: dict) -> float:
    mean = float(params.get("mean", 0))
    std = float(params.get("std", 1))
    return random.gauss(mean, std)

def _sample_uniform(params: dict) -> float:
    lo = float(params.get("min", 0))
    hi = float(params.get("max", 1))
    return random.uniform(lo, hi)

def _sample_triangular(params: dict) -> float:
    lo = float(params.get("min", 0))
    mode = float(params.get("mode", 0.5))
    hi = float(params.get("max", 1))
    return random.triangular(lo, hi, mode)

def _sample_lognormal(params: dict) -> float:
    mean_orig = float(params.get("mean", 0))
    std_orig = float(params.get("std", 1))
    if mean_orig <= 0:
        return 0.01
    mu = math.log(mean_orig / math.sqrt(1 + (std_orig / mean_orig) ** 2))
    sigma = math.sqrt(math.log(1 + (std_orig / mean_orig) ** 2))
    return random.lognormvariate(mu, sigma)

def _sample_fixed(params: dict) -> float:
    return float(params.get("value", 0))

_SAMPLERS = {
    "normal": _sample_normal,
    "uniform": _sample_uniform,
    "triangular": _sample_triangular,
    "lognormal": _sample_lognormal,
    "fixed": _sample_fixed,
}

def _clamp(val: float, lo: Optional[float] = None, hi: Optional[float] = None) -> float:
    if lo is not None:
        val = max(lo, val)
    if hi is not None:
        val = min(hi, val)
    return val

def _percentile(data: List[float], p: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = p / 100.0 * (len(sorted_data) - 1)
    if idx.is_integer():
        return sorted_data[int(idx)]
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    frac = idx - lo
    return sorted_data[lo] * (1 - frac) + sorted_data[hi] * frac


# ═══ 核心财务投影 ══════════════════════════════

def project_financials(drivers: Dict[str, float]) -> Dict[str, Any]:
    """基于业务驱动因素投影未来财务数据并计算 DCF 估值

    Args:
        drivers: 业务驱动因素字典, 见 DRIVER_FIELDS 定义

    Returns:
        财务预测 + DCF 估值结果
    """
    p = {**DEFAULT_DRIVERS, **drivers}

    price = p["product_price"]
    volume = p["sales_volume"]
    unit_cost = p["unit_cost"]
    sg_a_pct = p["sg_a_pct"] / 100.0
    rd_pct = p["rd_pct"] / 100.0
    tax_rate = p["tax_rate"] / 100.0
    growth = p["annual_growth"] / 100.0
    growth_years = max(1, int(round(p["growth_years"])))
    terminal_growth = p["terminal_growth"] / 100.0
    wacc = p["wacc"] / 100.0
    total_shares = p["total_shares"] * 1e8  # 亿 → 股
    net_debt = p["net_debt"] * 1e8  # 亿 → 元

    # ── 第 0 年 (基准年) ──
    revenue_0 = price * volume * 1e4  # 万件→件, revenue 单位=元
    cogs_0 = unit_cost * volume * 1e4

    # ── 投影 N 年 ──
    revenues = [revenue_0 * (1 + growth) ** i for i in range(growth_years)]
    cogs_list = [cogs_0 * (1 + growth) ** i for i in range(growth_years)]

    # 折旧近似为营收的固定比例
    depr_rate = 0.03  # 3% of revenue
    capex_rate = 0.05  # 5% of revenue
    wc_rate = 0.10  # 10% of revenue increment

    gross_profits = []
    sgas = []
    rds = []
    deprs = []
    ebits = []
    nopats = []
    capexs = []
    delta_wc = []
    fcfs = []

    prev_rev = revenue_0
    for i in range(growth_years):
        rev = revenues[i]
        gp = rev - cogs_list[i]
        sg = rev * sg_a_pct
        rd = rev * rd_pct
        dp = rev * depr_rate
        eb = gp - sg - rd - dp
        np = eb * (1 - tax_rate)
        cx = rev * capex_rate
        dwc = (rev - prev_rev) * wc_rate
        fcf = np + dp - cx - dwc

        gross_profits.append(gp)
        sgas.append(sg)
        rds.append(rd)
        deprs.append(dp)
        ebits.append(eb)
        nopats.append(np)
        capexs.append(cx)
        delta_wc.append(dwc)
        fcfs.append(fcf)
        prev_rev = rev

    # ── 终值 (Gordon Growth Model) ──
    last_fcf = fcfs[-1]
    if wacc > terminal_growth:
        terminal_value = last_fcf * (1 + terminal_growth) / (wacc - terminal_growth)
    else:
        terminal_value = 0.0

    # ── DCF ──
    pv_fcfs = [fcfs[i] / (1 + wacc) ** (i + 1) for i in range(growth_years)]
    pv_terminal = terminal_value / (1 + wacc) ** growth_years
    enterprise_value = sum(pv_fcfs) + pv_terminal
    equity_value = enterprise_value - net_debt
    per_share = equity_value / total_shares if total_shares > 0 else 0.0

    # ── 关键财务比率 ──
    gross_margin = gross_profits[0] / revenues[0] * 100 if revenues[0] > 0 else 0
    net_margin = nopats[0] / revenues[0] * 100 if revenues[0] > 0 else 0
    avg_ebit = sum(ebits) / len(ebits) if ebits else 0
    avg_fcf = sum(fcfs) / len(fcfs) if fcfs else 0
    fcf_growth = ((fcfs[-1] / fcfs[0]) ** (1 / growth_years) - 1) * 100 if fcfs[0] > 0 and growth_years > 0 else 0

    return {
        "per_share_price": round(per_share, 2),
        "enterprise_value_yi": round(enterprise_value / 1e8, 2),
        "equity_value_yi": round(equity_value / 1e8, 2),
        "first_year_revenue_yi": round(revenue_0 / 1e8, 2),
        "first_year_nopat_yi": round(nopats[0] / 1e8, 2),
        "first_year_fcf_yi": round(fcfs[0] / 1e8, 2) if fcfs else 0,
        "terminal_value_yi": round(terminal_value / 1e8, 2),
        "terminal_value_pct": round(pv_terminal / enterprise_value * 100, 1) if enterprise_value > 0 else 0,
        "gross_margin_pct": round(gross_margin, 1),
        "net_margin_pct": round(net_margin, 1),
        "avg_ebit_yi": round(avg_ebit / 1e8, 2),
        "avg_fcf_yi": round(avg_fcf / 1e8, 2),
        "fcf_growth_pct": round(fcf_growth, 1),
        "implied_pe": round(per_share / (nopats[-1] / total_shares), 1) if nopats[-1] > 0 and total_shares > 0 else 0,
        "ev_ebitda": round(enterprise_value / (ebits[-1] + deprs[-1]), 1) if (ebits[-1] + deprs[-1]) > 0 else 0,
        "revenue_list_yi": [round(r / 1e8, 2) for r in revenues],
        "fcf_list_yi": [round(f / 1e8, 2) for f in fcfs],
        "growth_years": growth_years,
        "terminal_growth_rate": terminal_growth * 100,
        "wacc_used": wacc * 100,
    }


# ═══ Monte Carlo 仿真 ══════════════════════════

def run_driver_monte_carlo(
    driver_defs: Dict[str, dict],
    n_iterations: int = 5000,
    default_drivers: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """对业务驱动因素做 Monte Carlo 仿真

    Args:
        driver_defs: 驱动因素分布定义 {key: {dist, mean, std, ...}}
        n_iterations: 仿真迭代次数
        default_drivers: 基础默认值 (未在 driver_defs 中的参数使用)

    Returns:
        估值分布统计 + 样本
    """
    default_drivers = {**DEFAULT_DRIVERS, **(default_drivers or {})}

    samples = []
    errors = 0
    all_results = []

    for i in range(n_iterations):
        try:
            drivers = dict(default_drivers)

            # 采样随机参数
            for field, defn in driver_defs.items():
                dist_type = defn.get("dist", "fixed")
                sampler = _SAMPLERS.get(dist_type)
                if sampler is None:
                    continue
                val = sampler(defn)
                # 边界约束 (来自 defn 或 DRIVER_FIELDS 定义)
                lo = defn.get("min") or DRIVER_DICT.get(field, {}).get("min")
                hi = defn.get("max") or DRIVER_DICT.get(field, {}).get("max")
                val = _clamp(val, lo, hi)
                drivers[field] = val

            result = project_financials(drivers)
            per_share = result.get("per_share_price", 0)
            if per_share and per_share > 0:
                samples.append(per_share)
                all_results.append({
                    "per_share": per_share,
                    "ev_yi": result.get("enterprise_value_yi", 0),
                    **{k: drivers.get(k) for k in driver_defs.keys()},
                })

        except Exception:
            errors += 1
            if errors > n_iterations * 0.1:
                break
            continue

    if not samples:
        return {
            "error": "No valid samples produced",
            "n_iterations": n_iterations,
            "errors": errors,
        }

    n_valid = len(samples)
    sample_mean = statistics.mean(samples)
    sample_median = statistics.median(samples)

    return {
        "mean": round(sample_mean, 2),
        "median": round(sample_median, 2),
        "p10": round(_percentile(samples, 10), 2),
        "p25": round(_percentile(samples, 25), 2),
        "p75": round(_percentile(samples, 75), 2),
        "p90": round(_percentile(samples, 90), 2),
        "std": round(statistics.stdev(samples), 2) if len(samples) > 1 else 0.0,
        "min": round(min(samples), 2),
        "max": round(max(samples), 2),
        "upside_prob": None,  # 没有 current_price，由前端自行计算
        "skew_indicator": round((sample_mean - sample_median) / sample_median * 100, 1) if sample_median > 0 else 0,
        "n_valid": n_valid,
        "n_iterations": n_iterations,
        "errors": errors,
        "samples": [round(s, 2) for s in samples[:10000]],
        "driver_fields": DRIVER_FIELDS,
    }


# ═══ 情景分析 (非随机) ══════════════════════════

def scenario_compare(
    base: Dict[str, float],
    optimistic: Dict[str, float],
    pessimistic: Dict[str, float],
) -> Dict[str, Any]:
    """三档情景对比: 基准/乐观/悲观

    每档假设只需传入与基准不同的参数即可。
    """
    base_result = project_financials(base)

    opt_drivers = {**base, **optimistic}
    opt_result = project_financials(opt_drivers)

    pes_drivers = {**base, **pessimistic}
    pes_result = project_financials(pes_drivers)

    return {
        "base": {
            "drivers": base,
            "result": base_result,
        },
        "optimistic": {
            "drivers": opt_drivers,
            "result": opt_result,
        },
        "pessimistic": {
            "drivers": pes_drivers,
            "result": pes_result,
        },
        "comparison": {
            "per_share_base": base_result["per_share_price"],
            "per_share_opt": opt_result["per_share_price"],
            "per_share_pes": pes_result["per_share_price"],
            "upside_opt": round((opt_result["per_share_price"] / base_result["per_share_price"] - 1) * 100, 1) if base_result["per_share_price"] > 0 else 0,
            "downside_pes": round((pes_result["per_share_price"] / base_result["per_share_price"] - 1) * 100, 1) if base_result["per_share_price"] > 0 else 0,
        },
    }
