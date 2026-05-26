"""
CapitalFlowScanner V1.0 — Step 1b: 全球资本流向扫描
定位: 寻找全球资本正在挤压产业系统的位置
输出: capex_vectors + constraint_vectors
"""
import asyncio, re
from decimal import Decimal
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger


class CapitalFlowScanner(ResearchAgent):
    """资本流向扫描 — 谁在花钱? 花在哪? 约束在哪?"""

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

    async def analyze(self, ctx: Dict[str, Any] = None, trace=None) -> Dict[str, Any]:
        ctx = await self.load_context(ctx or {})
        if not self.provider:
            return {"agent": self.name, "error": "No AI provider"}

        logger.info(f"[{self.name}] Scanning global capital flows...")

        # 4 轮自适应搜索
        search_chains = [
            [f"MAG7 科技巨头 CAPEX 资本开支 2025 2026 数据中心 芯片",
             f"大型科技企业 资本开支 AI 2026",
             f"global tech capex spending AI 2026"],
            [f"AI数据中心 电力 变压器 液冷 交期 瓶颈 2026",
             f"数据中心 电力瓶颈 变压器短缺 2026",
             f"data center power constraint transformer shortage"],
            [f"中国 专项债 财政支出 投向 算力 电网 2026",
             f"专项债 基建 新质生产力 半导体 2026",
             f"china fiscal spending infrastructure 2026"],
            [f"AI芯片 光模块 液冷 先进封装 国产替代 受益 A股 2026",
             f"算力产业链 国产化 受益标的 A股",
             f"china AI supply chain beneficiary stocks"],
            [f"国家电网 中芯国际 三大运营商 中国国企 CAPEX 资本开支 2026",
             f"中国 央企 国企 资本开支 投资 算力 电网 半导体 2026",
             f"china state grid SMIC telecom capex investment 2026"],
        ]

        search_data = await self._search_adaptive(search_chains, num=4, trace=trace)

        # LLM 结构化输出
        prompt = f"""你是全球资本流向分析师。你的任务不是写宏观报告, 而是识别**全球资本正在挤压哪些产业系统**。

核心问题: 谁在花钱(全球+中国)? 花在哪? 规模多大? 约束在哪? 中国谁受益?
注意: 必须同时覆盖全球巨头(MAG7等)和中国国内资本开支主体(国家电网/中芯国际/三大运营商等), 不要遗漏国内 initiator。

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

  "capex_vectors": [
    {
      "initiator": "花钱的主体 (MAG7/国家电网/三大运营商/中芯国际/专项债...)",
      "initiator_region": "global/domestic/both",
      "target": "资金流向的目标产业 (AI数据中心/电网升级/先进封装...)",
      "capex_scale": "CAPEX规模估算",
      "growth": "high",
      "duration": "3_5_years",
      "constraints": ["物理约束1", "物理约束2"],
      "china_exposure": "high",
      "china_beneficiary": ["受益产业1", "受益产业2"],
      "theme_type": "industrial_capex",
      "evidence": [
        {"fact": "具体事实", "from": "search[X.Y]·来源",
         "quality": {"level": "high", "source_type": "company_filing"}}
      ]
    }
  ],

  "constraint_vectors": [
    {
      "node": "约束节点 (变压器/液冷/先进封装...)",
      "constraint_type": "equipment_lead_time",
      "severity": "extreme",
      "lead_time": "18_24_months",
      "upstream_trigger": "什么需求触发了这个约束",
      "downstream_impact": ["影响1", "影响2"],
      "evidence": [...]
    }
  ],

  "theme_type_distribution": {
    "industrial_capex": 0,
    "commodity_cycle": 0,
    "macro_asset": 0,
    "policy_theme": 0
  }
}

## 枚举约束 (★ 强制)
- growth: high / moderate / low
- duration: under_1_year / 1_3_years / 3_5_years / over_5_years
- china_exposure: high / medium / low / none
- theme_type:
  industrial_capex (实体产业资本开支, Step2可消费) |
  commodity_cycle (商品周期, 部分可消费) |
  policy_theme (政策主题, 需拆分为具体产业) |
  macro_asset (宏观交易资产, 不进Step2)
- constraint_type:
  equipment_lead_time (设备交期) | natural_resource (资源稀缺) |
  certification_barrier (认证壁垒) | policy_restriction (政策管制) |
  infrastructure_bottleneck (基础设施瓶颈)
- severity: extreme / high / moderate
- lead_time: under_6_months / 6_12_months / 12_18_months / 18_24_months / over_24_months

## 规则
- capex_vectors 至少 3 条, 最多 5 条
- 优先 industrial_capex 类型
- 每条 evidence 必须带 quality (level: high/medium/low, source_type 枚举)
- "新质生产力""国产替代"等宏观口号不算 capex_vector — 必须拆分为具体产业
- 不做宏观叙事 (不要"滞胀""风险偏好下降"等套话)"""

        try:
            text = await asyncio.wait_for(
                self.provider.chat_pro(prompt, max_tokens=4096), timeout=120)
            if trace: trace.record_llm(prompt, text, model="deepseek-v4-pro")
            result = self.parse_json(text)
            if isinstance(result, dict):
                n_capex = len(result.get("capex_vectors", []))
                n_constraint = len(result.get("constraint_vectors", []))
                logger.info(f"[{self.name}] Done: {n_capex} capex vectors, {n_constraint} constraints")
                if trace: trace.record_note("summary", f"capex={n_capex}, constraints={n_constraint}")
                return result
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"[{self.name}] Failed: {e}")

        return {"agent": self.name, "error": "Analysis failed",
                "capex_vectors": [], "constraint_vectors": []}

    # ═══ 基类 ═══════════════════════════════

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await super().load_context(ctx)
        ctx["macro"] = await self.data_loader.load_macro()
        return ctx

    @staticmethod
    def build_prompt(ctx): return "CapitalFlowScanner V1.0"

    @staticmethod
    async def stream(ctx): yield "streaming not implemented"
