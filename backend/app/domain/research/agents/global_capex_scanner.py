"""
GlobalCapexScanner V4.0 — 全球前瞻景气度扫描专家
单一职责: 扫描海外巨头(MAG7)财报电话会资本开支计划, 识别全球科技投资趋势
输出: capex_signals + hot_sectors + 全球景气方向
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


class GlobalCapexScanner(ResearchAgent):
    """全球 CapEx 扫描仪 V4.0 — 前瞻景气度, 自上而下"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "GlobalCapexScanner"

    # ═══ 主入口 ═══════════════════════════════════

    async def analyze(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await self.load_context(ctx)
        industry = ctx.get("industry", "")

        if not self.provider:
            return {"agent": self.name, "error": "No AI provider"}

        logger.info(f"[{self.name}] Scanning global capex signals"
                    + (f" for: {industry}" if industry else " (broad)"))

        # 1. 多角度搜索 MAG7 CapEx
        search_data = await self._multi_angle_search(industry)

        # 2. LLM 分析 CapEx 流向
        result = await self._synthesize_capex_signals(industry, search_data)

        result["agent"] = self.name
        result["sources_count"] = search_data.get("total_results", 0)
        return result

    # ═══ 多角度搜索 ═════════════════════════════

    async def _multi_angle_search(self, industry: str) -> Dict:
        """4 个角度并行搜索全球 CapEx 信号"""
        if industry:
            queries = {
                "mag7": f"MAG7 Microsoft Meta Google Amazon capex 2026 AI infrastructure spending billions",
                "hyperscaler": f"hyperscaler datacenter capital expenditure 2026 {industry} cloud",
                "semicon": f"NVIDIA TSMC semiconductor equipment capex 2026 {industry} expansion",
                "supply": f"{industry} global supply chain investment capacity expansion 2026",
            }
        else:
            queries = {
                "mag7": "MAG7 Microsoft Meta Google Amazon Apple capex guidance 2026 AI spending",
                "hyperscaler": "hyperscaler datacenter infrastructure capital expenditure billions 2026",
                "semicon": "NVIDIA TSMC ASML semiconductor capex equipment orders 2026",
                "supply": "global tech supply chain reshoring capacity investment 2026",
            }

        results = {}
        total = 0
        for key, query in queries.items():
            items = []
            for r in await self.data_loader.search_web(query, num=4):
                items.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("snippet", "")[:300],
                })
            results[key] = items
            total += len(items)

        results["total_results"] = total
        return results

    # ═══ LLM 综合分析 ═════════════════════════════

    async def _synthesize_capex_signals(self, industry: str, search: Dict) -> Dict:
        """LLM 将搜索数据综合为 CapEx 景气信号"""
        focus = f"聚焦 {industry} 相关领域" if industry else "全局扫描所有科技领域"

        prompt = f"""你是全球科技产业首席策略师。{focus}。基于以下 MAG7 资本开支数据和供应链情报, 输出全球科技投资景气度判断。

## MAG7 财报/CapEx 搜索结果
{_j(search.get("mag7", []))}

## 超大规模云商 CapEx
{_j(search.get("hyperscaler", []))}

## 半导体设备/产能
{_j(search.get("semicon", []))}

## 供应链投资
{_j(search.get("supply", []))}

## 输出要求: 纯 JSON
{{
  "global_summary": "全球科技 CapEx 核心结论 (2-3句子)",
  "capex_signals": [
    {{
      "sector": "领域名 (如: AI数据中心/先进封装/HBM/光通信)",
      "signal": "ACCELERATING/STABLE/DECELERATING",
      "magnitude": "CapEx 规模估算 (亿美元, 如搜索中有)",
      "growth_yoy": "YoY增速% (估)",
      "key_drivers": "核心驱动因素",
      "mega_cap_source": "MAG7/其他/混合 — 哪类巨头在投",
      "timeline": "预计持续到何时",
      "confidence": "HIGH/MEDIUM/LOW — 依据搜索结果质量"
    }}
  ],
  "hot_sectors": [
    {{
      "name": "最受益赛道名",
      "capex_intensity": 10,
      "reason": "为什么直接受益于上述 CapEx 流向",
      "a_stock_theme": "A股对应主题 (如: 光模块/先进封装设备/半导体材料)"
    }}
  ],
  "divergence_alerts": [
    "任何 CapEx 计划与实际出货数据的背离点 (如搜索结果中有)"
  ],
  "forward_looking": "6-12个月前瞻: 哪些环节可能超预期/低于预期"
}}

评分标准:
- capex_intensity: 1-10, CapEx 流入强度, 10=核心受益环节
- signal: ACCELERATING=加速, STABLE=稳定, DECELERATING=减速
- confidence: 搜索结果充分→HIGH, 有限→MEDIUM, 极少→LOW"""

        try:
            text = await asyncio.wait_for(
                self.provider.chat(prompt, max_tokens=4096), timeout=60)
            result = self.parse_json(text)
            if isinstance(result, dict):
                signals = result.get("capex_signals", [])
                sectors = result.get("hot_sectors", [])
                logger.info(
                    f"[{self.name}] Generated: {len(signals)} capex signals, "
                    f"{len(sectors)} hot sectors")
                return result
        except asyncio.TimeoutError:
            logger.warning(f"[{self.name}] Analysis timeout")
        except Exception as e:
            logger.warning(f"[{self.name}] Analysis failed: {e}")

        return {"error": "LLM analysis failed", "raw_search": search}

    # ═══ 基类实现 ═══════════════════════════════

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await super().load_context(ctx)
        ctx["macro"] = await self.data_loader.load_macro()
        return ctx

    @staticmethod
    def build_prompt(ctx):
        return "GlobalCapexScanner V4.0"

    @staticmethod
    async def stream(ctx):
        yield "streaming not implemented"
