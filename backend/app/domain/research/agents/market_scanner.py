"""
MarketScanner V5.7 — Pipeline Gatekeeper
双模式: auto(扫描验证) / manual(单行业深挖)
输出: 6块定性判断, 不做数值评分
"""
import asyncio, json
from decimal import Decimal
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger


class _SafeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal): return float(obj)
        return super().default(obj)

def _j(obj): return json.dumps(obj, ensure_ascii=False, cls=_SafeEncoder)


class MarketScanner(ResearchAgent):
    """Pipeline Gatekeeper V5.7 — 定性筛选, 不做数值评分"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "MarketScanner"

    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await self.load_context(context)
        mode = ctx.get("mode", "auto")
        if not self.provider:
            return {"error": "No AI provider"}

        # auto 模式: 从 Step1 hypothesis_sectors 获取候选清单
        if mode == "manual":
            target = ctx.get("target_industry") or ctx.get("question", "")
            if not target:
                return {"error": "manual mode requires target_industry"}
            result = await self._deep_dive_manual(target)
            result["agent"] = self.name
            result["mode"] = "manual"
            return result

        # auto 模式 (默认, 向后兼容)
        hypothesis = ctx.get("hypothesis_sectors", [])
        if hypothesis:
            result = await self._scan_auto(hypothesis)
            result["agent"] = self.name
            result["mode"] = "auto"
            return result

        # Fallback: 旧的零参数扫描
        signals = await self._collect_signals(ctx)
        industries = await self._identify_hot_industries(signals)
        briefing = await self._generate_briefing(signals, industries)
        return {
            "agent": self.name, "mode": "legacy",
            "hot_industries": industries, "briefing": briefing,
        }

    # ═══ auto 模式: 从 Step1 候选清单验证 ═══════════

    async def _scan_auto(self, hypothesis_sectors: List[Dict]) -> Dict:
        """对 Step1 的 benefited_sectors 做验证+排序+补漏"""
        results = []
        for h in hypothesis_sectors[:5]:
            sector = h.get("sector", h.get("name", ""))
            if not sector: continue
            logger.info(f"[{self.name}] Scanning: {sector}")
            # 2 轮搜索
            search_data = []
            for q in [f"{sector} 景气度 增速 供需 产能 2026",
                       f"{sector} 产能利用率 CAPEX 扩产周期 龙头订单 2026"]:
                items = []
                for r in await self.data_loader.search_web(q, num=3):
                    items.append({"title": r.get("title",""), "snippet": r.get("snippet","")[:250]})
                search_data.append({"query": q, "results": items})

            # LLM 评估
            evaluation = await self._evaluate_industry(sector, search_data, h)
            if evaluation:
                results.append(evaluation)

        # 排序: 高 > 中 > 低 > 跳过
        priority_order = {"高": 0, "中": 1, "低": 2, "跳过": 3}
        results.sort(key=lambda r: priority_order.get(
            (r.get("verdict", {}).get("priority", "低")), 3))
        return {"industries": results, "count": len(results)}

    # ═══ manual 模式: 单行业深挖 ═══════════

    async def _deep_dive_manual(self, industry: str) -> Dict:
        """对用户指定的行业做 4 轮深度分析"""
        logger.info(f"[{self.name}] Deep dive: {industry}")
        search_data = []
        queries = [
            f"{industry} 行业概况 市场规模 TAM 增速 2026",
            f"{industry} 供需缺口 产能利用率 交期 CAPEX 扩产周期 2026",
            f"{industry} 竞争格局 政策环境 国产化率 全球份额 2026",
            f"{industry} 产业链 上游 下游 传导 瓶颈 成本结构 2026",
        ]
        for q in queries:
            items = []
            for r in await self.data_loader.search_web(q, num=4):
                items.append({"title": r.get("title",""), "snippet": r.get("snippet","")[:250]})
            search_data.append({"query": q, "results": items})

        evaluation = await self._evaluate_industry(industry, search_data, {})
        if evaluation:
            evaluation["mode"] = "manual"
        return evaluation or {"error": "LLM evaluation failed", "industry": industry}

    # ═══ LLM 评估 (auto + manual 共用) ═══════════

    async def _evaluate_industry(self, industry: str, search_data: List,
                                  hypothesis: Dict = None) -> Dict:
        """LLM 按 6 块定性结构评估一个行业"""
        h_info = _j(hypothesis)[:500] if hypothesis else "无预判信息"

        prompt = f"""你是买方资本配置分析师(Pipeline Gatekeeper)。你的任务不是描述行业, 而是判断这个行业是否值得进入深度推演。

## 核心原则: 五错配
只有同时满足以下条件的行业才值得深度推演:
1. 供需错配 — 需求增速 > 供给响应速度
2. 时间错配 — 扩产周期远长于需求爆发周期
3. 认知错配 — 市场尚未充分理解产业变化的深度
4. 利润迁移 — 利润正在从一个环节流向另一个环节
5. 尚未充分定价 — 当前估值未反映上述错配

缺少任何一条, enter_step3 应为 false。

## Step1 预判信息
{h_info}

## 搜索结果
"""
        for sd in search_data:
            prompt += f"\n### {sd['query']}\n"
            for r in sd["results"][:3]:
                prompt += f"- {r['title']}: {r['snippet'][:200]}\n"

        prompt += f"""
## 输出: 纯 JSON (6 块, 全定性, 不出现 1-10 数字评分)

{{
  "industry": "{industry}",

  "cycle_position": {{
    "phase": "bottleneck_formation",
    "sub_phase": "early",
    "evidence": "引用搜索结果中的具体数据支撑此判断",
    "next_phase": "...",
    "estimated_duration": "12-18个月",
    "phase_switch_trigger": "..."
  }},

  "prosperity": {{
    "type": "supply_shock",
    "demand_quality": "real_demand",
    "demand_evidence": "引用搜索结果证据",
    "growth_narrative": "行业增速 vs 供给响应的矛盾描述",
    "core_contradiction": "当前最核心的供需矛盾是什么",
    "driver_decomposition": [
      {{"driver": "驱动力1", "weight": "主导", "certainty": "高", "duration": "3-5年", "leading_indicator": "..."}}
    ]
  }},

  "payoff": {{
    "asymmetry": "强非对称",
    "narrative": "判断依据: 如果景气兑现会怎样, 如果证伪会怎样"
  }},

  "propagation": {{
    "depth": "深",
    "transmission_order": [
      {{"stage": 1, "node": "环节名", "reason": "最先受益的原因"}}
    ],
    "last_beneficiary": "...",
    "last_bottleneck": "...",
    "alpha_implication": "..."
  }},

  "time_horizon": {{
    "alpha_window": "6-12个月",
    "profit_expansion_window": "12-24个月",
    "capacity_relief_eta": "2028H1",
    "market_repricing_stage": "早期"
  }},

  "verdict": {{
    "enter_step3": true,
    "priority": "高",
    "rationale": "基于五错配原则的判断理由, 2-3句",
    "key_uncertainties": ["不确定性1", "不确定性2"]
  }},

  "kill_reasons": []
}}

## 规则
- 所有数值引用(增速/交期/规模)必须来自搜索结果, 不得编造
- 如果搜索结果质量不足以支撑判断, 在 evidence 中标注"数据有限"
- 如果 enter_step3=false, kill_reasons 必须至少填1条"""
        # 注入权威术语表, 确保语义一致
        from app.framework.pipeline.glossary import step2_glossary
        prompt += step2_glossary()

        try:
            text = await asyncio.wait_for(
                self.provider.chat_flash(prompt, max_tokens=3072), timeout=45)
            result = self.parse_json(text)
            if isinstance(result, dict):
                logger.info(f"[{self.name}] {industry}: priority={result.get('verdict',{}).get('priority','?')}, "
                           f"phase={result.get('cycle_position',{}).get('phase','?')}, "
                           f"type={result.get('prosperity',{}).get('type','?')}")
                return result
        except asyncio.TimeoutError:
            logger.warning(f"[{self.name}] {industry}: timeout")
        except Exception as e:
            logger.warning(f"[{self.name}] {industry}: {e}")
        return {}

    # ═══ 旧版方法 (向后兼容) ═══════════════════════

    async def _collect_signals(self, ctx: Dict) -> Dict:
        queries = {
            "market": "A股 热点板块 资金流向 领涨概念 2026",
            "flow": "北向资金 主力净流入 行业板块 2026",
            "global": "全球股市 AI 半导体 新能源 景气度 2026",
        }
        search_results = {}
        for key, query in queries.items():
            items = []
            for r in await self.data_loader.search_web(query, num=4):
                items.append({"title": r.get("title",""), "url": r.get("url",""), "snippet": r.get("snippet","")[:250]})
            search_results[key] = items
        macro = ctx.get("macro", {})
        return {"macro": macro, "market_pulse": {
            "market_news": search_results.get("market", []),
            "flow_news": search_results.get("flow", []),
            "global_news": search_results.get("global", []),
        }, "macro_news": [], "search_sources": sum(len(v) for v in search_results.values())}

    async def _identify_hot_industries(self, signals: Dict) -> List[Dict]:
        prompt = f"""你是 A 股市场策略师。基于以下实时市场数据, 识别当前最值得关注的 3-5 个行业/主题, 并判定每个行业所处的生命周期阶段。

## 市场热点与资金流
{_j(signals['market_pulse']['market_news'])}

## 资金流向
{_j(signals['market_pulse']['flow_news'])}

## 全球市场
{_j(signals['market_pulse']['global_news'])}

## 汇率/大宗
{_j(signals['macro'])}

## 要求
1. 每个行业输出: name, score(1-10), lifecycle_stage(导入期/成长期/成熟期/衰退期), stage_evidence, type(短期热点/中期趋势), reason, global_drivers, a_stock_codes
2. 优先关注有资金流入支撑的行业
3. 区分短期热点 vs 中期趋势
4. 搜索结果中提到的股票代码必须包含在 a_stock_codes 中

请输出纯 JSON 数组:
[{{"name":"AI算力","score":9,"lifecycle_stage":"成长期","stage_evidence":"AI芯片渗透率5%→15%, 四大云厂商capex+40%","type":"中期趋势","reason":"英伟达B200量产+...","global_drivers":"MAG7 capex +40%","a_stock_codes":["688256","300308"]}}]"""
        text = await asyncio.wait_for(
            self.provider.chat_flash(prompt, max_tokens=2048), timeout=30) or ""
        return self.parse_json(text)

    async def _generate_briefing(self, signals: Dict, industries: List) -> str:
        prompt = f"""你是资深投资顾问。基于实时数据生成今日 A 股投资简报。

## 宏观要闻
{_j(signals.get('macro_news',[])[:4])}

## 全球市场
{_j(signals['market_pulse']['global_news'][:3])}

## 热门赛道
{_j(industries)}

## 资金流
{_j(signals['market_pulse']['flow_news'][:3])}

## 输出格式 (Markdown)
### 今日市场环境 (2-3句宏观定调)
### 热门赛道 TOP 3 | 排名 | 行业 | 生命周期 | 类型 | 景气评分 | 核心逻辑 | 关注标的 |
### 生命周期分布
### 资金面信号 (1-2句)
### 操作建议 (1-2句)
### 风险提示 (1-2句)"""
        return await self._safe_call(prompt)

    async def _safe_call(self, prompt: str) -> str:
        try:
            return await asyncio.wait_for(
                self.provider.chat_pro(prompt, max_tokens=2048), timeout=45) or ""
        except asyncio.TimeoutError:
            logger.warning("[MarketScanner] LLM call timed out")
            return "分析超时, 请重试"
        except Exception as e:
            logger.warning(f"[MarketScanner] LLM call failed: {e}")
            return f"分析异常: {e}"

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await super().load_context(ctx)
        ctx["macro"] = await self.data_loader.load_macro()
        return ctx

    @staticmethod
    def build_prompt(ctx):
        return "MarketScanner V5.7"

    @staticmethod
    async def stream(ctx):
        yield "streaming not implemented"
