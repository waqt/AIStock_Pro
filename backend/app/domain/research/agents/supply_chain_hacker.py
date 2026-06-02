"""
SupplyChainHacker V5.11b — 供应链降维穿透
V5.11b: chokepoint_score→bottleneck_severity (定性枚举)
        sub_processes 三层抽象模型 (value_magnitude/value_owners/pricing_behavior)
        glossary 新增 bottleneck_severity/pricing_behavior/value_magnitude/value_share
输出: supply_chain_map + sub_processes + sales/expansion chain + scarcity_ranking
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
        result = await self._structure_output(industry, research_data, step2, trace=trace)

        result["agent"] = self.name
        result["industry"] = industry
        result["search_rounds"] = research_data.get("search_rounds", 0)
        if trace:
            trace.record_note("summary", f"layers={len(result.get('supply_chain_map',[]))}")
        return result

    # ═══ Phase 1: 供应链迭代深研 ═════════════════

    async def _hack_supply_chain(self, industry: str, step2: dict = None, trace=None) -> Dict:
        all_findings = []
        gaps = []
        round_num = 0
        step2 = step2 or {}

        industry_anchor = step2.get("industry_name_for_search", industry)
        if not industry_anchor: industry_anchor = industry
        
        for round_num in range(1, 4):
            if round_num == 1:
                phase = step2.get("cycle_phase", "")
                ptype = step2.get("prosperity_type", "")
                chains = [[
                    f"{industry_anchor} 产业链 核心瓶颈 产能 技术壁垒 龙头公司 市占率",
                    f"{industry_anchor} 产业链 瓶颈 龙头 产能 2026",
                    f"{industry_anchor} supply chain bottleneck key players",
                ]]
                if phase == "bottleneck_formation":
                    chains = [[
                        f"{industry_anchor} 产能 交期 设备约束 瓶颈环节 扩产周期",
                        f"{industry_anchor} 产能缺口 交期 供应链瓶颈 2026",
                        f"{industry_anchor} capacity lead time bottleneck supply chain",
                    ]]
                elif ptype == "supply_shock":
                    chains = [[
                        f"{industry_anchor} 供给约束 资源稀缺 设备禁令 认证壁垒",
                        f"{industry_anchor} 供给受限 原材料 设备 国产替代 2026",
                        f"{industry_anchor} supply constraint material equipment restriction",
                    ]]
            elif gaps:
                chains = [[
                    f"{industry_anchor} {' '.join(gaps[:3])}",
                    f"{industry_anchor} {' '.join(gaps[:2])}",
                ]]
            else:
                break

            search_data = await self._search_adaptive(chains, num=5, trace=trace)
            if not search_data[0]["results"] and round_num > 1:
                break

            prompt = f"""你是 {industry} 行业的产业链供给侧研究员。分析该行业实体产业链的瓶颈结构和国产替代机会。

## ★ 重要约束
- 产业链分析必须聚焦实体供给侧结构 (原材料→零部件→设备→组装→终端应用)
- 禁止偏向软件/SaaS/咨询/管理类公司 — 除非该行业本身是软件行业
- 禁止输出具体股票代码或公司名 — 只描述产业环节和角色
- 每条发现必须有搜索来源引用

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
                text = await self.provider.chat_pro(prompt, max_tokens=2048, timeout=120)
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

        industry_anchor = step2.get("industry_name_for_search", industry)
        if not industry_anchor: industry_anchor = industry

        fresh_data = await self._search_adaptive([[
            f"{industry_anchor} 供应链 最新 瓶颈 产能 缺口 2026",
            f"{industry_anchor} 产业链 瓶颈 最新 2026",
        ]], num=5, trace=trace)

        prompt = f"""你是买方首席产业研究员。输出 {industry_anchor} 行业的实体产业链深度穿透 JSON。

## ★ 重要约束
- 产业链拆解的最终目标是识别“全球产业链中的绝对话语权节点”和“A股可映射的卡脖子环节”。
- 产业链必须聚焦实体供给侧 (原材料→零部件→设备→组装→终端), 不要分析软件/SaaS/咨询公司。
- 如果某个瓶颈环节的核心受益方全部在海外上市（如台积电、ASML），你必须追问“这个全球瓶颈如何传导到 A 股标的？”，并找到：
  1. 国产替代受益方
  2. 被瓶颈挤压的上游国产供应商
  3. 瓶颈缓解后最先受益的国内下游
- 绝对禁止输出具体股票代码！只输出“价值节点特征标签” (value_node_tags)，供后续搜索股票使用（如“取向硅钢龙头”、“先进封装设备国产替代”、“特斯拉人形机器人丝杠供应商”）。

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

      "chokepoint_checklist": {{
        "is_sole_source": true,
        "customer_switch_cost_months": 18,
        "cost_share_of_downstream": 0.05,
        "price_hike_pass_through": 0.95,
        "capacity_util_rate": 0.95,
        "order_backlog_months": 24,
        "regulatory_moat": true,
        "bottleneck_severity": "very_high"
      }},

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
        "margin_data_source": "LLM估计",
        "pricing_power_narrative": "定价权描述"
      }},
      "value_capture": {{
        "market_attention": "very_high", "attention_quality": "profit_real",
        "gap_narrative": "关注度 vs 利润捕获",
        "who_captures_value": ["受益方"]
      }},
      "competitive_landscape": {{
        "structure": "oligopoly_CR3_above_70",
        "global_leaders": ["海外龙头"], "china_substitution_rate": "below_5pct"
      }},
      "value_node_tags": ["标签1", "标签2"],
      "a_stock_transmission": "全球瓶颈传导到 A 股标的逻辑",

      // ═══ V5.11b: 子工艺拆解 (可选, 仅 L1-L2 severity≥high 节点, max 5) ═══
      "sub_processes": [
        {{
          "name": "子工艺名如: TSV通孔制造",
          "confidence": "high",

          "supply_rigidity": {{
            "severity": "extreme/..." , "root_cause": "equipment_constraint/...",
            "expand_cycle": "over_24m/...", "substitutability": "none_short_term/...",
            "concentration": "monopoly_single_supplier/..."
          }},

          "value_magnitude": {{
            "order_of_magnitude": "1B_10B",
            "unit_economics_hint": "估算依据, 如: TSV设备市场约25亿美元, 占HBM成本约15%"
          }},

          "value_owners": [
            {{"name":"公司名","public_market":"NASDAQ:AMAT","value_share":"dominant","investable_in_a_share":false,"investment_logic":"为什么捕获此环节价值"}}
          ],

          "profit_pool": {{
            "share_of_industry_profit": "significant_15_30pct",
            "margin_level": "very_high_above_40pct",
            "margin_estimated": true,
            "margin_data_source": "LLM估计"
          }},

          "competitive_landscape": {{
            "structure": "oligopoly_CR3_above_70",
            "pricing_behavior": "collusive_oligopoly",
            "global_leaders": ["龙头1","龙头2"],
            "china_substitution_rate": "20_50pct"
          }},

          "a_stock_mapping": [
            {{"code":"688012","name":"中微公司","investment_logic":"TSV深硅刻蚀设备国产替代龙头"}}
          ],
          "value_node_tags": ["子工艺标签"],
          "evidence": [
            {{"fact":"关键事实","from":"search[1.3]·来源","quality":{{"level":"high","source_type":"industry_data"}}}}
          ]
        }}
      ],

      "evidence": [
        {{"fact":"关键事实1","from":"search[1.3]·来源","quality":{{"level":"high","source_type":"industry_data"}}}},
        {{"fact":"关键事实2","from":"search[2.1]·来源","quality":{{"level":"medium","source_type":"sell_side_report"}}}}
      ]
    }}
  ],
  "sales_chain": [{{"segment":"受益环节","value_node_tags":["受益标签"],"reason":"理由","lead_months":"1-3"}}],
  "expansion_chain": [{{"segment":"滞后环节","value_node_tags":["滞后标签"],"reason":"理由","lag_months":"6-12"}}],
  "chain_timeline": {{"sales_lead_months":"1-3","expansion_lag_months":"6-12","rotation_strategy":"策略"}},
  "scarcity_ranking": [{{"rank":1,"segment":"稀缺环节","rigidity_narrative":"刚性","value_node_tags":["稀缺标签"]}}],
  "catalysts": [{{"type":"capacity","catalyst":"事件","expected_date":"时间","watch_signal":"指标","affected_segment":"环节"}}],

  // ═══ V5.16: 供 Step 6 使用的资产搜索指引 ═══
  "asset_search_queries": [
    {{
      "query": "A股 HBM先进封装 设备 材料 上市公司 龙头",
      "source": "step3_L2_HBM先进封装",
      "priority": "high",
      "rationale": "HBM封装国产化率<5%, 需找到已进入供应链的设备/材料商",
      "mapping_type": "direct"
    }}
  ]
}}
"""
        # 注入枚举约束 glossary
        from app.framework.pipeline.glossary import step3_glossary
        prompt += step3_glossary()

        prompt += """
## 规则
- evidence 数组在节点级别 (每节点 2-4 条), 子字段不各自带 evidence
- from 格式: "search[轮次.序号]·来源简称", 禁止自创前缀
- supply_chain_map >= L1-L3, sales/expansion chain >= 各 2 条
- chokepoint_checklist.customer_switch_cost_months/cost_share_of_downstream 等基于搜索数据估算
- chokepoint_checklist.bottleneck_severity 从 glossary 枚举值中选, 不能从 supply_rigidity.severity 自动映射
- self_media/ai_summary 仅参考, 不得单独支撑关键判断
- ★ margin_estimated=true 表示 margin_level/share_of_profit 为 LLM 估计
- ★ 3轮搜索仍无有效结果时: 不丢弃数据, 输出 confidence=insufficient_data + confidence_note 说明缺口
- ★ expand_cycle 三档: under_12m / 12_24m / over_24m (与 Step 4/5 时间枚举对齐)

## 子工艺拆解规则 (V5.11b)
- sub_processes 仅对 L1-L2 且 supply_rigidity.severity 为 extreme 或 high 的节点展开, 非瓶颈节点不得展开
- 单个节点的 sub_processes 最多 5 个, 从物理工艺过程分解 (一个物理步骤一个子工艺), 不要按公司分解
- 每个子工艺必须标注 value_magnitude.order_of_magnitude (无搜索结果时标注 unknown, 不猜测)
- 每个子工艺须列出至少 1 个 value_owners[].investable_in_a_share 标记是否可直接在 A 股投资
- 每个子工艺必须标注 pricing_behavior, 且不能与 competitive_landscape.structure 自动关联 — 基于搜索中的实际定价行为独立推断
- 每个子工艺的 evidence 至少 1 条支撑 rigidity/value_magnitude 判断
- 零 A 股映射的子工艺标注 a_stock_mapping: [] (不要省略)
- pricing_behavior 定义见 glossary, 特别注意: collusive_oligopoly 和 capacity_war 同属 oligopoly 结构但投资含义完全不同

## asset_search_queries 生成规则 (V5.16)
- 每个 supply_chain_map 节点至少生成 1-2 条, 覆盖国产替代/设备/材料/间接参与各维度
- priority 判定: severity=extreme+国产替代率<5% → high, 其余 medium
- source 格式: "step3_L{level}_{节点名前4字}"
- ★ mapping_type 字段: "direct"=标准A股映射 / "a_share_equivalent"=海外龙头→A股间接参与映射
- 对 a_stock_mapping 有空缺的环节 (investable_in_a_share=false), 生成指引让 Step 6 搜索"间接参与"逻辑
- 对供应瓶颈明确且有 A 股映射的环节 (如中微/北方华创), 生成指引让 Step 6 验证护城河深度
- ★ 新增映射类查询规则 (瓶颈环节 global_leaders 全部海外上市且无可投 A 股标的时):
  1. 生成 mapping_type="a_share_equivalent" 的查询
  2. 查询方向覆盖: (a) 为海外龙头供货的 A 股供应商 (b) 海外龙头的 A 股竞争对手/国产替代 (c) 通过供应链间接参与的 A 股公司
  3. 示例: {"query":"A股 Tokyo Electron 供应商 合作伙伴 上市公司 2026","mapping_type":"a_share_equivalent","priority":"high","rationale":"TEL垄断涂胶显影设备, 寻找间接供应链参与者"}"""

        try:
            text = await self.provider.chat_pro(prompt, max_tokens=16000, timeout=300)
            if trace: trace.record_llm(prompt, text, model="deepseek-v4-pro")
            # ★ 修复 LLM 响应中的 mojibake 编码 (UTF-8 被当作 Latin-1 解码)
            text = self._fix_mojibake(text)
            result = self.parse_json(text)
            if isinstance(result, dict) and result.get("parse_error"):
                logger.warning(f"[{self.name}] Struct parse failed, retrying...")
                text2 = await self.provider.chat_pro(prompt, max_tokens=16000, timeout=300)
                text2 = self._fix_mojibake(text2)
                result = self.parse_json(text2)

            if isinstance(result, dict):
                result["findings_count"] = len(findings)
                # V5.11b: 标准化 — 旧 checkpoint 补 bottleneck_severity + sub_processes
                result = self._normalize_step3_output(result)
                logger.info(f"[{self.name}] Structured: {len(result.get('supply_chain_map',[]))} layers")
                return result
        except asyncio.TimeoutError:
            logger.warning(f"[{self.name}] Phase 2 timeout")
        except Exception as e:
            logger.warning(f"[{self.name}] Phase 2 failed: {e}")

        return {"raw_findings": findings, "error": "Structuring failed"}

    # ═══ V5.11b: 向后兼容标准化 ═════════════════

    @staticmethod
    def _normalize_step3_output(result: Dict) -> Dict:
        """标准化 Step 3 输出:
        - 旧 checkpoint: chokepoint_score → bottleneck_severity
        - 旧 checkpoint: 补 sub_processes: []
        - ★ V5.16: 确保 asset_search_queries 不缺位
        """
        for node in result.get("supply_chain_map", []):
            if "sub_processes" not in node:
                node["sub_processes"] = []
            cl = node.get("chokepoint_checklist", {})
            if cl and "bottleneck_severity" not in cl and "chokepoint_score" in cl:
                cl["bottleneck_severity"] = SupplyChainHacker._old_score_to_severity(cl["chokepoint_score"])

        # ★ V5.16: LLM 经常省略 asset_search_queries, 后处理兜底生成
        existing = result.get("asset_search_queries")
        if not isinstance(existing, list):
            existing = []
        if len(existing) >= len(result.get("supply_chain_map", [])):
            return result  # LLM 已生成足够数量, 无需干预

        fallback = []
        seen_queries = set()
        if existing:
            for q in existing:
                qry = q.get("query", "")
                if qry:
                    seen_queries.add(qry)
                    fallback.append(q)

        for node in result.get("supply_chain_map", []):
            node_name = node.get("name", "")
            if not node_name:
                continue
            severity = node.get("supply_rigidity", {}).get("severity", "")
            is_severe = severity in ("extreme", "very_high")

            # 检查该节点的子工艺中哪些没有 A 股映射
            sub_without_code = []
            for sp in node.get("sub_processes", []):
                has_code = any(
                    m.get("code") for m in sp.get("a_stock_mapping", [])
                )
                if not has_code:
                    sub_without_code.append(sp.get("name", ""))

            # 对每个节点至少生成 1 条通用查询
            q1 = f"A股 {node_name} 龙头企业 上市公司 2026"
            if q1 not in seen_queries:
                fallback.append({
                    "query": q1,
                    "source": f"step3_{node_name[:6]}",
                    "priority": "high" if is_severe else "medium",
                    "rationale": f"{node_name}环节供应商搜索",
                })
                seen_queries.add(q1)

            # 瓶颈严重 + 高国产替代率节点, 加 1 条国产替代查询
            if is_severe:
                q2 = f"A股 {node_name} 国产替代 设备 材料 2026"
                if q2 not in seen_queries:
                    fallback.append({
                        "query": q2,
                        "source": f"step3_{node_name[:6]}",
                        "priority": "high",
                        "rationale": f"{node_name}国产替代机会",
                    })
                    seen_queries.add(q2)

            # 有空缺子工艺 → 间接参与查询
            if sub_without_code:
                gap_names = " ".join(sub_without_code[:3])
                q3 = f"A股 {node_name} {gap_names} 供应链 间接参与 上市公司 2026"
                if q3 not in seen_queries:
                    fallback.append({
                        "query": q3,
                        "source": f"step3_{node_name[:6]}_gap",
                        "priority": "medium",
                        "rationale": f"{node_name}子工艺无直接A股映射, 搜索间接参与机会",
                    })
                    seen_queries.add(q3)

            # ★ V5.16: 海外龙头主导节点 → mapping_type=a_share_equivalent 映射查询
            leaders = node.get("competitive_landscape", {}).get("global_leaders", [])
            subst_rate = node.get("competitive_landscape", {}).get("china_substitution_rate", "")
            is_foreign_dominated = (
                bool(leaders) and subst_rate in ("below_5pct", "5_20pct", "")
                and sub_without_code
            )
            if is_foreign_dominated:
                for leader in leaders[:2]:
                    q_supplier = f"A股 {leader} 供应商 合作伙伴 上市公司 2026"
                    if q_supplier not in seen_queries:
                        fallback.append({
                            "query": q_supplier,
                            "source": f"step3_{node_name[:6]}_map",
                            "priority": "high" if is_severe else "medium",
                            "mapping_type": "a_share_equivalent",
                            "rationale": f"{leader}是{node_name}海外龙头, 寻找为其供货的A股供应商",
                        })
                        seen_queries.add(q_supplier)
                    q_compete = f"A股 {leader} 竞争对手 国产替代 上市公司 2026"
                    if q_compete not in seen_queries:
                        fallback.append({
                            "query": q_compete,
                            "source": f"step3_{node_name[:6]}_map",
                            "priority": "high" if is_severe else "medium",
                            "mapping_type": "a_share_equivalent",
                            "rationale": f"{leader}是{node_name}海外龙头, 寻找A股竞争对手/替代方",
                        })
                        seen_queries.add(q_compete)

        result["asset_search_queries"] = fallback
        n_missing = max(0, len(result.get("supply_chain_map", [])) - (len(existing) if existing else 0))
        if n_missing > 0:
            logger.info(f"[SupplyChainHacker] asset_search_queries fallback: generated {len(fallback)} queries "
                        f"(LLM had {len(existing) if existing else 0}, {n_missing} nodes missing)")
        return result

    @staticmethod
    def _fix_mojibake(text: str) -> str:
        """修复 UTF-8 字节被当作 Latin-1 解码导致的乱码 (mojibake)"""
        if not text:
            return text
        try:
            fixed = text.encode('latin-1').decode('utf-8')
            # 如果修复后的前 100 个字符中有 CJK 汉字, 说明是乱码后修复成功
            if any('一' <= c <= '鿿' for c in fixed[:100]):
                logger.info(f"[SupplyChainHacker] Fixed mojibake: {len(text)}→{len(fixed)} chars")
                return fixed
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        return text

    @staticmethod
    def _old_score_to_severity(score: int) -> str:
        """chokepoint_score (0-100) → bottleneck_severity 枚举"""
        if score >= 80: return "very_high"
        if score >= 60: return "high"
        if score >= 40: return "moderate"
        if score >= 20: return "low"
        return "none"

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
            text = await self.provider.chat_flash(prompt, max_tokens=4096, timeout=120)
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
    def build_prompt(ctx): return "SupplyChainHacker V5.11b"
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
