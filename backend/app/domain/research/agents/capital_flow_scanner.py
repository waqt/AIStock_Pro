"""
CapitalFlowScanner V1.2 — Step 1b: 资本+能源双维流向扫描
定位: 资本流向(谁在花钱?) + 能源流向(谁在开足马力生产?)
V1.2: +能源流向扫描维度, 用电量增速=产业活跃度硬信号, 无法造假
输出: pressure_vectors + constraint_vectors + energy_flow_signals
"""
import asyncio, re
from decimal import Decimal
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger


class CapitalFlowScanner(ResearchAgent):
    """资本+能源双维流向扫描 V1.2 — 钱去了哪? 电耗在了哪?"""

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

    # ═══ 搜索链构建 ═══════════════════════════════

    def _build_search_chains(self, industry: str = None) -> List[List[str]]:
        """资本流向搜索链 — 由用户行业驱动, 不预设赛道"""
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
        # 无行业指定 → 宽泛扫描
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
            [f"中国 央企 国企 龙头 资本开支 扩产 投资 2026",
             f"中国 大型企业 资本开支 CAPEX 产业投资 2026",
             f"china state enterprise capex industrial investment 2026"],
        ]

    def _build_energy_chains(self, industry: str = None) -> List[List[str]]:
        """能源流向搜索链 — 用电量增速 = 产业活跃度硬信号 (无法造假)"""
        if industry and industry.strip():
            ind = industry.strip()
            return [
                [f"{ind} 用电量 电力消费 增速 产能利用率 2026",
                 f"{ind} 电力需求 耗电 增长 2026",
                 f"{ind} electricity consumption growth 2026"],
                [f"{ind} 能源消耗 开工率 产量 产能 扩张 2026",
                 f"{ind} 产能利用率 高负荷 满产 2026",
                 f"{ind} capacity utilization production surge 2026"],
            ]
        return [
            [f"中国 行业 用电量 增速 排名 电力消费 2026",
             f"各地 用电量 增长 最快 行业 2026",
             f"china industry electricity consumption growth 2026"],
            [f"中国 高耗能 行业 产能利用率 开工率 2026",
             f"工业 用电量 产能 扩张 高景气 2026",
             f"china industrial capacity utilization 2026"],
        ]

    # ═══ 主入口 ═══════════════════════════════

    async def analyze(self, ctx: Dict[str, Any] = None, trace=None) -> Dict[str, Any]:
        ctx = await self.load_context(ctx or {})
        if not self.provider:
            return {"agent": self.name, "error": "No AI provider"}

        industry = ctx.get("industry", ctx.get("target_industry", ""))
        macro_regime = ctx.get("macro", {}).get("regime", "")

        logger.info(f"[{self.name}] V1.2 dual-scan: industry='{industry or '(broad)'}', regime='{macro_regime}'")

        # 并行: 资本流向 + 能源流向
        capital_chains = self._build_search_chains(industry if industry else None)
        energy_chains = self._build_energy_chains(industry if industry else None)

        capital_data, energy_data = await asyncio.gather(
            self._search_adaptive(capital_chains, num=4, trace=trace),
            self._search_adaptive(energy_chains, num=4, trace=trace),
        )

        industry_hint = ""
        if industry:
            industry_hint = f"用户关注行业: {industry}。请聚焦该行业相关的资本/能源流向和供给约束。"

        # 构建 prompt
        prompt = f"""你是全球资本与能源流向分析师。从两个维度扫描产业系统的承压点。

## 维度一: 资本流向 — 谁在花钱? 花在哪?
核心问题: 全球+中国的大型资本开支主体, 把钱投向哪些产业环节? 哪些系统节点正在承压?

## 维度二: 能源流向 — 谁在开足马力生产?
核心问题: 哪些行业的用电量/能源消耗在快速增长? 用电量增速=产业活跃度硬信号, 无法财务造假。
电力消费激增的行业 → 真实产能扩张 → 高景气确认。
电力消费骤降的行业 → 产能收缩 → 景气下行预警。

{industry_hint}
注意: 输出只描述系统级别的承压节点, 不要出现具体产业名称或股票代码。

## 资本流向搜索结果
"""
        for i, sd in enumerate(capital_data):
            prompt += f"\n### capital[{i+1}]: {sd['query']}\n"
            if not sd["results"]:
                prompt += "  (无结果)\n"
            for j, r in enumerate(sd["results"][:3]):
                prompt += f"  [{i+1}.{j+1}] {r['title']}: {r['snippet'][:200]}\n"

        prompt += "\n## 能源流向搜索结果\n"
        for i, sd in enumerate(energy_data):
            prompt += f"\n### energy[{i+1}]: {sd['query']}\n"
            if not sd["results"]:
                prompt += "  (无结果)\n"
            for j, r in enumerate(sd["results"][:3]):
                prompt += f"  [{i+1}.{j+1}] {r['title']}: {r['snippet'][:200]}\n"

        prompt += """
## 输出纯 JSON

{
  "capital_flow_summary": "资本流向一句话",
  "energy_flow_summary": "能源流向一句话: 哪些行业用电量增速最快/最慢, 说明了什么",

  "pressure_vectors": [
    {
      "capital_source": "资本来源",
      "source_region": "global/domestic/both",
      "system_node": "承压的系统节点",
      "pressure_type": "infrastructure_bottleneck",
      "pressure_signals": ["具体压力信号"],
      "intensity": "high",
      "duration": "3_5_years",
      "transmission_direction": "upstream",
      "evidence": [
        {"fact": "事实", "from": "capital[X.Y]·来源",
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
      "trigger": "触发条件",
      "evidence": [...]
    }
  ],

  "energy_flow_signals": [
    {
      "sector_hint": "用电量快速增长的行业方向 (非具体产业名, 如 '先进制造' '算力基础设施')",
      "energy_type": "electricity/gas/water/coal",
      "growth_direction": "surging/growing/stable/declining",
      "growth_narrative": "用电量增速约XX%, 反映真实产能扩张正在发生",
      "signal_strength": "strong/moderate/weak — 能源信号的可信度",
      "evidence": [
        {"fact": "事实", "from": "energy[X.Y]·来源",
         "quality": {"level": "medium", "source_type": "industry_data"}}
      ]
    }
  ]
}

## 枚举约束 (★ 强制)
- source_region: global / domestic / both
- intensity: high / moderate / low
- duration: under_1_year / 1_3_years / 3_5_years / over_5_years
- pressure_type: infrastructure_bottleneck | equipment_lead_time | natural_resource | certification_barrier | policy_restriction
- transmission_direction: upstream / downstream / bidirectional
- constraint_type: equipment_lead_time | natural_resource | certification_barrier | policy_restriction | infrastructure_bottleneck
- severity: extreme / high / moderate
- lead_time: under_12m / 12_24m / over_24m
- growth_direction: surging / growing / stable / declining
- signal_strength: strong / moderate / weak

## 规则 (★ 重要)
- pressure_vectors 至少 2 条, 最多 5 条
- energy_flow_signals 至少 1 条, 最多 3 条 — 从能源流向中提炼最显著的信号
- system_node 只能描述系统级别的承压点 (如 power_infrastructure/thermal_management/memory_bandwidth)
- sector_hint 不要用具体产业名 (如 "变压器" "液冷"), 用方向性描述 (如 "先进制造" "算力基础设施")
- 禁止出现股票代码或公司名
- 每条 evidence 必须带 quality 和来源标注 (capital[X] / energy[X])
- 不做宏观叙事, 不做受益分析
- 能源信号必须与资本信号交叉印证: 资本密集流入 + 用电量激增 = 最强景气确认"""

        try:
            text = await asyncio.wait_for(
                self.provider.chat_flash(prompt, max_tokens=4096), timeout=60)
            if trace: trace.record_llm(prompt, text, model="deepseek-v4-flash")
            result = self.parse_json(text)
            if isinstance(result, dict):
                n_pressure = len(result.get("pressure_vectors", []))
                n_constraint = len(result.get("constraint_vectors", []))
                n_energy = len(result.get("energy_flow_signals", []))
                logger.info(f"[{self.name}] Done: {n_pressure} pressure, {n_constraint} constraints, {n_energy} energy signals")
                if trace:
                    trace.record_note("summary", f"pressure={n_pressure}, constraints={n_constraint}, energy={n_energy}")
                return result
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"[{self.name}] Failed: {e}")

        return {"agent": self.name, "error": "Analysis failed",
                "pressure_vectors": [], "constraint_vectors": [], "energy_flow_signals": []}

    # ═══ 基类 ═══════════════════════════════

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await super().load_context(ctx)
        ctx["macro"] = await self.data_loader.load_macro()
        return ctx

    @staticmethod
    def build_prompt(ctx): return "CapitalFlowScanner V1.2"

    @staticmethod
    async def stream(ctx): yield "streaming not implemented"
