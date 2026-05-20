"""
DAG Orchestrator V4.0 — 图结构多Agent编排器
以 DAG 依赖图并行调度 5 专家, 替代 V3.0 的线性顺序调用

依赖图:
  GlobalCapexScanner ──┐
                        ├──→ [FOR EACH stock: FinancialAuditor || HumanCapital] ──→ ValuationPricer ──→ Report
  SupplyChainHacker ───┘
"""
import asyncio
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger


class DAGOrchestrator(ResearchAgent):
    """DAG 编排器 V4.0 — 专家委员会并行调度"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "DAGOrchestrator"

    # ═══ 主入口 ═══════════════════════════════════

    async def analyze(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await self.load_context(ctx)
        industry = ctx.get("industry", "")
        codes = ctx.get("stock_codes", [])
        hot_sectors = ctx.get("hot_sectors", [])  # 可选: MarketScanner 预扫描信号

        if not industry:
            return {"agent": self.name, "error": "No industry specified"}

        logger.info(f"[{self.name}] DAG pipeline starting for: {industry}"
                    + (f" (pre-scanned: {len(hot_sectors)} sectors)" if hot_sectors else ""))

        # ═══ Phase A: 顶层并行扫描 ═══
        logger.info(f"[{self.name}] Phase A: parallel top-down scan...")
        capex_task = self._run_capex_scanner(industry, hot_sectors)
        hacker_task = self._run_supply_chain_hacker(industry, codes)

        capex_result, hacker_result = await asyncio.gather(capex_task, hacker_task)
        logger.info(
            f"[{self.name}] Phase A complete: "
            f"capex_signals={len(capex_result.get('capex_signals', []))}, "
            f"core_stocks={len(hacker_result.get('core_stocks', []))}")

        core_stocks = hacker_result.get("core_stocks", [])
        if not core_stocks:
            return {
                "agent": self.name,
                "error": "No core stocks identified by SupplyChainHacker",
                "capex": capex_result,
                "supply_chain": hacker_result,
            }

        # ═══ Phase B: 每只标的并行审计 (Financial || HumanCapital) ═══
        logger.info(f"[{self.name}] Phase B: parallel audit for {len(core_stocks)} stocks...")
        audit_tasks = []
        for stock in core_stocks:
            audit_tasks.append(self._audit_stock(stock))

        audit_results = await asyncio.gather(*audit_tasks)
        logger.info(f"[{self.name}] Phase B complete: {len(audit_results)} stocks audited")

        # ═══ Phase C: 综合定价 ═══
        logger.info(f"[{self.name}] Phase C: pricing...")
        price_tasks = []
        for i, stock in enumerate(core_stocks):
            audits = audit_results[i] if i < len(audit_results) else {}
            price_tasks.append(self._price_stock(stock, audits))

        price_results = await asyncio.gather(*price_tasks)
        logger.info(f"[{self.name}] Phase C complete: {len(price_results)} stocks priced")

        # ═══ Phase D: 合成最终报告 ═══
        logger.info(f"[{self.name}] Phase D: synthesizing final report...")
        report = await self._synthesize_report(
            industry, capex_result, hacker_result, audit_results, price_results)

        report["agent"] = self.name
        report["industry"] = industry
        report["pipeline_stats"] = {
            "capex_signals": len(capex_result.get("capex_signals", [])),
            "supply_chain_layers": len(hacker_result.get("supply_chain_map", [])),
            "core_stocks": len(core_stocks),
            "stocks_audited": len(audit_results),
            "stocks_priced": len(price_results),
        }
        return report

    # ═══ Phase A: 并行顶层 ═══════════════════════

    async def _run_capex_scanner(self, industry: str, hot_sectors: list = None) -> Dict:
        from app.domain.research.agents.global_capex_scanner import GlobalCapexScanner
        scanner = GlobalCapexScanner(provider=self.provider)
        ctx = {"industry": industry}
        if hot_sectors:
            ctx["hot_sectors"] = hot_sectors  # 预扫描信号注入
        try:
            return await scanner.analyze(ctx)
        except Exception as e:
            logger.warning(f"[{self.name}] CapexScanner failed: {e}")
            return {"error": str(e), "agent": "GlobalCapexScanner"}

    async def _run_supply_chain_hacker(self, industry: str, codes: List[str]) -> Dict:
        from app.domain.research.agents.supply_chain_hacker import SupplyChainHacker
        hacker = SupplyChainHacker(provider=self.provider)
        try:
            return await hacker.analyze({
                "industry": industry, "stock_codes": codes,
                "include_portfolio": True})
        except Exception as e:
            logger.warning(f"[{self.name}] SupplyChainHacker failed: {e}")
            return {"error": str(e), "agent": "SupplyChainHacker", "core_stocks": []}

    # ═══ Phase B: 单股并行审计 ═══════════════════

    async def _audit_stock(self, stock: Dict) -> Dict:
        code = stock.get("code", "")
        name = stock.get("name", "")
        if not code:
            return {"code": code, "error": "No code"}

        # FinancialAuditor + HumanCapitalDetective 并行
        from app.domain.research.agents.financial_auditor import FinancialAuditor
        from app.domain.research.agents.human_capital_detective import HumanCapitalDetective

        auditor = FinancialAuditor()
        detective = HumanCapitalDetective(provider=self.provider)

        fin_task = auditor.analyze({"stock_code": code, "stock_name": name})
        hc_task = detective.analyze({"stock_code": code, "stock_name": name})

        fin_result, hc_result = await asyncio.gather(fin_task, hc_task)
        logger.info(
            f"[{self.name}] {code} audited: "
            f"FA={fin_result.get('verdict', '?')} "
            f"HC={hc_result.get('verdict', '?')}")

        return {
            "code": code, "name": name,
            "financial": fin_result,
            "human_capital": hc_result,
        }

    # ═══ Phase C: 单股定价 ═══════════════════════

    async def _price_stock(self, stock: Dict, audits: Dict) -> Dict:
        from app.domain.research.agents.valuation_pricer import ValuationPricer
        pricer = ValuationPricer(provider=self.provider)
        try:
            return await pricer.analyze({
                "stock": stock,
                "financial": audits.get("financial", {}),
                "human_capital": audits.get("human_capital", {}),
            })
        except Exception as e:
            logger.warning(f"[{self.name}] Pricer failed for {stock.get('code','?')}: {e}")
            return {"error": str(e), "verdict": "UNKNOWN"}

    # ═══ Phase D: 最终报告 ═══════════════════════

    async def _synthesize_report(self, industry: str,
                                 capex: Dict, hacker: Dict,
                                 audits: List[Dict], prices: List[Dict]) -> Dict:
        """LLM 将 5 专家输出合成为最终 CIO 报告"""
        if not self.provider:
            return {
                "capex": capex, "supply_chain": hacker,
                "audits": audits, "prices": prices,
                "note": "No AI provider — raw agent outputs"
            }

        # 精简数据量, 避免 token 溢出
        capex_summary = {
            "summary": capex.get("global_summary", ""),
            "hot_sectors": capex.get("hot_sectors", [])[:3],
        }
        sc_summary = {
            "chain_layers": len(hacker.get("supply_chain_map", [])),
            "stocks": [
                {"code": s.get("code"), "name": s.get("name"),
                 "monopoly_score": s.get("monopoly_score")}
                for s in hacker.get("core_stocks", [])[:5]
            ],
        }
        price_summary = [
            {"code": p.get("code"), "name": p.get("name"),
             "verdict": p.get("verdict"),
             "upside": p.get("target_valuation", {}).get("upside_pct"),
             "moat_years": p.get("moat_window", {}).get("years")}
            for p in prices[:5]
        ]

        import json as _json
        from decimal import Decimal

        class _SafeEncoder(_json.JSONEncoder):
            def default(self, o):
                if isinstance(o, Decimal):
                    return float(o)
                return super().default(o)

        def _j(obj):
            return _json.dumps(obj, ensure_ascii=False, cls=_SafeEncoder)

        prompt = f"""你是买方首席投资官(CIO)。基于投研专家委员会的5份独立分析报告, 输出最终投资研报。

## 行业: {industry}

## GlobalCapexScanner (全球CapEx前瞻)
{_j(capex_summary)}

## SupplyChainHacker (供应链穿透)
{_j(sc_summary)}

## 交叉验证 + 定价
{_j(price_summary)}

## 输出要求: 纯 JSON
{{
  "final_summary": "最终核心结论 (3-4句)",
  "top_picks": [
    {{"code": "688012", "name": "...", "rank": 1, "thesis": "核心投资逻辑 (1句)", "verdict": "BUY/HOLD", "conviction": "HIGH/MEDIUM"}}
  ],
  "portfolio_allocation": [
    {{"code": "688012", "name": "...", "weight_pct": 20, "role": "核心仓位/卫星仓位"}}
  ],
  "key_risks": ["风险1", "风险2"],
  "catalysts_to_watch": ["催化剂1", "催化剂2"],
  "timeline": "建议的时间线 (如: 2026Q3前完成建仓)"
}}"""

        try:
            text = await asyncio.wait_for(
                self.provider.chat_pro(prompt, max_tokens=3072), timeout=60)
            result = self.parse_json(text)
            if isinstance(result, dict):
                result["detail"] = {
                    "capex": capex, "supply_chain": hacker,
                    "audits": audits, "prices": prices,
                }
                return result
        except Exception as e:
            logger.warning(f"[{self.name}] Final synthesis failed: {e}")

        return {
            "final_summary": "Report synthesis failed — raw data attached",
            "detail": {"capex": capex, "supply_chain": hacker,
                       "audits": audits, "prices": prices},
        }

    # ═══ 基类实现 ═══════════════════════════════

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await super().load_context(ctx)
        ctx["macro"] = await self.data_loader.load_macro()
        ctx["positions"] = await self.data_loader.load_positions()
        return ctx

    @staticmethod
    def build_prompt(ctx):
        return "DAGOrchestrator V4.0"

    @staticmethod
    async def stream(ctx):
        yield "streaming not implemented"
