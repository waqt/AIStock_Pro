"""
HumanCapitalDetective V4.0 — 人力资本背景审计专家
单一职责: 穿透核心研发团队履历、专利质量、股权激励健康度
输出: 人力资本评分 + 创始人/CTO 背景 + 关键人员风险
"""
import asyncio
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger


class HumanCapitalDetective(ResearchAgent):
    """人力资本侦探 V4.0 — 研发团队背景穿透审计"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "HumanCapitalDetective"

    # ═══ 主入口 ═══════════════════════════════════

    async def analyze(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        code = ctx.get("stock_code", "")
        name = ctx.get("stock_name", "")
        if not code:
            return {"agent": self.name, "error": "No stock_code", "verdict": "SKIP"}

        logger.info(f"[{self.name}] Investigating {code} {name}")

        # 1. 多维度搜索
        search_data = await self._multi_search(name, code)

        # 2. LLM 穿透分析
        if not self.provider:
            return {"agent": self.name, "error": "No AI provider", "code": code}

        result = await self._audit_human_capital(name, code, search_data)
        result["agent"] = self.name
        result["code"] = code
        result["name"] = name
        return result

    # ═══ 多维度搜索 ═════════════════════════════

    async def _multi_search(self, name: str, code: str) -> Dict[str, List]:
        """3 个维度并行搜索"""
        queries = {
            "founder": f"{name} 创始人 董事长 CTO 履历 毕业院校 前任职",
            "patents": f"{name} 专利 研发投入 技术团队 核心技术人员",
            "equity": f"{name} 股权激励 员工持股 限售股 减持",
        }
        results = {}
        for key, query in queries.items():
            items = []
            for r in await self.data_loader.search_web(query, num=4):
                items.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("snippet", "")[:300],
                })
            results[key] = items
        return results

    # ═══ LLM 穿透分析 ═════════════════════════════

    async def _audit_human_capital(self, name: str, code: str, search: Dict) -> Dict:
        """LLM 综合分析人力资本质量"""
        import json as _json
        from decimal import Decimal

        class _SafeEncoder(_json.JSONEncoder):
            def default(self, o):
                if isinstance(o, Decimal):
                    return float(o)
                return super().default(o)

        prompt = f"""你是顶级猎头 + 专利律师 + 股权激励顾问的混合体。请分析 {name} ({code}) 的人力资本质量。

## 创始人/管理层搜索结果
{_json.dumps(search.get("founder", []), ensure_ascii=False, cls=_SafeEncoder)}

## 专利/研发团队搜索结果
{_json.dumps(search.get("patents", []), ensure_ascii=False, cls=_SafeEncoder)}

## 股权激励搜索结果
{_json.dumps(search.get("equity", []), ensure_ascii=False, cls=_SafeEncoder)}

## 输出纯 JSON
{{
  "founder_background": {{
    "name": "创始人姓名 (如搜索结果中有)",
    "education": "最高学历+毕业院校",
    "prior_experience": "前任职经历 (关键大厂/研究院/海外经历)",
    "industry_years": 20,
    "notable": "突出亮点 (如: IEEE Fellow, 国家科技进步奖, Nature/Science论文)"
  }},
  "core_team": {{
    "cto_name": "CTO/技术负责人姓名 (如有)",
    "cto_background": "CTO 关键履历",
    "rd_team_size_est": "研发团队规模估算",
    "rd_ratio_est": "研发人员占比估算%",
    "rd_investment_est": "年研发投入估算 (亿元)",
    "core_staff_stability": "稳定/一般/流动大 — 判断依据"
  }},
  "patent_quality": {{
    "total_patents_est": 500,
    "invention_ratio_est": "发明专利占比%",
    "international_patents": "PCT/海外专利数量 (估)",
    "citation_impact": "高/中/低 — 专利被引情况",
    "tech_independence": "高/中/低 — 核心技术自主可控程度"
  }},
  "equity_incentive": {{
    "esop_coverage": "员工持股覆盖比例 (估)",
    "lockup_pressure": "高/中/低 — 近期解禁压力",
    "insider_trend": "增持/减持/持平 — 高管买卖趋势",
    "incentive_health": "健康/一般/预警 — 激励计划是否合理"
  }},
  "human_capital_score": 8,
  "score_reason": "评分理由 (1句话)",
  "key_personnel_risk": "关键人员风险 (如: 创始人年近退休/CTO近期离职/核心技术依赖单一人员)",
  "verdict": "STRONG/ADEQUATE/WEAK"
}}

评分标准:
- 8-10 (STRONG): 创始人/CTO 有顶尖大厂/海外名校背景, 专利壁垒强, 激励合理
- 5-7 (ADEQUATE): 团队行业经验尚可, 但有明显短板
- 1-4 (WEAK): 团队资质不足, 专利薄弱, 或存在激励陷阱

搜索结果有限的字段填 null, 不要编造。"""

        try:
            text = await asyncio.wait_for(
                self.provider.chat(prompt, max_tokens=3072), timeout=60)
            result = self.parse_json(text)
            if isinstance(result, dict):
                logger.info(
                    f"[{self.name}] {code} verdict: {result.get('verdict')}, "
                    f"score: {result.get('human_capital_score')}")
                return result
        except asyncio.TimeoutError:
            logger.warning(f"[{self.name}] {code} analysis timeout")
        except Exception as e:
            logger.warning(f"[{self.name}] {code} analysis failed: {e}")

        return {"verdict": "ERROR", "error": "LLM analysis failed"}

    # ═══ 基类实现 ═══════════════════════════════

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return await super().load_context(ctx)

    @staticmethod
    def build_prompt(ctx):
        return "HumanCapitalDetective V4.0"

    @staticmethod
    async def stream(ctx):
        yield "streaming not implemented"
