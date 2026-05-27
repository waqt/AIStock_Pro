"""
SupplyChainHacker V5.9 — 供应链降维穿透 (纯静态拆链)
V5.9: 移除 Phase 1.8 (→ Step 4), 专注 L1-L4 瓶颈图谱 + 证据层
V5.9.1: 证据节点级合并 + chat_pro→chat_flash + glossary注入
输出: supply_chain_map + core_stocks + sales/expansion chain
"""
import asyncio, re
from decimal import Decimal
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger


class SupplyChainHacker(ResearchAgent):
    """供应链黑客 V5.9 — 产业瓶颈降维穿透"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "SupplyChainHacker"

    # ═══ 搜索工具 ═══════════════════════════════

    @staticmethod
    def _clean_snippet(text: str) -> str:
        if not text: return ""
        if "%PDF" in text or "endstream" in text or "endobj" in text: return ""
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

    async def analyze(self, ctx: Dict[str, Any], trace=None) -> Dict[str, Any]:
        ctx = await self.load_context(ctx)
        industry = ctx.get("industry", ctx.get("target_industry", "未指定"))

        if not self.provider:
            return {"agent": self.name, "error": "No AI provider", "data": ctx}

        step2 = ctx.get("step2_guidance", {})
        logger.info(f"[{self.name}] Hacking: {industry} | Step2: {step2.get('cycle_phase','?')}/{step2.get('prosperity_type','?')}")

        research_data = await self._hack_supply_chain(industry, step2, trace=trace)
        core_stocks = await self._extract_stocks_simple(industry, research_data)
        result = await self._structure_output(industry, research_data, step2, trace=trace)

        if not result.get("core_stocks") and core_stocks:
            result["core_stocks"] = core_stocks
        if not result.get("core_stocks"):
            result["core_stocks"] = core_stocks

        result["agent"] = self.name
        result["industry"] = industry
        result["search_rounds"] = research_data.get("search_rounds", 0)
        if trace:
            trace.record_note("summary", f"layers={len(result.get('supply_chain_map',[]))}, stocks={len(result.get('core_stocks',[]))}")
        return result

    # ═══ Phase 1: 供应链迭代深研 ═════════════════

    async def _hack_supply_chain(self, industry: str, step2: dict = None, trace=None) -> Dict:
        all_findings = []
        gaps = []
        round_num = 0
        step2 = step2 or {}

        for round_num in range(1, 4):
            if round_num == 1:
                phase = step2.get("cycle_phase", "")
                ptype = step2.get("prosperity_type", "")
                chains = [[
                    f"{industry} 产业链 核心瓶颈 产能 技术壁垒 龙头公司 市占率",
                    f"{industry} 产业链 瓶颈 龙头 产能 2026",
                    f"{industry} supply chain bottleneck key players",
                ]]
                if phase == "bottleneck_formation":
                    chains = [[
                        f"{industry} 产能 交期 设备约束 瓶颈环节 扩产周期",
                        f"{industry} 产能缺口 交期 供应链瓶颈 2026",
                        f"{industry} capacity lead time bottleneck supply chain",
                    ]]
                elif ptype == "supply_shock":
                    chains = [[
                        f"{industry} 供给约束 资源稀缺 设备禁令 认证壁垒",
                        f"{industry} 供给受限 原材料 设备 国产替代 2026",
                        f"{industry} supply constraint material equipment restriction",
                    ]]
            elif gaps:
                chains = [[
                    f"{industry} {' '.join(gaps[:3])}",
                    f"{industry} {' '.join(gaps[:2])}",
                ]]
            else:
                break

            search_data = await self._search_adaptive(chains, num=5, trace=trace)
            if not search_data[0]["results"] and round_num > 1:
                break

            prompt = f"""你是全球半导体/制造业供应链研究员。分析 {industry} 产业链的瓶颈结构和国产替代机会。

## 本轮搜索结果
{_j(search_data)}

## 前几轮发现
{_j(all_findings)}

## 任务
1. 基于搜索结果提取关键供应链信息, 每条发现附来源引用 (from字段标注search[X])
2. 供应链自检: 缺产能数据? 缺设备交期? 缺国产化率? 缺技术代际差?
3. 如果缺数据, 列出下一轮搜索关键词 (最多 3 个)

请输出纯 JSON:
{{"findings": [{{"key": "瓶颈发现", "detail": "具体细节", "from": "search[1.2]·来源简称"}}],
  "gaps": ["缺口关键词1", "缺口关键词2"],
  "need_more_search": true/false}}"""

            try:
                text = await asyncio.wait_for(
                    self.provider.chat_pro(prompt, max_tokens=2048), timeout=60)
                if trace: trace.record_llm(prompt, text, model="deepseek-v4-pro")
                result = self.parse_json(text)
                if isinstance(result, dict):
                    findings = result.get("findings", [])
                    gaps = result.get("gaps", [])
                    all_findings.extend(findings)
                    if not result.get("need_more_search") and round_num > 1:
                        break
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(f"[{self.name}] Round {round_num} failed: {e}")
                break

        return {"findings": all_findings, "search_rounds": round_num}

    # ═══ Phase 1.5: 股票提取 ═══════════════════

    async def _extract_stocks_simple(self, industry: str, research: Dict) -> list:
        findings = research.get("findings", [])
        if not findings: return []
        summary = "; ".join(
            f.get("key","") + ":" + f.get("detail","")[:100]
            for f in findings[:10] if isinstance(f, dict))
        if not summary.strip(): return []

        codes_raw = list(set(re.findall(r'\b(60[0-4]\d{3}|688\d{3}|00[0-3]\d{3}|30[0-2]\d{3})\b', summary)))
        if len(codes_raw) >= 3:
            logger.info(f"[{self.name}] Regex extracted {len(codes_raw)} codes")
            return [{"code": c, "name": c, "segment": "待确认"} for c in codes_raw[:8]]

        prompt = f"列出{industry}产业链相关的5-8只A股标的(6位代码+名称)。输出纯JSON数组: [{{\"code\":\"000001\",\"name\":\"平安银行\"}}]。基于: {summary[:3000]}"
        try:
            text = await asyncio.wait_for(self.provider.chat_flash(prompt, max_tokens=4096), timeout=30)
            result = self.parse_json(text)
            if isinstance(result, list): return result
            if isinstance(result, dict):
                for v in result.values():
                    if isinstance(v, list) and len(v) > 0: return v
            fallback = list(set(re.findall(r'\b(60[0-4]\d{3}|688\d{3}|00[0-3]\d{3}|30[0-2]\d{3})\b', text)))
            if fallback: return [{"code": c, "name": c, "segment": "待确认"} for c in fallback[:8]]
        except Exception as e:
            logger.warning(f"[{self.name}] Stock extract failed: {e}")
        return []

    # ═══ Phase 2: 结构化输出 (V5.9.1 精简版) ═══════

    async def _structure_output(self, industry: str, research: Dict, step2: dict = None, trace=None) -> Dict:
        findings = research.get("findings", [])
        step2 = step2 or {}

        step2_context = ""
        if step2:
            step2_context = f"""
## 上游决策 (Step 2 看门人)
- 周期阶段: {step2.get('cycle_phase','?')} → {step2.get('cycle_meaning','')}
- 景气类型: {step2.get('prosperity_type','?')} → {step2.get('prosperity_meaning','')}
- 搜索聚焦: {step2.get('search_focus','')}
"""

        fresh_data = await self._search_adaptive([[
            f"{industry} 供应链 最新 瓶颈 产能 缺口 2026",
            f"{industry} 产业链 瓶颈 最新 2026",
        ]], num=5, trace=trace)

        prompt = f"""你是买方首席产业研究员。输出 {industry} 产业深度穿透 JSON。

{step2_context}
## 研究发现 ({len(findings)} 条)
{_j(findings[:10])}

## 补充搜索
{_j(fresh_data)}

## 输出纯 JSON (精简版 — 每节点一个 evidence 数组)
{{
  "confidence": "high/medium/low/insufficient_data",
  "confidence_note": "搜索覆盖情况说明: 数据缺口在哪, 哪些结论依赖单一来源",

  "supply_chain_map": [
    {{
      "level": 1,
      "name": "瓶颈环节名",
      "bottleneck_narrative": "瓶颈简述 (1-2句)",
      "confidence": "high/medium/low",

      "supply_rigidity": {{
        "severity": "extreme", "root_cause": "equipment_constraint",
        "expand_cycle": "over_24m", "substitutability": "none_short_term",
        "concentration": "monopoly_single_supplier",
        "alpha_narrative": "供给刚性→定价权→景气窗口"
      }},
      "profit_pool": {{
        "share_of_industry_profit": "dominant_30_50pct",
        "margin_level": "very_high_above_40pct",
        "margin_estimated": true,
        "margin_data_source": "LLM估计, 基于搜索片段中的研报引用 | 待Step 6财务验证回写",
        "pricing_power_narrative": "定价权描述"
      }},
      "value_capture": {{
        "market_attention": "very_high", "attention_quality": "profit_real",
        "gap_narrative": "关注度 vs 利润捕获",
        "who_captures_value": ["受益方"]
      }},
      "competitive_landscape": {{
        "structure": "oligopoly_CR3_above_70",
        "global_leaders": ["龙头"], "china_substitution_rate": "below_5pct",
        "china_players": {{"tier1":[],"tier2":[],"tier3":[]}}
      }},
      "future_outlook": {{
        "next_2_3_years": "bottleneck_persists",
        "potential_relief": "缓解路径", "emerging_bottleneck": "新瓶颈"
      }},
      "assets": [{{"code":"688012","name":"公司","role":"角色","market_position":"tier1"}}],
      "assets_note": "暂无A股标的时填说明",

      "evidence": [
        {{"fact":"关键事实1","from":"search[1.3]·来源","quality":{{"level":"high","source_type":"industry_data"}}}},
        {{"fact":"关键事实2","from":"search[2.1]·来源","quality":{{"level":"medium","source_type":"sell_side_report"}}}}
      ]
    }}
  ],
  "core_stocks": [{{"code":"688012","name":"公司","segment":"环节","role":"龙头","moat":"壁垒"}}],
  "sales_chain": [{{"segment":"受益环节","companies":["688XXX"],"reason":"理由","lead_months":"1-3"}}],
  "expansion_chain": [{{"segment":"滞后环节","companies":["688YYY"],"reason":"理由","lag_months":"6-12"}}],
  "chain_timeline": {{"sales_lead_months":"1-3","expansion_lag_months":"6-12","rotation_strategy":"策略"}},
  "scarcity_ranking": [{{"rank":1,"segment":"稀缺环节","rigidity_narrative":"刚性","beneficiary_stocks":["688012"]}}],
  "catalysts": [{{"type":"capacity","catalyst":"事件","expected_date":"时间","watch_signal":"指标","affected_segment":"环节"}}]
}}
"""
        # 注入枚举约束 glossary
        from app.framework.pipeline.glossary import step3_glossary
        prompt += step3_glossary()

        prompt += """
## 规则
- evidence 数组在节点级别 (每节点 2-4 条), 子字段不各自带 evidence
- from 格式: "search[轮次.序号]·来源简称", 禁止自创前缀
- core_stocks >= 5 只, supply_chain_map >= L1-L3, sales/expansion chain >= 各 2 条
- assets 空时用 assets_note 说明; 同公司不出现在多个 tier
- self_media/ai_summary 仅参考, 不得单独支撑关键判断
- ★ margin_estimated=true 表示 margin_level/share_of_profit 为 LLM 基于搜索片段估计 (非硬财务数据)
- ★ 3轮搜索仍无有效结果时: 不丢弃数据, 输出 confidence=insufficient_data + confidence_note 说明缺口
- ★ expand_cycle 三档: under_12m / 12_24m / over_24m (与 Step 4/5 时间枚举对齐)"""

        try:
            text = await asyncio.wait_for(
                self.provider.chat_pro(prompt, max_tokens=8192), timeout=480)
            if trace: trace.record_llm(prompt, text, model="deepseek-v4-pro")
            result = self.parse_json(text)
            if isinstance(result, dict) and result.get("parse_error"):
                logger.warning(f"[{self.name}] Struct parse failed, retrying...")
                retry_prompt = f"列出 {industry} 产业链核心A股标的, 输出纯JSON: {{\"core_stocks\":[{{\"code\":\"000001\",\"name\":\"公司\",\"segment\":\"环节\"}}]}}。基于: {_j(findings[:8])}"
                text2 = await asyncio.wait_for(self.provider.chat_flash(retry_prompt, max_tokens=2048), timeout=30)
                result = self.parse_json(text2)

            if isinstance(result, dict):
                result["findings_count"] = len(findings)
                logger.info(f"[{self.name}] Structured: {len(result.get('supply_chain_map',[]))} layers, {len(result.get('core_stocks',[]))} stocks")
                return result
        except asyncio.TimeoutError:
            logger.warning(f"[{self.name}] Phase 2 timeout")
        except Exception as e:
            logger.warning(f"[{self.name}] Phase 2 failed: {e}")

        codes = list(set(re.findall(r'\b(\d{6})\b', str(findings))))[:10]
        if codes:
            return {"core_stocks": [{"code": c, "name": c, "segment": "待确认"} for c in codes]}
        return {"raw_findings": findings, "error": "Structuring failed"}

    # ═══ analyze_level ═════════════════════════

    async def analyze_level(self, industry: str, level_name: str, level_info: Dict = None) -> Dict:
        logger.info(f"[{self.name}] Deep-diving level: {level_name} ({industry})")
        search_data = await self._search_adaptive([[
            f"{industry} {level_name} 龙头企业 市占率 国产替代 产能 技术壁垒",
            f"{industry} {level_name} 产业链 龙头 国产 2026",
            f"{industry} {level_name} companies market share",
        ]], num=6)

        prompt = f"""对 {industry} 的 {level_name} 环节做独立深度穿透。
已知信息: {_j(level_info) if level_info else '无'}
搜索结果: {_j(search_data)}
输出纯JSON:
{{"level_name":"{level_name}","overview":"地位","market_structure":{{"global_size":"规模","growth_rate":"增速","concentration":"CR","entry_barriers":"壁垒"}},
"all_assets":[{{"code":"688012","name":"公司","tier":"tier1","moat_type":"技术垄断","moat_level":"absolute_monopoly","catalyst":"催化"}}],
"investment_thesis":"逻辑","top_pick":{{"code":"...","name":"...","reason":"理由"}}}}
all_assets >= 5家, moat_level: absolute_monopoly/strong/medium/weak"""
        try:
            text = await asyncio.wait_for(self.provider.chat_flash(prompt, max_tokens=4096), timeout=60)
            result = self.parse_json(text)
            if isinstance(result, dict):
                result["agent"] = self.name
                logger.info(f"[{self.name}] Level: {level_name} — {len(result.get('all_assets',[]))} assets")
                return result
        except Exception as e:
            logger.warning(f"[{self.name}] Level analysis failed: {e}")
        return {"level_name": level_name, "error": "Analysis failed"}

    # ═══ 基类 ═══════════════════════════════

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await super().load_context(ctx)
        ctx["macro"] = await self.data_loader.load_macro()
        ctx["positions"] = await self.data_loader.load_positions()
        return ctx

    @staticmethod
    def build_prompt(ctx): return "SupplyChainHacker V5.9.1"
    @staticmethod
    async def stream(ctx): yield "streaming not implemented"


# ═══ 工具 ═════════════════════════════════════

def _j(obj, **kw):
    import json
    class _SafeEncoder(json.JSONEncoder):
        def default(self, o):
            if isinstance(o, Decimal): return float(o)
            return super().default(o)
    kw.setdefault("ensure_ascii", False)
    kw.setdefault("cls", _SafeEncoder)
    return json.dumps(obj, **kw)
