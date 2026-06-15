"""
CandidateComparator V1.1 — 独立候选比较智能体
职责: 同源比较 (同一瓶颈节点内的候选) + 全局排名 (跨节点已验证候选)
原则: 只用外部硬事实 (搜索原文 + 财务数据), 不用 pipeline 内部标签, 避免循环论证
V1.1: 不排名, 只输出观察+排除建议
"""
import json
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger


def _j(obj, **kw):
    from decimal import Decimal
    class _SafeEncoder(json.JSONEncoder):
        def default(self, o):
            if isinstance(o, Decimal):
                return float(o)
            return super().default(o)
    kw.setdefault("ensure_ascii", False)
    kw.setdefault("cls", _SafeEncoder)
    return json.dumps(obj, **kw)


class CandidateComparator(ResearchAgent):
    """候选比较智能体 V1.1 — 独立上下文、自己搜索、定性比较"""

    def __init__(self, provider=None, search_cache=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "CandidateComparator"
        self._search_cache = search_cache or {}

    # ═══ 同源比较 — PES 三阶段 ═════════════════════════════

    async def compare_within_source(self, candidates: List[Dict],
                                    node_context: Dict) -> Dict:
        """同一瓶颈节点内的候选比较 — PES 三阶段

        PLAN:     LLM 根据节点特征策划比较维度
        EXECUTE:  系统按维度收集证据 (搜索+财务)
        SYNTHESIZE: LLM 逐维度比较 + 排除建议

        Args:
            candidates: [{"code":"688012","name":"中微公司","source_type":"a_stock_mapping"}, ...]
            node_context: 节点背景

        Returns:
            {"source": "节点名", "observations": [...],
             "exclusion_suggestions": [...], "comparison_dimensions": [...]}
        """
        if len(candidates) < 2:
            return {
                "source": node_context.get("name", ""),
                "observations": [{"code": c["code"], "name": c.get("name", "")} for c in candidates],
                "exclusion_suggestions": [],
                "comparison_dimensions": [],
            }

        names = [c.get("name", c.get("code", "?")) for c in candidates]
        node_name = node_context.get("name", "")
        logger.info(f"[{self.name}] compare_within_source '{node_name}': {names}")

        # ── Phase 0: 基础数据收集 (通用背景) ──────────
        search_data = await self._search_for_comparison(candidates, node_context)
        fundamentals = {}
        try:
            codes = [c["code"] for c in candidates if c.get("code")]
            if codes:
                fundamentals = await self.data_loader.load_fundamentals(codes)
        except Exception:
            pass

        # ── Phase PLAN: LLM 定比较维度 ────────────────
        plan = await self._plan_comparison(candidates, node_context)
        if plan is None:
            plan = {"dimensions": [], "analytical_focus": ""}

        # ── Phase EXECUTE: 系统按维度收集证据 ──────────
        dimension_evidence = await self._execute_comparison_plan(
            candidates, node_context, plan)

        # ── Phase SYNTHESIZE: LLM 逐维度比较 ──────────
        result = await self._synthesize_comparison(
            candidates, node_context, plan, search_data, fundamentals, dimension_evidence)

        if result is not None:
            result.setdefault("observations", [])
            result.setdefault("exclusion_suggestions", [])
            result.setdefault("comparison_dimensions", [])
            result["source"] = node_name
            logger.info(f"[{self.name}] Done: candidates={len(candidates)}, "
                        f"suggested_exclude={[s.get('code','?') for s in result['exclusion_suggestions']]}")
            return result

        # ★ 安全兜底: LLM 完全失败 → 全保留
        logger.warning(f"[{self.name}] All LLM attempts failed, passing all '{node_name}' candidates through")
        return {
            "source": node_name,
            "observations": [{"code": c["code"], "name": c.get("name", "")} for c in candidates],
            "exclusion_suggestions": [],
            "comparison_dimensions": [],
        }

    async def _search_for_comparison(self, candidates: List[Dict],
                                      node_context: Dict) -> Dict[str, List]:
        """为每只候选搜索比较用信息 (★ snippet 裁剪至 150 字符控制 token)"""
        node_name = node_context.get("name", "")
        results = {}
        for c in candidates:
            name = c.get("name", "")
            code = c.get("code", "")
            queries = [
                f"{name} {code} {node_name} 市场份额 营收 技术 产品 2026",
                f"{name} {code} 客户 供应链 竞争 毛利率 客户 认证 2025 2026",
            ]
            items = []
            for q in queries:
                try:
                    cache_key = q.strip().lower()
                    if cache_key in self._search_cache:
                        r = self._search_cache[cache_key]
                    else:
                        r = await self.data_loader.search_web(q, num=3)
                        self._search_cache[cache_key] = r
                    for rr in r:
                        snippet = (rr.get("snippet", "") or "")[:150]
                        if snippet:
                            items.append({
                                "query": q,
                                "title": (rr.get("title", "") or "")[:100],
                                "snippet": snippet,
                            })
                except Exception:
                    pass
            results[code] = items
        return results

    # ── Phase PLAN: LLM 定比较维度 ──────────────────

    async def _plan_comparison(self, candidates: List[Dict],
                                node_context: Dict) -> Dict:
        """PLAN: LLM 根据节点特征策划比较维度和证据需求"""
        node_name = node_context.get("name", "")
        narrative = node_context.get("bottleneck_narrative", "")
        profit_pool = node_context.get("profit_pool", "")
        rigidity = node_context.get("supply_rigidity", "")
        substitution = node_context.get("china_substitution_rate", "")
        leaders = node_context.get("global_leaders", [])
        magnitude = node_context.get("value_magnitude", "")

        cand_lines = "\n".join(
            f"- {c.get('name','?')}({c.get('code','?')}): {c.get('source_type','')}"
            for c in candidates
        )

        prompt = f"""你是一位资深产业分析师。请为以下候选比较策划比较框架。

## 环节背景
- 环节: {node_name}
- 利润池: {profit_pool}  |  市场量级: {magnitude}
- 供给刚性: {rigidity}
- 国产替代率: {substitution}
- 全球龙头: {', '.join(leaders) if leaders else 'N/A'}
- 瓶颈描述: {narrative[:300]}

## 候选公司
{cand_lines}

## 任务

根据此环节的产业链特征和竞争本质，策划比较维度。

关键原则:
1. 维度必须与 **该环节的竞争本质** 相关（不同环节需要不同维度）
   - 技术瓶颈环节 → 技术代差、产品覆盖度、客户认证壁垒
   - 资源约束环节 → 资源储量、开采成本、产能扩张能力
   - 规模效应环节 → 市场份额、成本结构、产能规模
   - 渠道/品牌环节 → 渠道覆盖、品牌认知、客户粘性
2. 每个维度说明需要什么 **证据类型**: search(搜索补充) 和/或 fundamentals(财务数据)
3. 不预设固定维度，不设限制

## 输出 JSON

{{
  "dimensions": [
    {{
      "name": "技术代差与产品覆盖度",
      "weight": "high",
      "rationale": "该环节为技术瓶颈，制程先进度是核心竞争壁垒",
      "evidence_type": ["search"],
      "search_query_template": "{{name}} {{node}} 技术 产品 参数 制程",
      "financial_indicators": []
    }},
    {{
      "name": "客户认证壁垒",
      "weight": "high",
      "rationale": "半导体设备需客户长期验证，认证进度决定营收可见度",
      "evidence_type": ["search"],
      "search_query_template": "{{name}} {{node}} 客户 认证 导入 验证",
      "financial_indicators": []
    }}
  ],
  "analytical_focus": "该环节竞争本质是..."
}}

规则:
- dimensions 至少 2 个，最多 4 个
- evidence_type 从 ["search", "fundamentals"] 中选择
- search_query_template 用 {{{{name}}}} 和 {{{{node}}}} 作为占位符
- financial_indicators 列出想查的具体指标名 (如 ["gross_margin", "rd_intensity"])"""

        try:
            text = await self.provider.chat_flash(prompt, max_tokens=4096, timeout=60)
            result = self.parse_json(text)
            if isinstance(result, dict) and result.get("dimensions"):
                logger.info(f"[{self.name}] PLAN '{node_name}': "
                            f"{[d['name'] for d in result['dimensions']]}")
                return result
            raise ValueError("Invalid plan")
        except Exception as e:
            logger.warning(f"[{self.name}] PLAN failed ({e}), using dimensions from node type")
            return self._fallback_plan(node_context)

    @staticmethod
    def _fallback_plan(node_context: Dict) -> Dict:
        """PLAN 降级: 根据节点类型推导合理维度"""
        narrative = (node_context.get("bottleneck_narrative", "") or "").lower()
        dims = []

        # 从瓶颈描述判断节点类型
        if any(kw in narrative for kw in ["技术", "制程", "工艺", "材料", "研发", "专利", "芯片"]):
            dims = [
                {"name": "技术能力与产品覆盖度", "weight": "high",
                 "evidence_type": ["search"]},
                {"name": "客户认证与导入进度", "weight": "high",
                 "evidence_type": ["search"]},
                {"name": "盈利能力与财务健康", "weight": "medium",
                 "evidence_type": ["fundamentals"]},
            ]
        elif any(kw in narrative for kw in ["资源", "矿产", "产能", "产量"]):
            dims = [
                {"name": "资源储量与产能规模", "weight": "high",
                 "evidence_type": ["search"]},
                {"name": "成本优势与毛利率", "weight": "high",
                 "evidence_type": ["search", "fundamentals"]},
            ]
        else:
            dims = [
                {"name": "市场地位与份额", "weight": "high",
                 "evidence_type": ["search"]},
                {"name": "产品竞争力与壁垒", "weight": "high",
                 "evidence_type": ["search"]},
                {"name": "盈利能力与增长", "weight": "medium",
                 "evidence_type": ["search", "fundamentals"]},
            ]

        return {"dimensions": dims, "analytical_focus": narrative[:200]}

    # ── Phase EXECUTE: 系统按维度收集证据 ──────────

    async def _execute_comparison_plan(self, candidates: List[Dict],
                                        node_context: Dict,
                                        plan: Dict) -> Dict[str, Dict]:
        """EXECUTE: 按 PLAN 的维度配置，为每候选收集搜索+财务证据

        Returns:
            {dim_name: {code: [evidence_items], ...}, ...}
        """
        node_name = node_context.get("name", "")
        dimensions = plan.get("dimensions", [])
        if not dimensions:
            return {}

        evidence = {}
        for dim in dimensions:
            dim_name = dim.get("name", "?")
            evidence[dim_name] = {}
            etypes = dim.get("evidence_type", ["search"])

            for c in candidates:
                code = c.get("code", "")
                name = c.get("name", "")
                evidence[dim_name].setdefault(code, [])

                # 搜索证据
                if "search" in etypes:
                    tmpl = dim.get("search_query_template", "")
                    if tmpl:
                        query = tmpl.replace("{{name}}", name).replace("{{node}}", node_name)
                        try:
                            r = await self.data_loader.search_web(query, num=3)
                            for rr in r:
                                snippet = (rr.get("snippet", "") or "")[:200]
                                if snippet:
                                    evidence[dim_name][code].append({
                                        "source": "search",
                                        "query": query,
                                        "content": snippet,
                                    })
                        except Exception:
                            pass

                # 财务证据 (基本面已有, 标注引用)
                if "fundamentals" in etypes:
                    evidence[dim_name][code].append({
                        "source": "fundamentals",
                        "note": "参照基础数据中的财务指标",
                    })

        # 统计日志
        dim_counts = {d: sum(len(v) for v in ev.values()) for d, ev in evidence.items()}
        logger.info(f"[{self.name}] EXECUTE '{node_name}': {dim_counts}")
        return evidence

    # ── Phase SYNTHESIZE: LLM 逐维度比较 ──────────

    async def _synthesize_comparison(self, candidates, node_context, plan,
                                      search_data, fundamentals,
                                      dimension_evidence) -> Dict:
        """SYNTHESIZE: LLM 基于证据逐维度比较，输出观察+排除建议"""
        node_name = node_context.get("name", "")
        narrative = node_context.get("bottleneck_narrative", "")
        profit_pool = node_context.get("profit_pool", "")
        rigidity = node_context.get("supply_rigidity", "")
        substitution = node_context.get("china_substitution_rate", "")
        leaders = node_context.get("global_leaders", [])
        magnitude = node_context.get("value_magnitude", "")

        # ── 候选基本信息 ──
        cand_lines = "\n".join(
            f"- {c.get('name','?')}({c.get('code','?')}): {c.get('investment_logic', c.get('source_type',''))}"
            for c in candidates
        )

        # ── 基础搜索结果 (通用背景) ──
        search_lines = []
        for code, items in search_data.items():
            name = next((c.get("name", code) for c in candidates if c.get("code") == code), code)
            search_lines.append(f"\n## {name}({code})")
            for item in items[:5]:
                s = item["snippet"][:200]
                search_lines.append(f"- {item['query']}: {s}")
        search_block = "\n".join(search_lines) if search_lines else "（无搜索结果）"

        # ── 基本面 ──
        fund_lines = []
        for code, info in fundamentals.items():
            name = info.get("name", code)
            pe = info.get("pe_ttm") or info.get("pe", "N/A")
            pb = info.get("pb", "N/A")
            mcap = info.get("market_capital", "N/A")
            fund_lines.append(f"{name}({code}): PE={pe} PB={pb} 市值={mcap}")
        fund_block = "\n".join(fund_lines) if fund_lines else "（无基本面数据）"

        # ── 维度证据 (按维度组织) ──
        dim_blocks = []
        for dim in plan.get("dimensions", []):
            dim_name = dim.get("name", "?")
            dim_evidence = dimension_evidence.get(dim_name, {})
            if not dim_evidence:
                continue

            block_lines = [f"\n### {dim_name}"]
            for c in candidates:
                code = c.get("code", "")
                name = c.get("name", code)
                items = dim_evidence.get(code, [])
                if items:
                    block_lines.append(f"\n{name}({code}):")
                    for item in items[:4]:
                        if item.get("source") == "search":
                            block_lines.append(f"  - {item['content']}")
                        else:
                            block_lines.append(f"  - [参考基本面数据]")
                else:
                    block_lines.append(f"\n{name}({code}):（无特定证据）")
            dim_blocks.append("\n".join(block_lines))

        dim_block = "\n".join(dim_blocks)

        # ── 分析方法说明 ──
        dim_names = [d.get("name", "?") for d in plan.get("dimensions", [])]
        analysis_method = "\n".join(
            f"{i+1}. {name} — {dim.get('rationale', '')[:100]}"
            for i, (name, dim) in enumerate(zip(dim_names, plan.get("dimensions", [])))
        )

        prompt = f"""你是资深产业分析师。基于以下证据，比较候选公司在 "{node_name}" 环节的竞争力。

## 环节背景
- 环节: {node_name}
- 利润池: {profit_pool}  |  市场量级: {magnitude}
- 供给刚性: {rigidity}
- 国产替代率: {substitution}
- 全球龙头: {', '.join(leaders) if leaders else 'N/A'}
- 瓶颈描述: {narrative[:300]}

## 比较框架
{analysis_method if analysis_method else '无预设维度, 自行判断'}

## 候选公司
{cand_lines}

## 基础搜索证据 (通用背景)
{search_block}

## 基本面参考
{fund_block}

## 按维度整理的专项证据
{dim_block if dim_blocks else "（无专项证据）"}

## 任务

按以下步骤分析:

1. **逐维度比较**: 对每个维度, 评估各候选的表现 (strong/medium/weak/emerging)
2. **识别差异**: 找出哪些候选在该维度有明显优势或明显短板
3. **排除判断**: 综合各维度, 哪些候选在该环节明显竞争力不足

## 输出 JSON

{{
  "observations": [
    {{"code": "688012", "key_advantages": "技术优势: 7nm已量产", "key_concerns": "客户集中度高"}}
  ],
  "exclusion_suggestions": [
    {{"code": "xxx", "reason": "在该环节缺乏核心技术/客户基础/规模"}}
  ],
  "comparison_dimensions": [
    {{"dimension": "技术能力", "leaders": ["688012"], "evidence": "具体事实"}}
  ]
}}

规则:
- observations 覆盖 **全部** 候选
- exclusion_suggestions 只包含该排除的 (没有就为空数组 [])
- comparison_dimensions 的 leaders 是该维度领先的候选代码列表
- 证据必须引用上面的搜索结果或基本面数据，不要编造"""
        try:
            text = await self.provider.chat_pro(prompt, max_tokens=8192, timeout=120)
            result = self.parse_json(text)
            if isinstance(result, dict) and "observations" in result:
                return result
            # JSON 中有 observations 但缺少 exclusion_suggestions
            if isinstance(result, dict) and "exclusion_suggestions" not in result:
                result["exclusion_suggestions"] = []
                return result
            raise ValueError("Invalid synthesis output")
        except Exception as first_err:
            logger.warning(f"[{self.name}] SYNTHESIZE failed ({first_err}), retrying simple...")
            try:
                return await self._retry_simple_synthesis(
                    candidates, node_context, search_data, fundamentals)
            except Exception:
                return None

    async def _retry_simple_synthesis(self, candidates, node_context,
                                       search_data, fundamentals) -> Dict:
        """SYNTHESIZE 重试: 简化版 prompt，只要求基本比较"""
        node_name = node_context.get("name", "")
        cand_lines = [f"- {c.get('name','?')}({c.get('code','?')})" for c in candidates]
        search_lines = []
        for code, items in search_data.items():
            name = next((c.get("name", code) for c in candidates if c.get("code") == code), code)
            for item in items[:3]:
                search_lines.append(f"- {name}: {item['snippet'][:150]}")
        fund_lines = []
        for code, info in fundamentals.items():
            fund_lines.append(
                f"{info.get('name',code)}({code}): PE={info.get('pe_ttm','N/A')} "
                f"营收={info.get('revenue','N/A')} 市值={info.get('market_capital','N/A')}")

        text2 = await self.provider.chat_pro(f"""比较以下公司在"{node_name}"环节的竞争力。

候选: {chr(10).join(cand_lines)}

搜索证据: {chr(10).join(search_lines[:30]) if search_lines else '无'}

基本面: {chr(10).join(fund_lines) if fund_lines else '无'}

先逐票分析每家公司在技术能力、市场地位、盈利能力和竞争壁垒方面的表现，
找出差异，然后指出明显竞争力不足的候选。
最后输出JSON:
{{"observations": [{{"code":"xxx","key_advantages":"...","key_concerns":"..."}}],
  "exclusion_suggestions": [{{"code":"xxx","reason":"..."}}]}}""",
            max_tokens=4096, timeout=90)
        result2 = self.parse_json(text2)
        if isinstance(result2, dict) and result2.get("exclusion_suggestions") is not None:
            logger.info(f"[{self.name}] Retry synthesis succeeded")
            return result2
        return None

    @staticmethod
    def _fallback_rank(candidates: List[Dict]) -> List[Dict]:
        """LLM 调用失败时的降级排序 (已弃用, 保留向后兼容)"""
        return [{"code": c.get("code", ""), "name": c.get("name", ""),
                 "rank": i + 1, "why": "LLM比较失败, 保留原始顺序"}
                for i, c in enumerate(candidates)]

    @staticmethod
    def _fallback_rank(candidates: List[Dict]) -> List[Dict]:
        """LLM 调用失败时的降级排序 (已弃用, 保留向后兼容)"""
        return [{"code": c.get("code", ""), "name": c.get("name", ""),
                 "rank": i + 1, "why": "LLM比较失败, 保留原始顺序"}
                for i, c in enumerate(candidates)]

    def _quantitative_rank(self, candidates: List[Dict], fundamentals: Dict,
                            node_name: str, node_context: Dict) -> Dict:
        """★ 定量排序兜底: 用基本面指标做客观排序 (无需 LLM)"""
        scored = []
        for c in candidates:
            code = c.get("code", "")
            fd = fundamentals.get(code, {})
            score = 0.0
            details = []

            # 维度1: 营收规模 (归一化到组内)
            rev = fd.get("revenue") or 0
            if rev:
                score += min(rev / 100, 30)  # 最多30分
                details.append(f"营收={rev}亿")

            # 维度2: 营收增速
            growth = fd.get("revenue_growth") or fd.get("profit_growth") or 0
            if growth:
                score += min(growth * 2, 25)  # 最多25分
                details.append(f"增速={growth}%")

            # 维度3: 净利润率
            margin = fd.get("net_margin") or 0
            if margin:
                score += min(margin, 20)  # 最多20分
                details.append(f"利润率={margin}%")

            # 维度4: PE (低的优先)
            pe = fd.get("pe_ttm") or fd.get("pe") or 0
            if pe and pe > 0:
                pe_score = max(0, 15 - pe / 10)
                score += pe_score
                details.append(f"PE={pe}")

            # 维度5: 市值 (流动性)
            mcap = fd.get("market_capital") or 0
            if mcap:
                mcap_score = min(mcap / 500, 10)
                score += mcap_score
                details.append(f"市值={mcap}亿")

            scored.append((code, c.get("name", code), score, "; ".join(details)))

        # 按得分降序
        scored.sort(key=lambda x: -x[2])

        ranked = []
        for i, (code, name, score, detail) in enumerate(scored):
            ranked.append({
                "rank": i + 1,
                "code": code,
                "name": name,
                "why": f"定量排序 ({detail}, 总分={score:.1f})",
            })

        # 维度比较从基本面数据提取
        dims = []
        if len(scored) >= 2:
            top_code = scored[0][0]
            dims = [
                {"dimension": "营收规模", "winner": top_code,
                 "evidence": f"最高({scored[0][3]})"},
                {"dimension": "基本面总分", "winner": top_code,
                 "evidence": f"{scored[0][2]:.1f} vs {'/'.join(f'{s[2]:.1f}' for s in scored[1:])}"},
            ]

        logger.info(f"[{self.name}] Quantitative rank for '{node_name}': "
                     f"top={ranked[0]['code'] if ranked else 'none'} score={scored[0][2] if scored else 0:.1f}")
        return {
            "source": node_name,
            "ranked": ranked,
            "eliminated": [],
            "comparison_dimensions": dims,
        }

    # ═══ 全局排名 ═══════════════════════════════

    async def global_ranking(self, all_candidates: List[Dict]) -> Dict:
        """跨节点全局排序。

        Args:
            all_candidates: 已验证候选列表

        Returns:
            {"ranked_stocks": [{"rank":1,"code":"688012","why":"..."}], "runner_ups": [...]}
        """
        if not all_candidates:
            return {"ranked_stocks": [], "runner_ups": []}

        active = [c for c in all_candidates if not c.get("eliminated_by")]
        logger.info(f"[{self.name}] Global ranking: {len(active)} active of {len(all_candidates)} total")

        prompt = self._build_global_ranking_prompt(all_candidates)
        try:
            text = await self.provider.chat_pro(prompt, max_tokens=8192, timeout=120)
            result = self.parse_json(text)
            if isinstance(result, dict) and result.get("ranked_stocks"):
                for i, r in enumerate(result["ranked_stocks"]):
                    r["rank"] = i + 1
                logger.info(f"[{self.name}] Done: top={result['ranked_stocks'][0].get('code','?')}")
                return result
            raise ValueError("Invalid LLM output")
        except Exception as e:
            logger.warning(f"[{self.name}] Failed ({e}), fallback to pool order")
            return self._fallback_global(all_candidates)

    def _build_global_ranking_prompt(self, candidates: List[Dict]) -> str:
        """构建全局排名 prompt"""
        cand_lines = []
        for c in candidates:
            code = c.get("code", "")
            name = c.get("name", "")
            node = c.get("node", "")
            eliminated = c.get("eliminated_by")
            elim_reason = c.get("eliminated_reason", "")

            nc = c.get("node_context", {})
            profit_pool = nc.get("profit_pool", "?")
            severity = nc.get("bottleneck_severity", "?")
            magnitude = nc.get("value_magnitude", "?")

            v = c.get("verification", {})
            dims = v.get("analysis_dimensions", [])
            dim_summary = "; ".join(
                f"{d.get('dimension','?')}={d.get('rating','?')}"
                for d in dims[:4]
            )
            roic_note = v.get("roic_note", "")[:60]

            if eliminated:
                status = f"[同源淘汰→输给{eliminated}] {elim_reason}"
            else:
                status = f"[活跃] 维度:{dim_summary}  ROIC:{roic_note}"

            cand_lines.append(
                f"[{candidates.index(c)+1}] {name}({code}) — 节点:{node} "
                f"(利润池:{profit_pool} 严重度:{severity} 量级:{magnitude})\n"
                f"    {status}"
            )

        return f"""你是首席投资官。综合以下各节点的已验证候选，给出全局投资价值排序。

## 候选公司列表
{chr(10).join(cand_lines)}

## 排序原则
1. 首要: 节点的利润池大小 + 供给刚性（利润的量和确定性）
2. 次要: 公司在节点内的不可替代性（护城河证据 + 竞争格局）
3. 辅助: 财务健康度（审计结果 + ROIC）、估值上行空间
4. 如果某节点内多家公司，只考虑该节点排名最高的
5. 被同源淘汰的公司排在最后（若仍有投资价值）
6. 每档排序必须引用事实证据

## 输出JSON
{{
  "ranked_stocks": [
    {{"rank": 1, "code": "688012", "name": "中微公司", "why": "不超过80字的事实依据"}}
  ],
  "runner_ups": [
    {{"code": "688525", "name": "佰维存储", "why": "不入选理由"}}
  ]
}}
只输出JSON。"""

    @staticmethod
    def _fallback_global(candidates: List[Dict]) -> Dict:
        """降级排序 — 按利润池大小"""
        pool_order = {"dominant_30_50pct": 5, "significant_15_30pct": 4,
                      "moderate_5_15pct": 3, "marginal_below_5pct": 2}
        sorted_c = sorted(candidates, key=lambda c: (
            -(pool_order.get(c.get("node_context", {}).get("profit_pool", ""), 1)),
            0 if c.get("eliminated_by") else 1,
        ))
        ranked = []
        for i, c in enumerate(sorted_c):
            if c.get("eliminated_by"):
                break
            ranked.append({"rank": i + 1, "code": c.get("code", ""),
                           "name": c.get("name", ""),
                           "why": "LLM排序失败, 按节点利润池降序"})
        return {"ranked_stocks": ranked, "runner_ups": []}
