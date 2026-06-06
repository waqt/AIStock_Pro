"""Monte Carlo 仿真引擎 — 对任意估值方法做参数不确定性分析

功能:
  对估值方法的关键参数（营收增速、WACC、毛利率、终端增速等）按分布采样,
  运行 N 次迭代 → 输出目标指标的概率分布。

支持分布类型:
  - normal:    正态分布 (mean, std)
  - uniform:   均匀分布 (min, max)
  - triangular:三角分布 (min, mode, max)
  - lognormal: 对数正态分布 (mean, std) — 适用于 >0 的有偏参数
  - fixed:     固定值 (value) — 不随机, 用于敏感性设定

用法:
  engine = MonteCarloEngine()
  result = await engine.run(
      stock_code="688012",
      method_name="three_stage_growth",
      n_iterations=5000,
      param_defs={
          "rev_yoy_ttm": {"dist": "normal", "mean": 25, "std": 5},
          "wacc": {"dist": "normal", "mean": 9, "std": 1.5},
      },
      target_field="three_stage_value",
  )
  # → {mean, median, p10, p25, p75, p90, upside_prob, samples, ...}
"""
import math
import random
import statistics
from typing import Dict, List, Optional, Any
from app.framework.logger import logger


def _sample_normal(params: dict) -> float:
    """正态分布采样"""
    mean = float(params.get("mean", 0))
    std = float(params.get("std", 1))
    return random.gauss(mean, std)


def _sample_uniform(params: dict) -> float:
    """均匀分布采样"""
    lo = float(params.get("min", 0))
    hi = float(params.get("max", 1))
    return random.uniform(lo, hi)


def _sample_triangular(params: dict) -> float:
    """三角分布采样"""
    lo = float(params.get("min", 0))
    mode = float(params.get("mode", 0.5))
    hi = float(params.get("max", 1))
    return random.triangular(lo, hi, mode)


def _sample_lognormal(params: dict) -> float:
    """对数正态分布采样 (参数为正态分布的 mean/std, 自动转换)"""
    mean_orig = float(params.get("mean", 0))
    std_orig = float(params.get("std", 1))
    if mean_orig <= 0:
        return 0.01
    # 对数正态参数转换
    mu = math.log(mean_orig / math.sqrt(1 + (std_orig / mean_orig) ** 2))
    sigma = math.sqrt(math.log(1 + (std_orig / mean_orig) ** 2))
    return random.lognormvariate(mu, sigma)


def _sample_fixed(params: dict) -> float:
    """固定值"""
    return float(params.get("value", 0))


SAMPLERS = {
    "normal": _sample_normal,
    "uniform": _sample_uniform,
    "triangular": _sample_triangular,
    "lognormal": _sample_lognormal,
    "fixed": _sample_fixed,
}


def _clamp(val: float, params: dict) -> float:
    """对采样值做边界约束 (可选)"""
    lo = params.get("min")
    hi = params.get("max")
    if lo is not None:
        val = max(float(lo), val)
    if hi is not None:
        val = min(float(hi), val)
    return val


def _percentile(data: List[float], p: float) -> float:
    """计算百分位数"""
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


class MonteCarloEngine:
    """Monte Carlo 仿真引擎

    包装任意 ValuationMethod, 对其关键参数做分布采样,
    输出目标估值指标的完整概率分布。
    """

    def __init__(self, seed: Optional[int] = None):
        self._seed = seed
        if seed is not None:
            random.seed(seed)

    async def run(
        self,
        stock_code: str,
        method_name: str,
        n_iterations: int = 5000,
        param_defs: Optional[Dict[str, dict]] = None,
        target_field: Optional[str] = None,
    ) -> dict:
        """运行 Monte Carlo 仿真

        Args:
            stock_code: 股票代码
            method_name: 估值方法名 (VALUATION_REGISTRY 中的 name)
            n_iterations: 仿真迭代次数 (默认 5000, 常用 5000-20000)
            param_defs: 参数分布定义 {field_name: {dist, mean, std, ...}}
            target_field: 目标输出字段 (默认取方法的第一个数值输出字段)

        Returns:
            {mean, median, p10, p25, p75, p90, upside_prob, n_iterations,
             samples, method_name, target_field, ...}
        """
        from app.domain.quant.valuation import VALUATION_REGISTRY
        from app.domain.quant.valuation.engine.runner import ValuationRunner

        # 1. 查找方法
        method_cls = VALUATION_REGISTRY.get(method_name)
        if not method_cls:
            return {"error": f"Method '{method_name}' not found in registry"}

        # 2. 确定目标字段
        if not target_field:
            for f in method_cls.output:
                if f not in getattr(method_cls, 'text_output', []):
                    target_field = f
                    break
        if not target_field:
            return {"error": "No numeric output field found for simulation"}

        # 3. 加载基础数据 (用 ValuationRunner 的数据加载方法)
        runner = ValuationRunner()
        val_data = await runner._load_valuation_data(stock_code)
        fin_data = await runner._load_financial_data(stock_code)
        info = await runner._load_stock_info(stock_code)
        fin_ind_data = runner._load_financial_indicators(stock_code)

        if not val_data:
            return {"error": f"No valuation data for {stock_code}, sync first"}

        base_kwargs = {
            **val_data,
            **fin_data,
            **info,
            **method_cls.params,
        }
        if fin_ind_data:
            base_kwargs.update(fin_ind_data)

        # 4. 运行仿真
        param_defs = param_defs or {}
        samples = []
        errors = 0

        for i in range(n_iterations):
            try:
                kwargs = dict(base_kwargs)

                # 采样参数
                for field, defn in param_defs.items():
                    dist_type = defn.get("dist", "fixed")
                    sampler = SAMPLERS.get(dist_type)
                    if sampler is None:
                        continue
                    val = sampler(defn)
                    val = _clamp(val, defn)
                    kwargs[field] = val

                # 调用 compute
                output = method_cls.compute(**kwargs)
                result_val = output.get(target_field)
                if result_val is not None:
                    try:
                        samples.append(float(result_val))
                    except (ValueError, TypeError):
                        pass

            except Exception as e:
                errors += 1
                if errors > n_iterations * 0.1:  # 超过10%错误则终止
                    logger.warning(f"[MCSim] {stock_code}/{method_name}: too many errors ({errors}), aborting")
                    break
                continue

        # 5. 统计
        if not samples:
            return {
                "error": f"No valid samples produced ({errors} errors)",
                "method_name": method_name,
                "target_field": target_field,
                "n_iterations": n_iterations,
            }

        n_valid = len(samples)
        sample_mean = statistics.mean(samples)
        sample_median = statistics.median(samples)

        # 当前价格 (作为基准)
        current_price = None
        if val_data.get("mcap_yi") and info.get("total_shares"):
            current_price = (val_data["mcap_yi"] * 1e8) / info["total_shares"]

        # 上行概率 (sample > current_price)
        upside_prob = None
        if current_price and current_price > 0:
            upside_count = sum(1 for s in samples if s > current_price)
            upside_prob = round(upside_count / n_valid * 100, 1)

        # 分布偏差: (mean - median) / median × 100, 正=右偏(均值拉高)
        skew_indicator = 0.0
        if sample_median > 0:
            skew_indicator = round((sample_mean - sample_median) / sample_median * 100, 1)

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
            "upside_prob": upside_prob,
            "skew_indicator": skew_indicator,
            "current_price": round(current_price, 2) if current_price else None,
            "n_valid": n_valid,
            "n_iterations": n_iterations,
            "errors": errors,
            "method_name": method_name,
            "target_field": target_field,
            "stock_code": stock_code,
            # 采样样本 (前端绘图用, 限制最多 10000 点)
            "samples": [round(s, 2) for s in samples[:10000]],
        }


# 单例
monte_carlo = MonteCarloEngine()
