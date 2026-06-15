"""
CoreScreeningAgent V5.15 — Step 6: 核心资产筛选
定位: 线索汇总 → 搜索 → 先比较 → 再验证 → 全局排名
方法: 四阶段流程 (Collect → Search → Compare+Verify → Rank)
原则: FinancialAuditor 标注不排除, 财务不是第一筛
"""
import asyncio, re
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger


def _j(obj, **kw):
    import json
    from decimal import Decimal
    class _SafeEncoder(json.JSONEncoder):
        def default(self, o):
            if isinstance(o, Decimal): return float(o)
            return super().default(o)
    kw.setdefault("ensure_ascii", False)
    kw.setdefault("cls", _SafeEncoder)
    return json.dumps(obj, **kw)


class CoreScreeningAgent(ResearchAgent):
    """核心资产筛选 V5.15 — 四阶段: 线索汇总 → 搜索 → 比较+验证 → 全局排名"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "CoreScreeningAgent"
        self._search_cache = {}  # 搜索缓存: {query: results}, 同 run 不重复搜

    async def _cached_search_web(self, query: str, num: int = 5) -> list:
        """带缓存的 search_web，同 run 内相同 query 只搜一次"""
        key = query.strip().lower()
        if key in self._search_cache:
            return self._search_cache[key]
        raw = await self.data_loader.search_web(query, num=num)
        self._search_cache[key] = raw
        return raw

    # ═══ 工具 ═══════════════════════════════════════

    @staticmethod
    def _clean_snippet(text: str) -> str:
        if not text: return ""
        if "%PDF" in text or "endstream" in text: return ""
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
        return text[:250]

    # ═══ Phase 1: 线索汇总 ═════════════════════════

    async def _collect_all_clues(self, industry: str, step3: Dict, step4: Dict, step5: Dict) -> Dict:
        """汇聚全部线索源 (V5.16: 源4-7合并移除, 统一走 asset_search_queries)。

        线索源:
          1. a_stock_mapping (Step3)       → direct_candidates
          2. bottleneck_inversions (Step3)  → direct_candidates
          3. asset_search_queries (Step3+4) → search_clues (Step4 已含 spillover)
          4. human_capital (Step3)         → search_clues

        Returns:
            {"direct_candidates": [...], "search_clues": [...], "seen_codes": set()}
        """
        direct = []
        seen = set()
        search_clues = []
        step3 = step3 or {}
        step4 = step4 or {}
        sd_out = step4.get("system_dynamics", {})

        # ── 源1: a_stock_mapping (Step 3 sub_processes) ──
        for node in step3.get("supply_chain_map", []):
            node_ctx = _extract_node_context(node)
            for sub in node.get("sub_processes", []):
                for s in sub.get("a_stock_mapping", []):
                    code = s.get("code", "")
                    if code and code not in seen:
                        seen.add(code)
                        cl = {
                            "code": code,
                            "name": s.get("name", code),
                            "_source_type": "a_stock_mapping",
                            "source_node": node.get("name", ""),
                            "source_node_info": node_ctx,
                            "investment_logic": s.get("investment_logic", ""),
                            "source": [{"step": "step3_a_stock",
                                        "field": sub.get("name", ""),
                                        "role": s.get("investment_logic", "")}],
                        }
                        direct.append(cl)

        # ── 源2: bottleneck_inversions (Step 3 Phase 2b) ──
        for inv in step3.get("bottleneck_inversions", []):
            base_bottleneck = inv.get("source_bottleneck", "")
            for comp in inv.get("decomposed_components", []):
                opportunity = comp.get("a_stock_opportunity", "")
                if opportunity not in ("high", "medium"):
                    continue
                for c in comp.get("a_stock_candidates", []):
                    code = c.get("code", "")
                    if code and code not in seen:
                        seen.add(code)
                        cl = {
                            "code": code,
                            "name": c.get("name", code),
                            "_source_type": "bottleneck_inversion",
                            "source_node": f"{base_bottleneck}→{comp.get('component','')}",
                            "source_node_info": {
                                "name": base_bottleneck,
                                "value_share_pct": comp.get("value_share_pct"),
                                "supplier_concentration": comp.get("supplier_concentration", ""),
                            },
                            "investment_logic": c.get("investment_logic", ""),
                            "source": [{"step": "step3_bottleneck_inversion",
                                        "field": comp.get("component", ""),
                                        "role": c.get("investment_logic", "")}],
                        }
                        direct.append(cl)

        # ── 源3: asset_search_queries (Step 3 + Step 4, 已含 spillover 搜索项) ──
        for q in step3.get("asset_search_queries", []):
            qry = q.get("query", "")
            if qry:
                search_clues.append({
                    "_source_type": "asset_search_query",
                    "query": f"A股 {qry} 上市公司 2026",
                    "priority": q.get("priority", "medium"),
                    "rationale": q.get("rationale", ""),
                    "mapping_type": q.get("mapping_type", "direct"),
                })
        for q in sd_out.get("asset_search_queries", []):
            qry = q.get("query", "")
            if qry:
                search_clues.append({
                    "_source_type": "asset_search_query",
                    "query": qry,  # Step 4 已经拼好了 query 前缀
                    "source": q.get("source", "step4"),
                    "source_node": q.get("source_node", ""),
                    "priority": q.get("priority", "medium"),
                    "mapping_type": q.get("mapping_type", "direct"),
                })

        # ── 源4: 人力资本线索 (对低国产化率且无已有标的的节点) ──
        for node in step3.get("supply_chain_map", []):
            subst = node.get("competitive_landscape", {}).get("china_substitution_rate", "")
            if subst in ("below_5pct", "5_20pct"):
                # 如果该节点已有 a_stock_mapping (直接标的)，不再搜人力资本
                has_mapping = any(
                    sub.get("a_stock_mapping") for sub in node.get("sub_processes", [])
                )
                if has_mapping:
                    continue
                leaders = node.get("competitive_landscape", {}).get("global_leaders", [])
                node_name = node.get("name", "")
                for leader in leaders[:2]:
                    search_clues.append({
                        "_source_type": "human_capital",
                        "query": f"前{leader} 团队 创业 A股 {node_name} 2026",
                        "leader": leader,
                        "source_node": node_name,
                    })

        logger.info(f"[{self.name}] Collect: {len(direct)} direct candidates, {len(search_clues)} search clues")
        return {"direct_candidates": direct, "search_clues": search_clues, "seen_codes": seen}

    # ═══ a_stock_mapping 交叉验证 ══════════════════

    async def _crosscheck_a_stock_mapping(self, direct_candidates: List[Dict],
                                            search_clues: List[Dict]) -> tuple:
        """验证 a_stock_mapping 标的在数据库中存在。

        Step 3 LLM 产出 a_stock_mapping（股票→产业链节点映射）。
        此方法做确定性事实核查：如果映射的股票代码在 DB 中不存在，
        说明可能是 LLM 幻觉，降级为 search_clue 让搜索重新验证。

        纯 DB 查询，不加 LLM 调用。
        """
        mapping_candidates = [c for c in direct_candidates if c.get("_source_type") == "a_stock_mapping"]
        non_mapping = [c for c in direct_candidates if c.get("_source_type") != "a_stock_mapping"]

        if not mapping_candidates:
            return direct_candidates, search_clues

        codes = [c["code"] for c in mapping_candidates]
        stock_info = await self.data_loader.load_fundamentals(codes)

        verified = []
        downgraded = []

        for cand in mapping_candidates:
            code = cand.get("code", "")
            info = stock_info.get(code)

            if info and info.get("name"):
                cand["name"] = info["name"]  # 用 DB 中的正式名称
                verified.append(cand)
            else:
                downgraded.append(cand)

        # 降级的标的转为搜索线索
        for cand in downgraded:
            node = cand.get("source_node", "")
            query = f"A股 {cand.get('name','')} {node} 上市公司"
            search_clues.append({
                "_source_type": "asset_search_query",
                "query": query,
                "priority": "high",
                "rationale": f"从a_stock_mapping降级: {node} 代码{cand.get('code','')} 未在DB中找到",
                "mapping_type": "direct",
            })

        n_verified = len(verified)
        n_downgraded = len(downgraded)
        if n_downgraded:
            logger.info(f"[{self.name}] a_stock_mapping crosscheck: {n_verified} verified, "
                        f"{n_downgraded} downgraded to search_clue")
        elif n_verified:
            logger.info(f"[{self.name}] a_stock_mapping crosscheck: all {n_verified} verified in DB")

        return non_mapping + verified, search_clues

    # ═══ Phase 2: 搜索 ═════════════════════════════

    async def _execute_search_clues(self, search_clues: List[Dict], trace=None) -> List[Dict]:
        """对 search_clues 并发执行 web search → LLM 提取股票代码 (最多 4 条并发)"""
        if not search_clues:
            return []

        sem = asyncio.Semaphore(4)

        async def _process_one(clue: Dict, idx: int) -> List[Dict]:
            """处理单条搜索线索，返回提取到的候选列表"""
            async with sem:
                st = clue.get("_source_type", "unknown")
                query = clue.get("query", "")
                mapping_type = clue.get("mapping_type", "direct")
                if not query:
                    return []

                logger.info(f"[{self.name}] Search clue [{idx+1}/{len(search_clues)}]: type={st} mapping={mapping_type} q={query[:80]}")

                # ── a_share_equivalent: 多角度深度搜索 ──
                if mapping_type == "a_share_equivalent":
                    # 从 query 中提取海外公司名 (A股 {name} ... → name)
                    import re
                    m = re.match(r'A股\s+(.+?)\s+(?:供应商|竞争对手|国产替代|上市公司|合作伙伴)', query)
                    foreign_company = m.group(1) if m else ""
                    if not foreign_company:
                        # 回退: 取第一个非中文词段
                        parts = re.split(r'[一-鿿\s]+', query.replace('A股', '').strip())
                        foreign_company = parts[0] if parts else ""

                    deep_queries = [
                        f"A股 {foreign_company} 供应商 合作伙伴 供货 上市公司 2026",
                        f"A股 {foreign_company} 竞争对手 国产替代 对标 上市公司 2026",
                        f"{foreign_company} 中国 供应链 合作 A股 供应商 2026",
                    ]
                    logger.info(f"[{self.name}] Deep search for '{foreign_company}': {len(deep_queries)} queries")

                    all_results = []
                    for dq in deep_queries:
                        try:
                            raw = await self._cached_search_web(dq, num=5)
                            for r in raw:
                                snippet = self._clean_snippet(r.get("snippet", ""))
                                if snippet:
                                    all_results.append({"title": r.get("title", ""), "snippet": snippet})
                            if trace: trace.record_search(dq, [])
                        except Exception:
                            pass

                    if not all_results:
                        return []

                    prompt = f"""你正在找A股中与海外公司"{foreign_company}"有关联的上市公司。
关联关系包括: 供应链供货、竞争对手、国产替代、技术合作、零部件供应。

从以下搜索结果中，找出所有明确提到的 A 股上市公司。
输出JSON数组: [{{"code":"688012","name":"中微公司","relevance":"为该公司的刻蚀设备供应商"}}]

搜索结果:
{_j(all_results)}

要求:
1. 每家公司输出 code + name + relevance (具体说明与{foreign_company}的关联)
2. 最多 8 家, 按关联紧密度排序
3. 只输出JSON数组"""
                else:
                    # ── 标准搜索路径 ──
                    results = []
                    try:
                        raw = await self._cached_search_web(query, num=5)
                        for r in raw:
                            snippet = self._clean_snippet(r.get("snippet", ""))
                            if snippet:
                                results.append({"title": r.get("title", ""), "snippet": snippet})
                    except Exception:
                        pass

                    if trace:
                        trace.record_search(query, results)

                    if not results:
                        return []

                    prompt = f"""从以下搜索结果中，找出明确提到的 A 股上市公司。
每家公司输出: code(股票代码), name(公司名), relevance(与搜索目标的相关性说明)

搜索目标: {query}

搜索结果:
{_j(results)}

输出JSON数组: [{{"code":"688012","name":"中微公司","relevance":"..."}}]
最多 5 家。只输出JSON数组。"""

                try:
                    text = await self.provider.chat_flash(prompt, max_tokens=1024, timeout=60)
                    if trace: trace.record_llm(prompt, text, model="deepseek-v4-flash")
                    parsed = self.parse_json(text)
                    raw_list = []
                    if isinstance(parsed, list):
                        raw_list = parsed
                    elif isinstance(parsed, dict):
                        for k in ("stocks", "candidates", "companies", "results", "data"):
                            raw_list = parsed.get(k, [])
                            if raw_list:
                                break
                    batch = []
                    for r in raw_list:
                        if isinstance(r, dict) and r.get("code"):
                            batch.append({
                                "code": r["code"],
                                "name": r.get("name", r["code"]),
                                "_source_type": st,
                                "source_node": clue.get("source_node", "") or st,
                                "source_node_info": {},
                                "investment_logic": r.get("relevance", clue.get("rationale", clue.get("reason", ""))),
                                "source": [{"step": f"step6_{st}", "field": clue.get("source_node", query[:40]),
                                            "role": r.get("relevance", "")}],
                            })
                    return batch
                except Exception as e:
                    logger.warning(f"[{self.name}] Extract failed for clue {idx}: {e}")
                    return []

        # 并发执行所有线索
        tasks = [_process_one(clue, i) for i, clue in enumerate(search_clues)]
        results = await asyncio.gather(*tasks)

        # 去重合并
        new_candidates = []
        seen_here = set()
        for batch in results:
            for c in batch:
                if c["code"] not in seen_here:
                    seen_here.add(c["code"])
                    new_candidates.append(c)

        logger.info(f"[{self.name}] Search done: {len(new_candidates)} new candidates from {len(search_clues)} clues")
        return new_candidates

    # ═══ 搜索线索去重 ═════════════════════════════

    async def _dedup_search_clues(self, search_clues: List[Dict]) -> List[Dict]:
        """对搜索线索做 LLM 语义去重，取代 Jaccard 硬阈值。

        - asset_search_query: LLM 判断语义相似度，保留 priority 更高的
        - human_capital: 按 leader 名去重 (精确匹配)
        """
        if not search_clues:
            return []

        # 1. human_capital: 按 leader 名去重 (精确匹配, 无需 LLM)
        kept = []
        seen_leaders = set()
        for clue in search_clues:
            if clue.get("_source_type") == "human_capital":
                leader = clue.get("leader", "")
                if leader and leader not in seen_leaders:
                    seen_leaders.add(leader)
                    kept.append(clue)
            else:
                kept.append(clue)

        # 2. asset_search_query: LLM 语义去重
        asset_queries = [c for c in kept if c.get("_source_type") == "asset_search_query"]
        non_asset = [c for c in kept if c.get("_source_type") != "asset_search_query"]

        if not asset_queries or len(asset_queries) <= 2:
            final = non_asset + asset_queries
            logger.info(f"[CoreScreeningAgent] Dedup clues: {len(search_clues)} -> {len(final)} (skip LLM, too few)")
            return final

        # 构建 LLM prompt
        prompt_lines = []
        for i, c in enumerate(asset_queries):
            q = c.get("query", "")
            priority = c.get("priority", "medium")
            context = c.get("rationale", "") or c.get("source_node", "") or c.get("source", "")
            prompt_lines.append(f"[{i}] query={q} | priority={priority} | context={context}")

        prompt = f"""你是一个A股产业链搜索策略师。以下是从产业链分析中提取的搜索线索，
每条线索代表一个寻找A股上市公司的搜索方向。

你的任务是将这些搜索条件整合为**最少但覆盖最全**的搜索查询集合。

## 背景
我们正在分析"{industry}"产业链，需要找到以下细分环节中的A股上市公司。
每条线索就是一个搜索条件，用于在互联网上找到相关公司。

每条线索格式: [序号] query=搜索词 | priority=优先级 | context=来源上下文

线索列表:
{chr(10).join(prompt_lines)}

## 整合原则
1. 两条线索指向同一产业环节（如同为"行星滚柱丝杠"的不同角度）
	   → 合并为一条更精准的查询，合并时保留关键信息
2. 两条线索指向不同细分环节（如"丝杠"vs"磨床设备"）
	   → 各自保留，因为需要覆盖独立子赛道
3. 合并后的每条查询应该有清晰的投资含义，覆盖一个有独立意义的细分方向
4. 不确定是否合并时，宁可分成两条，不要漏掉细分环节
5. 不要删除高优先级线索，优先保留包含具体公司名/产品名的查询

## 输出格式
{{"integrated_queries": [
	  {{"query": "整合后的搜索查询", "kept": [0, 1], "merged": [2, 3], "rationale": "合并原因"}},
	  ...
	]}}
只输出 JSON。"""

        try:
            text = await self.provider.chat_flash(prompt, max_tokens=1024, timeout=30)
            parsed = self.parse_json(text)
            integrated = []
            if isinstance(parsed, dict):
                integrated = parsed.get("integrated_queries", [])

            kept_indices = set()
            removed_indices = set()
            for entry in integrated:
                for k in (entry.get("kept") or []):
                    try:
                        kept_indices.add(int(k))
                    except (ValueError, TypeError):
                        pass
                for m in (entry.get("merged") or []):
                    try:
                        removed_indices.add(int(m))
                    except (ValueError, TypeError):
                        pass

            # LLM 输出异常时全保留
            if not integrated or not kept_indices or len(removed_indices) >= len(asset_queries):
                logger.warning(f"[CoreScreeningAgent] LLM dedup abnormal, keeping all {len(asset_queries)}")
                final = non_asset + asset_queries
                return final

            final = list(non_asset)
            for i, c in enumerate(asset_queries):
                if i not in removed_indices:
                    final.append(c)

            logger.info(f"[CoreScreeningAgent] Dedup clues: {len(search_clues)} -> {len(final)} (LLM, {len(integrated)} groups)")
            return final

        except Exception as e:
            logger.warning(f"[CoreScreeningAgent] LLM dedup failed: {e}, keeping all")
            return non_asset + asset_queries

    # ═══ Phase 3a: 同源比较 ═════════════════════════

    @staticmethod
    def _group_by_source(candidates: List[Dict], step3: Dict) -> List[Dict]:
        """按瓶颈节点分组候选。

        Returns:
            [{"node": "节点名", "node_context": {...}, "candidates": [...]}, ...]
        """
        # 建立 node_context 映射 (从 Step 3)
        node_ctx_map = {}
        for node in (step3 or {}).get("supply_chain_map", []):
            nname = node.get("name", "")
            if nname:
                node_ctx_map[nname] = _extract_node_context(node)

        groups = {}  # node_name -> list
        for c in candidates:
            src_node = c.get("source_node", "") or "_other"
            if src_node not in groups:
                groups[src_node] = []
            groups[src_node].append(c)

        result = []
        for node_name, cands in groups.items():
            ctx = node_ctx_map.get(node_name, {"name": node_name})
            result.append({"node": node_name, "node_context": ctx, "candidates": cands})

        # 排序: 候选多的组排前面
        result.sort(key=lambda g: -len(g["candidates"]))
        return result

    # ═══ Phase 3b: 逐只验证 ═════════════════════════

    async def _verify_single(self, candidate: Dict, industry: str,
                              stock_info_map: Dict, trace=None) -> Dict:
        """V3 Plan-Execute-Synthesize — LLM 策划 → 系统执行 → LLM 综合研判

        Phase 1 (PLAN):   LLM 收到标的+产业链角色+概念能力目录 → 策划验证计划
        Phase 2 (EXECUTE): 系统确定性执行 plan, 并行调用工具/服务 → 收集证据包
        Phase 3 (SYNTHESIZE): LLM 收到规划+真实证据 → 综合研判输出结构化结论
        """
        code = candidate["code"]
        name = candidate.get("name", code)

        logger.info(f"[{self.name}] Verifying {code} {name} (v3 PES)")

        src_info = candidate.get("source_node_info", {})
        source_context = self._fmt_source_context(candidate.get("source", []))

        # ═══ Phase 1: PLAN ════════════════════════════
        plan = await self._plan_verification(name, code, industry, src_info, source_context)
        if trace:
            trace.record_llm(f"Phase1_plan_{code}", str(plan)[:300], model="deepseek-v4-pro")

        # ═══ Phase 2: EXECUTE ═════════════════════════
        evidence = await self._execute_verification_plan(code, plan)
        if trace:
            trace.record_llm(f"Phase2_evidence_{code}", str(list(evidence.keys())), model="system")

        # ═══ Phase 3: SYNTHESIZE ══════════════════════
        analysis = await self._synthesize_verdict(name, code, industry, plan, evidence)
        if trace:
            trace.record_llm(f"Phase3_synthesis_{code}", str(analysis)[:200], model="deepseek-v4-pro")

        # ═══ 解析输出 (兼容旧 schema, 含 0 维度降级) ══
        lifecycle_stage = "startup"
        category = "future_strong"
        if isinstance(analysis, dict):
            raw_stage = (analysis.get("lifecycle_stage") or "").lower().strip()
            valid_stages = ("startup", "inflection", "growth", "mature",
                            "cyclical_bottom", "cyclical_decline")
            if raw_stage in valid_stages:
                lifecycle_stage = raw_stage

            dims = analysis.get("analysis_dimensions", [])
            if not dims:
                # ★ 0 维度降级: 证据不足以做出判断, 放入观察名单
                category = "watchlist"
                logger.warning(f"[{self.name}] {code}: 0 dims -> downgraded to watchlist")
            else:
                cat = (analysis.get("category_suggestion") or "").lower().strip()
                if cat in ("current_strong", "future_strong", "watchlist"):
                    category = cat

        result_dict = {
            "code": code,
            "name": name,
            "_source_type": candidate.get("_source_type", ""),
            "source_node": candidate.get("source_node", ""),
            "source_node_info": candidate.get("source_node_info", {}),
            "node_context": candidate.get("source_node_info", {}),
            "source": candidate.get("source", []),
            "flags": candidate.get("flags", []),
            "company_stage": lifecycle_stage,
            "category": category,
            "verification": {
                "analysis_dimensions": (analysis or {}).get("analysis_dimensions", []),
                "industry_context": (analysis or {}).get("industry_context", ""),
                "profit_capture_thesis": (analysis or {}).get("profit_capture_thesis", ""),
                "thesis_breakers": (analysis or {}).get("thesis_breakers", []),
                "watch_events": (analysis or {}).get("watch_events", []),
                "roic_note": (analysis or {}).get("roic_note", ""),
            },
        }

        dim_count = len((analysis or {}).get("analysis_dimensions", []))
        logger.info(f"[{self.name}] Verified {code}: category={category}, "
                    f"dimensions={dim_count}")
        return result_dict

    # ═══ V3 PES 子方法 ═══════════════════════════════

    async def _plan_verification(self, name: str, code: str, industry: str,
                                  node_context: Dict, source_context: str) -> Dict:
        """Phase 1: LLM 策划验证计划"""
        from app.domain.research.agents.research_tools import build_plan_prompt
        prompt = build_plan_prompt(name, code, industry, node_context, source_context)
        try:
            text = await self.provider.chat_pro(prompt, max_tokens=3072, timeout=120)
            plan = self.parse_json(text)
            if isinstance(plan, dict) and plan.get("investigations"):
                logger.info(f"[{self.name}] Plan {code}: {len(plan['investigations'])} investigations")
                return plan
            logger.warning(f"[{self.name}] Plan {code}: missing investigations, using defaults")
            return self._default_plan(code)
        except Exception as e:
            logger.warning(f"[{self.name}] Plan {code} failed: {e}, using defaults")
            return self._default_plan(code)

    async def _execute_verification_plan(self, code: str, plan: Dict) -> Dict:
        """Phase 2: 系统确定性执行验证计划

        读取 LLM 策划的 plan JSON, 调用对应 TOOL_REGISTRY handler。
        不走 tool calling, 直接调异步函数, 并行执行, 异常隔离。
        """
        from app.domain.research.agents.base import TOOL_REGISTRY
        import asyncio

        evidence = {}

        # 1. 执行 investigations (财务数据查询)
        fin_tasks = []
        for inv in plan.get("investigations", []):
            tool_name = inv.get("tool", "query_financial_data")
            params = inv.get("params", {})
            params.setdefault("code", code)
            handler = TOOL_REGISTRY.get(tool_name)
            if handler:
                fin_tasks.append(_safe_tool_call(handler, tool_name, params))

        # 2. 执行估值 (如需要)
        val_needed = plan.get("valuation", {}).get("needed", False)
        val_future = None
        if val_needed:
            val_params = {
                "code": code,
                "methods": plan["valuation"].get("methods", ["peg", "pe"]),
                "params": plan["valuation"].get("params", {}),
            }
            val_handler = TOOL_REGISTRY.get("calculate_valuation")
            if val_handler:
                val_future = asyncio.ensure_future(
                    _safe_tool_call(val_handler, "calculate_valuation", val_params)
                )

        # 3. 执行搜索
        search_tasks = []
        for sq in plan.get("search_queries", []):
            query = sq.get("query", "")
            if query:
                search_handler = TOOL_REGISTRY.get("web_search")
                if search_handler:
                    search_tasks.append(
                        _safe_tool_call(search_handler, "web_search",
                                        {"query": query, "num": 5})
                    )

        # 4. 保底: 确保至少有一次 financial data 查询
        if not fin_tasks:
            fin_handler = TOOL_REGISTRY.get("query_financial_data")
            if fin_handler:
                fin_tasks.append(
                    _safe_tool_call(fin_handler, "query_financial_data", {"code": code})
                )

        # 5. 并行执行所有任务
        fin_results = await asyncio.gather(*fin_tasks, return_exceptions=True) if fin_tasks else []
        search_results = await asyncio.gather(*search_tasks, return_exceptions=True) if search_tasks else []
        val_result = await val_future if val_future else None

        # 按概念分组整理证据 (仅财务数据按概念分组, 搜索不分组)
        for i, inv in enumerate(plan.get("investigations", [])):
            concept = inv.get("concept", f"dim_{i}")
            concept_data = {"financial": None}

            if i < len(fin_results) and not isinstance(fin_results[i], Exception):
                concept_data["financial"] = _truncate_dict(fin_results[i])

            evidence[concept] = concept_data

        # 所有搜索结果汇总 (不按概念分组 — 之前的关键词子串匹配从未工作)
        search_all = []
        for sr in search_results:
            if isinstance(sr, Exception):
                continue
            if isinstance(sr, list):
                for item in sr:
                    if isinstance(item, dict) and item.get("snippet"):
                        search_all.append(item["snippet"][:200])
        if search_all:
            evidence["search_all"] = search_all[:15]  # 最多15条

        # 估值结果
        if val_result and not isinstance(val_result, Exception):
            evidence["valuation_result"] = val_result

        logger.info(f"[{self.name}] Execute {code}: "
                    f"{len(fin_tasks)} fin, {len(search_tasks)} search, val={val_needed}")
        return evidence

    async def _synthesize_verdict(self, name: str, code: str, industry: str,
                                   plan: Dict, evidence: Dict) -> Dict:
        """Phase 3: LLM 基于证据做综合研判 (带1次重试, 应对 analysis_dimensions 缺失)"""
        from app.domain.research.agents.research_tools import build_synthesis_prompt
        prompt = build_synthesis_prompt(name, code, industry, plan, evidence)

        for attempt in range(2):
            try:
                text = await self.provider.chat_pro(prompt, max_tokens=4096, timeout=180)
                result = self.parse_json(text)
                if isinstance(result, dict) and result.get("analysis_dimensions"):
                    logger.info(f"[{self.name}] Synthesis {code}: "
                                f"{len(result['analysis_dimensions'])} dims (attempt {attempt+1})")
                    return result
                logger.warning(f"[{self.name}] Synthesis {code}: "
                               f"missing analysis_dimensions (attempt {attempt+1})")
                if attempt == 0:
                    prompt += ("\n\n**警告: 上次输出缺少 analysis_dimensions 数组。"
                               "必须输出至少 1 个 analysis_dimensions 维度。"
                               "证据不足时也需输出 1 个维度并在 evidence 中注明'证据有限'。**\n")
            except Exception as e:
                logger.warning(f"[{self.name}] Synthesis {code} failed (attempt {attempt+1}): {e}")

        return {}

    def _default_plan(self, code: str) -> Dict:
        """Plan 失败时的兜底计划 — 保底查一次财务数据"""
        return {
            "preliminary_judgment": "",
            "investigations": [
                {
                    "concept": "财务基本面",
                    "tool": "query_financial_data",
                    "rationale": "兜底: 获取财务数据",
                    "params": {"code": code},
                },
            ],
            "valuation": {"needed": False},
            "search_queries": [],
        }

    def _fmt_source_context(self, sources: list) -> str:
        """格式化来源线索供 plan prompt 使用"""
        if not sources:
            return ""
        lines = []
        for s in sources[:5]:
            step = s.get("step", "?")
            role = s.get("role", "")[:100]
            lines.append(f"- {step}: {role}")
        return "\n".join(lines)

    # ═══ Phase 3a-1: LLM 快速预筛选 ═══════════════

    async def _llm_screen_group(self, candidates: List[Dict],
                                 node_context: Dict) -> List[Dict]:
        """零搜索, 纯 LLM 快速筛掉明显不相关的候选。

        只筛明显不相关的, 边界情况全保留。失败时全保留。
        """
        if len(candidates) <= 3:
            return candidates

        node_name = node_context.get("name", "")
        cand_lines = [f"{c.get('name','?')}({c.get('code','?')})" for c in candidates]

        prompt = (
            f"快速筛选以下候选在\"{node_name}\"环节的相关性。\n\n"
            f"环节背景: {node_name}\n"
            f"利润池: {node_context.get('profit_pool','?')}\n"
            f"供给刚性: {node_context.get('supply_rigidity','?')}\n"
            f"瓶颈描述: {node_context.get('bottleneck_narrative','')[:300]}\n\n"
            f"候选:\n{chr(10).join(cand_lines)}\n\n"
            f"哪些候选明显不具备参与该环节的资格？例如：行业完全不相关、产品不覆盖该环节。\n"
            f"边界情况不排除。宁可多留，不要误杀。\n"
            f"输出JSON: {{\"remove\": [\"code1\", \"code2\"]}}\n"
            f"只输出JSON。"
        )
        try:
            text = await self.provider.chat_flash(prompt, max_tokens=1024, timeout=60)
            parsed = self.parse_json(text)
            remove_codes = set()
            if isinstance(parsed, dict):
                rc = parsed.get("remove", [])
                if isinstance(rc, list):
                    remove_codes = set(rc)
            elif isinstance(parsed, list):
                remove_codes = set(parsed)

            if remove_codes:
                survivors = [c for c in candidates if c.get("code") not in remove_codes]
                removed = [c for c in candidates if c.get("code") in remove_codes]
                logger.info(f"[{self.name}] Phase A screen '{node_name}': "
                            f"{len(candidates)}->{len(survivors)} (removed: {[r.get('code') for r in removed]})")
                return survivors if survivors else candidates
            return candidates
        except Exception as e:
            logger.warning(f"[{self.name}] Phase A screen failed for '{node_name}': {e}, keeping all")
            return candidates

    # ═══ 主入口 (V5.15 四阶段) ═════════════════════

    async def analyze(self, ctx: Dict[str, Any] = None, trace=None) -> Dict[str, Any]:
        ctx = await self.load_context(ctx or {})
        if not self.provider:
            return {"agent": self.name, "error": "No AI provider"}

        industry = ctx.get("industry", "未指定")
        step3 = ctx.get("step3_output", ctx.get("supply_chain_map_ctx", {}))
        step4 = ctx.get("step4_output", {})
        step5 = ctx.get("step5_output", {})

        logger.info(f"[{self.name}] === V5.15 4-Phase Screening: {industry} ===")

        # ═══ Phase 1: 线索汇总 ═════════════════════
        clues = await self._collect_all_clues(industry, step3, step4, step5)

        # ★ a_stock_mapping 交叉验证: 检查映射的股票是否存在于 DB
        clues["direct_candidates"], clues["search_clues"] = await self._crosscheck_a_stock_mapping(
            clues["direct_candidates"], clues["search_clues"]
        )

        # ═══ Phase 2: 搜索 ═══════════════════════════
        # 取前12条 search_clues (按优先级: a_share_equivalent > asset_search_query > human_capital > tag)
        priority_map = {"asset_search_query": 0, "human_capital": 1}
        def _sort_key(c):
            base = priority_map.get(c.get("_source_type", ""), 99)
            mt = c.get("mapping_type", "direct")
            # a_share_equivalent 需要深度搜索, 排在最前面
            mapping_bonus = -1 if mt == "a_share_equivalent" else 0
            return (base + mapping_bonus)
        search_clues = await self._dedup_search_clues(sorted(clues["search_clues"], key=_sort_key))
        search_candidates = await self._execute_search_clues(search_clues, trace)
        all_candidates = clues["direct_candidates"] + search_candidates

        # 去重
        seen = set(clues["seen_codes"])
        deduped = []
        for c in all_candidates:
            code = c.get("code", "")
            if code and code not in seen:
                seen.add(code)
                deduped.append(c)

        logger.info(f"[{self.name}] Pool: {len(deduped)} candidates ({len(clues['direct_candidates'])} direct + {len(search_candidates)} search)")

        if not deduped:
            return self._empty_result(industry)

        # ── 硬过滤器 + 基本面 (生命周期由 _verify_single 中 LLM 自主判定) ──
        from app.domain.research.services.screening_gate import hard_filter

        codes = [c["code"] for c in deduped[:20]]
        stock_info_map = await self.data_loader.load_fundamentals(codes) if codes else {}
        cycle_position = (step3 if isinstance(step3, dict) else {}).get("cycle_position", "")

        # 硬过滤器: 只排除 ST / 低流动性
        passed, filtered = hard_filter(deduped, stock_info_map)
        if not passed:
            logger.warning(f"[{self.name}] All {len(deduped)} candidates filtered by hard_filter")
            return self._empty_result(industry, filtered=filtered, cycle_position=cycle_position)

        # ═══ Phase 3a: 分组 → 3a-1预筛选 → 3a-2同源比较 ════
        from app.domain.research.agents.candidate_comparator import CandidateComparator
        comparator = CandidateComparator(provider=self.provider, search_cache=self._search_cache)
        groups = self._group_by_source(passed, step3)
        all_comparisons = []
        to_verify = []  # (candidate, is_winner, eliminated_by, eliminated_reason)

        for group in groups:
            cands = group["candidates"]
            node_name = group["node"]
            node_ctx = group["node_context"]

            # Phase A: 候选太多则 LLM 快速筛 (>=4家)
            if len(cands) >= 4:
                cands = await self._llm_screen_group(cands, node_ctx)

            # Phase B: 同源比较 (搜索+LLM, 不排名, 只排除)
            if len(cands) >= 2:
                result = await comparator.compare_within_source(cands, node_ctx)
                all_comparisons.append(result)

                excluded_codes = {s["code"] for s in result.get("exclusion_suggestions", [])}
                for c in cands:
                    if c["code"] in excluded_codes:
                        reason = next(
                            (s.get("reason", "比较排除") for s in result.get("exclusion_suggestions", [])
                             if s.get("code") == c["code"]),
                            "同源比较中竞争力不足")
                        to_verify.append((c, False, "comparison_excluded", reason))
                    else:
                        to_verify.append((c, True, None, None))
            elif len(cands) == 1:
                all_comparisons.append({
                    "source": node_name,
                    "observations": [{"code": cands[0]["code"], "name": cands[0].get("name", "")}],
                    "exclusion_suggestions": [],
                })
                to_verify.append((cands[0], True, None, None))
            # len(cands)==0: 全部被Phase A筛掉

        # ═══ Phase 3b: 逐只验证 (仅胜出者) ════════
        verified = []
        for cand, is_winner, elim_by, elim_reason in to_verify:
            if is_winner:
                # ★ 溢出候选 (audit_pass_no_compare): 跳过全套验证, 直接进 watchlist
                if cand.get("_audit_pass_no_compare"):
                    v = {
                        "code": cand["code"],
                        "name": cand.get("name", cand["code"]),
                        "_source_type": cand.get("_source_type", ""),
                        "source_node": cand.get("source_node", ""),
                        "node_context": cand.get("source_node_info", {}),
                        "source": cand.get("source", []),
                        "_eliminated_by": None,
                        "company_stage": "unknown",  # 溢出候选, 不单独验证
                        "category": "watchlist",
                        "verification": {},
                    }
                    v.setdefault("_tags", []).append("overflow_audit_pass")
                    verified.append(v)
                else:
                    v = await self._verify_single(cand, industry, stock_info_map, trace)
                    v["_eliminated_by"] = None
                    verified.append(v)
            else:
                cand["_eliminated_by"] = elim_by
                cand["_eliminated_reason"] = elim_reason
                # 输家不做全套验证, 只保留基础信息
                verified.append({
                    "code": cand["code"],
                    "name": cand.get("name", cand["code"]),
                    "_source_type": cand.get("_source_type", ""),
                    "source_node": cand.get("source_node", ""),
                    "node_context": cand.get("source_node_info", {}),
                    "source": cand.get("source", []),
                    "_eliminated_by": elim_by,
                    "_eliminated_reason": elim_reason,
                    "company_stage": "unknown",  # 淘汰者, 不单独验证
                    "category": "watchlist",
                    "verification": {},
                })

        # ═══ Phase 4: 全局排名 ══════════════════════
        ranking = await comparator.global_ranking(verified)
        ranked_stocks = ranking.get("ranked_stocks", [])

        # ★ V5.16: ranked_stocks 是轻量摘要 (rank/code/name/why),
        #          从 verified 中补全 verification/category 等字段
        verified_map = {c["code"]: c for c in verified if c.get("code")}
        enriched_ranked = []
        for r in ranked_stocks:
            code = r.get("code", "")
            v = verified_map.get(code, {})
            enriched = dict(r)
            if v.get("verification"):
                enriched["verification"] = v.get("verification")
            if v.get("category"):
                enriched["category"] = v.get("category")
            enriched_ranked.append(enriched)
        ranked_stocks = enriched_ranked

        # ── 输出构建 ──
        future_strong = [
            c for c in verified
            if c.get("category") in ("future_strong", "current_strong")
            and not c.get("_eliminated_by")
        ]
        watchlist_out = [
            c for c in verified
            if c.get("category") == "watchlist" and not c.get("_eliminated_by")
        ]
        eliminated = [c for c in verified if c.get("_eliminated_by")]

        # 分类统计
        current_strong = [c for c in verified if c.get("category") == "current_strong"]
        logger.info(f"[{self.name}] Done: {len(current_strong)} strong, {len(future_strong)} future, "
                    f"{len(watchlist_out)} watchlist, {len(eliminated)} eliminated")

        # 线索来源统计
        source_counts = {}
        for c in passed:
            st = c.get("_source_type", "unknown")
            source_counts[st] = source_counts.get(st, 0) + 1

        # Step 3 回写
        backfill = {}
        for code, info in stock_info_map.items():
            if info.get("roe"):
                backfill[code] = {"actual_roe": info["roe"]}

        return {
            "agent": self.name,
            "confidence": "high" if ranked_stocks else "medium",
            "lifecycle_gate": {"cycle_position": cycle_position, "gate_mode": "auto"},
            "candidate_pool": {
                "total_collected": len(deduped),
                "after_prescreen": len(passed),
                "ranked": len(ranked_stocks),
            },
            "ranked_stocks": ranked_stocks,
            "future_strong_candidates": future_strong,
            "watchlist": watchlist_out,
            "eliminated": eliminated,
            "candidates_map": verified_map,  # ★ V5.16: code→全量数据映射, 方便消费者按 code 查找
            "comparisons": all_comparisons,
            "source_detail": source_counts,
            "step3_backfill": backfill,
            "filter_log": filtered,
        }


    # ═══ 旧候选聚合 (标记 deprecated, 对外兼容) ═══

    async def _aggregate_candidates(self, industry: str, step3: Dict, step4: Dict, step5: Dict, trace=None) -> List[Dict]:
        """(Deprecated V5.15) 保留供外部直接调用兼容, 新 analyze 不再使用"""
        logger.warning(f"[{self.name}] _aggregate_candidates deprecated, use _collect_all_clues + _execute_search_clues")
        clues = await self._collect_all_clues(industry, step3, step4, step5)
        search_cands = await self._execute_search_clues(clues["search_clues"], trace)
        result = clues["direct_candidates"] + search_cands
        seen = set(clues["seen_codes"])
        return [c for c in result if c.get("code") and c["code"] not in seen or seen.add(c["code"])]
    # ═══ 工具 ═══════════════════════════════════════

    def _empty_result(self, industry, filtered=None, cycle_position="", gate_mode="growth"):
        return {
            "agent": self.name,
            "confidence": "insufficient_data",
            "confidence_note": f"{industry}: 无候选股票",
            "lifecycle_gate": {"cycle_position": cycle_position, "gate_mode": gate_mode},
            "candidate_pool": {"total_collected": 0, "after_prescreen": 0, "ranked": 0},
            "ranked_stocks": [],
            "future_strong_candidates": [],
            "watchlist": [],
            "comparisons": [],
            "source_detail": {},
            "step3_backfill": {},
            "filter_log": filtered or [],
        }

    # ═══ Patch 补跑 ═══════════════════════════════

    async def patch_verify_single(self, stock_code: str, step6_checkpoint: dict,
                                   industry: str, trace=None) -> dict:
        """增量补跑单只股票的 verification (用于 parse_error / moat_failed)

        Args:
            stock_code: 股票代码
            step6_checkpoint: 已有的 step6 checkpoint output (含 candidates)
            industry: 行业

        Returns:
            updated_candidate: 更新后的 candidate dict (仅 verification 部分更新)
        """
        # 1. 找现有 candidate
        all_cands = (
            step6_checkpoint.get("future_strong_candidates", []) +
            step6_checkpoint.get("watchlist", []) +
            step6_checkpoint.get("eliminated", [])
        )
        cand = next((c for c in all_cands if c.get("code") == stock_code), None)
        if not cand:
            return {"error": f"{stock_code} not found in checkpoint"}

        stock_info_map = {}
        try:
            codes = [stock_code]
            stock_info_map = await self.data_loader.load_fundamentals(codes) if codes else {}
        except Exception:
            pass

        logger.info(f"[{self.name}] Patch verify {stock_code}: re-running verification")
        v = await self._verify_single(cand, industry, stock_info_map, trace)

        # 2. 只更新 verification 部分
        cand["verification"] = v.get("verification", {})
        cand["company_stage"] = v.get("company_stage", "unknown")
        cand["category"] = v.get("category", cand.get("category", "watchlist"))
        cand["risk_tags"] = v.get("risk_tags", cand.get("risk_tags", []))
        return cand

    # ═══ 基类 ═══════════════════════════════════════

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return await super().load_context(ctx)

    @staticmethod
    def build_prompt(ctx): return "CoreScreeningAgent V5.15"

    @staticmethod
    async def stream(ctx): yield "streaming not implemented"


# ═══ 模块级工具 ═══════════════════════════════════

def _extract_node_context(node: Dict) -> Dict:
    """从 Step 3 supply_chain_map 节点提取比较用的上下文"""
    cl = node.get("competitive_landscape", {})
    return {
        "name": node.get("name", ""),
        "bottleneck_narrative": (node.get("bottleneck_narrative", "") or "")[:300],
        "profit_pool": node.get("profit_pool", {}).get("share_of_industry_profit", ""),
        "margin_level": node.get("profit_pool", {}).get("margin_level", ""),
        "supply_rigidity": node.get("supply_rigidity", {}).get("severity", ""),
        "china_substitution_rate": cl.get("china_substitution_rate", ""),
        "competitive_structure": cl.get("structure", ""),
        "global_leaders": cl.get("global_leaders", []),
        "value_magnitude": "",
        "bottleneck_severity": node.get("supply_rigidity", {}).get("severity", ""),
    }


async def _safe_tool_call(handler, name: str, params: dict) -> dict:
    """安全调用 TOOL_REGISTRY handler, 异常返回 dict"""
    try:
        result = await handler(**params)
        return result or {}
    except Exception as e:
        logger.warning(f"[_safe_tool_call] {name} failed: {e}")
        return {"_tool_error": str(e), "_tool_name": name}


def _truncate_dict(d: dict, max_len: int = 5000) -> dict:
    """截断 dict 中的长字符串/列表, 防止证据包过大"""
    import json as _j
    text = _j.dumps(d, ensure_ascii=False, default=str)
    if len(text) <= max_len:
        return d
    # 截断每个值到 200 字符
    truncated = {}
    for k, v in d.items():
        if isinstance(v, str) and len(v) > 200:
            truncated[k] = v[:200] + "..."
        elif isinstance(v, (list, dict)):
            txt = _j.dumps(v, ensure_ascii=False, default=str)
            truncated[k] = txt[:300] + "..." if len(txt) > 300 else v
        else:
            truncated[k] = v
    return truncated
