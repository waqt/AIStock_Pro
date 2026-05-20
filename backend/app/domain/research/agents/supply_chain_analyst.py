"""
供应链深度分析师 V3.0 — 迭代自反思 + 结构化深度报告
"""
import json, asyncio, re
from decimal import Decimal
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger


class _SafeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal): return float(obj)
        return super().default(obj)

def _j(obj, **kw):
    kw.setdefault("ensure_ascii", False); kw.setdefault("cls", _SafeEncoder)
    return json.dumps(obj, **kw)


class SupplyChainAnalyst(ResearchAgent):
    """供应链深度分析 V3.0 — 迭代自反思 + 结构化深度报告"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "SupplyChainAnalyst"

    # ═══ 主入口 ═══════════════════════════════════

    async def analyze(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await self.load_context(ctx)
        industry = ctx.get("industry", "未指定")
        codes = ctx.get("stock_codes", [])

        if not self.provider:
            return {"agent": self.name, "error": "No AI provider", "data": ctx}

        # ── Phase 1: 迭代深研 (搜索→分析→自检→补搜) ──
        logger.info(f"[{self.name}] Starting iterative deep research on: {industry}")
        research_data = await self._iterative_deep_research(industry, codes)

        # ── Phase 2: 结构化深度报告 ──
        report = await self._generate_structured_report(industry, research_data, ctx)

        report["industry"] = industry
        report["agent"] = self.name
        return report

    # ═══ Phase 1: 迭代深研 ═════════════════════════

    async def _iterative_deep_research(self, industry: str, codes: List[str]) -> Dict:
        """3 轮迭代: 搜索→分析→自检缺口→补搜→最终分析"""

        all_findings = []
        gaps = []

        for round_num in range(1, 4):
            # 1. 搜索
            if round_num == 1:
                query = f"{industry} 产业 供应链 技术壁垒 龙头公司 2025 2026"
            elif gaps:
                query = f"{industry} {' '.join(gaps[:3])}"
            else:
                break

            search_results = []
            for r in await self.data_loader.search_web(query, num=5):
                search_results.append({"title": r.get("title",""), "url": r.get("url",""), "snippet": r.get("snippet","")[:200]})

            if not search_results and round_num > 1:
                break

            # 2. LLM 分析 + 自检
            prompt = f"""你是全球科技产业研究员。请分析 {industry} 行业的供应链结构和投资机会。

## 本轮搜索结果
{_j(search_results, ensure_ascii=False)}

## 前几轮发现
{_j(all_findings, ensure_ascii=False)}

## 任务
1. 基于搜索结果提取关键信息
2. **自检**: 当前分析够不够深入? 还缺什么关键数据?
   - 缺公司财务数据? 缺技术参数? 缺市占率? 缺产能数据?
3. 如果缺数据, 列出下一轮搜索的关键词 (最多 3 个)

请输出纯 JSON:
{{"findings": [{{"key": "关键发现1", "detail": "细节"}}], "gaps": ["缺口1","缺口2"], "need_more_search": true/false}}"""

            try:
                text = await asyncio.wait_for(self.provider.chat_pro(prompt, max_tokens=2048), timeout=45)
                result = self.parse_json(text)
                if isinstance(result, dict):
                    findings = result.get("findings", [])
                    gaps = result.get("gaps", [])
                    all_findings.extend(findings)
                    if not result.get("need_more_search") and round_num > 1:
                        break
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(f"[{self.name}] Round {round_num} failed: {e}")
                break

        return {"findings": all_findings, "search_rounds": round_num}

    # ═══ Phase 2: 结构化深度报告 ═══════════════════

    async def _generate_structured_report(self, industry: str, research: Dict, ctx: Dict) -> Dict:
        """生成对标 Gemini Deep Research 的结构化深度报告"""

        findings = research.get("findings", [])
        fundamentals = ctx.get("fundamentals", {})
        macro = ctx.get("macro", {})
        positions = ctx.get("positions", [])

        # 再搜一轮确保新鲜度
        fresh_search = []
        for r in await self.data_loader.search_web(f"{industry} 最新 财报 营收 利润 市值 对标 2026", num=5):
            fresh_search.append({"title": r.get("title",""), "url": r.get("url",""), "snippet": r.get("snippet","")[:200]})

        prompt = f"""你是一位首席投资官(CIO), 需要输出一份对标 Gemini Deep Research 质量的深度投研报告。

## 行业
{industry}

## 三轮迭代研究发现
{_j(findings, ensure_ascii=False)}

## 最新搜索 ({len(fresh_search)} 条)
{_j(fresh_search[:5], ensure_ascii=False)}

## A股映射标的估值数据
{_j({c: f for c, f in fundamentals.items() if f.get('pe_ttm')}, ensure_ascii=False)}

## 宏观环境
{_j(macro, ensure_ascii=False)}

## 输出要求: 纯 JSON, 结构化深度报告
{{
  "summary": "核心结论 2-3 句",
  "core_stocks": [
    {{
      "code": "688361",
      "name": "公司全称",
      "exchange": "SH/SZ/HK/US",
      "revenue": "最近年度营收 (亿元/亿美元, 注明单位)",
      "revenue_growth": "营收增速%",
      "profit": "归母净利润 (亿元/亿美元)",
      "profit_growth": "利润增速%",
      "gross_margin": "毛利率%",
      "market_cap": "当前市值 (亿元/亿美元)",
      "target_mcap": "目标市值区间",
      "upside": "上涨空间%",
      "global_peer": "全球对标公司+代码",
      "peer_ps": 15.5,
      "peer_pe": 45.0,
      "key_tech": "核心技术壁垒 (1句话)",
      "moat": "护城河原因 (技术专利/客户认证/人才壁垒)",
      "moat_type": "技术垄断/寡头格局/国产替代/标准制定",
      "founder_background": "创始人/CTO 关键履历 (如有)",
      "human_capital_score": 8,
      "scissor_gap": {{
        "revenue_growth": "48%",
        "profit_growth": "609%",
        "margin_trend": "上升/下降/持平",
        "contract_liability_change": "合同负债变化%",
        "verdict": "PASS/FAIL — 原因"
      }},
      "risk": "核心风险 (1句话)",
      "catalysts": "近期催化剂",
      "position_suggest": "建议仓位%"
    }}
  ],
  "supply_chain_map": [
    {{"level": 1, "name": "显性瓶颈名称", "gap_score": 3, "gap_reason": "已被充分定价"}},
    {{"level": 2, "name": "工艺瓶颈", "gap_score": 8, "gap_reason": "市场未认知"}},
    {{"level": 3, "name": "材料瓶颈", "gap_score": 9, "gap_reason": "消耗倍增未定价"}},
    {{"level": 4, "name": "设备/测试瓶颈", "gap_score": 10, "gap_reason": "全市场忽视"}}
  ],
  "temporal": [
    {{"segment": "环节名", "demand_growth": "25%", "supply_gap": "15%", "gap_filled": "2027-Q2", "overcapacity_risk": "2028-Q1", "heat_level": "合理/偏热/过热"}}
  ],
  "valuation_peers": [
    {{"name": "全球对标A", "code": "KLAC", "exchange": "US", "pe": 45, "ps": 17, "relevance": "直接对标"}}
  ],
  "risk_alerts": [
    {{"type": "物理/财务/地缘/技术替代", "severity": "高/中/低", "description": "..."}}
  ],
  "watchlist": ["后续关键跟踪指标1", "指标2"]
}}

每个财务数据字段如果搜索结果中有就填, 没有就基于训练知识估算并标注 (估)。"""

        try:
            text = await asyncio.wait_for(self.provider.chat_pro(prompt, max_tokens=8192), timeout=90)
            if not text:
                logger.warning(f"[{self.name}] Phase 2: provider returned empty response")
                return {"summary": "结构化报告生成失败: AI 无响应", "raw_findings": findings}
            logger.info(f"[{self.name}] Phase 2 response length: {len(text)} chars")
            report = self.parse_json(text)
            if isinstance(report, dict) and report.get("core_stocks"):
                logger.info(f"[{self.name}] Phase 2: generated report with {len(report['core_stocks'])} core stocks")
                return report
            else:
                logger.warning(f"[{self.name}] Phase 2: JSON parsed but missing core_stocks. Keys: {list(report.keys()) if isinstance(report, dict) else type(report).__name__}")
                # Return whatever we got
                if isinstance(report, dict):
                    report["raw_findings"] = findings
                    return report
        except asyncio.TimeoutError:
            logger.warning(f"[{self.name}] Phase 2: timed out (90s)")
        except Exception as e:
            logger.warning(f"[{self.name}] Phase 2: {type(e).__name__}: {e}")

        return {"summary": "结构化报告生成失败", "raw_findings": findings}

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await super().load_context(ctx)
        ctx["macro"] = await self.data_loader.load_macro()
        ctx["positions"] = await self.data_loader.load_positions()
        return ctx

    def build_prompt(self, ctx): return "SupplyChainAnalyst V3.0"
    async def stream(self, ctx): yield "streaming not implemented"
