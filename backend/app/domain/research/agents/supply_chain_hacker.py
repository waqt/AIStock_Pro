"""
SupplyChainHacker V5.7 — 供应链降维穿透 + 第二层思维
单一职责: 顺景气赛道向下递归 L1-L4, 定位技术卡脖子/独占资源/产能真空期
第二层思维: 产能挤出效应 + 投入产出关联 + 副产品效应
输出: supply_chain_map + temporal + core_stocks + second_order_effects
"""
import asyncio
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger


class SupplyChainHacker(ResearchAgent):
    """供应链黑客 V5.7 — 产业瓶颈降维穿透 + 第二层思维"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "SupplyChainHacker"

    # ═══ 主入口 ═══════════════════════════════════

    async def analyze(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await self.load_context(ctx)
        industry = ctx.get("industry", "未指定")

        if not self.provider:
            return {"agent": self.name, "error": "No AI provider", "data": ctx}

        logger.info(f"[{self.name}] Hacking supply chain: {industry}")

        # Phase 1: 供应链专项迭代深研
        research_data = await self._hack_supply_chain(industry)

        # Phase 1.5: 从搜索文本中提取股票代码 (不依赖复杂JSON解析)
        core_stocks = await self._extract_stocks_simple(industry, research_data)

        # Phase 1.8: 第二层思维 — 产能挤出/投入产出/副产品效应
        second_order = await self._second_level_analysis(industry, research_data)

        # Phase 2: 结构化输出 (supply_chain_map + temporal)
        result = await self._structure_output(industry, research_data)

        # 确保 core_stocks 一定有值 (Phase 1.5 或 Phase 2, 优先Phase 2)
        if not result.get("core_stocks") and core_stocks:
            result["core_stocks"] = core_stocks
        if not result.get("core_stocks"):
            result["core_stocks"] = core_stocks  # Phase 1.5 fallback

        result["agent"] = self.name
        result["industry"] = industry
        result["search_rounds"] = research_data.get("search_rounds", 0)
        result["second_order_effects"] = second_order
        return result

    # ═══ Phase 1: 供应链迭代深研 ═════════════════

    async def _hack_supply_chain(self, industry: str) -> Dict:
        """3 轮迭代: 搜索→瓶颈定位→自检→补搜 (供应链专项)"""
        all_findings = []
        gaps = []
        round_num = 1

        for round_num in range(1, 4):
            # 供应链专项搜索词 (区别于 V3.0 的泛财务搜索)
            if round_num == 1:
                query = f"{industry} 产业链 核心瓶颈 产能 技术壁垒 龙头公司 市占率"
            elif gaps:
                query = f"{industry} {' '.join(gaps[:3])}"
            else:
                break

            search_results = []
            for r in await self.data_loader.search_web(query, num=5):
                search_results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("snippet", "")[:200],
                })

            if not search_results and round_num > 1:
                break

            # LLM 分析 + 供应链自检
            prompt = f"""你是全球半导体/制造业供应链研究员。分析 {industry} 产业链的瓶颈结构和国产替代机会。

## 本轮搜索结果
{_j(search_results)}

## 前几轮发现
{_j(all_findings)}

## 任务
1. 基于搜索结果提取关键供应链信息
2. **供应链自检**: 当前分析够不够深入?
   - 缺产能数据 (晶圆产能/封装产能/材料产能)?
   - 缺设备交期 (光刻/刻蚀/检测设备)?
   - 缺国产化率 (某环节国产占比<20%)?
   - 缺技术代际差 (与国际领先差几代)?
3. 如果缺数据, 列出下一轮搜索关键词 (最多 3 个)

请输出纯 JSON:
{{"findings": [{{"key": "瓶颈发现", "detail": "具体细节"}}],
  "gaps": ["缺口关键词1", "缺口关键词2"],
  "need_more_search": true/false}}"""

            try:
                text = await asyncio.wait_for(
                    self.provider.chat_pro(prompt, max_tokens=2048), timeout=45)
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

    # ═══ Phase 1.5: 简单股票提取 ═════════════════

    async def _extract_stocks_simple(self, industry: str, research: Dict) -> list:
        """从Phase 1研究发现中提取A股标的 (简单prompt, 不依赖复杂JSON)"""
        findings = research.get("findings", [])
        if not findings:
            return []
        summary = "; ".join(
            f.get("key","") + ":" + f.get("detail","")[:100]
            for f in findings[:10] if isinstance(f, dict))
        if not summary.strip():
            return []

        # 先尝试纯正则提取 (不依赖LLM)
        import re
        codes_raw = list(set(re.findall(r'\b(60[0-4]\d{3}|688\d{3}|00[0-3]\d{3}|30[0-2]\d{3})\b', summary)))
        if len(codes_raw) >= 3:
            logger.info(f"[{self.name}] Regex extracted {len(codes_raw)} codes: {codes_raw[:8]}")
            return [{"code": c, "name": c, "segment": "待确认"} for c in codes_raw[:8]]

        prompt = f"列出{industry}产业链相关的5-8只A股标的(6位代码+名称)。输出纯JSON数组: [{{\"code\":\"000001\",\"name\":\"平安银行\"}}]。基于: {summary[:3000]}"
        try:
            text = await asyncio.wait_for(
                self.provider.chat_flash(prompt, max_tokens=4096), timeout=30)
            result = self.parse_json(text)
            if isinstance(result, list):
                return result
            if isinstance(result, dict):
                for v in result.values():
                    if isinstance(v, list) and len(v) > 0:
                        return v
            # 解析失败: 正则兜底
            fallback = list(set(re.findall(r'\b(60[0-4]\d{3}|688\d{3}|00[0-3]\d{3}|30[0-2]\d{3})\b', text)))
            if fallback:
                return [{"code": c, "name": c, "segment": "待确认"} for c in fallback[:8]]
            return []
        except Exception as e:
            logger.warning(f"[{self.name}] Simple stock extract failed: {e}")
            return []

    # ═══ Phase 1.8: 第二层思维 ═════════════════════

    async def _second_level_analysis(self, industry: str, research: Dict) -> Dict:
        """基于 Phase 1 瓶颈发现, 反向推演:
        1. 产能挤出效应 — 这个行业的扩张会挤占谁的资源? 谁意外受益?
        2. 投入产出关联 — 上游供应商和下游消费者如何联动?
        3. 副产品效应 — 主产品生产的副产品对下游的影响
        """
        findings = research.get("findings", [])
        if not findings:
            return {}

        logger.info(f"[{self.name}] Phase 1.8: Second-level thinking for {industry}")

        # 第二轮搜索: 第二层思维专项
        second_queries = [
            f"{industry} 产能扩张 挤占 原材料 供应紧张 溢出效应",
            f"{industry} 供应链 上游 原料 副产品 关联产业 影响",
            f"{industry} 投入产出 关联行业 谁受益 谁受损",
        ]

        so_results = []
        for q in second_queries[:2]:  # 限制2轮
            items = []
            for r in await self.data_loader.search_web(q, num=3):
                items.append({
                    "title": r.get("title", ""),
                    "snippet": r.get("snippet", "")[:200],
                })
            so_results.append({"query": q, "results": items})

        # 摘要用于 LLM
        search_summary = "; ".join(
            r.get("title","")+": "+r.get("snippet","")[:100]
            for sq in so_results for r in sq["results"]
        )[:3000]

        findings_summary = "\n".join(
            f"- {f.get('key','?')}: {f.get('detail','')[:150]}"
            for f in findings[:6] if isinstance(f, dict)
        )[:2000]

        prompt = f"""你是产业经济学和供应链专家。运用"第二层思维", 分析 {industry} 产业扩张的深层影响。

## 产业瓶颈发现
{findings_summary}

## 最新搜索
{search_summary}

## 三个维度分析

### 1. 产能挤出效应 (Capacity Crowding-out)
- 这个行业的产能扩张会挤占哪些原材料的供给?
- 谁是被挤出者? (未能获得资源的弱势行业)
- 谁是意外受益者? (被动获得供给缺口的替代供应商)

### 2. 投入产出关联 (Input-Output Linkages)
- 这个行业的上游供应商有哪些? 哪个环节的供应商议价能力最强?
- 下游哪些行业最依赖这个环节的产品? 如果供给不足, 下游会怎样?
- 是否存在跨行业价值溢出? (一个行业的扩张带动另一个不相干的行业)

### 3. 副产品效应 (Byproduct Economics)
- 这个环节生产主产品时, 是否会产生重要的副产品?
- 主产品产量变化 (扩张/收缩) 对副产品供给和价格的影响?
- 如果主产品减产 (如地缘冲突/政策限制), 副产品价格是否会飞涨? 谁会受益?

## 输出纯 JSON
{{
  "crowding_out": [
    {{"victim_sector": "被挤占的行业", "resource": "被挤占的资源", "beneficiary": "意外受益方", "reasoning": "分析逻辑", "a_stock_codes": ["受益A股代码"]}}
  ],
  "io_linkages": [
    {{"upstream": "上游行业", "downstream": "下游行业", "multiplier": 1.8, "bottleneck_level": "瓶颈程度 HIGH/MEDIUM/LOW", "reasoning": "分析逻辑", "a_stock_codes": ["关键A股代码"]}}
  ],
  "byproduct_effects": [
    {{"main_product": "主产品", "byproduct": "副产品", "byproduct_use": "副产品用途", "supply_elasticity": "供给弹性 LOW/MEDIUM/HIGH", "impact_on": "对哪些行业的影响", "a_stock_codes": ["受影响A股代码"]}}
  ],
  "synthesis": "第二层思维综合: 哪些非共识机会最值得关注? (2-3句)"
}}

要求:
- 每个维度至少1条, 最多3条分析
- 尽可能列出相关A股代码 (6位真实代码)
- 如果某个维度没有明显效应, 标注"暂无显著发现"并解释原因
- 聚焦于非共识、反直觉的洞察"""

        try:
            text = await asyncio.wait_for(
                self.provider.chat_pro(prompt, max_tokens=4096), timeout=60)
            result = self.parse_json(text)
            if isinstance(result, dict):
                for dim in ["crowding_out", "io_linkages", "byproduct_effects"]:
                    n = len(result.get(dim, []))
                    logger.info(f"[{self.name}] Second-order {dim}: {n} items")
                return result
        except asyncio.TimeoutError:
            logger.warning(f"[{self.name}] Second-level analysis timeout")
        except Exception as e:
            logger.warning(f"[{self.name}] Second-level analysis failed: {e}")

        return {"crowding_out": [], "io_linkages": [], "byproduct_effects": [],
                "synthesis": "第二层思维分析暂不可用"}

    # ═══ Phase 2: 结构化输出 ═════════════════════

    async def _structure_output(self, industry: str, research: Dict) -> Dict:
        """将研究发现转化为 L1-L4 瓶颈图谱 + 核心标的 + 时间预测"""
        findings = research.get("findings", [])

        # 再搜一轮确保新鲜度
        fresh = []
        for r in await self.data_loader.search_web(
            f"{industry} 供应链 最新 瓶颈 产能 缺口 2026", num=5
        ):
            fresh.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("snippet", "")[:200],
            })

        prompt = f"""你是买方首席产业研究员。输出 {industry} 产业深度穿透 JSON。

## 研究发现 ({len(findings)} 条)
{_j(findings[:10], ensure_ascii=False)}

## 输出纯 JSON (不要 markdown, 不要注释):
{{
  "core_stocks": [
    {{"code": "688012", "name": "中微公司", "segment": "刻蚀设备", "role": "龙头", "moat": "技术垄断"}}
  ],
  "supply_chain_map": [
    {{"level": 1, "name": "瓶颈环节", "bottleneck": "卡脖子原因", "assets": [{{"code":"000001","name":"公司","role":"角色"}}]}}
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
    "rotation_strategy": "先配销售链路标的, 3-6个月后转配扩产链路标的"
  }}
}}

**要求**:
- core_stocks 至少列出 5 只 A 股相关标的, 股票代码必须是真实存在的 6 位数字
- sales_chain: 识别景气度最先传导的环节 (直接承接订单爆发), 列出受益公司和传导周期
- expansion_chain: 识别滞后受益的环节 (上游扩产→设备/材料需求), 列出受益公司和滞后期
- chain_timeline: 给出两条链路的时序关系, 以及轮动策略建议
- 如果无法确定代码, 写 "待确认", 不要编造代码
- supply_chain_map 每层至少 2 家公司
- JSON 不要换行, 但可以正常使用逗号分隔"""

        try:
            text = await asyncio.wait_for(
                self.provider.chat_pro(prompt, max_tokens=8192), timeout=120)
            result = self.parse_json(text)
            # 解析失败时重试一次
            if isinstance(result, dict) and result.get("parse_error"):
                logger.warning(f"[{self.name}] First struct parse failed, retrying...")
                retry_prompt = f"列出 {industry} 产业链核心A股标的, 输出纯JSON: {{\"core_stocks\":[{{\"code\":\"000001\",\"name\":\"公司\",\"segment\":\"环节\"}}]}}。基于: {_j(findings[:8], ensure_ascii=False)}"
                text2 = await asyncio.wait_for(
                    self.provider.chat_pro(retry_prompt, max_tokens=2048), timeout=60)
                result = self.parse_json(text2)

            if isinstance(result, dict):
                result["findings_count"] = len(findings)
                logger.info(
                    f"[{self.name}] Structured: "
                    f"{len(result.get('supply_chain_map', []))} layers, "
                    f"{len(result.get('core_stocks', []))} stocks, "
                    f"sales_chain={len(result.get('sales_chain', []))}, "
                    f"expansion_chain={len(result.get('expansion_chain', []))}"
                )
                return result
        except asyncio.TimeoutError:
            logger.warning(f"[{self.name}] Phase 2 timeout")
        except Exception as e:
            logger.warning(f"[{self.name}] Phase 2 failed: {e}")

        # 第三次尝试: 极简 prompt
        try:
            retry3 = f"列出{industry}产业链5只A股核心标的, 只输出JSON: {{\"core_stocks\":[{{\"code\":\"000001\",\"name\":\"平安银行\"}}]}}"
            text3 = await asyncio.wait_for(
                self.provider.chat_flash(retry3, max_tokens=1024), timeout=30)
            result = self.parse_json(text3)
            if isinstance(result, dict) and result.get("core_stocks"):
                return result
        except Exception:
            pass

        # 从原始发现中提取股票代码
        import re
        raw_text = str(findings)
        codes = list(set(re.findall(r'\b(\d{6})\b', raw_text)))[:10]
        if codes:
            return {"core_stocks": [{"code": c, "name": c, "segment": "待确认"} for c in codes]}

        return {"raw_findings": findings, "error": "Structuring failed"}

    # ═══ 层级独立深钻 ══════════════════════════

    async def analyze_level(self, industry: str, level_name: str,
                            level_info: Dict = None) -> Dict:
        """对供应链的**单一层级**做独立深度分析 — 找出该层所有高价值资产"""
        logger.info(f"[{self.name}] Deep-diving level: {level_name} ({industry})")

        # 针对该层搜索
        search_results = []
        query = f"{industry} {level_name} 产业链 龙头企业 市占率 国产替代 产能 技术壁垒"
        for r in await self.data_loader.search_web(query, num=6):
            search_results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("snippet", "")[:250],
            })

        prompt = f"""你是半导体/制造业产业链专家。请对 {industry} 的 **{level_name}** 环节做独立深度穿透。

## 上下文
行业: {industry}
层级: {level_name}
已知信息: {_j(level_info) if level_info else '无'}

## 搜索结果
{_j(search_results)}

## 输出纯 JSON
{{
  "level_name": "{level_name}",
  "industry": "{industry}",
  "overview": "该环节的产业地位和技术经济特征 (2-3句)",
  "market_structure": {{
    "global_size": "全球市场规模 (亿美元/亿元)",
    "growth_rate": "年增速%",
    "concentration": "CR3/CR5 集中度%",
    "entry_barriers": "进入壁垒 (技术/资金/客户认证/规模)"
  }},
  "technology_landscape": {{
    "current_gen": "当前主流技术代际",
    "next_gen": "下一代技术方向",
    "gap_with_global_leader": "国产与国际领先的代差",
    "key_patents_holders": ["专利持有方1", "专利持有方2"]
  }},
  "all_assets": [
    {{
      "code": "688012", "name": "公司名", "exchange": "SH/SZ/HK",
      "role": "代工/设备/材料/封测/设计",
      "market_share_est": "市占率%(估)",
      "revenue_est": "该环节营收(亿元, 估)",
      "tech_level": "技术实力描述",
      "key_customers": "核心客户",
      "capacity": "产能数据 (如有)",
      "moat_type": "技术垄断/客户认证/成本优势/规模壁垒",
      "moat_score": 8,
      "catalyst": "近期催化剂"
    }}
  ],
  "investment_thesis": "该层级的核心投资逻辑 (2-3句)",
  "top_pick": {{"code": "...", "name": "...", "reason": "首选理由"}}
}}

要求:
- all_assets 必须包含**所有**能识别的高价值公司 (A股优先, 含港股, 海外龙头作为对标)
- 至少列出 5-8 家公司
- 区分 tier1(龙头)/tier2(追赶者)/tier3(新进入者)
- moat_score: 1-10, 10=绝对垄断"""

        try:
            text = await asyncio.wait_for(
                self.provider.chat_pro(prompt, max_tokens=4096), timeout=60)
            result = self.parse_json(text)
            if isinstance(result, dict):
                result["agent"] = self.name
                logger.info(f"[{self.name}] Level analysis: {level_name} — "
                            f"{len(result.get('all_assets', []))} assets found")
                return result
        except Exception as e:
            logger.warning(f"[{self.name}] Level analysis failed: {e}")

        return {"level_name": level_name, "error": "Analysis failed",
                "search_results": search_results}

    # ═══ 基类实现 ═══════════════════════════════

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await super().load_context(ctx)
        ctx["macro"] = await self.data_loader.load_macro()
        ctx["positions"] = await self.data_loader.load_positions()
        return ctx

    @staticmethod
    def build_prompt(ctx):
        return "SupplyChainHacker V4.0"

    @staticmethod
    async def stream(ctx):
        yield "streaming not implemented"


# ═══ 工具 ═════════════════════════════════════

def _j(obj, **kw):
    """JSON 序列化 (Decimal 安全)"""
    import json
    from decimal import Decimal

    class _SafeEncoder(json.JSONEncoder):
        def default(self, o):
            if isinstance(o, Decimal):
                return float(o)
            return super().default(o)

    kw.setdefault("ensure_ascii", False)
    kw.setdefault("cls", _SafeEncoder)
    return json.dumps(obj, **kw)
