"""
ExpectationGapAgent V1.0 — Step 9: 市场预期差分析
定位: 对比 Pipeline 输出与市场共识, 找出认知偏差和预期差
核心问题: 市场哪里错了? 共识在什么假设上是脆弱的?
方法论: 简化 Bull/Bear 辩论 — 多维度共识检验
"""
import asyncio, re
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger
from app.framework.pipeline.glossary import inject_glossary


class ExpectationGapAgent(ResearchAgent):
    """市场预期差分析 V1.0 — 共识检验 + 认知偏差识别"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "ExpectationGapAgent"

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
        eliminated = step6_out.get("eliminated", [])

        lines.append(f"## 已排名标的 ({len(ranked)} 只)")
        for s in ranked[:10]:
            v = s.get("verification", {})
            dims = ", ".join(v.get("analysis_dimensions", [])[:4]) if isinstance(v, dict) else ""
            lines.append(f"- {s.get('code','?')} {s.get('name','?')}: rank={s.get('rank','?')}, stage={s.get('company_stage','?')}, dims=[{dims}]")
            why = s.get("why", "")
            if why: lines.append(f"  └ {why[:200]}")

        if future:
            lines.append(f"\n## 未来强势候选 ({len(future)} 只)")
            for s in future:
                lines.append(f"- {s.get('code','?')} {s.get('name','?')}: category={s.get('category','?')}, stage={s.get('company_stage','?')}")

        if eliminated:
            lines.append(f"\n## 已淘汰 ({len(eliminated)} 只)")
            for s in eliminated[:5]:
                lines.append(f"- {s.get('code','?')} {s.get('name','?')}: {s.get('why','')[:100]}")

        return "\n".join(lines)

    # ═══ 主入口 ═══════════════════════════════

    async def analyze(self, ctx: Dict[str, Any] = None, trace=None) -> Dict[str, Any]:
        ctx = await self.load_context(ctx or {})
        if not self.provider:
            return {"agent": self.name, "error": "No AI provider"}

        industry = ctx.get("industry", "未指定")
        step6_out = ctx.get("step6_output", {})
        step2_out = ctx.get("step2_output", {})

        if not step6_out:
            logger.warning(f"[{self.name}] {industry}: no Step 6 output, skipping")
            return {"agent": self.name, "industry": industry, "error": "No Step 6 output", "expectation_gaps": []}

        logger.info(f"[{self.name}] Analyzing expectation gaps: {industry}")

        # 搜索维度: 市场共识 + 看空观点 + 被忽视信号
        search_chains = [
            [f"{industry} 2026 市场预期 机构观点 共识 分歧",
             f"{industry} 券商 研报 2026 预测 目标价",
             f"{industry} 2026 景气度 展望 consensus forecast"],
            [f"{industry} 2026 风险 看空 质疑 产能过剩 竞争加剧",
             f"{industry} 唱空 分歧 过度乐观 估值泡沫 压力",
             f"{industry} 2026 risk downside overcapacity competition"],
            [f"{industry} 被忽视 预期差 未被市场定价 认知偏差 2026",
             f"{industry} 低估 高估 市场误判 被忽略的机会",
             f"{industry} overlooked mispricing expectation gap 2026"],
        ]
        search_data = await self._search_adaptive(search_chains, num=5, trace=trace)

        # 看多/看空搜索 (针对 top 候选)
        top_stocks = (step6_out.get("ranked_stocks", [])[:3] +
                      step6_out.get("future_strong_candidates", [])[:2])
        stock_search_data = []
        for s in top_stocks:
            code = s.get("code", "")
            name = s.get("name", "")
            if not name: continue
            chains = [
                [f"{name} {code} 2026 目标价 机构评级 业绩预测 券商",
                 f"{name} {code} 最新研报 盈利预测 估值"],
                [f"{name} {code} 风险 挑战 竞争 客户依赖 估值过高",
                 f"{name} {code} 看空 分歧 利空 减持"],
            ]
            sd = await self._search_adaptive(chains, num=3, trace=trace)
            stock_search_data.append({"code": code, "name": name, "search_data": sd})

        # 构建 prompt 并调用 LLM
        prompt = self._build_prompt(industry, step6_out, step2_out, search_data, stock_search_data)

        try:
            text = await self.provider.chat_pro(prompt, max_tokens=16384, timeout=600)
            if trace: trace.record_llm(prompt, text, model="deepseek-v4-pro")
            result = self.parse_json(text)

            if isinstance(result, dict):
                gaps = result.get("expectation_gaps", [])
                verdict = result.get("consensus_verdict", {})
                logger.info(f"[{self.name}] Done: {len(gaps)} gaps, verdict_confidence={verdict.get('confidence','?')}")
                if trace:
                    trace.record_note("summary", f"{len(gaps)} gaps, verdict={verdict.get('overall_bias','?')}")
                result["industry"] = industry
                return result

        except asyncio.TimeoutError:
            logger.warning(f"[{self.name}] Timeout: {industry}")
        except Exception as e:
            logger.warning(f"[{self.name}] Failed: {e}")

        return {"agent": self.name, "industry": industry, "error": "Analysis failed", "expectation_gaps": []}

    # ═══ Prompt 构建 ═══════════════════════════

    def _build_prompt(self, industry: str, step6_out: dict, step2_out: dict,
                      search_data: list, stock_search_data: list) -> str:
        candidates_str = self._format_candidates(step6_out)

        # 搜索摘要
        search_summary = ""
        for sd in search_data:
            search_summary += f"\n### {sd['query']}\n"
            for r in sd["results"][:3]:
                search_summary += f"  - {r['title']}: {r['snippet'][:200]}\n"

        # 个股搜索摘要
        stock_search_summary = ""
        for ss in stock_search_data:
            stock_search_summary += f"\n### {ss['name']} ({ss.get('code','')})\n"
            for chain in ss["search_data"]:
                for r in chain["results"][:2]:
                    stock_search_summary += f"  - {r['title']}: {r['snippet'][:180]}\n"

        # Step 2 信息 (可选)
        step2_text = ""
        if step2_out and isinstance(step2_out, dict):
            entry = step2_out.get("industries", [{}])[0] if step2_out.get("industries") else {}
            if entry:
                step2_text = f"""
- 周期阶段: {entry.get('cycle_position',{}).get('phase','?')}
- 市场重定价阶段: {entry.get('time_horizon',{}).get('market_repricing_stage','?')}
- 赔率不对称性: {entry.get('payoff',{}).get('asymmetry','?')}
"""

        # 术语
        glossary = inject_glossary("", [
            "market_repricing_stage", "attention_quality", "future_outlook",
            "demand_quality", "payoff_asymmetry", "thesis_killers",
        ])

        return f"""你是买方预期差分析师。你的任务是: 基于 Pipeline Step 6 的筛选结果 + 网络搜索, 判断**市场共识在哪里, 以及市场共识可能错在哪里**。

## ★ 核心方法论: 共识检验五维度

你需要从以下五个维度逐一检验 Pipeline 结论 vs 市场共识:

### 1. 估值预期差 (Valuation Gap)
- 市场给这些标的什么估值? PE/PEG/PS 在什么水平?
- Step 6 认为的合理估值 vs 市场当前定价的差距?
- 如果 Step 6 的景气判断成立, 当前估值是便宜还是贵?

### 2. 增长预期差 (Growth Perception Gap)
- 市场对业绩增长的预期是否过于保守/乐观?
- 关键分歧点: 收入增速/利润率/毛利率趋势
- Step 6 识别出的"需求爆发"是否已反映在卖方模型中?

### 3. 关注度预期差 (Attention Gap)
- 这些标的的机构覆盖度如何? 有多少卖方覆盖?
- 市场关注度处于什么阶段 (early/mid/late repricing)?
- 关注度低是因为真的有价值, 还是因为确实不值得关注?

### 4. 时间差 (Timing Gap)
- 市场认为景气兑现的时间点 vs Step 6 的判断是否一致?
- 如果市场预期过早或过晚, 当前的介入时机是否合适?

### 5. 结构性预期差 (Structural Gap)
- 市场是否低估了某个结构性变化 (技术范式/供应链重构/政策) 的持续性?
- 这是周期性的还是结构性的? 市场是否将其误判为周期性?

## 输入数据

### 行业/产业链
{industry}

### Step 2 前置分析 (市场重定价阶段参考)
{step2_text or '(无 Step 2 数据)'}

### Step 6 候选标的
{candidates_str}

### 市场共识搜索
{search_summary}

### 个股共识搜索
{stock_search_summary or '(无个股搜索数据)'}

## 输出 JSON

{{
  "consensus_verdict": {{
    "overall_bias": "bullish / bearish / neutral — Pipeline vs 市场共识的总体偏差方向",
    "confidence": "high / medium / low — 基于搜索覆盖度和证据充分性",
    "key_premise": "市场共识最核心的隐含假设是什么? 一句话概括",
    "premise_vulnerability": "这个假设在什么条件下会被打破?",
    "most_likely_surprise": "市场最可能被什么意外事件打脸?"
  }},

  "expectation_gaps": [
    {{
      "gap_type": "valuation / growth / attention / timing / structural",
      "stock_codes": ["受此预期差影响的股票代码列表"],
      "direction": "bullish / bearish — Pipeline 角度 vs 市场共识的方向",
      "gap_magnitude": "large / moderate / small — 预期差空间大小",
      "market_consensus": "市场当前的主流观点是什么",
      "pipeline_view": "Pipeline 分析认为真实情况是什么",
      "gap_source": "预期差产生的根因: '市场忽略了X' 或 '市场过度乐观关于Y'",
      "catalyst": "什么事件/数据能触发预期差的收敛 (市场认知向Pipeline靠拢)",
      "time_horizon": "3-6个月 / 6-12个月 / 12-24个月 — 预期差收敛需要多久",
      "evidence": [
        {{"fact": "支持这一判断的具体事实", "source": "搜索来源或Pipeline分析"}}]
    }}
  ],

  "bull_case": {{
    "narrative": "完整的看多叙事 — 如果Pipeline正确, 市场最大的upside是什么",
    "key_assumptions": ["支撑看多叙事的3-5个关键假设"],
    "upside_triggers": ["哪些事件会推动市场重新定价"]
  }},

  "bear_case": {{
    "narrative": "完整的看空叙事 — Pipeline可能错在哪里, 市场可能正确",
    "key_assumptions": ["支撑看空叙事的3-5个关键假设"],
    "downside_triggers": ["哪些事件会验证看空观点"]
  }},

  "watch_signals": [
    {{
      "signal": "需要监控的具体信号",
      "what_it_tells": "这个信号出现说明什么 (验证/证伪哪个预期差)",
      "frequency": "daily / weekly / quarterly — 可观测频率",
      "source": "从哪获取这个信号"
    }}
  ]
}}

## 输出约束 (★ 强制)
- gap_type 必须是 valuation / growth / attention / timing / structural 之一
- direction 必须是 bullish 或 bearish
- gap_magnitude 必须是 large / moderate / small
- 每个 gap 必须有至少一条 evidence (不能空的 evidence 数组)
- 如果搜索证据不足以支撑某个 gap, 将该 gap 的 confidence 标记为 low
- 禁止输出没有证据支撑的 gap
- 禁止编造具体的 PE/PEG/PS 数值 (LLM 不擅长精确估值, 用定性判断替代)
- watch_signals 必须具体可观测, 不是宽泛的"关注行业动态"

{glossary}
"""

    # ═══ 基类 ═══════════════════════════════

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return await super().load_context(ctx)

    @staticmethod
    def build_prompt(ctx): return "ExpectationGapAgent V1.0"

    @staticmethod
    async def stream(ctx): yield "streaming not implemented"
