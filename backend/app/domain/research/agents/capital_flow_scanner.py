"""
CapitalFlowScanner V1.1 — Step 1b: 全球资本流向扫描
定位: 寻找全球资本正在挤压产业系统的位置 — 行业无关, 不预设赛道
V1.1: 搜索链由用户行业+宏观regime动态生成, 去除硬编码AI/电力偏向
输出: pressure_vectors + constraint_vectors
"""
import asyncio, re
from decimal import Decimal
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger


class CapitalFlowScanner(ResearchAgent):
    """资本流向扫描 V1.1 — 谁在花钱? 花在哪? 约束在哪? (行业无关)"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "CapitalFlowScanner"

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

    # ═══ 主入口 ═══════════════════════════════

    def _build_search_chains(self, industry: str = None) -> List[List[str]]:
        """构建搜索链 — 由用户行业驱动, 不预设赛道"""
        if industry and industry.strip():
            ind = industry.strip()
            return [
                [f"{ind} 全球 资本开支 CAPEX 投资 龙头 2026",
                 f"{ind} related global capex investment 2026",
                 f"global {ind} capital expenditure spending"],
                [f"{ind} 产业链 瓶颈 产能 供给约束 短缺 2026",
                 f"{ind} 供应链 制约 产能缺口 2026",
                 f"{ind} supply chain bottleneck constraint 2026"],
                [f"中国 {ind} 专项债 财政 投资 扩产 2026",
                 f"{ind} 中国 政策 支持 产能扩张 2026",
                 f"china {ind} fiscal investment expansion 2026"],
                [f"{ind} 受益方 供应商 产业链 上游 设备 材料 2026",
                 f"{ind} 供应链 国产替代 受益标的",
                 f"{ind} supply chain beneficiary equipment material"],
                [f"中国 央企 国企 {ind} 资本开支 布局 投资 2026",
                 f"{ind} 中国 龙头企业 CAPEX 扩产 2026",
                 f"china state enterprise {ind} capex investment"],
            ]
        # 无行业指定 → 宽泛扫描全球+中国资本流向
        return [
            [f"2026 全球 资本开支 CAPEX 投资 趋势 行业",
             f"global capex investment trend sector 2026",
             f"global capital expenditure spending 2026"],
            [f"2026 全球 供应链 瓶颈 产能 短缺 制约",
             f"global supply chain bottleneck shortage constraint 2026",
             f"global industrial capacity shortage bottleneck"],
            [f"中国 专项债 财政支出 产业投资 投向 2026",
             f"中国 财政 产业政策 投资 方向 2026",
             f"china fiscal spending industrial investment 2026"],
            [f"全球 资本流向 产业 受益方 供应商 2026",
             f"global capital flow beneficiary sector 2026",
             f"capex beneficiary supplier equipment 2026"],
            [f"中国 央企 国企 资本开支 扩产 投资 方向 2026",
             f"中国 国家电网 中芯国际 三大运营商 资本开支 2026",
             f"china state enterprise capex investment 2026"],
        ]

    async def analyze(self, ctx: Dict[str, Any] = None, trace=None) -> Dict[str, Any]:
        ctx = await self.load_context(ctx or {})
        if not self.provider:
            return {"agent": self.name, "error": "No AI provider"}

        # 从 ctx 获取行业 (用户指定的, 或 Step 1a macro_regime 推断的)
        industry = ctx.get("industry", ctx.get("target_industry", ""))
        macro_regime = ctx.get("macro", {}).get("regime", "")

        logger.info(f"[{self.name}] Scanning: industry='{industry or '(broad)'}', regime='{macro_regime}'")

        search_chains = self._build_search_chains(industry if industry else None)
        search_data = await self._search_adaptive(search_chains, num=4, trace=trace)

        # 行业提示
        industry_hint = ""
        if industry:
            industry_hint = f"用户关注行业: {industry}。请聚焦该行业相关的资本流向和供给约束, 但不要将视野局限于该行业本身——关注上下游相关的系统节点。"

        # LLM 结构化输出
        prompt = f"""你是全球资本流向分析师。你的任务不是写宏观报告, 而是识别**全球资本正在挤压哪些产业系统**。

核心问题: 谁在花钱(全球+中国)? 花在哪? 规模多大? 哪个系统节点先承压?
{industry_hint}
注意: 必须同时覆盖全球巨头和中国国内资本开支主体, 不要遗漏国内 initiator。
输出只描述系统级别的承压节点 (如基础设施/设备交期/自然资源/认证壁垒/政策管制), 不要出现具体产业名称或股票代码。

## 搜索结果
"""
        for i, sd in enumerate(search_data):
            prompt += f"\n### search[{i+1}]: {sd['query']}\n"
            if not sd["results"]:
                prompt += "  (无结果)\n"
            for j, r in enumerate(sd["results"][:3]):
                prompt += f"  [{i+1}.{j+1}] {r['title']}: {r['snippet'][:200]}\n"

        prompt += """
## 输出纯 JSON

{
  "capital_flow_summary": "一句话: 全球资本正集中流向..., ...已成瓶颈",

  "capital_flow_summary": "一句话: 全球资本正集中流向..., ...系统正在承压",

  "pressure_vectors": [
    {
      "capital_source": "资本来源 (MAG7/国家电网/三大运营商/专项债...)",
      "source_region": "global/domestic/both",
      "system_node": "承压的系统节点 (power_infrastructure/thermal_management/memory_bandwidth...)",
      "pressure_type": "infrastructure_bottleneck",
      "pressure_signals": ["具体压力信号1", "信号2", "信号3"],
      "intensity": "high",
      "duration": "3_5_years",
      "transmission_direction": "upstream",
      "evidence": [
        {"fact": "具体事实", "from": "search[X.Y]·来源",
         "quality": {"level": "high", "source_type": "company_filing"}}
      ]
    }
  ],

  "constraint_vectors": [
    {
      "node": "约束节点",
      "constraint_type": "equipment_lead_time",
      "severity": "extreme",
      "lead_time": "over_24m",
      "trigger": "什么需求触发了这个约束",
      "evidence": [...]
    }
  ]
}

## 枚举约束 (★ 强制)
- source_region: global / domestic / both
- intensity: high / moderate / low
- duration: under_1_year / 1_3_years / 3_5_years / over_5_years
- pressure_type:
  infrastructure_bottleneck (基础设施瓶颈) | equipment_lead_time (设备交期) |
  natural_resource (自然资源稀缺) | certification_barrier (认证壁垒) |
  policy_restriction (政策管制)
- transmission_direction: upstream / downstream / bidirectional
- constraint_type:
  equipment_lead_time | natural_resource | certification_barrier |
  policy_restriction | infrastructure_bottleneck
- severity: extreme / high / moderate
- lead_time: under_12m / 12_24m / over_24m

## 规则 (★ 重要)
- pressure_vectors 至少 2 条, 最多 5 条
- system_node 只能描述系统级别的承压点 (如 power_infrastructure/thermal_management/memory_bandwidth)
- 禁止出现产业名称 (如"变压器""液冷""HBM") — 这些留给 Step 2 判断
- 禁止出现股票代码或公司名
- 每条 evidence 必须带 quality (level: high/medium/low, source_type 枚举)
- 不做宏观叙事 (不要"滞胀""风险偏好下降"等套话)
- 不做受益分析 (不要"XX产业受益")"""

        try:
            text = await asyncio.wait_for(
                self.provider.chat_flash(prompt, max_tokens=4096), timeout=60)
            if trace: trace.record_llm(prompt, text, model="deepseek-v4-flash")
            result = self.parse_json(text)
            if isinstance(result, dict):
                n_pressure = len(result.get("pressure_vectors", []))
                n_constraint = len(result.get("constraint_vectors", []))
                logger.info(f"[{self.name}] Done: {n_pressure} pressure vectors, {n_constraint} constraints")
                if trace: trace.record_note("summary", f"pressure={n_pressure}, constraints={n_constraint}")
                return result
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"[{self.name}] Failed: {e}")

        return {"agent": self.name, "error": "Analysis failed",
                "pressure_vectors": [], "constraint_vectors": []}

    # ═══ 基类 ═══════════════════════════════

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await super().load_context(ctx)
        ctx["macro"] = await self.data_loader.load_macro()
        return ctx

    @staticmethod
    def build_prompt(ctx): return "CapitalFlowScanner V1.0"

    @staticmethod
    async def stream(ctx): yield "streaming not implemented"
