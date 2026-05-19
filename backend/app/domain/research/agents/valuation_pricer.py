"""
ValuationPricer V4.0 — 估值与时间窗测算专家
单一职责: 量化护城河时间窗口 + 全球对标 PEG/PS + 目标市值区间
输入: core_stock + financial_audit + human_capital + global_peer
输出: target_mcap, moat_window_years, position_suggest, valuation_method
"""
import asyncio
import json as _json
from decimal import Decimal
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger


class _SafeEncoder(_json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


def _j(obj, **kw):
    kw.setdefault("ensure_ascii", False)
    kw.setdefault("cls", _SafeEncoder)
    return _json.dumps(obj, **kw)


class ValuationPricer(ResearchAgent):
    """估值定价师 V4.0 — 护城河时间窗量化 + 全球对标定价"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "ValuationPricer"

    # ═══ 主入口 ═══════════════════════════════════

    async def analyze(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """对单只标的综合定价
        ctx 应包含: stock (from SupplyChainHacker), financial (from FinancialAuditor),
                    human_capital (from HumanCapitalDetective), peers (from search)
        """
        stock = ctx.get("stock", {})
        financial = ctx.get("financial", {})
        human = ctx.get("human_capital", {})

        code = stock.get("code", ctx.get("stock_code", ""))
        name = stock.get("name", ctx.get("stock_name", ""))

        if not code:
            return {"agent": self.name, "error": "No stock_code"}

        logger.info(f"[{self.name}] Pricing {code} {name}")

        # 搜索全球对标数据
        peers_data = await self._search_global_peers(name, code)

        # 从 DB 获取实时 PE/PB/市值 作为估值硬锚
        fundamentals = await self.data_loader.load_fundamentals([code])
        db_metrics = fundamentals.get(code, {})
        hard_anchor = {
            "pe_ttm": db_metrics.get("pe_ttm"),
            "pb": db_metrics.get("pb"),
            "mcap_yi": db_metrics.get("mcap_yi"),
        }

        # LLM 综合定价
        if not self.provider:
            return {"agent": self.name, "error": "No AI provider", "code": code}

        result = await self._price_target(stock, financial, human, peers_data, hard_anchor)
        result["agent"] = self.name
        result["code"] = code
        result["name"] = name
        return result

    # ═══ 全球对标搜索 ═════════════════════════════

    async def _search_global_peers(self, name: str, code: str) -> List:
        query = f"{name} global peer competitor market cap PE PS valuation 2026"
        items = []
        for r in await self.data_loader.search_web(query, num=4):
            items.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("snippet", "")[:300],
            })
        return items

    # ═══ LLM 综合定价 ═════════════════════════════

    async def _price_target(self, stock: Dict, financial: Dict,
                            human: Dict, peers: List, hard_anchor: Dict) -> Dict:
        prompt = f"""你是买方首席估值分析师。基于以下多维度数据, 对标的进行综合估值定价。

## 标的基本信息
{_j(stock)}

## 实时估值锚 (来自DB, 硬数据)
{_j(hard_anchor)}

## 财务审计结果 (FinancialAuditor)
{_j(financial)}

## 人力资本审计 (HumanCapitalDetective)
{_j(human)}

## 全球对标搜索
{_j(peers)}

## 关键规则
- pe_current / ps_current 必须使用上述"实时估值锚"中的 pe_ttm 值
- market_cap 必须使用上述 mcap_yi 值 (单位: 亿元)
- 如果 hard_anchor 中某字段为 null, 使用同业对标数据估算

## 输出要求: 纯 JSON
{{
  "valuation_summary": "估值核心结论 (1-2句子)",
  "moat_window": {{
    "years": 5,
    "barrier_type": "技术专利/客户认证/产能规模/政策壁垒",
    "threat_level": "LOW/MEDIUM/HIGH — 对手追赶难度",
    "reasoning": "时间窗量化依据"
  }},
  "target_valuation": {{
    "base_case_mcap": 500,
    "unit": "亿元",
    "bull_case_mcap": 700,
    "bear_case_mcap": 350,
    "upside_pct": 30,
    "downside_pct": -15
  }},
  "valuation_method": {{
    "primary": "PEG/PS/DCF/可比估值",
    "pe_current": 45.0,
    "pe_target": 55.0,
    "peg_ratio": 0.8,
    "ps_current": 8.0,
    "ps_target": 10.0,
    "growth_rate_est": "未来3年利润CAGR%",
    "reasoning": "为什么用这个方法"
  }},
  "global_peer_comparison": [
    {{"name": "对标公司", "code": "NVDA.US", "pe": 55, "ps": 20, "premium_discount": "溢价/折价原因"}}
  ],
  "position_suggest": {{
    "allocation_pct": 10,
    "time_horizon": "6-12个月/1-3年",
    "entry_strategy": "现价建仓/等回调/分步建仓",
    "exit_trigger": "什么情况下该卖出"
  }},
  "verdict": "BUY/HOLD/SELL",
  "risk_reward_ratio": "1:3 — 解释"
}}

关键定价规则:
- moat_window: 护城河能阻挡对手多长时间? 量化到年
- peg_ratio: PE / 利润增速%, <1=低估, >2=泡沫
- 综合 FinancialAuditor 的 verdict 调整风险溢价
- 综合 HumanCapitalDetective 的 score 调整管理层折价/溢价"""

        try:
            text = await asyncio.wait_for(
                self.provider.chat(prompt, max_tokens=3072), timeout=60)
            result = self.parse_json(text)
            if isinstance(result, dict):
                logger.info(
                    f"[{self.name}] {stock.get('code', '?')} "
                    f"verdict: {result.get('verdict')}, "
                    f"upside: {result.get('target_valuation', {}).get('upside_pct', '?')}%")
                return result
        except asyncio.TimeoutError:
            logger.warning(f"[{self.name}] Pricing timeout")
        except Exception as e:
            logger.warning(f"[{self.name}] Pricing failed: {e}")

        return {"error": "LLM pricing failed", "verdict": "UNKNOWN"}

    # ═══ 基类实现 ═══════════════════════════════

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return await super().load_context(ctx)

    @staticmethod
    def build_prompt(ctx):
        return "ValuationPricer V4.0"

    @staticmethod
    async def stream(ctx):
        yield "streaming not implemented"
