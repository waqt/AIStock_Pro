"""
RiskAnalysisAgent V1.0 — Step 10: 风险分析
定位: 系统性风险评估 — 对 Pipeline 筛选出的候选标的进行多维度风险扫描
核心问题: 什么可能出错? 什么信号出现时需要重新评估?
方法论: 六维风险框架 + 情景压力测试
"""
import asyncio, re
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger
from app.framework.pipeline.glossary import inject_glossary


class RiskAnalysisAgent(ResearchAgent):
    """风险分析 V1.0 — 六维风险框架 + 情景分析"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "RiskAnalysisAgent"

    # ═══ 工具 ═══════════════════════════════

    @staticmethod
    def _clean_snippet(text: str) -> str:
        if not text: return ""
        if "%PDF" in text or "endstream" in text: return ""
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
        return text[:300]

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

    @staticmethod
    def _format_candidates(step6_out: dict) -> str:
        """格式化候选股票列表"""
        lines = []
        ranked = step6_out.get("ranked_stocks", [])
        future = step6_out.get("future_strong_candidates", [])

        for s in ranked[:8]:
            v = s.get("verification", {})
            theses = []
            if isinstance(v, dict):
                tb = v.get("thesis_breakers", [])
                if tb: theses = [t[:100] for t in tb[:2]]
            lines.append(f"- {s.get('code','?')} {s.get('name','?')}: rank={s.get('rank','?')}, stage={s.get('company_stage','?')}")
            if theses:
                lines.append(f"  └ thesis_breakers: {'; '.join(theses)}")

        for s in future[:4]:
            lines.append(f"- {s.get('code','?')} {s.get('name','?')}: category={s.get('category','?')}")

        return "\n".join(lines) if lines else "(无候选标的)"

    # ═══ 主入口 ═══════════════════════════════

    async def analyze(self, ctx: Dict[str, Any] = None, trace=None) -> Dict[str, Any]:
        ctx = await self.load_context(ctx or {})
        if not self.provider:
            return {"agent": self.name, "error": "No AI provider"}

        industry = ctx.get("industry", "未指定")
        step6_out = ctx.get("step6_output", {})
        step9_out = ctx.get("step9_output", {})
        step4_out = ctx.get("step4_output", {})

        if not step6_out:
            logger.warning(f"[{self.name}] {industry}: no Step 6 output, skipping")
            return {"agent": self.name, "industry": industry, "error": "No Step 6 output", "risks": []}

        logger.info(f"[{self.name}] Risk analysis: {industry}")

        # 搜索维度: 政策/监管 + 技术替代 + 宏观 + 供应链
        search_chains = [
            [f"{industry} 政策 监管 风险 出口管制 关税 2026",
             f"{industry} 政策风险 行业监管 地缘政治",
             f"{industry} regulatory policy risk export control 2026"],
            [f"{industry} 技术替代 颠覆 风险 路线变更 2026",
             f"{industry} 技术路线 替代方案 颠覆性创新",
             f"{industry} technology disruption substitution risk 2026"],
            [f"{industry} 产能过剩 竞争加剧 价格战 库存 需求下滑 2026",
             f"{industry} 供给过剩 需求不足 下行风险",
             f"{industry} overcapacity demand slowdown competition risk 2026"],
        ]
        search_data = await self._search_adaptive(search_chains, num=4, trace=trace)

        # 个股风险搜索 (top 候选)
        top_stocks = (step6_out.get("ranked_stocks", [])[:3] +
                      step6_out.get("future_strong_candidates", [])[:2])
        stock_risk_data = []
        for s in top_stocks:
            name = s.get("name", "")
            if not name: continue
            chains = [
                [f"{name} 风险 客户单一 技术替代 竞争 财务 2026",
                 f"{name} 利空 风险 减持 财务风险"],
                [f"{name} 供应链 依赖 客户集中度 应收账款 存货",
                 f"{name} 研发 资本开支 烧钱 现金流"],
            ]
            sd = await self._search_adaptive(chains, num=3, trace=trace)
            stock_risk_data.append({"code": s.get("code", ""), "name": name, "search_data": sd})

        prompt = self._build_prompt(industry, step6_out, step9_out, step4_out, search_data, stock_risk_data)

        try:
            text = await self.provider.chat_pro(prompt, max_tokens=16384, timeout=600)
            if trace: trace.record_llm(prompt, text, model="deepseek-v4-pro")
            result = self.parse_json(text)

            if isinstance(result, dict):
                risks = result.get("risks", [])
                scenario = result.get("scenario_analysis", {})
                logger.info(f"[{self.name}] Done: {len(risks)} risks, scenarios={len(scenario.get('scenarios',[]))}")
                if trace:
                    trace.record_note("summary", f"{len(risks)} risks, top_risk={risks[0].get('category','?') if risks else 'none'}")
                result["industry"] = industry
                return result

        except asyncio.TimeoutError:
            logger.warning(f"[{self.name}] Timeout: {industry}")
        except Exception as e:
            logger.warning(f"[{self.name}] Failed: {e}")

        return {"agent": self.name, "industry": industry, "error": "Analysis failed", "risks": []}

    # ═══ Prompt 构建 ═══════════════════════════

    def _build_prompt(self, industry: str, step6_out: dict, step9_out: dict,
                      step4_out: dict, search_data: list, stock_risk_data: list) -> str:
        candidates_str = self._format_candidates(step6_out)

        # 搜索摘要
        search_summary = ""
        for sd in search_data:
            search_summary += f"\n### {sd['query']}\n"
            for r in sd["results"][:3]:
                search_summary += f"  - {r['title']}: {r['snippet'][:200]}\n"

        # 个股风险搜索
        stock_search_summary = ""
        for ss in stock_risk_data:
            stock_search_summary += f"\n### {ss['name']} ({ss.get('code','')})\n"
            for chain in ss["search_data"]:
                for r in chain["results"][:2]:
                    stock_search_summary += f"  - {r['title']}: {r['snippet'][:180]}\n"

        # Step 9 预期差信息 (可选)
        step9_text = ""
        if step9_out and isinstance(step9_out, dict):
            gaps = step9_out.get("expectation_gaps", [])
            if gaps:
                step9_text = "\n".join(
                    f"- {g.get('gap_type','?')} {g.get('direction','?')}: {g.get('market_consensus','')[:100]}"
                    for g in gaps[:4])

        # Step 4 系统动力学瓶颈信息 (可选)
        step4_text = ""
        if step4_out and isinstance(step4_out, dict):
            sd = step4_out.get("system_dynamics", {})
            if sd:
                theses = sd.get("thesis_breakers", [])
                if theses:
                    step4_text = "\n".join(
                        f"- thesis: {t.get('thesis','')[:100]} → break: {t.get('break_condition','')[:100]}"
                        for t in theses[:3])

        # 术语
        glossary = inject_glossary("", [
            "thesis_killers", "cycle_phase", "bottleneck_severity", "future_outlook",
        ])

        return f"""你是买方风险分析师。你的任务是: 对 Pipeline 筛选出的候选标的和产业逻辑进行**系统性风险评估**, 识别可能破坏投资逻辑的关键风险因素。

## ★ 核心方法论: 六维风险框架

从以下六个维度逐一扫描风险:

### 1. 政策/地缘风险 (Policy/Geopolitical)
- 出口管制/技术封锁升级风险
- 关税/贸易壁垒变化
- 行业监管政策突变
- 国产替代政策不及预期

### 2. 技术/替代风险 (Technology)
- 技术路线被颠覆 (如: 光互连替代电互连)
- 替代方案快速成熟 (如: 非HBM方案异军突起)
- 关键技术节点突破延迟

### 3. 市场/竞争风险 (Market/Competitive)
- 产能过剩/价格战
- 新进入者颠覆格局
- 客户集中度风险 (单客户>30%)
- 需求不及预期 (补库 vs 真实需求)

### 4. 财务/估值风险 (Financial)
- 烧钱速度 > 融资能力
- 应收账款/存货恶化
- 资产负债率过高
- 估值脱离基本面支撑

### 5. 供应链风险 (Supply Chain)
- 单一供应商依赖
- 原材料价格大幅波动
- 产能释放不及预期
- 品质/良率爬坡失败

### 6. 执行风险 (Execution)
- 管理层战略失误
- 产能扩张节奏失控
- 客户认证进度低于预期
- 研发里程碑延误

## 输入数据

### 行业
{industry}

### Step 6 候选标的
{candidates_str}

### Step 9 预期差 (风险叠加参考)
{step9_text or '(无 Step 9 数据)'}

### Step 4 系统动力学 thesis_breakers
{step4_text or '(无 Step 4 数据)'}

### 风险搜索 (行业)
{search_summary}

### 个股风险搜索
{stock_search_summary or '(无个股搜索数据)'}

你需要结合以上所有输入, 做系统性风险识别。

## 输出 JSON

{{
  "risk_summary": "整体风险评估 — 一句话概括当前产业及标的的风险状况",

  "risks": [
    {{
      "category": "policy / technology / market / financial / supply_chain / execution",
      "risk": "具体风险描述",
      "severity": "critical / high / moderate / low — 如果发生, 影响程度",
      "probability": "high / medium / low — 发生的可能性",
      "impact_area": "影响范围: '全产业' / '某类标的' / '某只标的'",
      "affected_stocks": ["受影响的股票代码"],
      "mitigation": "这个风险如何缓解或对冲?",
      "watch_signal": "什么具体信号出现时风险将兑现? (必须是可观测的)",
      "time_horizon": "3-6个月 / 6-12个月 / 12-24个月 / 24个月以上 — 风险可能爆发的时间",
      "evidence": [
        {{"fact": "支撑该风险判断的证据", "source": "来源"}}]
    }}
  ],

  "scenario_analysis": {{
    "scenarios": [
      {{
        "name": "场景名称 (如: '乐观 — 技术突破如期推进')",
        "probability": "high / medium / low",
        "description": "场景描述",
        "key_assumptions": ["驱动该场景的关键假设"],
        "market_impact": "对候选标的的整体影响描述"
      }}
    ],
    "worst_case": {{
      "narrative": "最坏情况描述",
      "trigger": "触发最坏情况的关键事件",
      "affected_thesis": "哪些投资逻辑会被破坏"
    }}
  }},

  "watch_list": [
    {{
      "signal": "需要监控的具体风险信号",
      "related_risk": "关联的风险 (引用 risk 的简要描述)",
      "frequency": "daily / weekly / quarterly",
      "source": "从哪里获取这个信号"
    }}
  ]
}}

## 输出约束 (★ 强制)
- category 必须严格是 policy / technology / market / financial / supply_chain / execution 之一
- severity 和 probability 必须分别赋值, 不能合并
- severity=critical 的风险必须有 mitigation 方案
- 每个 risk 必须有至少一条 evidence
- 如果某个维度搜索无证据支撑, 该维度的风险可以不输出 (不在 evidence 上编造)
- scenario_analysis 至少包含 3 个场景 (乐观/基准/悲观)
- 禁止输出没有搜索或数据支撑的风险判断
- watch_list 中的 signal 必须具体可观测

{glossary}
"""

    # ═══ 基类 ═══════════════════════════════

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return await super().load_context(ctx)

    @staticmethod
    def build_prompt(ctx): return "RiskAnalysisAgent V1.0"

    @staticmethod
    async def stream(ctx): yield "streaming not implemented"
