"""
MarketScanner V5.11 — per-industry _step3_guidance + kill_reasons/catalysts
双模式: auto(扫描验证) / manual(单行业深挖)
输出: 6块定性判断 + 结构化证据 + Step3指引
V5.8: 证据层结构化 + 自适应搜索降级 + PDF过滤 + Step3决策摘要
"""
import asyncio, json, re
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
    """Pipeline Gatekeeper V5.8 — 定性筛选 + 结构化证据 + 自适应搜索"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "MarketScanner"

    # ═══ 搜索工具 ═══════════════════════════════

    @staticmethod
    def _clean_snippet(text: str) -> str:
        """过滤 PDF 二进制、HTML标签、不可读字符"""
        if not text: return ""
        # PDF 二进制: 出现 PDF header 直接丢弃整条
        if "%PDF" in text or "endstream" in text or "endobj" in text:
            return ""
        # 去掉 HTML 标签
        text = re.sub(r'<[^>]+>', '', text)
        # 去掉控制字符
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
        return text[:250]

    async def _search_with_fallback(self, queries: List[str], num: int = 4, trace=None) -> List:
        """自适应搜索: 逐级降级, 结果为空时自动换词重试"""
        all_items = {}
        for q in queries:
            items = []
            for r in await self.data_loader.search_web(q, num=num):
                snippet = self._clean_snippet(r.get("snippet", ""))
                if not snippet and not r.get("title", ""):
                    continue
                items.append({"title": r.get("title", ""), "snippet": snippet})
            if trace:
                trace.record_search(q, items)
            if items:
                return {"query": q, "results": items}  # 返回第一个非空结果
            # 0 结果 → 记录并尝试下一个 (简化 query)
            logger.debug(f"[{self.name}] Search empty for '{q[:60]}', trying fallback")
        return {"query": queries[0], "results": []}  # 全部失败


    # ═══ 主入口 ═══════════════════════════════

    async def analyze(self, context: Dict[str, Any], trace=None) -> Dict[str, Any]:
        ctx = await self.load_context(context)
        mode = ctx.get("mode", "auto")
        if not self.provider:
            return {"error": "No AI provider"}

        if mode == "manual":
            target = ctx.get("target_industry") or ctx.get("question", "")
            if not target:
                return {"error": "manual mode requires target_industry"}
            result = await self._deep_dive_manual(target, trace=trace)
            result["agent"] = self.name
            result["mode"] = "manual"
            # 附加 Step 3 决策指引
            if not result.get("error"):
                result["_step3_guidance"] = self._build_step3_guidance(result)
            return result

        hypothesis = ctx.get("hypothesis_sectors", [])
        if hypothesis:
            result = await self._scan_auto(hypothesis, trace=trace)
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

    # ═══ auto 模式 ═══════════════════════════

    async def _scan_auto(self, hypothesis_sectors: List[Dict], trace=None) -> Dict:
        results = []
        for h in hypothesis_sectors[:5]:
            sector = h.get("sector", h.get("name", ""))
            if not sector: continue
            logger.info(f"[{self.name}] Scanning: {sector}")
            search_data = []
            for q in [f"{sector} 景气度 增速 供需 产能 2026",
                       f"{sector} 产能利用率 CAPEX 扩产周期 龙头订单 2026"]:
                sd = await self._search_with_fallback([q], num=3, trace=trace)
                search_data.append(sd)
            evaluation = await self._evaluate_industry(sector, search_data, h, trace=trace)
            if evaluation:
                evaluation["_step3_guidance"] = self._build_step3_guidance(evaluation)
                results.append(evaluation)

        results = self._deduplicate_industries(results)

        priority_order = {"高": 0, "中": 1, "低": 2, "跳过": 3}
        results.sort(key=lambda r: priority_order.get(
            (r.get("verdict", {}).get("priority", "低")), 3))
        return {"industries": results, "count": len(results)}

    def _deduplicate_industries(self, results: List[Dict]) -> List[Dict]:
        """如果父行业和子行业同时出现，保留子行业（更具体可操作）"""
        SUBSECTOR_MAP = {
            "电网设备": ["变压器", "开关设备", "配电自动化", "电力电子"],
            "半导体": ["封装", "刻蚀", "光刻", "存储", "先进封装", "半导体设备", "半导体材料"],
            "消费电子": ["智能手机", "PC", "可穿戴设备", "AR/VR"],
            "新能源车": ["电池", "电机", "电控", "整车", "充电桩"],
        }
        industry_names = [r.get("industry", "") for r in results]
        output = []
        for r in results:
            ind = r.get("industry", "")
            children_of_ind = SUBSECTOR_MAP.get(ind, [])
            has_child_present = any(c in industry_names for c in children_of_ind)
            if has_child_present:
                logger.info(f"[{self.name}] 剔除宽泛父行业: {ind}, 因存在更细分子行业")
                continue
            output.append(r)
        return output

    # ═══ manual 模式: 自适应搜索 ═══════════

    async def _deep_dive_manual(self, industry: str, trace=None) -> Dict:
        """对用户指定的行业做 4 轮自适应深度搜索"""
        logger.info(f"[{self.name}] Deep dive: {industry}")
        search_data = []

        # 4 个搜索维度, 每个带降级 chain
        search_chains = [
            [f"{industry} 行业概况 市场规模 TAM 增速 2026",
             f"{industry} 市场规模 增速 2026",
             f"{industry} market size growth 2026"],
            [f"{industry} 供需缺口 产能利用率 交期 CAPEX 扩产周期 2026",
             f"{industry} 产能 扩产 瓶颈 供应链 2026",
             f"{industry} supply chain bottleneck capacity"],
            [f"{industry} 竞争格局 政策环境 国产化率 全球份额 2026",
             f"{industry} 国产替代 竞争 龙头 企业 2026",
             f"{industry} competition landscape china 2026"],
            [f"{industry} 产业链 上游 下游 传导 瓶颈 成本结构 2026",
             f"{industry} 产业链 上下游 关键环节 2026",
             f"{industry} supply chain upstream downstream"],
        ]

        for chain in search_chains:
            sd = await self._search_with_fallback(chain, num=4, trace=trace)
            search_data.append(sd)

        evaluation = await self._evaluate_industry(industry, search_data, {}, trace=trace)
        if evaluation:
            evaluation["mode"] = "manual"
            if trace:
                trace.record_note("verdict",
                    f"enter_step3={evaluation.get('verdict',{}).get('enter_step3')}, "
                    f"priority={evaluation.get('verdict',{}).get('priority')}, "
                    f"kill_reasons={evaluation.get('kill_reasons',[])}")
        return evaluation or {"error": "LLM evaluation failed", "industry": industry}

    # ═══ LLM 评估 (共用) ═══════════════════════

    async def _evaluate_industry(self, industry: str, search_data: List,
                                  hypothesis: Dict = None, trace=None) -> Dict:
        """LLM 按 6 块定性结构评估一个行业 — 每个结论带结构化证据"""
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
        for i, sd in enumerate(search_data):
            prompt += f"\n### 搜索[{i+1}]: {sd['query']}\n"
            if not sd["results"]:
                prompt += "  (无结果)\n"
            for j, r in enumerate(sd["results"][:3]):
                prompt += f"  [{i+1}.{j+1}] {r['title']}: {r['snippet'][:200]}\n"

        prompt += f"""
## 输出: 纯 JSON (7 块, 全定性, 每个结论必须附证据数组)

{{
  "industry": "{industry}",

  "industry_granularity": {{
    "type": "specific_industry",
    "action": "allow",
    "reason": "为什么判定为该粒度类型 (1句话)"
  }},

  "cycle_position": {{
    "phase": "theme_emergence",
    "sub_phase": "early",
    "evidence": [
      {{"fact": "具体事实1", "from": "search[1.2]·报告标题",
        "quality": {{"level": "high", "source_type": "industry_data"}}}}
    ],
    "next_phase": "...",
    "estimated_duration": "12-18个月",
    "phase_switch_trigger": "..."
  }},

  "prosperity": {{
    "type": "demand_explosion",
    "demand_quality": "real_demand",
    "demand_evidence": [
      {{"fact": "市场规模从A增至B", "from": "search[1.X]·报告标题",
        "quality": {{"level": "medium", "source_type": "sell_side_report"}}}}
    ],
    "growth_narrative": "行业增速 vs 供给响应的矛盾描述",
    "core_contradiction": "当前最核心的供需矛盾是什么",
    "driver_decomposition": [
      {{"driver": "驱动力1", "weight": "主导", "certainty": "高", "duration": "3-5年", "leading_indicator": "...",
        "evidence": [{{"fact": "...", "from": "search[X.Y]·...", "quality": {{"level": "high", "source_type": "company_filing"}}}}]}}
    ]
  }},

  "payoff": {{
    "asymmetry": "强非对称",
    "narrative": "判断依据: 如果景气兑现会怎样, 如果证伪会怎样",
    "evidence": [
      {{"fact": "支撑非对称判断的关键事实", "from": "search[X.Y]·...",
        "quality": {{"level": "medium", "source_type": "sell_side_report"}}}}
    ]
  }},

  "propagation": {{
    "depth": "深",
    "transmission_order": [
      {{"stage": 1, "node": "环节名", "reason": "最先受益的原因",
        "evidence": [{{"fact": "...", "from": "search[X.Y]·...", "quality": {{"level": "medium", "source_type": "news_media"}}}}]}}
    ],
    "last_beneficiary": "...",
    "last_bottleneck": "...",
    "alpha_implication": "..."
  }},

  "time_horizon": {{
    "alpha_window": "6-12个月",
    "profit_expansion_window": "12-24个月",
    "capacity_relief_eta": "2028H1",
    "market_repricing_stage": "早期",
    "evidence": [{{"fact": "支撑时间判断的证据", "from": "search[X.Y]·...",
      "quality": {{"level": "medium", "source_type": "sell_side_report"}}}}]
  }},

  "mismatch_analysis": {{
    "supply_demand_mismatch": "strong",
    "timing_mismatch": "moderate",
    "expectation_gap": "weak",
    "profit_redistribution": {{
      "strength": "strong",
      "direction": "upstream"
    }},
    "pricing_gap": "uncertain",
    "evidence": [
      {{"fact": "支撑逐项判断的关键事实", "from": "search[X.Y]·...",
        "quality": {{"level": "medium", "source_type": "sell_side_report"}}}}
    ]
  }},

  "thesis_killers": {{
    "substitution_risk": "low",
    "policy_block_risk": "low",
    "investable_exposure": "sufficient",
    "details": "解释性文字, 说明为什么这些威胁级别低/高"
  }},

  "verdict": {{
    "enter_step3": true,
    "priority": "高",
    "rationale": "基于 mismatch_analysis 的结果说明: 哪几条错配程度高、哪条不确定、为什么综合判断为进入/跳过",
    "key_uncertainties": ["不确定性1", "不确定性2"],
    "evidence": [
      {{"fact": "支撑 verdict 的关键事实", "from": "search[X.Y]·...",
        "quality": {{"level": "medium", "source_type": "sell_side_report"}}}}
    ]
  }},

  "kill_reasons": [
    {{"reason": "标准枚举值", "monitor_signal": "什么指标变化会触发证伪", "data_source_hint": "可从哪获取这个指标"}}
  ],

  "catalysts": [
    {{"type": "earnings/product/policy/capacity/order",
      "catalyst": "催化事件描述", "expected_date": "预计发生时间", "watch_signal": "什么数据确认催化兑现", "status": "pending"}}
  ]
}}

## industry_granularity 粒度判定 (★ 在分析之前先判定)
判定标准: 能否画出这个主题的物理供应链? (GPU→HBM→CoWoS→封装→测试 这种)
- specific_industry (CoWoS/HBM/SOFC/CPU/液冷散热 等具体产业节点) → action=allow
- subsector (AI算力/半导体设备/创新药/新能源车 等产业板块, 范围宽但有真实供需链) → action=allow
- macro_theme (新质生产力/国产替代/碳中和/AI新基建 等纯政策概念, 无统一供给链) → action=split_or_skip, 强制 enter_step3=false
- asset_class (黄金ETF/REITs等金融产品) → action=skip, enter_step3=false
- 注意: "AI算力/英伟达产业链/半导体"等不是macro_theme — 它们有真实供应链, 应归为subsector
- subsector 级别分析的核心原则: 不要评估"整个篮子", 而要识别篮子中**具体哪个子环节存在五错配**。
  例如"英伟达产业链"整体预期差弱, 但其中的CoWoS封装/HBM/液冷散热可能存在强预期差。
  输出 mismatch_analysis 时, 以最具错配特征的子环节为准, 而非整体平均
- 如果判定为 macro_theme 或 asset_class, 后续 6 块仍需填写但 verdict 必须拒绝

## evidence_quality 证据质量 (★ 每条 evidence 必须标注)
- quality.level: high / medium / low
- quality.source_type 枚举:
  company_filing(公司财报/公告) | industry_data(海关/行业协会/产能统计) | official_policy(政府文件/产业规划) |
  sell_side_report(券商研报) | news_media(财经媒体) | self_media(自媒体/知乎/公众号) | ai_summary(AI摘要)

## 证据降权规则 (★ 强制)
- 裁决时优先采信 quality.level=high 且 source_type=company_filing/industry_data/official_policy 的证据
- source_type=self_media/ai_summary 的证据仅作参考, 不得单独支撑 enter_step3 或 priority 判断
- 如果某结论的高质量证据全部缺失, 必须在 rationale 中标注"证据质量不足"

## 证据格式要求
- 每个结论块的 evidence 数组至少包含 1 条证据
- from 格式: "search[轮次.序号]·来源简称", 如 "search[1.2]·慧博出品"
- 如果某轮搜索无结果, evidence 中标注 {{"fact": "该维度搜索结果为空", "from": "search[2]·无结果", "quality": {{"level": "low", "source_type": "ai_summary"}}}}

## mismatch_analysis 取值: strong / moderate / weak / uncertain
- strong: 搜索结果有明确数据支撑该错配
- moderate: 有间接证据, 逻辑链需要一步推断
- weak: 证据薄弱或矛盾
- uncertain: 完全没有数据, 不确定

## profit_redistribution.direction 方向枚举
- upstream: 利润向上游迁移（资源/原材料瓶颈受益）
- midstream: 利润在中游集中（制造/加工环节）
- downstream: 利润向下游迁移（渠道/品牌/应用）
- 分散: 利润分布变化不明确或全线受益

## thesis_killers — 论文杀手 (独立于五错配, 评估结构性威胁)
- substitution_risk: low/medium/high — 替代技术是否可能在3年内颠覆产业链
- policy_block_risk: low/medium/high — 政策/地缘风险是否可能阻断投资逻辑
- investable_exposure: sufficient/limited/none — A股是否有可投资的纯正标的
- details: 解释性文字
注意: thesis_killers 与 mismatch_analysis 无关。即使 S+T+E+P+$ 全 strong,
如果 thesis_killers 有高风险, verdict 应降级。

## 避免同质化重复 (★ 强制)
- 规则：每条 evidence 只能在整个输出中引用一次（不要用同样的事实填充不同的字段）。
- 如果某条 evidence 需要支撑多个字段，请在 evidence 数组中用 "also_supports": ["prosperity", "payoff"] 声明适用范围，但 fact 本身只写一次。

## 规则
- 不要在 rationale 中使用"五错配全部满足/不满足"等笼统表述 — 必须引用 mismatch_analysis 的具体结果
- 如果 enter_step3=false, kill_reasons 必须使用标准枚举值(需求来自渠道补库存/已进入资本狂热后期/估值透支3年增长/政策抢装非真实需求/供给扩张>需求/传导链<3层Alpha空间有限), 选最接近的。每个 kill_reason 附带 monitor_signal 和 data_source_hint
- 所有数值引用必须来自搜索结果, 不得编造
- catalysts 从 phase_switch_trigger 和 key_uncertainties 中提取, 标注预计时间和可观测信号"""
        # 注入权威术语表 (放在规则后面, 距离核心指令近)
        from app.framework.pipeline.glossary import step2_glossary
        prompt += step2_glossary()

        try:
            text = await self.provider.chat_flash(prompt, max_tokens=6144, timeout=90)
            if trace:
                trace.record_llm(prompt, text, model=getattr(self.provider, 'model', 'deepseek-v4-flash'))
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

    # ═══ Step2 → 路径推荐 ═══════════════════════

    @staticmethod
    def _recommend_path(ma: dict, cycle_phase: str = "unknown",
                        mkt_repricing: str = "unknown",
                        thesis_killers: dict = None) -> dict:
        """五错配 → 推荐路径 (A/B/C/KILL) 确定性映射

        整合:
          - mismatch_analysis 五维度 (S/T/E/P/$)
          - cycle_phase 交互 (bottleneck_formation/capital_frenzy 等)
          - market_repricing_stage (早期/中期/晚期)
          - thesis_killers (substitution_risk/policy_block_risk/investable_exposure)
        优先级: thesis_killers(investable) > KILL > C > A > B
        """
        S = ma.get("supply_demand_mismatch", "uncertain")
        T = ma.get("timing_mismatch", "uncertain")
        E = ma.get("expectation_gap", "uncertain")
        P_raw = ma.get("profit_redistribution", "uncertain")
        D = ma.get("pricing_gap", "uncertain")  # $ → D
        tk = thesis_killers or {}

        # P 兼容: 旧格式 "strong" / 新格式 {"strength":"strong","direction":"upstream"}
        if isinstance(P_raw, str):
            P = P_raw
            P_dir = "unknown"
        else:
            P = P_raw.get("strength", "uncertain") if isinstance(P_raw, dict) else "uncertain"
            P_dir = P_raw.get("direction", "unknown") if isinstance(P_raw, dict) else "unknown"

        def _make(path, confidence, rationale, extra=None):
            return {"path": path, "confidence": confidence, "rationale": rationale,
                    **(extra or {})}

        # ── Thesis Killer 前置检查: investable_exposure=none → 强制 KILL ──
        inv_exp = tk.get("investable_exposure", "unknown")
        if inv_exp == "none":
            return _make("KILL", "high",
                "A股无纯正可投标的(investable_exposure=none), 即使逻辑通也无法投资")

        # ── 路径选择 (基础) ──────────────────────────

        # Priority 1: KILL — 供需无缺口
        if S in ("weak", "uncertain"):
            return _make("KILL", "high",
                f"供需错配缺失(S={S}), 无基本面分析基础, 建议跳过")

        # Priority 2: Path C — 认知差强
        if E == "strong":
            base_conf = "high"
            base_rationale = (
                f"认知差强(E=strong), 供需={S}, 时间={T}, 利润迁移={P}, 定价={D}")

            # cycle_phase 交互: E=strong 的含义取决于处在什么阶段
            phase_modifier = ""
            if cycle_phase == "theme_emergence":
                base_conf = "high_priority"
                phase_modifier = "主题刚浮现, 市场尚未关注, 优先深挖 ⭐⭐"
            elif cycle_phase == "bottleneck_formation":
                base_conf = "high"
                phase_modifier = "瓶颈形成期+认知差, 预期差最大 ⭐"
            elif cycle_phase == "capital_frenzy":
                base_conf = "medium"
                phase_modifier = "注意: 资本狂热期认知差可能为假象, 需验证真伪"
            elif cycle_phase == "demand_explosion":
                base_conf = "high"
                phase_modifier = "需求爆发期+认知差, 好赛道还没人看懂 ⭐"

            # market_repricing_stage 调节
            repricing_modifier = ""
            if mkt_repricing == "晚期":
                base_conf = "medium" if base_conf == "high" else "low"
                repricing_modifier = ", 市场已晚期定价, 空间有限"
            elif mkt_repricing == "早期":
                if base_conf not in ("high_priority",):
                    base_conf = "high"
                repricing_modifier = ", 市场尚未定价, 空间大"

            # thesis_killers 降级
            if tk.get("substitution_risk") == "high":
                base_conf = "medium" if base_conf != "low" else "low"
                phase_modifier += " [警告: 替代风险高]"
            if tk.get("policy_block_risk") == "high":
                base_conf = "medium" if base_conf != "low" else "low"
                phase_modifier += " [警告: 政策阻断风险高]"
            if inv_exp == "limited":
                base_conf = "medium" if base_conf != "low" else "low"
                phase_modifier += " [A股敞口有限]"

            highlight = base_conf in ("high", "high_priority")
            return _make("C", base_conf,
                f"{phase_modifier}{repricing_modifier} | {base_rationale}".strip(" | "),
                {"highlight": highlight, "cycle_phase_modulation": phase_modifier})

        # Priority 3: Path A — 市场已定价但逻辑硬 + 利润迁移明确
        if E == "weak" and S == "strong" and P == "strong":
            if D == "weak":
                return _make("A", "medium",
                    "产业逻辑硬(S=strong+P=strong)但认知已定价+估值已反映, "
                    "直挖标的并严格评估安全边际",
                    {"mismatch_status": "逻辑硬但无估值空间"})
            if D == "strong":
                path_note = ""
                if inv_exp == "limited":
                    path_note = " [A股敞口有限, 需精选标的]"
                return _make("A", "high",
                    f"供需错配+利润迁移明确, 市场已有认知(E=weak), "
                    f"但估值尚未完全反映($=strong), 直挖受益标的 ⭐{path_note}",
                    {"highlight": True, "mismatch_status": "S+P+$ 三强, 快速兑现"})
            # D=uncertain
            path_note = ""
            if inv_exp == "limited":
                path_note = " [A股敞口有限, 需精选]"
            return _make("A", "medium",
                f"产业逻辑硬(S=strong+P=strong)但认知已定价(E=weak)+定价不确定($={D}), "
                f"推荐直挖快速扫描, 结合实际估值判断安全边际{path_note}",
                {"mismatch_status": "逻辑硬但估值模糊"})

        # Priority 4: Path B — 二阶推演
        if E == "weak" and D in ("weak", "uncertain"):
            return _make("B", "medium",
                f"认知差弱(E=weak)+定价模糊($={D}), 主产业吸引力有限, "
                "尝试二阶推演寻找跨产业溢出机会")

        if S == "strong" and P in ("weak", "moderate"):
            return _make("B", "low",
                f"供需缺口存在(S=strong)但利润迁移不明确(P={P}), "
                "主产业受益标的难识别, 尝试二阶推演看跨产业受益者")

        # ── Fallback ──────────────────────────────
        if S in ("moderate", "strong"):
            return _make("C", "low",
                f"未完全匹配已知模式(S={S}/T={T}/E={E}/P={P}/$={D}), "
                "推荐全链路深挖进一步验证确定性")

        return _make("B", "low",
            "各维度均不突出, 二阶推演寻找边缘机会")

    # ═══ Step2 → Step3 决策指引 ═════════════════

    @staticmethod
    def _build_step3_guidance(output: dict) -> dict:
        cp = output.get("cycle_position", {})
        pr = output.get("prosperity", {})
        pp = output.get("propagation", {})
        v = output.get("verdict", {})
        ma = output.get("mismatch_analysis", {})
        ig = output.get("industry_granularity", {})
        th = output.get("time_horizon", {})
        tk = output.get("thesis_killers", {})

        # 周期阶段的含义映射
        phase_meanings = {
            "theme_emergence": "技术验证阶段, 收入未体现 — 搜索时关注技术路线和专利, 而非产能数据",
            "demand_explosion": "订单暴增, 渗透率快速拉升 — 搜索时关注下游订单和产能扩张计划",
            "bottleneck_formation": "交期暴涨, 供给不足 — 搜索时重点找产能/交期/设备约束数据",
            "capital_frenzy": "全行业扩产 — 关注新增供给投放时点和价格松动信号",
            "capacity_release": "产能释放, 价格松动 — 关注成本最低者和出清节奏",
            "commoditization": "价格战, ROE崩塌 — 关注竞争格局和成本曲线",
        }
        phase = cp.get("phase", "unknown")

        prosperity_meanings = {
            "demand_explosion": "需求驱动 — 分析框架: 找产能扩张瓶颈和订单传导链",
            "supply_shock": "供给冲击 — 分析框架: 找供给约束源头和替代方案",
            "policy_driven": "政策驱动 — 分析框架: 关注政策稳定性窗口和补贴退坡风险",
            "replacement_cycle": "更新周期 — 分析框架: 关注存量替换节奏和换机周期",
            "capex_cycle": "资本开支周期 — 分析框架: 关注CAPEX达产时点和供需拐点",
            "inventory_cycle": "库存周期 — 分析框架: 区分补库和终端真实需求",
        }
        ptype = pr.get("type", "unknown")
        mkt_repricing = th.get("market_repricing_stage", "unknown")

        # profit_redistribution 兼容: str → {strength, direction}
        pr_raw = ma.get("profit_redistribution", "?")
        if isinstance(pr_raw, str):
            P_strength = pr_raw
            P_direction = "unknown"
        elif isinstance(pr_raw, dict):
            P_strength = pr_raw.get("strength", "?")
            P_direction = pr_raw.get("direction", "unknown")
        else:
            P_strength = "?"
            P_direction = "unknown"

        return {
            "industry_name_for_search": output.get("industry", ""),
            "cycle_phase": phase,
            "cycle_meaning": phase_meanings.get(phase, ""),
            "prosperity_type": ptype,
            "prosperity_meaning": prosperity_meanings.get(ptype, ""),
            "propagation_depth": pp.get("depth", "中"),
            "enter_step3": v.get("enter_step3", False),
            "priority": v.get("priority", "低"),
            "mismatch_summary": f"S={ma.get('supply_demand_mismatch','?')}/T={ma.get('timing_mismatch','?')}/E={ma.get('expectation_gap','?')}/P={P_strength}/$={ma.get('pricing_gap','?')}",
            "recommended_path": MarketScanner._recommend_path(ma, phase, mkt_repricing, tk),
            "profit_redistribution_detail": {"strength": P_strength, "direction": P_direction},
            "thesis_killers": tk,
            "market_repricing_stage": mkt_repricing,
            "industry_granularity": ig.get("type", "unknown"),
            "search_focus": (
                f"周期阶段={phase} → {phase_meanings.get(phase, '')}; "
                f"景气类型={ptype} → {prosperity_meanings.get(ptype, '')}"
            ),
            "key_uncertainties": v.get("key_uncertainties", []),
            "core_contradiction": pr.get("core_contradiction", ""),
        }

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
1. 每个行业输出: name, score(1-10), lifecycle_stage, stage_evidence, type, reason, global_drivers, a_stock_codes
2. 优先关注有资金流入支撑的行业
3. 区分短期热点 vs 中期趋势
4. 搜索结果中提到的股票代码必须包含在 a_stock_codes 中

请输出纯 JSON 数组:
[{{"name":"AI算力","score":9,"lifecycle_stage":"成长期","stage_evidence":"...","type":"中期趋势","reason":"...","global_drivers":"...","a_stock_codes":["688256","300308"]}}]"""
        text = await self.provider.chat_flash(prompt, max_tokens=2048, timeout=60) or ""
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
            return await self.provider.chat_pro(prompt, max_tokens=2048, timeout=120) or ""
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
        return "MarketScanner V5.8"

    @staticmethod
    async def stream(ctx):
        yield "streaming not implemented"
