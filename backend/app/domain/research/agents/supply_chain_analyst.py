"""
供应链深度分析师 — 5步推理: 景气信号→供应链图谱→供需瓶颈→垄断标的→定量估值
全球视角: 覆盖 A股/美股/台股/韩股, LLM 补全球行业知识
"""
import json
from decimal import Decimal
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger


class _SafeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def _json_dumps(obj, **kwargs):
    kwargs.setdefault("ensure_ascii", False)
    kwargs.setdefault("cls", _SafeEncoder)
    return json.dumps(obj, **kwargs)


class SupplyChainAnalyst(ResearchAgent):
    """供应链深度分析智能体 — 全球价值链下钻"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "SupplyChainAnalyst"
        self._steps = []  # 记录每步输出供前端展示

    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行完整的5步供应链分析 (每步 45s 超时, 失败不中断)"""
        self._steps = []
        ctx = await self.load_context(context)
        industry = ctx.get("industry", "未指定")
        codes = ctx.get("stock_codes", [])

        results = {
            "agent": self.name,
            "industry": industry,
            "stock_codes": codes,
        }

        if not self.provider:
            results["error"] = "No AI provider configured"
            results["data"] = ctx
            return results

        import asyncio

        async def _safe_step(name, coro):
            try:
                return await asyncio.wait_for(coro, timeout=45)
            except asyncio.TimeoutError:
                logger.warning(f"[{self.name}] {name} timed out")
                return {"error": "timeout", "step": name}
            except Exception as e:
                logger.warning(f"[{self.name}] {name} failed: {e}")
                return {"error": str(e), "step": name}

        # ── Step 1-5: 各自超时保护 ──
        step1 = await _safe_step("prosperity", self._analyze_prosperity_signals(ctx))
        self._steps.append({"step": 1, "name": "景气信号识别", "output": step1})
        results["prosperity_signals"] = step1

        step2 = await _safe_step("supply_chain", self._map_supply_chain(ctx, step1))
        self._steps.append({"step": 2, "name": "供应链映射", "output": step2})
        results["supply_chain"] = step2

        step3 = await _safe_step("bottleneck", self._locate_bottleneck(ctx, step2))
        self._steps.append({"step": 3, "name": "供需瓶颈定位", "output": step3})
        results["bottleneck"] = step3

        step4 = await _safe_step("core_targets", self._select_core_targets(ctx, step3))
        self._steps.append({"step": 4, "name": "核心标的锁定", "output": step4})
        results["core_targets"] = step4

        # ── Step 3.5: 时间维度分析 ──
        step35 = await _safe_step("temporal", self._temporal_analysis(ctx, step3))
        self._steps.append({"step": 4, "name": "景气周期预测", "output": step35})
        results["temporal"] = step35

        step5 = await _safe_step("valuation", self._quantitative_valuation(ctx, step4))
        self._steps.append({"step": 5, "name": "定量估值", "output": step5})
        results["valuation"] = step5

        # ── Summary ──
        summary = await _safe_step("summary", self._generate_summary(results))
        results["summary"] = summary.get("raw_text", "") if isinstance(summary, dict) else summary
        results["steps"] = self._steps

        return results

    # ═══ 各步骤实现 ═════════════════════════════

    async def _analyze_prosperity_signals(self, ctx: Dict) -> Dict:
        """Step 1: 识别全球高景气信号"""
        industry = ctx.get("industry", "")
        macro = ctx.get("macro", {})
        fundamentals = ctx.get("fundamentals", {})
        market_data = ctx.get("market_data", {})

        # 汇总可用的定量数据
        pe_list = [f"{c}: PE={f.get('pe_ttm','?')}" for c, f in fundamentals.items() if f.get('pe_ttm')]
        volume_trends = []
        for code, rows in market_data.items():
            if len(rows) >= 10:
                recent_vol = sum(r.get("volume", 0) for r in rows[:5])
                prev_vol = sum(r.get("volume", 0) for r in rows[5:10])
                if prev_vol > 0:
                    trend = "放量" if recent_vol > prev_vol * 1.2 else ("缩量" if recent_vol < prev_vol * 0.8 else "持平")
                    volume_trends.append(f"{code}: {trend} (近期/前期={recent_vol/prev_vol:.2f})")

        prompt = f"""你是一位全球科技产业研究员。请分析 {industry} 行业的高景气信号。

## 宏观环境
{_json_dumps(macro, ensure_ascii=False)}

## A股映射标的估值
{_json_dumps(pe_list, ensure_ascii=False) if pe_list else "暂无A股映射数据"}

## 成交量趋势
{_json_dumps(volume_trends, ensure_ascii=False) if volume_trends else "暂无"}

## 你的任务
基于你的训练知识(截至2025), 请分析:
1. **国际龙头资本开支**: {industry} 领域全球 Top3 公司(NVDA/TSMC/ASML/Intel等)的最新资本开支计划和扩产动态
2. **全球资金流向**: 该赛道是否在吸引全球热钱? (参考美股科技ETF资金流入/SOX指数走势)
3. **产业事件催化**: 近期是否有重大订单、技术突破、政策扶持?
4. **景气度综合评分** (1-10分)
5. **推荐关注的高景气子环节**: 列出最受益的上游/中游/下游环节

请输出结构化 JSON:
{{"capex_analysis": "...", "capital_flow": "...", "catalysts": "...", "prosperity_score": N, "hot_segments": ["环节1","环节2"]}}"""

        text = await self.provider.chat(prompt)
        return self._extract_json_block(text, "prosperity")

    async def _map_supply_chain(self, ctx: Dict, signals: Dict) -> Dict:
        """Step 2: 映射全球供应链层级"""
        industry = ctx.get("industry", "")
        hot_segments = signals.get("hot_segments", [])

        prompt = f"""你是一位全球半导体/科技供应链专家。请为 {industry} 行业绘制完整的全球供应链图谱。

## 高景气子环节
{_json_dumps(hot_segments, ensure_ascii=False)}

## 你的任务
请按 上游→中游→下游 结构, 列出每个环节的:
1. 环节名称和技术壁垒
2. 全球主要公司 (含美股代码/台股代码/韩股代码)
3. A股映射标的 (如果存在)
4. 该环节的供需状况 (供不应求/平衡/过剩)
5. 扩产周期 (月)

特别关注:
- 产能集中度 (全球前3家市占率)
- 是否有垄断/寡头特征

请输出纯 JSON (不要 Markdown 代码块, 不要任何解释文字).
JSON 示例: {{"layers":[{{"name":"环节","tier":"上游","barriers":"壁垒","global_leaders":[{{"name":"公司","code":"AAPL","market":"US"}}],"a_share_peers":[{{"code":"000001","name":"公司"}}],"supply_status":"供不应求","expansion_months":18,"concentration":"前3家80%"}}]}}"""

        text = await self.provider.chat(prompt)
        return self._extract_json_block(text, "supply_chain")

    async def _locate_bottleneck(self, ctx: Dict, chain: Dict) -> Dict:
        """Step 3: 定位供需瓶颈 (垄断性分析)"""
        layers = chain.get("layers", [])
        fundamentals = ctx.get("fundamentals", {})
        positions = ctx.get("positions", [])

        # 筛选供不应求的环节
        bottlenecks = [l for l in layers if "供不应求" in l.get("supply_status", "")]
        if not bottlenecks:
            bottlenecks = layers[:3]  # fallback

        prompt = f"""你是一位全球供应链投资专家。请深度分析以下供不应求的瓶颈环节。

## 瓶颈环节
{_json_dumps(bottlenecks, ensure_ascii=False, indent=2)}

## A股映射基本面
{_json_dumps({c: f for c, f in fundamentals.items() if f.get('pe_ttm')}, ensure_ascii=False)}

## 持仓数据
{_json_dumps(positions, ensure_ascii=False, indent=2) if positions else '无'}

## 你的任务
对每个瓶颈环节, 分析:
1. **垄断性根源**: 为什么只有少数公司能做? (技术专利/规模效应/客户锁定/原材料控制)
2. **供需缺口量化**: 当前产能 vs 需求, 缺口多大? 扩产需要多久?
3. **定价权验证**: 是否观察到"利润增速>营收增速"的垄断特征?
4. **国产替代可行性**: 中国公司能否进入? 需要多长时间? 哪些A股公司在尝试?
5. **垄断评分** (1-10分)
6. **A股受益标的推荐**: 列出最可能受益的A股公司及逻辑

请输出结构化 JSON:
[{{"segment": "环节名", "monopoly_root": "...", "supply_gap": "...", "pricing_power": "...", "localization_possible": true/false, "monopoly_score": N, "a_share_picks": [{{"code":"","name":"","logic":"..."}}]}}]"""

        text = await self.provider.chat(prompt)
        return self._extract_json_block(text, "bottleneck")

    async def _temporal_analysis(self, ctx: Dict, bottlenecks: List) -> Dict:
        """Step 3.5: 时间维度分析 — 景气持续性 + 供需缺口量化 + 产能过剩预警"""
        bn_list = bottlenecks if isinstance(bottlenecks, list) else []
        if not bn_list:
            return {"note": "无瓶颈数据, 跳过时间分析"}

        fundamentals = ctx.get("fundamentals", {})

        # 汇总 PE 数据用于热度判断
        pe_summary = []
        for code, f in fundamentals.items():
            if f.get("pe_ttm") and f["pe_ttm"] > 0:
                pe_summary.append({"code": code, "name": f.get("name",""), "pe_ttm": f["pe_ttm"], "pb": f.get("pb")})

        prompt = f"""你是一位半导体/科技产业分析师, 擅长产能周期和供需模型。请对以下瓶颈环节做时间维度量化分析。

## 瓶颈环节
{_json_dumps(bn_list, ensure_ascii=False)}

## A股标的 PE 数据 (用于热度判断)
{_json_dumps(pe_summary, ensure_ascii=False)}

## 分析任务 (每个环节)

1. **当前需求增速**: 估计年化需求增速 (%)
2. **当前产能利用率**: 估计全球产能利用率 (%)
3. **在建产能**: 在建新产能占现有产能的比例 (%)
4. **新产能投产时间**: 预计新产能何时开始释放 (YYYY-QQ 或 月份数)
5. **供需缺口**: 当前缺口百分比 (%)
6. **缺口填补时间**: 缺口何时被填补 (YYYY-QQ 或 月份数)
7. **产能过剩预警**: 如果新产能继续投入, 何时可能过剩 (YYYY-QQ 或 "暂无风险")
8. **景气持续性评分** (1-10): 高景气还能持续多久
9. **热度判断**: 基于 PE 数据和行业生命周期, 判断当前热度是 "合理/偏热/过热"

请输出纯JSON数组:
[{{"segment":"环节名","demand_growth":"25%","capacity_util":"95%","pipeline_pct":"30%","new_capacity_online":"2026-Q4","supply_gap":"15%","gap_filled":"2027-Q2","overcapacity_risk":"2028-Q1","sustainability_score":7,"sustainability_quarters":6,"heat_level":"合理","heat_reason":"PE30处于历史中位, 行业成长期"}}]"""

        text = await self.provider.chat(prompt)
        return self._extract_json_block(text, "temporal")

    async def _select_core_targets(self, ctx: Dict, bottlenecks: List) -> Dict:
        """Step 4: 锁定核心标的"""
        all_picks = []
        for b in bottlenecks if isinstance(bottlenecks, list) else []:
            all_picks.extend(b.get("a_share_picks", []))

        if not all_picks:
            return {"picks": [], "note": "未找到A股映射标的, 建议关注全球龙头"}

        # 查询这些标的的基本面
        pick_codes = [p["code"] for p in all_picks if p.get("code")]
        fund = await self.data_loader.load_fundamentals(pick_codes)

        picks_with_data = []
        for p in all_picks:
            code = p.get("code", "")
            f = fund.get(code, {})
            picks_with_data.append({
                **p,
                "pe_ttm": f.get("pe_ttm"), "pb": f.get("pb"),
                "mcap_yi": f.get("mcap_yi"),
            })

        prompt = f"""你是一位投资组合经理。请从以下候选中选出 3-5 只最值得配置的标的。

## 候选标的
{_json_dumps(picks_with_data, ensure_ascii=False, indent=2)}

## 选择标准
1. 在供应链瓶颈环节中占据最核心位置
2. 估值合理 (PE相对行业均值不过分高估)
3. 业绩确定性高 (有订单/产能/客户支撑)
4. 与用户现有持仓风格匹配

请输出:
{{"picks": [{{"code":"","name":"","score":N,"reason":"","position_suggest":"10%","risk":""}}]}}"""

        text = await self.provider.chat(prompt)
        return self._extract_json_block(text, "core_picks")

    async def _quantitative_valuation(self, ctx: Dict, targets: Dict) -> Dict:
        """Step 5: 定量估值"""
        picks = targets.get("picks", [])
        if not picks:
            return {"note": "无标的可估值"}

        # 加载估值数据
        codes = [p["code"] for p in picks if p.get("code")]
        fund = await self.data_loader.load_fundamentals(codes)

        valuations = []
        for p in picks:
            code = p.get("code", "")
            f = fund.get(code, {})
            valuations.append({
                "code": code, "name": p.get("name", ""),
                "pe_ttm": f.get("pe_ttm"), "pb": f.get("pb"),
                "mcap_yi": f.get("mcap_yi"),
                "score": p.get("score", 5),
            })

        prompt = f"""你是一位买方分析师。请为以下标的做定量估值。

## 标的估值数据
{_json_dumps(valuations, ensure_ascii=False, indent=2)}

## 你的任务
对每只标的:
1. 判断当前 PE 处于历史什么分位 (基于你的训练知识)
2. 给出合理 PE 区间和对应股价区间
3. 估算上涨空间 (%)
4. 对标国际龙头, 是否存在估值折价/溢价?
5. 给出 6-12个月目标价

请输出结构化 JSON。"""

        text = await self.provider.chat(prompt)
        return self._extract_json_block(text, "valuation")

    async def _generate_summary(self, results: Dict) -> str:
        """汇总生成最终投资建议"""
        prompt = f"""你是一位首席投资官(CIO)。请基于以下分析结果, 生成最终投资建议。

## 分析报告
{_json_dumps({
    "prosperity": results.get("prosperity_signals"),
    "core_picks": results.get("core_targets"),
    "valuation": results.get("valuation"),
}, ensure_ascii=False, indent=2)}

## 输出要求 (Markdown格式)
1. **核心结论** (1-2句话)
2. **推荐标的及配置比例**
3. **买入逻辑** (为什么现在买)
4. **风险提示**
5. **后续跟踪指标** (什么数据变化时需要重新评估)"""

        try:
            return await self.provider.chat(prompt)
        except Exception:
            return "AI 汇总生成失败, 请查看各步骤独立报告"

    # ═══ Helpers ══════════════════════════════════

    def _extract_json_block(self, text: str, fallback_key: str) -> Dict:
        """从 LLM 返回中提取 JSON — 处理多种格式"""
        import re
        text = text.strip()

        # 1. 去 markdown 代码块 (含中文属性)
        if "```" in text:
            # 匹配 ```json ... ``` 或 ``` ... ```
            m = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
            if m:
                text = m.group(1).strip()

        # 2. 提取第一个 JSON 对象或数组
        if text.startswith('{'):
            # 找匹配的结束括号
            depth = 0
            end = 0
            for i, ch in enumerate(text):
                if ch == '{': depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end > 0:
                text = text[:end]
        elif text.startswith('['):
            depth = 0
            end = 0
            for i, ch in enumerate(text):
                if ch == '[': depth += 1
                elif ch == ']':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end > 0:
                text = text[:end]

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"[{self.name}] JSON parse failed for {fallback_key}, returning raw")
            return {"raw_text": text[:800], "step": fallback_key}

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await super().load_context(ctx)
        ctx["macro"] = await self.data_loader.load_macro()
        return ctx

    def build_prompt(self, ctx: Dict[str, Any]) -> str:
        return "SupplyChainAnalyst — see _analyze_prosperity_signals etc."

    async def stream(self, context: Dict[str, Any]):
        yield "Supply chain analysis streaming not implemented"
