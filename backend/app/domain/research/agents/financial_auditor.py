"""
FinancialAuditor V4.0 — 财务排雷与体检专家
专注 8Q 财务剪刀差 + 营收/利润四连击 + 存货/合同负债异动审查
"""
from typing import Dict, Any, List, Optional
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.finance.financial_data_view import (
    compute_quarterly_metrics,
    compute_beneish_m_score,
    compute_audit as _compute_audit_shared,
)
from app.framework.logger import logger


class FinancialAuditor(ResearchAgent):
    """财务审计师 — V4.0 专家节点, 负责定量排雷"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "FinancialAuditor"

    # ═══ 主入口 ═══════════════════════════════════

    async def analyze(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """对单个标的执行财务体检"""
        code = ctx.get("stock_code", "")
        name = ctx.get("stock_name", "")
        if not code:
            return {"agent": self.name, "error": "No stock_code", "verdict": "SKIP"}

        logger.info(f"[{self.name}] Auditing {code} {name}")

        # 1. 加载 8Q 财务数据
        fin = await self.data_loader.load_financial_statements(code, periods=8)
        quarters = fin.get("quarters", [])
        if len(quarters) < 4:
            return {
                "agent": self.name, "code": code, "name": name,
                "verdict": "INSUFFICIENT_DATA",
                "reason": f"Only {len(quarters)} quarters available (need >=4)",
                "quarters_available": len(quarters),
            }

        # 2. 计算核心指标 (复用 framework/finance/financial_data_view)
        metrics = compute_quarterly_metrics(quarters)

        # 3. 审计判定 (复用 framework/finance/financial_data_view)
        audit = _compute_audit_shared(metrics, quarters)

        audit["agent"] = self.name
        audit["code"] = code
        audit["name"] = name
        audit["quarters_count"] = len(quarters)
        return audit

    # ═══ 基类要求 ═══════════════════════════════

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return await super().load_context(ctx)

    def build_prompt(self, ctx): return ""

    async def stream(self, ctx): yield "streaming not implemented"
