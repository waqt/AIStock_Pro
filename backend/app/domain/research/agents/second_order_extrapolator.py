"""
SecondOrderExtrapolator V1.0 — Path B: 二阶推演
定位: 当主产业链逻辑硬但认知差弱时, 外推相邻产业/节点中的预期差。
区别于 Step 5 (CrossIndustryLinkage): Step 5 依赖 Step 3+4 数据做跨产业关联,
此 Agent 仅依赖 Step 2 输出, 从 transmission_order + cycle_position 出发,
寻找市场尚未定价的相邻产业机会。
"""
import asyncio, json, re
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger


class SecondOrderExtrapolator(ResearchAgent):
    """二阶推演 V1.0 — 从 Step 2 输出寻找相邻产业的预期差"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "SecondOrderExtrapolator"

    # ═══ 工具 ═══════════════════════════════

    @staticmethod
    def _clean_snippet(text: str) -> str:
        if not text: return ""
        if "%PDF" in text or "endstream" in text: return ""
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
        return text[:250]

    async def _search_adaptive(self, chains: List[List[str]], num: int = 4, trace=None) -> List[Dict]:
        all_data = []
        for chain in chains:
            items = []
            for q in chain:
                results = await self.data_loader.search_web(q, num=num)
                items = []
                for r in results:
                    snippet = self._clean_snippet(r.get("snippet", ""))
                    if snippet:
                        items.append({"title": r.get("title", ""), "snippet": snippet})
                if trace: trace.record_search(q, items)
                if items: break
            all_data.append({"query": chain[0] if not items else q, "results": items})
        return all_data

    # ═══ 提取 Step 2 关键节点 ═══════════════════

    @staticmethod
    def _extract_key_nodes(step2_output: Dict) -> List[Dict]:
        """从 Step 2 的 transmission_order 提取价值传导节点"""
        propagation = step2_output.get("propagation", {}) if isinstance(step2_output, dict) else {}
        order = propagation.get("transmission_order", [])
        nodes = []
        for node in order:
            if isinstance(node, dict) and node.get("node"):
                nodes.append({
                    "name": node.get("node", ""),
                    "reason": node.get("reason", node.get("detail", "")),
                    "role": node.get("role", "transmission"),
                })
        return nodes

    # ═══ 主入口 ═══════════════════════════════

    async def analyze(self, ctx: Dict[str, Any] = None, trace=None) -> Dict[str, Any]:
        ctx = await self.load_context(ctx or {})
        if not self.provider:
            return {"agent": self.name, "error": "No AI provider"}

        industry = ctx.get("industry", "未指定")
        step2 = ctx.get("step2_output", {})
        step2_guidance = ctx.get("step2_guidance", {})

        key_nodes = self._extract_key_nodes(step2)
        cycle_position = step2.get("cycle_position", {})
        catalysts = step2.get("catalysts", []) or []
        kill_reasons = step2.get("kill_reasons", []) or []

        logger.info(f"[{self.name}] Second-order: {industry} ({len(key_nodes)} nodes, {len(catalysts)} catalysts)")

        if not key_nodes:
            logger.warning(f"[{self.name}] No transmission_order nodes found in Step 2 output")
            return {"agent": self.name, "confidence": "insufficient_data",
                    "adjacent_industries": [], "recommended_drilldown": [],
                    "note": "Step 2 未提供 transmission_order 节点信息"}

        # 节点摘要
        node_summary = "\n".join(
            f"- {n['name']}: {n['reason'][:150] if n.get('reason') else '(无说明)'}"
            for n in key_nodes[:5])
        catalyst_str = "\n".join(
            f"- {c.get('catalyst','')}: expect={c.get('expected_date','?')}, watch_signal={c.get('watch_signal','?')}"
            for c in catalysts[:4])
        kill_str = "\n".join(f"- {k.get('reason','')}" for k in kill_reasons[:3])

        # 多轮 Web 搜索
        node_names = [n["name"] for n in key_nodes[:3]]
        search_chains = [
            # Round 1: 瓶颈节点还影响哪些行业
            [f"{' '.join(node_names)} 还用于哪些行业 下游 应用 领域",
             f"{node_names[0] if node_names else ''} 应用领域 下游行业"],
            # Round 2: 隐藏受益者
            [f"{' '.join(node_names)} 供给紧张 隐藏受益者 未被市场关注 预期差 2026",
             f"{' '.join(node_names)} 受益标的 未被充分定价"],
            # Round 3: 跨产业溢出效应
            [f"{' '.join(node_names)} 涨价 溢出效应 影响 其他行业 利润弹性 2026",
             f"{' '.join(node_names)} supply chain spillover beneficiary 2026"],
            # Round 4: 资源挤占效应
            [f"{' '.join(node_names)} 产能挤占 产能紧缺 替代效应 受益行业",
             f"{' '.join(node_names)} 供需缺口 国产替代 受益方向"],
        ]

        all_search_data = []
        for chain in search_chains:
            data = await self._search_adaptive([chain], num=4, trace=trace)
            all_search_data.extend(data)

        # 构建 LLM prompt
        s_summary = ""
        for sd in all_search_data:
            s_summary += f"\n### {sd['query']}\n"
            for r in sd["results"][:3]:
                s_summary += f"  - {r['title']}: {r['snippet'][:180]}\n"

        prompt = f"""你是二阶思维分析师。Step 2 已经分析了"{industry}"产业的逻辑和传导路径。
你的任务不是重复分析这个产业, 而是**外推**: 寻找市场尚未定价的相邻产业/跨产业机会。

## Step 2 结论: 价值传导节点
{node_summary}

## 催化剂
{catalyst_str}

## 证伪信号
{kill_str}

## 周期定位
{json.dumps(cycle_position, indent=2, ensure_ascii=False) if isinstance(cycle_position, dict) else str(cycle_position)}

## Web 搜索证据
{s_summary}

## 输出格式
{{
  "confidence": "high/medium/low",
  "analysis_approach": "二阶思维的简要说明",
  "adjacent_industries": [
    {{
      "name": "相邻产业名称",
      "derived_from": "从哪个价值节点推导而来",
      "linkage_type": "shared_equipment / crowding_out / horizontal_benefit / resource_crowding / technology_spillover",
      "expectation_gap": "strong / medium / weak",
      "expectation_gap_analysis": "详细分析: 市场为什么没有定价这个逻辑? 预期差在哪里? 需要什么条件触发定价?",
      "time_to_impact": "触发预期差收敛的时间窗口, 如 '6-12个月'",
      "a_share_exposure": "A股相关方向/标的(产业级, 不是个股推荐)",
      "search_evidence": ["搜索证据1", "搜索证据2"]
    }}
  ],
  "recommended_drilldown": [
    "建议 Step 3 深挖的产业1",
    "建议 Step 3 深挖的产业2"
  ],
  "second_order_logic": "二阶推导的完整逻辑链"
}}

## 要求
1. **二阶思维**: 看"别人没看到"的关系。不是简单找 "X的上游", 而是找:
   - 共享同一稀缺资源的两个产业, 一个景气挤压另一个
   - 某个瓶颈缓解后, 最大的意外受益者
   - 市场认为"A利好B", 但实际"A利好C"(市场错配)
2. **预期差为核心**: expectation_gap=weak → 不输出。只有 strong/medium 才是有价值的二阶推演
3. **必须有搜索证据支撑**: 每条 evidence 都要能追溯到搜索结果
4. **禁止**输出个股推荐。只输出产业级方向
5. **格式**: 纯JSON, 不包含其他文字"""

        try:
            text = await self.provider.chat_pro(prompt, max_tokens=4096, timeout=300)
            if trace: trace.record_llm(prompt, text, model="deepseek-v4-pro")
            result = self.parse_json(text)
            if isinstance(result, dict):
                n_adj = len(result.get("adjacent_industries", []))
                n_drill = len(result.get("recommended_drilldown", []))
                confident = result.get("confidence", "?")
                logger.info(f"[{self.name}] Done: confidence={confident}, adjacent={n_adj}, drilldown={n_drill}")
                return result
        except asyncio.TimeoutError:
            logger.warning(f"[{self.name}] Timeout: {industry}")
        except Exception as e:
            logger.warning(f"[{self.name}] Failed: {e}")

        return {"agent": self.name, "confidence": "low", "error": "Analysis failed",
                "adjacent_industries": [], "recommended_drilldown": []}

    # ═══ 基类 ═══════════════════════════════

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return await super().load_context(ctx)

    @staticmethod
    def build_prompt(ctx): return "SecondOrderExtrapolator V1.0"

    @staticmethod
    async def stream(ctx): yield "streaming not implemented"
