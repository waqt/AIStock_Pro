"""
SystemDynamicsAgent V5.14 — Step 4: 双轨推演(链内+链外)
定位: 同一产业链内二层思维外推 + 跨产业溢出分析 (原Step 5合并)
核心问题: 链内怎么变形? 链外哪些产业被波及? 资金拥挤效应? 二阶后果?
V5.14: +跨产业溢出(cross_chain_spillover) +Q3链内边界限定 +搜索链双轨合并
V5.13: +二层思维外推框架(Q1-Q4) +影响力度估算(每节impact_assessment) +反编造(移除至少N条)
"""
import asyncio, re
from decimal import Decimal
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger
from app.framework.pipeline.glossary import step4_glossary


class SystemDynamicsAgent(ResearchAgent):
    """系统动力学推演 V5.14 — 双轨推演: 链内二层思维 + 链外跨产业溢出"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "SystemDynamicsAgent"

    # ═══ 工具 ═══════════════════════════════

    @staticmethod
    def _clean_snippet(text: str) -> str:
        if not text: return ""
        if "%PDF" in text or "endstream" in text: return ""
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
        return text[:250]

    @staticmethod
    def _format_chain_with_sub(chain_map: list, max_nodes: int = 2, max_subs: int = 5) -> str:
        """展开 supply_chain_map, 含 sub_processes 子工艺概要 (V5.12)"""
        lines = []
        for node in chain_map[:max_nodes]:
            sr = node.get("supply_rigidity", {})
            node_conf = node.get("confidence", "?")
            margin_est = node.get("profit_pool", {}).get("margin_estimated", "?")
            lines.append(f"- L{node.get('level','?')} {node.get('name','?')}: severity={sr.get('severity','?')}, root_cause={sr.get('root_cause','?')}, expand={sr.get('expand_cycle','?')}, confidence={node_conf} | margin_estimated={margin_est}")
            # sub_processes (仅 severity>=high 的节点才展开)
            sps = node.get("sub_processes", [])
            if sps:
                for sp in sps[:max_subs]:
                    vm = sp.get("value_magnitude", {}).get("order_of_magnitude", "?")
                    pb = sp.get("competitive_landscape", {}).get("pricing_behavior", "?")
                    sub = sp.get("supply_rigidity", {}).get("substitutability", "?")
                    lines.append(f"  └ {sp.get('name','?')}: value_magnitude={vm}, pricing={pb}, substitutability={sub}")
        # 剩余节点不带 sub_processes
        for node in chain_map[max_nodes:]:
            sr = node.get("supply_rigidity", {})
            lines.append(f"- L{node.get('level','?')} {node.get('name','?')}: severity={sr.get('severity','?')}, root_cause={sr.get('root_cause','?')}, expand={sr.get('expand_cycle','?')}")
        return "\n".join(lines)

    @staticmethod
    def _extract_bottleneck_nodes(chain_map: List[Dict]) -> List[Dict]:
        """从 supply_chain_map 提取 severity=extreme/high 的瓶颈节点 (V5.14 从 Step 5 搬移)"""
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

    async def analyze(self, ctx: Dict[str, Any] = None, trace=None) -> Dict[str, Any]:
        ctx = await self.load_context(ctx or {})
        if not self.provider:
            return {"agent": self.name, "error": "No AI provider"}

        industry = ctx.get("industry", "未指定")
        # Step 3 输出
        chain_map = ctx.get("supply_chain_map", [])
        scarcity = ctx.get("scarcity_ranking", [])
        core_stocks = ctx.get("core_stocks", [])
        # V5.12: Step 2 前置判断 (可选)
        step2 = ctx.get("step2_analysis", {})

        logger.info(f"[{self.name}] Deduction: {industry} ({len(chain_map)} chain nodes) | step2={'yes' if step2 and step2.get('cycle_phase') else 'no'}")

        # 2+1 轮搜索: 瓶颈迁移 + 隐藏受益者 + 兜底(不依赖 top_node)
        top_node = (scarcity[0].get("segment", industry) if scarcity else industry)
        top_node_conf = (scarcity[0].get("confidence", "?") if scarcity else "?") if isinstance(scarcity, list) and scarcity and isinstance(scarcity[0], dict) else "?"
        search_chains = [
            [f"{industry} {top_node} 扩产 瓶颈迁移 新瓶颈 制约 2026",
             f"{industry} 产能扩张 瓶颈转移 新约束",
             f"{industry} supply chain bottleneck shift constraint"],
            [f"{industry} 供应链 意外受益 被忽视 隐性 受益方 受损",
             f"{industry} 产业链 隐藏 受益 挤占 受损 2026",
             f"{industry} hidden beneficiary crowding out supply chain"],
            # 兜底: 不依赖 Step 3 的 top_node, 从整个产业链视角搜索
            [f"{industry} 产业链 结构变形 利润迁移 赢家 输家 2026",
             f"{industry} 产能 释放 CAPEX 受益者 受损者 2026",
             f"{industry} supply chain winners losers structural shift 2026"],
            # V5.12: 竞争格局 + 替代技术验证
            [f"{industry} {top_node} 竞争格局 市场份额 龙头 集中度 定价权 2026",
             f"{industry} 供应商 议价权 竞争 壁垒 格局 替代",
             f"{industry} pricing power market share concentration competition"],
        ]
        search_data = await self._search_adaptive(search_chains, num=4, trace=trace)

        # V5.14: 跨产业搜索 (原Step 5 的 N×3 节点搜索)
        bn_nodes = self._extract_bottleneck_nodes(chain_map)
        cross_search_data = []
        for node in bn_nodes[:3]:
            node_name = node["name"]
            narrative = node.get("bottleneck_narrative", node_name)
            chains = [
                [f"{narrative} 还用于 哪些行业 下游 应用 领域",
                 f"{node_name} 应用 领域 下游 行业",
                 f"{node_name} industry application downstream"],
                [f"{node_name} 产能 挤占 影响 涨价 替代 受益",
                 f"{narrative} 供应紧张 受益 标的 营收占比",
                 f"{node_name} crowding out beneficiary 2026"],
                [f"{node_name} 涨价 影响 下游 产业链 传导",
                 f"{narrative} 国产替代 受益 业绩弹性 2026",
                 f"{node_name} supply squeeze spillover cross industry"],
            ]
            node_data = await self._search_adaptive(chains, num=4, trace=trace)
            cross_search_data.append({"node": node_name, "search_data": node_data})
        logger.info(f"[{self.name}] Cross-industry search: {len(bn_nodes)} bottleneck nodes, {sum(len(d['search_data']) for d in cross_search_data)} chains")

        # LLM 推演
        prompt = self._build_prompt(industry, chain_map, scarcity, core_stocks, search_data, step2, cross_search_data, bn_nodes)

        try:
            text = await self.provider.chat_pro(prompt, max_tokens=16384, timeout=600)
            if trace: trace.record_llm(prompt, text, model="deepseek-v4-pro")
            result = self.parse_json(text)
            if isinstance(result, dict):
                sd = result.get("system_dynamics", {})
                n_dynamics = len(sd.get("bottleneck_migration", {}).get("migration_drivers", []))
                n_crowding = len(sd.get("resource_crowding", []))
                n_hidden = len(sd.get("hidden_beneficiaries", []))
                n_cross = len(sd.get("cross_chain_spillover", []))
                n_queries = len(sd.get("asset_search_queries", []))
                sanity = result.get("step3_sanity_check", {})
                n_questioned = len(sanity.get("questioned", []))
                confidence = result.get("confidence", "?")
                logger.info(f"[{self.name}] Done: confidence={confidence}, sanity={n_questioned}, migration={n_dynamics}, crowding={n_crowding}, hidden={n_hidden}, cross={n_cross}, queries={n_queries}")
                if trace:
                    trace.record_note("summary", f"confidence={confidence}, sanity_checks={n_questioned}, crowding={n_crowding}, hidden={n_hidden}, cross_chain={n_cross}")

                # ── 后处理: 将 spillover 搜索项注入 asset_search_queries ──
                # 这样 Step 6 只需统一读取 asset_search_queries, 不需要再单独解析
                # cross_chain_spillover / hidden_beneficiaries / profit_pool_shift
                def _infer_mapping_type(text):
                    import re
                    if not text: return "direct"
                    non_cjk = len(re.sub(r'[一-鿿\s]', '', text))
                    total = len(text) - text.count(' ')
                    return "a_share_equivalent" if total > 0 and non_cjk / total > 0.4 else "direct"

                asset_queries = sd.get("asset_search_queries", [])
                seen_q = {q.get("query") for q in asset_queries if q.get("query")}

                for spill in sd.get("cross_chain_spillover", []):
                    if spill.get("impact_direction") != "positive":
                        continue
                    queries = spill.get("search_queries", [])
                    if not queries and spill.get("target_profile"):
                        queries = [spill["target_profile"]]
                    for sq in queries:
                        if sq and sq not in seen_q:
                            asset_queries.append({
                                "query": f"A股 {sq} 上市公司 2026",
                                "source_node": spill.get("source_node", ""),
                                "source": f"cross_chain_spillover: {spill.get('source_node', '')}",
                                "priority": "high",
                                "mapping_type": _infer_mapping_type(sq),
                            })
                            seen_q.add(sq)

                for hb in sd.get("hidden_beneficiaries", []):
                    queries = hb.get("search_queries", [])
                    if not queries and hb.get("sector"):
                        queries = [hb["sector"]]
                    for sq in queries:
                        if sq and sq not in seen_q:
                            asset_queries.append({
                                "query": f"A股 {sq} 龙头 上市公司 2026",
                                "source": f"hidden_beneficiary: {hb.get('sector', '')}",
                                "priority": "medium",
                                "mapping_type": _infer_mapping_type(sq),
                            })
                            seen_q.add(sq)

                for shift in sd.get("profit_pool_shift", []):
                    to_seg = shift.get("to_segment", "")
                    if to_seg and to_seg not in seen_q:
                        asset_queries.append({
                            "query": f"A股 {to_seg} 龙头 上市公司 2026",
                            "source": f"profit_pool_shift: {shift.get('trigger', '')[:80]}",
                            "priority": shift.get("confidence", "medium"),
                            "mapping_type": _infer_mapping_type(to_seg),
                        })
                        seen_q.add(to_seg)

                if asset_queries:
                    sd["asset_search_queries"] = asset_queries
                    result["system_dynamics"] = sd

                logger.info(f"[{self.name}] After post-process: {len(asset_queries)} total asset_search_queries")
                return result
        except asyncio.TimeoutError:
            logger.warning(f"[{self.name}] Timeout: {industry}")
        except Exception as e:
            logger.warning(f"[{self.name}] Failed: {e}")

        return {"agent": self.name, "error": "Analysis failed", "system_dynamics": {}}

    # ═══ Prompt 构建 ═══════════════════════════

    def _build_prompt(self, industry, chain_map, scarcity, core_stocks, search_data, step2=None, cross_search_data=None, bn_nodes=None) -> str:
        # V5.12: 含 sub_processes 展开 + Step 2 可选输入
        chain_summary = self._format_chain_with_sub(chain_map, max_nodes=2, max_subs=5)

        scarcity_summary = "\n".join(
            f"{s.get('rank','?')}. {s.get('segment','?')}: {s.get('rigidity_narrative','')[:80]}"
            for s in (scarcity or [])[:3])

        stocks_str = ", ".join(s.get("code","?")+" "+s.get("name","?") for s in (core_stocks or [])[:5])

        search_summary = ""
        for sd in search_data:
            search_summary += f"\n### {sd['query']}\n"
            for r in sd["results"][:3]:
                search_summary += f"  - {r['title']}: {r['snippet'][:180]}\n"

        # V5.14: 跨产业搜索结果
        cross_search_summary = ""
        if cross_search_data:
            for cs in cross_search_data:
                cross_search_summary += f"\n### Node: {cs['node']}\n"
                for chain in cs["search_data"]:
                    for r in chain["results"][:2]:
                        cross_search_summary += f"  - {r['title']}: {r['snippet'][:150]}\n"
        else:
            cross_search_summary = "(无瓶颈节点, 跨产业搜索未执行)"

        # V5.12: Step 2 可选输入
        step2_available = bool(step2 and step2.get("cycle_phase"))
        if step2_available:
            s2 = step2
            step2_text = f"""
- 周期阶段: {s2.get('cycle_phase','?')}/{s2.get('sub_phase','?')}
- 利润再分配方向: {s2.get('profit_redirection','?')}
- 市场重定价阶段: {s2.get('repricing_stage','?')}
- 赔率不对称性: {s2.get('payoff_asymmetry','?')}
- 替代风险: {s2.get('substitution_risk','?')}
- 传导深度: {s2.get('propagation_depth','?')}
"""
        else:
            step2_text = "(本轮分析未运行 Step 2, 以下推演仅基于 Step 3 结构)"

        return f"""你是系统动力学专家。输入是 Step 3 输出的产业链静态结构, 你的任务是应用**二层思维 (Second-Level Thinking)** 推演这个结构在压力下**怎么变形**, 并**估算每项推演的影响力度**。

## ★ 核心方法: 二层思维外推 (V5.13)

### 第一层: 链式推演 (常规分析, 建立 baseline)
需求变化 → 资源变化 → 供给变化 → 价格变化 → 利润变化 → CAPEX变化 → 再平衡
建立"市场共识"层面的 baseline。大多数分析师和报告都能做到这一步。

### 第二层: 二阶效应推断 (这是你的差异化价值, 必须执行)
在第一层基础上追问四个问题:

**Q1 资金拥挤效应** — 当所有人都看到了同样的链式推演, 资金涌向哪里?
  → 拥挤本身会改变供需格局, 加速或反转第一层的推演路径
  → 例: 全行业扩 CoWoS → 设备交期不降反升 → 设备商比封测厂更受益

**Q2 共识盲区** — 市场共识中隐含了什么"不会变"的假设? 这个假设可能是错的?
  → 例: "HBM 持续紧缺"是共识 → 但云厂自研芯片可能绕过 HBM
  → 识别未被市场质疑但值得挑战的隐含假设

**Q3 二阶后果** (限定: **同一产业链内**, 跨产业的波及归到下方 `cross_chain_spillover` 节) — A→B 之后, B→C 是什么? C 才是市场真正忽略的机会。
  → 例: HBM 挤占 DDR(A→B) → DDR 涨价 → 二线 DDR 厂意外受益(C)
  → 不是找直接供应商, 而是找"因为别人都去找直接供应商而留下的空白"

**Q4 反身性** — 推演结果会改变参与者行为, 行为反过来改变推演的前提。
  → 例: 全行业为缓解瓶颈1而扩产 → 新增供给过剩 → CAPEX 回收率低于预期

### 第一步: Step 3 反向校验 (推演前提审视, 必须执行)

在开始推演之前, 先审视 Step 3 的输出:
1. 哪个瓶颈的 severity 可能被高估/低估? (注意: margin_level 是 LLM 估计值, 见 margin_estimated=true 标记, 需 Step 6 财务审计后回写真实值)
2. 哪个 profit_pool 判断可能因搜索片段偏差而不准确?
3. 哪个环节的"零替代"断言可能有例外?

→ 找出 1-2 个"可能不准确"的 Step 3 判断, 在输出的 step3_sanity_check 字段中写明质疑和调整。
→ 如果审视后认为 Step 3 判断合理, 可以没有质疑, 如实写 step3_sanity_check 为空即可。
→ 基于质疑调整后续推演的前提假设 (如: severity=extreme 被质疑 → 推演中降低该节点的确定性, 标记 confidence=medium)。

## 参考案例 (few-shot, 标注了一阶→二阶外推)
1. 资源挤占: HBM消耗3x晶圆 → 挤占DDR产能 → DRAM涨价 → 二线DRAM厂受益
   → 二层外推: DDR涨价 → 下游延长DDR4生命周期 → DDR4控制器/接口芯片意外需求
2. 瓶颈迁移: GPU短缺 → 云厂自研芯片 → CoWoS成新瓶颈 → 封装设备受益
   → 二层外推: 全行业扩CoWoS需要大量设备 → 设备交期成为下一个瓶颈 → 比封测厂更早受益的是设备商
3. CAPEX错配: 成熟制程CAPEX不足 → MCU缺货2年 → 成熟代工厂暴利
   → 二层外推: MCU缺货 → 下游被迫做多源供应 → 验证周期反而缩短 → 国内代工厂加速导入
4. 供给刚性: 高纯石英砂只有北卡矿 → 光伏扩产 → 石英砂2年涨价10倍
   → 二层外推: 石英砂涨价 → 坩埚成本占比大幅提升 → 坩埚厂商定价权增强(非石英砂本身)

## Step 3 产业链结构 (注意: margin_estimated=true 表示该值为 LLM 估计, 待 Step 6 修正)
行业: {industry}
核心标的: {stocks_str}
瓶颈图谱:
{chain_summary}
稀缺排序:
{scarcity_summary}

## Step 2 前置判断 (可选输入, 用于交叉验证)
{step2_text}

使用说明:
- profit_redirection (利润再分配方向) 可作为 profit_pool_shift 的方向锚定
- repricing_stage (市场重定价阶段) 影响瓶颈迁移置信度 (晚期→已定价→迁移空间有限)
- payoff_asymmetry (赔率不对称性) 和 substitution_risk (替代风险) 应纳入 thesis_breakers 考量
- cycle_phase (周期阶段) 影响迁移速度判断
- 如果无 Step 2 数据, 完全基于 Step 3 结构独立推演, 不受此段影响

## 补充搜索
{search_summary}

## 跨产业溢出分析 (V5.14)

### 搜索输入 — 瓶颈节点跨产业波及
{cross_search_summary}

### 五种跨产业传导方法 (仅用于 cross_chain_spillover 节)

1. **产能挤出 (crowding_out)**: 高利润/高优先级产品挤占别人的产能 → 受害方和受益方在别的产业
   → 例: HBM疯狂扩产挤占DRAM晶圆产能 → DDR5涨价 → DDR5配套接口芯片意外受损
2. **副产品经济学 (byproduct_economics)**: 主产品供给剧变 → 副产品供给同步变化 → 波及其他产业
   → 例: 存储扩产需要大量高纯气体 → 气体供给被存储抢走 → 逻辑芯片的气体供应不足
3. **投入产出溢出 (io_spillover)**: 扩产 → 上游设备/材料的订单外溢到其他产业的使用者
   → 例: 存储抢刻蚀设备 → 成熟制程代工厂设备交期拉长 → 汽车/工业芯片产能释放延迟
4. **牛鞭效应 (bullwhip_effect)**: 终端需求小波动 → 上游放大到存储原厂扩产 → 波及其他使用同一供给源的产业
   → 例: AI推理需求增长 → HBM预期暴增 → 全行业备货 → ABF基板被各路芯片争抢
5. **蛛网模型 (cobweb_oversupply)**: CAPEX洪峰 → 某一节点在未来某个时点突然过剩 → 冲击相关产业
   → 例: 2026-27年CoWoS产能集中释放 → 测试环节需求脉冲式爆发 → 独立测试厂量价齐升

要求:
- 每条 spillover 必须标注所使用的方法 (linkage_type)
- 必须有 evidence 支撑 (搜索已提供输入)
- 如果搜索无证据支撑某个传导路径, 不在 evidence 上编造
- 跨产业推演依赖的是本节的瓶颈节点搜索, 不使用 Q1-Q4 的补充搜索数据

## 输出纯 JSON (全定性, 不做数值评分)

{{
  "confidence": "high/medium/low/insufficient_data — 基于 Step 3 数据质量 + 补充搜索覆盖度综合判断",
  "confidence_note": "说明数据缺口或不确定性来源",

  "step3_sanity_check": {{
    "questioned": [
      {{"claim": "Step 3 中哪个具体判断", "doubt": "为什么可能不准确"}}
    ],
    "adjustment": "基于质疑, 调整了推演中的哪些前提假设"
  }},

  "system_dynamics": {{

    "bottleneck_migration": {{
      "current": "当前最主要的瓶颈环节",
      "next_12m": "12个月后哪个环节可能成为新瓶颈",
      "next_24m": "24个月后",
      "next_36m": "36个月后",
      "migration_drivers": [
        {{
          "from": "从哪个瓶颈", "to": "迁移到哪个瓶颈", "trigger": "触发条件是什么",
          "monitoring_metric": "可观测的量化监控指标 (如: 台积电CoWoS月产能 wpm)",
          "trigger_threshold": "触发新瓶颈的量化阈值 (如: CoWoS月产能突破200K wpm时)",
          "evidence": [
            {{"fact":"事实","from":"search[1.X]·来源","quality":{{"level":"high","source_type":"company_filing"}},"evidence_type":"hard_data_confirmation"}}
          ]
        }}
      ],
      "evidence": [...],
      "impact_assessment": {{
        "magnitude": "重大 / 中等 / 轻微",
        "reasoning": "定性判断: 市场规模/利润弹性/A股映射明确度/时间紧迫度等",
        "time_horizon": "3-6个月 / 6-12个月 / 12-24个月 / 24个月以上"
      }}
    }},

    "resource_crowding": [
      {{
        "resource": "被挤占的资源",
        "squeezed_from": "从哪个环节被挤走",
        "squeezed_by": "被哪个环节挤占",
        "victim_sector": "受害方 — 谁被迫承受涨价/断供",
        "hidden_beneficiary": "谁意外受益 — 替代供应商或关联方",
        "visibility": "very_low/low/moderate — 如实判断市场关注度, 不因Alpha大而压低",
        "time_to_impact": "immediate/medium_term/long_term",
        "monitoring_metric": "监控指标 (如: ABF基板交期 周)",
        "trigger_threshold": "触发受益标的筛查的量化阈值 (如: 交期突破26周时)",
        "search_queries": ["用于下游标的映射的精准搜索词", "禁止输出股票代码"],
        "evidence": [
          {{"fact":"事实","from":"search[X]·来源","quality":{{"level":"high","source_type":"industry_data"}},"evidence_type":"forward_looking_rumor"}}
        ],
        "impact_assessment": {{
          "magnitude": "重大 / 中等 / 轻微",
          "reasoning": "定性判断",
          "time_horizon": "3-6个月 / 6-12个月 / 12-24个月 / 24个月以上"
        }}
      }}
    ],

    "profit_pool_shift": [
      {{
        "from_segment": "利润从哪个环节流出",
        "to_segment": "利润流向哪个环节",
        "trigger": "触发利润迁移的条件",
        "timeline": "6-12个月/12-24个月/24-36个月",
        "confidence": "high/medium/low/speculative",
        "monitoring_metric": "监控指标",
        "trigger_threshold": "触发阈值",
        "evidence": [...],
        "impact_assessment": {{
          "magnitude": "重大 / 中等 / 轻微",
          "reasoning": "定性判断",
          "time_horizon": "3-6个月 / 6-12个月 / 12-24个月 / 24个月以上"
        }}
      }}
    ],

    "hidden_beneficiaries": [
      {{
        "sector": "被市场忽视的受益方",
        "reason": "为什么受益, 为什么市场没注意到",
        "visibility": "very_low/low/moderate — 如实判断, 禁止为追求Alpha压低",
        "time_to_impact": "immediate/medium_term/long_term",
        "search_queries": ["用于下游标的映射的搜索词"],
        "evidence": [...],
        "impact_assessment": {{
          "magnitude": "重大 / 中等 / 轻微",
          "reasoning": "定性判断",
          "time_horizon": "3-6个月 / 6-12个月 / 12-24个月 / 24个月以上"
        }}
      }}
    ],

    "thesis_breakers": [
      {{
        "thesis": "推演出的核心论点",
        "break_condition": "什么具体条件变化会打破这个论点 (必须是可量化/可观测的)",
        "watch_signal": "监控什么指标来验证 (必须是可获取的高频数据)",
        "evidence": [...],
        "impact_assessment": {{
          "magnitude": "重大 / 中等 / 轻微",
          "reasoning": "定性判断",
          "time_horizon": "3-6个月 / 6-12个月 / 12-24个月 / 24个月以上"
        }}
      }}
    ],

    "cross_chain_spillover": [
      {{
        "source_node": "上游瓶颈节点名称",
        "linkage_type": "crowding_out / byproduct_economics / io_spillover / bullwhip_effect / cobweb_oversupply",
        "affected_sector": "受波及的细分行业",
        "sector_description": "行业描述, 用于Step 6标的识别",
        "impact_direction": "positive / negative",
        "impact_narrative": "完整的二阶段传导逻辑 (A→B→C 三层结构)",
        "target_profile": "受益或受损企业的特征画像 (供Step 6圈定标的)",
        "visibility": "very_low / low / moderate",
        "time_horizon": "3-6个月 / 6-12个月 / 12-24个月 / 24个月以上",
        "search_queries": ["用于下游标的映射的搜索词"],
        "evidence": [
          {{"fact":"事实","from":"search[N]·来源","quality":{{"level":"high","source_type":"industry_analysis"}},"evidence_type":"hard_data_confirmation"}}
        ],
        "impact_assessment": {{
          "magnitude": "重大 / 中等 / 轻微",
          "reasoning": "定性判断: 市场规模/利润弹性/A股映射明确度/时间紧迫度",
          "time_horizon": "3-6个月 / 6-12个月 / 12-24个月 / 24个月以上"
        }}
      }}
    ],

    "asset_search_queries": [
      {{
        "query": "用于Step 6资产标的检索的精准搜索词, 含行业+环节+A股关键词",
        "source": "哪个推演结论产生的 (如: bottleneck_migration→设备瓶颈)",
        "priority": "high / medium"
      }}
    ]

  }}
}}

## sub_processes 使用说明 (V5.12)
- 瓶颈迁移: 引用具体子工艺名称 (如 "CoWoS.硅中介层制造"), 不只说 "L1 HBM先进封装"
- 利润迁移: 参考 value_magnitude 判断绝对量级, 不只说 "利润流向X"
- 资源挤占: 参考 pricing_behavior 判断谁有转嫁能力优势 (monopoly→能转嫁, capacity_war→不能)
- hidden_beneficiaries: 如果 Step 3 已提供 sub_processes[].value_owners[] 和 a_stock_mapping[], 聚焦跨节点二阶效应, 不重复子工艺级的价值捕获者
- 如果 Step 3 未提供 sub_processes (空数组), 维持原有 L1/L2 级别推演粒度

## 枚举约束 (★ 强制)
- confidence (整体): high / medium / low / insufficient_data
- profit_pool_shift.confidence: high / medium / low / speculative
- visibility: very_low / low / moderate — 如实判断, 禁止为追求Alpha而压低
- time_to_impact: immediate(<3月) / medium_term(3-12月) / long_term(12-36月)
- migration_drivers.from/to: 必须是具体的产业环节名称 (不是行业分类)
- evidence_type: forward_looking_rumor / hard_data_confirmation

## 证据要求 (V5.13 — 能找到就找, 找不到不要瞎编)
- 每个结论块优先附 evidence 数组, **如果搜索返回结果不足以支撑, 数组可以为空**
- 空证据的结论块须在 confidence_note 中说明"缺乏直接搜索证据, 属于逻辑推演"
- 来源可信度权重: company_filing > official_policy > industry_data > sell_side_report > news_media
- quality.level=high 必须有 company_filing 或 official_policy 支撑, 纯媒体来源最高 medium
- quality.level=low 或 insufficient_data 是诚实的, 不被惩罚
- evidence_type: forward_looking_rumor (前瞻信号/传闻) / hard_data_confirmation (财报/公告)
- self_media/ai_summary 仅参考, 不得单独支撑关键推演

## 质量自检 — 推演十问 (逐条确认)
1.真正驱动力? 2.哪个资源最稀缺? 3.高利润会吸走谁的资源?
4.谁会供给下降? 5.谁会意外涨价? 6.谁拥有定价权?
7.哪个瓶颈最难扩产? 8.利润会迁移到哪里? 9.市场还没发现谁?
10.什么信号会证伪我?

**跨产业溢出质量自检 (cross_chain_spillover 节):**
- 每条 spillover 是否有明确的传导方向 (A→B→C)?
- linkage_type 是否对应五种方法之一?
- 是否与 Q3 链内内容重复? (同一件事既出现在 Q3 又出现在 cross_chain → 去重)
- evidence 是否来自本节搜索输入, 而非编造?
- target_profile 是否足够具体供 Step 6 做标的映射?

确保你的推演尽可能回答以上问题。如果某方面搜索无结果, 对应部分可精简或为空, 不在 evidence 上编造。
禁止 LLM 直接输出股票代码 (china_stocks 已删除, 用 search_queries 替代)。
不做数值评分, 不做行业分类描述, 聚焦跨环节推演。

{step4_glossary()}
"""

    # ═══ 基类 ═══════════════════════════════

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return await super().load_context(ctx)

    @staticmethod
    def build_prompt(ctx): return "SystemDynamicsAgent V5.14"

    @staticmethod
    async def stream(ctx): yield "streaming not implemented"
