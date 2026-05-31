"""
CrossIndustryLinkageAgent V1.0 — Step 5: 跨产业关联分析
定位: 发现段的终点。寻找被主流分析遗漏的跨产业意外受益方和受损方。
区别于 Step 4: Step 4 推演同一产业链内部的变形，Step 5 搜索与主供应链共享资源/设备/工艺的相邻产业。
V1.0: 3轮×N节点搜索 + 5种推演方法 + Step3/4反向校验
"""
import asyncio, re
from decimal import Decimal
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger


class CrossIndustryLinkageAgent(ResearchAgent):
    """跨产业关联分析 V1.0 — 共享资源/设备/工艺的相邻产业"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "CrossIndustryLinkageAgent"

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

    # ═══ 瓶颈节点提取 ═══════════════════════════════

    @staticmethod
    def _extract_bottleneck_nodes(chain_map: List[Dict]) -> List[Dict]:
        """从 supply_chain_map 提取 severity=extreme/high 的瓶颈节点"""
        nodes = []
        for node in chain_map:
            sr = node.get("supply_rigidity", {})
            severity = sr.get("severity", "")
            if severity in ("extreme", "high"):
                nodes.append({
                    "name": node.get("name", "unknown"),
                    "level": node.get("level", "?"),
                    "severity": severity,
                    "root_cause": sr.get("root_cause", ""),
                    "bottleneck_narrative": node.get("bottleneck_narrative", ""),
                    "profit_pool": node.get("profit_pool", {}),
                })
        return nodes

    # ═══ 主入口 ═══════════════════════════════

    async def analyze(self, ctx: Dict[str, Any] = None, trace=None) -> Dict[str, Any]:
        ctx = await self.load_context(ctx or {})
        if not self.provider:
            return {"agent": self.name, "error": "No AI provider"}

        industry = ctx.get("industry", "未指定")
        chain_map = ctx.get("supply_chain_map", [])
        resource_crowding = ctx.get("resource_crowding", [])
        bottleneck_migration = ctx.get("bottleneck_migration", {})

        # 提取瓶颈节点
        bn_nodes = self._extract_bottleneck_nodes(chain_map)
        logger.info(f"[{self.name}] Cross-industry: {industry} ({len(bn_nodes)} bottleneck nodes, {len(resource_crowding)} crowding)")

        if not bn_nodes and not resource_crowding:
            return {"agent": self.name, "error": "No bottleneck nodes or crowding data",
                    "cross_industry_linkages": [], "confidence": "insufficient_data",
                    "confidence_note": "Step 3+4 未提供足够的瓶颈/挤占数据"}

        # 对每个瓶颈节点执行 3 轮搜索
        all_search_data = []
        for node in bn_nodes[:3]:  # 最多 3 个瓶颈节点
            node_name = node["name"]
            # 从 bottleneck_narrative 提取稀缺资源/设备名
            narrative = node.get("bottleneck_narrative", node_name)

            chains = [
                # Round 1: 共享约束 — 该稀缺资源/设备还用于哪些行业
                [f"{narrative} 还用于 哪些行业 下游 应用 领域",
                 f"{node_name} 应用 领域 下游 行业",
                 f"{node_name} industry application downstream"],
                # Round 2: 挤占/受益 — 产能挤出效应
                [f"{node_name} 产能 挤占 影响 涨价 替代 受益",
                 f"{narrative} 供应紧张 受益 标的 营收占比",
                 f"{node_name} crowding out beneficiary 2026"],
                # Round 3: 跨产业溢出
                [f"{node_name} 涨价 影响 下游 产业链 传导",
                 f"{narrative} 国产替代 受益 业绩弹性 2026",
                 f"{node_name} supply squeeze spillover cross industry"],
            ]
            node_data = await self._search_adaptive(chains, num=4, trace=trace)
            all_search_data.append({"node": node_name, "chains": node_data})

        # 如果 Step 4 有 resource_crowding, 加一轮挤占方向搜索
        if resource_crowding:
            rc_names = [r.get("resource", "") for r in resource_crowding[:2] if r.get("resource")]
            if rc_names:
                rc_chains = [
                    [f"{' '.join(rc_names)} 产能 挤占 受益 受损 行业 2026",
                     f"{rc_names[0]} 供应紧张 受益 行业",
                     f"{' '.join(rc_names)} crowding beneficiary sector"],
                ]
                rc_data = await self._search_adaptive(rc_chains, num=4, trace=trace)
                all_search_data.append({"node": "resource_crowding", "chains": rc_data})

        # LLM 推演
        prompt = self._build_prompt(industry, bn_nodes, resource_crowding, bottleneck_migration, all_search_data)

        try:
            text = await self.provider.chat_pro(prompt, max_tokens=6144, timeout=300)
            if trace: trace.record_llm(prompt, text, model="deepseek-v4-pro")
            result = self.parse_json(text)
            if isinstance(result, dict):
                n_linkages = len(result.get("cross_industry_linkages", []))
                confidence = result.get("confidence", "?")
                sanity = result.get("step3_step4_sanity_check", {})
                n_questioned = len(sanity.get("questioned", []))
                logger.info(f"[{self.name}] Done: confidence={confidence}, sanity={n_questioned}, linkages={n_linkages}")
                if trace:
                    trace.record_note("summary", f"confidence={confidence}, linkages={n_linkages}, sanity_checks={n_questioned}")
                return result
        except asyncio.TimeoutError:
            logger.warning(f"[{self.name}] Timeout: {industry}")
        except Exception as e:
            logger.warning(f"[{self.name}] Failed: {e}")

        return {"agent": self.name, "error": "Analysis failed", "cross_industry_linkages": []}

    # ═══ Prompt 构建 ═══════════════════════════════

    def _build_prompt(self, industry, bn_nodes, resource_crowding, bottleneck_migration, search_data) -> str:
        bn_summary = ""
        for n in bn_nodes:
            pp = n.get("profit_pool", {})
            bn_summary += f"- L{n.get('level','?')} {n.get('name','?')}: severity={n.get('severity','?')}, root_cause={n.get('root_cause','?')} | margin_estimated={pp.get('margin_estimated','?')}\n"

        crowding_summary = "\n".join(
            f"- {r.get('resource','?')}: squeezed_from={r.get('squeezed_from','?')}, hidden_beneficiary={r.get('hidden_beneficiary','?')}, visibility={r.get('visibility','?')}"
            for r in (resource_crowding or [])[:3])

        migration_str = ""
        if isinstance(bottleneck_migration, dict):
            migration_str = f"current={bottleneck_migration.get('current','?')} → next_12m={bottleneck_migration.get('next_12m','?')} → next_24m={bottleneck_migration.get('next_24m','?')}"

        s_summary = ""
        for sd in search_data:
            s_summary += f"\n### Node: {sd['node']}\n"
            for chain in sd["chains"]:
                s_summary += f"\n#### {chain['query']}\n"
                for r in chain["results"][:3]:
                    s_summary += f"  - {r['title']}: {r['snippet'][:180]}\n"

        return f"""你是跨产业关联分析师。Step 3 拆解了产业链结构, Step 4 推演了产业内部的变形, 你的任务是搜索**跨产业**的意外波及。

核心方法: 一个产业的瓶颈节点(稀缺资源/核心设备/关键技术)会影响共享这些要素的**其他产业**。找到这些关联。

## ★ 强制: Step 3+4 反向校验

先审视 Step 3 的瓶颈节点和 Step 4 的推演:
1. 哪个瓶颈节点的 severity 可能被高估? (margin_estimated=true 表示财务数据是 LLM 估计)
2. Step 4 的 resource_crowding 是否遗漏了重要方向?
3. 哪个 bottleneck_migration 的 time horizon 可能不对?

→ 找出 1-2 个"可能不准确"的判断, 在输出的 step3_step4_sanity_check 中写明。
→ 至少找出 1 个。基于质疑调整后续联想的前提。

## 五种跨产业推演方法 (★ 每种都尝试, 但只输出有搜索证据支撑的)

1. **产能挤出 (Crowding-out)**: 瓶颈环节的高利润产品挤占谁的产能/资源?
   例: HBM消耗3x晶圆→DDR供给收缩→二线DRAM厂受益。传导: immediate (~3月)

2. **副产品经济学 (Byproduct Economics)**: 主产品供需剧变→哪些副产品受影响?
   例: 炼油减产→硫磺断供→磷肥飞涨→化肥企业受益。传导: immediate~medium_term

3. **投入产出溢出 (Input-Output Spillover)**: 扩产→上游设备/材料需求溢出到其他行业?
   例: CoWoS扩产→ABF基板紧缺→还有谁需要ABF? 传导: medium_term~long_term

4. **牛鞭效应 (Bullwhip Effect)**: 终端需求小幅波动→上游过度放大?
   例: 手机-5%→芯片砍单-30%→晶圆厂利用率骤降。传导: immediate

5. **蛛网模型 (Cobweb Theorem)**: 高利润吸引的CAPEX→τ时间后供给洪峰?
   例: MLCC扩产τ=18月→2027H2供给洪峰→提前预警。传导: long_term

## Step 3 瓶颈节点
行业: {industry}
{bn_summary}

## Step 4 推演结果
资源挤占:
{crowding_summary if crowding_summary else '(无)'}
瓶颈迁移: {migration_str}

## 跨产业搜索
{s_summary}

## 输出纯 JSON (全定性, 不做数值评分)

{{
  "confidence": "high/medium/low/insufficient_data",
  "confidence_note": "数据覆盖情况, 不确定性来源",

  "step3_step4_sanity_check": {{
    "questioned": [
      {{"source": "Step3/Step4", "claim": "具体判断", "doubt": "为什么可能不准确"}}
    ],
    "adjustment": "基于质疑调整了哪些联想的前提"
  }},

  "cross_industry_linkages": [
    {{
      "source_node": "上游瓶颈节点名 (如: 高纯钛酸钡 MLCC核心原料)",
      "linkage_type": "shared_constraint",
      "affected_sector": "受波及的细分行业 (自由文本, 不要编申万分类)",
      "sector_description": "行业通俗描述 (如: 做压电陶瓷元件的, 下游半导体设备)",
      "impact_direction": "positive/negative",
      "impact_narrative": "传导逻辑简述 (如: MLCC扩产消耗钛酸钡→压电陶瓷原料收缩→成本上升)",
      "target_profile": "该类企业的核心业务特征 (主营/规模/毛利/关键原料占比), 供下游圈定股票, 禁止写股票代码",
      "linkage_method": "crowding_out/byproduct_economics/io_spillover/bullwhip_amplification/cobweb_oversupply/shared_constraint/shared_equipment",
      "time_to_impact": "immediate/medium_term/long_term",
      "impact_materiality": "high/medium/low",
      "visibility": "very_low/low/moderate — 如实判断, 不为Alpha压低",
      "evidence": [
        {{"fact":"事实","from":"search[X.Y]·来源","quality":{{"level":"high","source_type":"industry_data"}},"evidence_type":"forward_looking_rumor"}}
      ]
    }}
  ],

  "discovery_summary": "一句话总结跨产业发现"
}}

## 枚举约束 (★ 强制)
- confidence: high / medium / low / insufficient_data
- linkage_type: shared_constraint | crowding_out_beneficiary | crowding_out_victim | shared_equipment | byproduct_economics | bullwhip_amplification | cobweb_oversupply
- impact_direction: positive / negative
- time_to_impact: immediate(<3月) / medium_term(3-12月) / long_term(12-36月)
- impact_materiality: high(>20%营收) / medium(10-20%) / low(<10%) — low标记降权不删除
- visibility: very_low / low / moderate — 如实判断, 禁止为Alpha压低
- evidence_type: forward_looking_rumor / hard_data_confirmation

## 规则 (★ 重要)
- cross_industry_linkages 至少 2 条, 最多 6 条
- 禁止输出股票代码或公司名 (用 target_profile 替代)
- sector_description 用自然语言, 不要编造申万行业分类
- 每条 evidence 必须带 quality, 标注 from
- 跨产业关联本质上是推演, 大部分 linkage 的 confidence 不超过 medium
- 不要重复 Step 4 已有结论 (resource_crowding 已识别的不要再重复输出)
- impact_materiality=low 标记但不删除 — 第二曲线的营收占比初期必然低"""

    # ═══ 基类 ═══════════════════════════════

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return await super().load_context(ctx)

    @staticmethod
    def build_prompt(ctx): return "CrossIndustryLinkageAgent V1.0"

    @staticmethod
    async def stream(ctx): yield "streaming not implemented"
