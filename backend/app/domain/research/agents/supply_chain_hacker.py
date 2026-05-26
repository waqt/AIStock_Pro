"""
SupplyChainHacker V5.9 — 供应链降维穿透 (纯静态拆链)
V5.9: 移除 Phase 1.8 (→ Step 4), 专注 L1-L4 瓶颈图谱 + 证据层
输出: supply_chain_map + core_stocks + sales/expansion chain
"""
import asyncio, re
from decimal import Decimal
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger


class SupplyChainHacker(ResearchAgent):
    """供应链黑客 V5.8 — 产业瓶颈降维穿透 + 第二层思维"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "SupplyChainHacker"

    # ═══ 搜索工具 ═══════════════════════════════

    @staticmethod
    def _clean_snippet(text: str) -> str:
        """过滤 PDF 二进制、HTML标签、不可读字符"""
        if not text: return ""
        if "%PDF" in text or "endstream" in text or "endobj" in text: return ""
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
        return text[:250]

    async def _search_adaptive(self, chains: List[List[str]], num: int = 4, trace=None) -> List[Dict]:
        """自适应搜索: 每个维度带降级 chain, 返回所有轮次的结果"""
        all_data = []
        for chain in chains:
            items = []
            used_query = chain[0]
            for q in chain:
                results = await self.data_loader.search_web(q, num=num)
                items = []
                for r in results:
                    snippet = self._clean_snippet(r.get("snippet", ""))
                    if snippet:
                        items.append({"title": r.get("title", ""), "snippet": snippet})
                if trace: trace.record_search(q, items)
                if items:
                    used_query = q
                    break
            all_data.append({"query": used_query, "results": items})
        return all_data

    # ═══ 主入口 ═══════════════════════════════

    async def analyze(self, ctx: Dict[str, Any], trace=None) -> Dict[str, Any]:
        ctx = await self.load_context(ctx)
        industry = ctx.get("industry", ctx.get("target_industry", "未指定"))

        if not self.provider:
            return {"agent": self.name, "error": "No AI provider", "data": ctx}

        # 消费 Step 2 指引
        step2 = ctx.get("step2_guidance", {})
        search_focus = step2.get("search_focus", "")
        logger.info(f"[{self.name}] Hacking: {industry} | Step2: {step2.get('cycle_phase','?')}/{step2.get('prosperity_type','?')}")

        # Phase 1: 供应链迭代深研 (自适应搜索)
        research_data = await self._hack_supply_chain(industry, step2, trace=trace)

        # Phase 1.5: 提取股票代码
        core_stocks = await self._extract_stocks_simple(industry, research_data)

        # Phase 2: 结构化输出 (新schema)
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
        """3 轮自适应迭代: 搜索→瓶颈定位→自检→补搜"""
        all_findings = []
        gaps = []
        round_num = 0
        step2 = step2 or {}

        for round_num in range(1, 4):
            if round_num == 1:
                # 首轮: 根据 Step 2 指引选择搜索聚焦
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
2. **供应链自检**: 当前分析够不够深入?
   - 缺产能数据 (晶圆产能/封装产能/材料产能)?
   - 缺设备交期 (光刻/刻蚀/检测设备)?
   - 缺国产化率 (某环节国产占比<20%)?
   - 缺技术代际差 (与国际领先差几代)?
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

    # ═══ Phase 1.5: 股票提取 (保留原有逻辑) ═══════

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

    # ═══ Phase 2: 结构化输出 (V5.8 新schema) ═══════
    # (Phase 1.8 second_order_effects 已移至 Step 4 SystemDynamicsAgent)

    async def _structure_output(self, industry: str, research: Dict, step2: dict = None, trace=None) -> Dict:
        """将研究发现转化为 L1-L4 瓶颈图谱 (定性版 schema + 结构化证据)"""
        findings = research.get("findings", [])
        step2 = step2 or {}

        # 来自 Step 2 的指引
        step2_context = ""
        if step2:
            step2_context = f"""
## 上游决策 (Step 2 看门人)
- 周期阶段: {step2.get('cycle_phase','?')} → {step2.get('cycle_meaning','')}
- 景气类型: {step2.get('prosperity_type','?')} → {step2.get('prosperity_meaning','')}
- 搜索聚焦: {step2.get('search_focus','')}
- 核心矛盾: {step2.get('core_contradiction','')}
"""

        # 补充搜索
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

## 输出纯 JSON — V5.8 定性版 schema (★ 每个结论必须附 evidence 数组)

{{
  "supply_chain_map": [
    {{
      "level": 1,
      "name": "瓶颈环节名",
      "bottleneck_narrative": "瓶颈原因简述",

      "supply_rigidity": {{
        "severity": "extreme",
        "root_cause": "equipment_constraint",
        "expand_cycle": "18_24_months",
        "substitutability": "none_short_term",
        "concentration": "monopoly_single_supplier",
        "alpha_narrative": "供给刚性→定价权→景气窗口的分析",
        "evidence": [{{"fact": "支撑供给刚性判断的具体事实", "from": "search[1.3]·来源",
          "quality": {{"level": "high", "source_type": "industry_data"}}}}]
      }},

      "profit_pool": {{
        "share_of_industry_profit": "dominant_30_50pct",
        "margin_level": "very_high_above_40pct",
        "pricing_power_narrative": "定价权描述",
        "evidence": [{{"fact": "支撑利润池判断的事实", "from": "search[1.2]·来源",
          "quality": {{"level": "medium", "source_type": "sell_side_report"}}}}]
      }},

      "value_capture": {{
        "market_attention": "very_high",
        "attention_quality": "profit_real",
        "gap_narrative": "关注度 vs 利润捕获的分析",
        "who_captures_value": ["受益方1", "受益方2"],
        "evidence": [{{"fact": "支撑价值捕获判断的事实", "from": "search[1.2]·来源",
          "quality": {{"level": "medium", "source_type": "sell_side_report"}}}}]
      }},

      "competitive_landscape": {{
        "structure": "oligopoly_CR3_above_70",
        "global_leaders": ["龙头1", "龙头2"],
        "china_substitution_rate": "below_5pct",
        "china_players": {{"tier1": [], "tier2": ["追赶者"], "tier3": ["新进入者"]}},
        "evidence": [{{"fact": "支撑竞争格局判断的事实", "from": "search[1.3]·来源",
          "quality": {{"level": "medium", "source_type": "sell_side_report"}}}}]
      }},

      "future_outlook": {{
        "next_2_3_years": "bottleneck_persists",
        "potential_relief": "缓解路径",
        "emerging_bottleneck": "可能出现的新瓶颈",
        "evidence": [{{"fact": "支撑未来展望的事实", "from": "search[3.1]·来源",
          "quality": {{"level": "medium", "source_type": "sell_side_report"}}}}]
      }},

      "assets": [
        {{"code": "688012", "name": "公司名", "role": "角色", "market_position": "tier2_challenger",
          "evidence": [{{"fact": "该公司在该环节的事实依据", "from": "search[1.3]·来源",
            "quality": {{"level": "high", "source_type": "company_filing"}}}}]}}
      ],
      "assets_note": "该环节在A股暂无直接标的时填写说明, 如'中国暂无MLCC叠层机供应商'"
    }}
  ],

  "core_stocks": [
    {{"code": "688012", "name": "中微公司", "segment": "刻蚀设备", "role": "龙头", "moat": "技术垄断"}}
  ],

  "sales_chain": [
    {{"segment": "直接受益环节", "companies": ["688XXX"], "reason": "下游订单爆发→最先感知", "lead_months": "1-3"}}
  ],

  "expansion_chain": [
    {{"segment": "滞后受益环节", "companies": ["688YYY"], "reason": "上游扩产→设备/材料滞后受益", "lag_months": "6-12"}}
  ],

  "chain_timeline": {{
    "sales_lead_months": "1-3",
    "expansion_lag_months": "6-12",
    "rotation_strategy": "轮动策略建议"
  }},

  "scarcity_ranking": [
    {{"rank": 1, "segment": "最稀缺环节", "rigidity_narrative": "刚性描述", "beneficiary_stocks": ["688012"]}}
  ]
}}

## 枚举值约束 (★ 强制)
- supply_rigidity.severity: extreme | high | moderate | low | oversupply
- supply_rigidity.root_cause: equipment_constraint | natural_resource | certification_barrier | policy_restriction | capital_scale
- supply_rigidity.expand_cycle: under_6_months | 6_12_months | 12_18_months | 18_24_months | over_24_months
- supply_rigidity.substitutability: none_short_term | partial_high_cost | partial_emerging | multiple_options
- supply_rigidity.concentration: monopoly_single_supplier | duopoly | oligopoly | fragmented
- profit_pool.share_of_industry_profit: dominant_30_50pct | significant_15_30pct | moderate_5_15pct | marginal_below_5pct
- profit_pool.margin_level: very_high_above_40pct | high_25_40pct | moderate_15_25pct | low_below_15pct
- value_capture.attention_quality: profit_real | profit_diverted | under_the_radar | deservedly_low
- competitive_landscape.china_substitution_rate: below_5pct | 5_20pct | 20_50pct | above_50pct
- future_outlook.next_2_3_years: bottleneck_persists | bottleneck_easing | bottleneck_resolved | new_bottleneck_emerging

## 证据质量标注 (★ 强制, 每条 evidence 必须带 quality)
- quality.level: high | medium | low
- quality.source_type 枚举:
  company_filing (公司财报/公告) | industry_data (海关/行业协会/产能统计) |
  official_policy (政府文件/产业规划) | sell_side_report (券商研报) |
  news_media (财经媒体) | self_media (自媒体/知乎/公众号) | ai_summary (AI摘要)

## 证据格式要求 (★ 强制)
- evidence 数组至少1条
- from 格式: "search[轮次.序号]·来源简称", 如 "search[1.3]·天风电新"
- 搜索结果编号统一用 search[1]~search[N] (Phase1发现) 或 search_supp[1]~search_supp[N] (Phase2补充搜索)
- 禁止自创编号前缀 (如 search_fresh), 否则下游无法溯源
- fact 必须是搜索文字中明确出现的具体事实, 不得编造
- 如果某项判断无搜索结果支撑, evidence 标注: {{"fact": "该维度搜索结果为空", "from": "search[X]·无结果", "quality": {{"level": "low", "source_type": "ai_summary"}}}}

## 输出要求
- core_stocks 至少 5 只, 代码必须是真实 6 位数字, 不确定写"待确认"
- sales_chain + expansion_chain 至少各 2 条
- supply_chain_map 至少 L1-L3 三个层级
- assets 空时用 assets_note 说明原因, 不要留空数组
- scarcity_ranking 按供给刚性从高到低排
- 同一公司不要出现在 china_players 的多个 tier 中
- value_capture.market_attention: very_high | high | moderate | low (新增)"""

# ═══ 工具 ═════════════════════════════════════

        try:
            text = await asyncio.wait_for(self.provider.chat_pro(prompt, max_tokens=8192), timeout=180)
            if trace: trace.record_llm(prompt, text, model="deepseek-v4-pro")
            result = self.parse_json(text)
            if isinstance(result, dict) and result.get("parse_error"):
                logger.warning(f"[{self.name}] Struct parse failed, retrying...")
                retry_prompt = f"列出 {industry} 产业链核心A股标的, 输出纯JSON: {{\"core_stocks\":[{{\"code\":\"000001\",\"name\":\"公司\",\"segment\":\"环节\"}}]}}。基于: {_j(findings[:8])}"
                text2 = await asyncio.wait_for(self.provider.chat_pro(retry_prompt, max_tokens=2048), timeout=60)
                result = self.parse_json(text2)

            if isinstance(result, dict):
                result["findings_count"] = len(findings)
                logger.info(f"[{self.name}] Structured: {len(result.get('supply_chain_map',[]))} layers, {len(result.get('core_stocks',[]))} stocks")
                return result
        except asyncio.TimeoutError:
            logger.warning(f"[{self.name}] Phase 2 timeout")
        except Exception as e:
            logger.warning(f"[{self.name}] Phase 2 failed: {e}")

        # fallback: simple extraction
        codes = list(set(re.findall(r'\b(\d{6})\b', str(findings))))[:10]
        if codes:
            return {"core_stocks": [{"code": c, "name": c, "segment": "待确认"} for c in codes]}
        return {"raw_findings": findings, "error": "Structuring failed"}

    # ═══ analyze_level (定性修正) ═════════════════

    async def analyze_level(self, industry: str, level_name: str, level_info: Dict = None) -> Dict:
        logger.info(f"[{self.name}] Deep-diving level: {level_name} ({industry})")
        search_data = await self._search_adaptive([[
            f"{industry} {level_name} 龙头企业 市占率 国产替代 产能 技术壁垒",
            f"{industry} {level_name} 产业链 龙头 国产 2026",
            f"{industry} {level_name} companies market share",
        ]], num=6)

        prompt = f"""你是产业链专家。请对 {industry} 的 **{level_name}** 环节做独立深度穿透。

已知信息: {_j(level_info) if level_info else '无'}
搜索结果: {_j(search_data)}

## 输出纯 JSON
{{
  "level_name": "{level_name}", "industry": "{industry}",
  "overview": "该环节的产业地位 (2-3句)",
  "market_structure": {{
    "global_size": "全球市场规模",
    "growth_rate": "年增速",
    "concentration": "CR3/CR5 集中度",
    "entry_barriers": "进入壁垒"
  }},
  "all_assets": [
    {{
      "code": "688012", "name": "公司名", "exchange": "SH/SZ/HK",
      "role": "角色 (代工/设备/材料/封测/设计)",
      "tier": "tier1/tier2/tier3",
      "moat_type": "技术垄断/客户认证/成本优势/规模壁垒",
      "moat_level": "absolute_monopoly/strong/medium/weak",
      "catalyst": "近期催化剂"
    }}
  ],
  "investment_thesis": "投资逻辑 (2-3句)",
  "top_pick": {{"code": "...", "name": "...", "reason": "首选理由"}}
}}
all_assets 至少 5-8 家, tier1龙头/tier2追赶者/tier3新进入者。moat_level 用定性标签(absolute_monopoly/strong/medium/weak)"""

        try:
            text = await asyncio.wait_for(self.provider.chat_pro(prompt, max_tokens=4096), timeout=90)
            result = self.parse_json(text)
            if isinstance(result, dict):
                result["agent"] = self.name
                logger.info(f"[{self.name}] Level: {level_name} — {len(result.get('all_assets',[]))} assets")
                return result
        except Exception as e:
            logger.warning(f"[{self.name}] Level analysis failed: {e}")
        return {"level_name": level_name, "error": "Analysis failed"}

    # ═══ 基类实现 ═══════════════════════════════

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await super().load_context(ctx)
        ctx["macro"] = await self.data_loader.load_macro()
        ctx["positions"] = await self.data_loader.load_positions()
        return ctx

    @staticmethod
    def build_prompt(ctx): return "SupplyChainHacker V5.8"

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
