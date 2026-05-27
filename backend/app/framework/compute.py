"""
ComputationContext — LLM选方法, 代码算数字, LLM写叙事
解耦"定性判断"和"定量计算", 避免 LLM 猜数字
"""
import json
from typing import Dict, Any, Optional, Callable
from app.framework.finance import (
    pe_valuation, pb_valuation, ps_valuation,
    ev_ebitda_valuation, peg_valuation, fcf_yield_valuation,
    scenario_weighted, apply_pricing_power_premium,
    apply_quality_adjustment, apply_financial_risk_discount,
    VALUATION_MODEL_MAP, match_asset_type, get_valuation_method,
)
from app.framework.logger import logger

# 方法名 → 计算函数映射
METHOD_REGISTRY: Dict[str, Callable] = {
    "pe_valuation": pe_valuation,
    "pb_valuation": pb_valuation,
    "ps_valuation": ps_valuation,
    "ev_ebitda_valuation": ev_ebitda_valuation,
    "peg_valuation": peg_valuation,
    "fcf_yield_valuation": fcf_yield_valuation,
    "scenario_weighted": scenario_weighted,
}


class ComputationContext:
    """LLM定性 → 程序化定量 → LLM叙事的串联器

    用法:
        ctx = ComputationContext(provider)
        # 1. LLM 分类 + 选方法
        decision = await ctx.classify(prompt, options=[...], output_key="method")
        # 2. 代码算数字
        result = ctx.execute(decision["method"], **decision.get("params", {}))
        # 3. LLM 写叙事
        narrative = await ctx.narrate(prompt_with_context, result)
    """

    def __init__(self, provider, db=None):
        self.provider = provider
        self.db = db
        self.computed = {}

    # ═══ 1. LLM 分类 ═══════════════════════════

    async def classify(self, prompt: str, options: list = None,
                       output_key: str = "method") -> dict:
        """LLM 从预定义选项中分类选择。返回 {method, params, reasoning}"""
        constraint = ""
        if options:
            constraint = f"method 必须从以下选项中选择: {', '.join(options)}"
        full_prompt = f"""{prompt}

## 输出要求
输出纯 JSON: {{"{output_key}": "选项名", "params": {{...}}, "reasoning": "选择理由"}}
{constraint}"""
        try:
            text = await self.provider.chat_flash(full_prompt, max_tokens=1024)
            result = json.loads(text) if isinstance(text, str) else text
            if isinstance(result, dict):
                logger.info(f"[Computation] Classified: {result.get(output_key, '?')}")
                return result
        except Exception as e:
            logger.warning(f"[Computation] Classify failed: {e}")
        return {output_key: "pe_valuation", "params": {}}  # 默认降级

    # ═══ 2. 程序化计算 ═══════════════════════════

    def execute(self, method: str, **params) -> Any:
        """调用对应的计算函数。method 必须在 METHOD_REGISTRY 中"""
        func = METHOD_REGISTRY.get(method)
        if not func:
            logger.warning(f"[Computation] Unknown method: {method}, fallback to pe_valuation")
            func = pe_valuation
        try:
            result = func(**params)
            self.computed[method] = {"params": params, "result": result}
            logger.info(f"[Computation] {method}({params}) = {result}")
            return result
        except Exception as e:
            logger.error(f"[Computation] {method} failed: {e}")
            return None

    # ═══ 3. LLM 叙事 ═══════════════════════════

    async def narrate(self, context: str, computed_values: dict) -> str:
        """LLM 基于计算结果写叙事分析"""
        prompt = f"""{context}

## 程序化计算结果
{json.dumps(computed_values, ensure_ascii=False, indent=2)}

请基于以上数据, 用中文写出估值分析叙事 (2-3段)"""
        try:
            return await self.provider.chat_flash(prompt, max_tokens=2048)
        except Exception as e:
            logger.warning(f"[Computation] Narrate failed: {e}")
            return "分析暂不可用"

    # ═══ 便捷方法: 资产类型匹配 ══════════════════

    def match_asset(self, industry: str) -> Optional[str]:
        """根据行业名匹配资产类型 → 估值方法"""
        return match_asset_type(industry)

    def get_method_for(self, asset_type: str = None, cycle_phase: str = None) -> str:
        """根据资产类型/周期阶段获取推荐的估值方法"""
        return get_valuation_method(asset_type, cycle_phase)
