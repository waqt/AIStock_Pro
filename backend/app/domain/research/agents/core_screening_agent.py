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

    # ═══ 工具 ═══════════════════════════════════════

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

        # ── 源4: 人力资本线索 (对低国产化率节点) ──
        for node in step3.get("supply_chain_map", []):
            subst = node.get("competitive_landscape", {}).get("china_substitution_rate", "")
            if subst in ("below_5pct", "5_20pct"):
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
                            raw = await self.data_loader.search_web(dq, num=5)
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
                        raw = await self.data_loader.search_web(query, num=5)
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
                              stock_info_map: Dict, fin_map: Dict,
                              stage_map: Dict, trace=None) -> Dict:
        """对单只候选做完整验证: 财务审计 → 6维护城河 → ROIC → 估值"""
        code = candidate["code"]
        name = candidate.get("name", code)

        logger.info(f"[{self.name}] Verifying {code} {name}")

        # 1. FinancialAudit (s 参数 bug)
        from app.domain.research.agents.financial_auditor import FinancialAuditor
        auditor = FinancialAuditor(provider=self.provider)
        audit = {}
        try:
            audit = await auditor.analyze({"stock_code": code, "stock_name": name, "industry": industry})
            if not audit or not audit.get("verdict"):
                audit = {"verdict": "SKIP", "score": 0, "reason": "Auditor returned empty"}
        except Exception as e:
            logger.warning(f"[{self.name}] Audit failed for {code}: {e}")
            audit = {"verdict": "SKIP", "score": 0, "error": str(e)}

        # 2. ROIC/ROIIC 计算 + 落库 (★ 按需加载 + 搜索兜底)
        from app.framework.finance.roiic import compute_roic, compute_roiic
        from app.domain.quant.engine.indicator_store import store_financial_indicator
        roic_val, roiic_val = None, None

        # 2a. 从 fin_map 获取财务数据 (预加载)
        fin = fin_map.get(code, {}).get("quarters", [])

        # 2b. 如果 fin_map 没数据或不足4季, 按需加载
        if not fin or len(fin) < 4:
            try:
                on_demand = await self.data_loader.load_financial_statements(code, periods=8)
                if on_demand and on_demand.get("quarters"):
                    q = on_demand["quarters"]
                    logger.info(f"[{self.name}] On-demand fin loaded for {code}: {len(q)} quarters")
                    fin = q
            except Exception as e:
                logger.warning(f"[{self.name}] On-demand fin load failed for {code}: {e}")

        # 2c. ROIC 计算
        roic_source = "none"
        if fin and len(fin) >= 4:
            try:
                recent_first = list(reversed(fin))
                company_stage = stage_map.get(code, "startup")
                capitalize_rd = company_stage in ["startup", "inflection", "growth"]
                roic_data = compute_roic(recent_first, capitalize_rd=capitalize_rd)
                roiic_data = compute_roiic(recent_first, capitalize_rd=capitalize_rd) if len(recent_first) >= 8 else {}

                if roic_data.get("roic_pct") is not None:
                    roic_val = roic_data["roic_pct"]
                    roic_source = "db_computed"
                elif roic_data.get("error"):
                    logger.warning(f"[{self.name}] ROIC compute error for {code}: {roic_data['error']}")

                if roiic_data.get("roiic_pct") is not None:
                    roiic_val = roiic_data["roiic_pct"]

                # 落库
                if roic_val is not None:
                    report_date = recent_first[0].get("report_date", "")[:10]
                    store_financial_indicator(code, report_date, {
                        "roic": roic_data.get("roic"),
                        "roic_pct": roic_val,
                        "roiic": roiic_data.get("roiic"),
                        "roiic_pct": roiic_val,
                        "capitalized_rd": capitalize_rd,
                    })
            except Exception as e:
                logger.warning(f"[{self.name}] ROIC compute failed for {code}: {e}")

        # 2d. 搜索兜底: 如果DB计算失败, web search 获取 ROIC
        if roic_val is None:
            try:
                search_q = f"{name} {code} ROIC 投入资本回报率 2025 2026"
                search_results = await self.data_loader.search_web(search_q, num=3)
                for sr in search_results:
                    snippet = (sr.get("snippet", "") or "")[:300]
                    # 正则: "ROIC" 附近找数字+百分号
                    import re
                    matches = re.findall(r'ROIC[^\d]*?([\d]+\.[\d]|[\d]+)%', snippet, re.IGNORECASE)
                    if not matches:
                        matches = re.findall(r'投入资本回报率[^\d]*?([\d]+\.[\d]|[\d]+)%', snippet)
                    if not matches:
                        matches = re.findall(r'(?:ROIC|回报率)[：:\s]*([\d]+\.[\d]+)%', snippet, re.IGNORECASE)
                    if matches:
                        roic_val = float(matches[0])
                        roic_source = "web_search"
                        logger.info(f"[{self.name}] ROIC from search for {code}: {roic_val}%")
                        break
            except Exception as e:
                logger.warning(f"[{self.name}] ROIC search fallback failed for {code}: {e}")

        # 填充结果到 candidate, 供下游使用
        candidate["_roic_val"] = roic_val
        candidate["_roic_source"] = roic_source

        # 3. 6维护城河画像 (LLM + 搜索)
        search_data = await self._search_adaptive([[
            f"{name} {code} 行业地位 市场份额 竞争壁垒 护城河",
            f"{name} {code} 定价权 毛利率 客户 认证",
            f"{name} {code} moat competitive advantage 2026",
        ]], num=3, trace=trace)

        # 注入节点上下文
        src_info = candidate.get("source_node_info", {})
        prompt = self._build_moat_prompt(
            name, code, industry, candidate.get("source", []), search_data,
            node_context=src_info, roic=roic_val)

        moat_result = {}
        moat_status = "pending"  # ★ 三态: assessed / insufficient_data / failed
        try:
            text = await self.provider.chat_flash(prompt, max_tokens=4096, timeout=90)
            if trace: trace.record_llm(prompt, text, model="deepseek-v4-flash")
            result = self.parse_json(text)
            if isinstance(result, dict) and result.get("moat_profile"):
                moat_result = result
                moat_status = "assessed"
        except asyncio.TimeoutError:
            logger.warning(f"[{self.name}] Moat profiling timeout for {code}, retrying...")
            # ★ 超时重试: 简化 prompt, 仅基于节点背景推断 position_power+certification_power
            try:
                retry_prompt = (
                    f"基于以下节点背景, 判断{name}({code})在'{industry}'的6维护城河。\n"
                    f"节点背景: {_j(src_info)}\n"
                    f"重点: 该企业是否处于产业链必经节点(position_power)? "
                    f"客户切换成本是否高(certification_power)? 技术路线是否正确(cognitive_power)?\n"
                    f"输出JSON: {{\"moat_profile\":{{\"position_power\":\"strong/weak/unknown\","
                    f"\"pricing_power\":\"strong/weak/unknown\","
                    f"\"certification_power\":\"strong/weak/unknown\","
                    f"\"cognitive_power\":\"strong/weak/unknown\"}}}}"
                )
                text2 = await self.provider.chat_flash(retry_prompt, max_tokens=2048, timeout=60)
                result2 = self.parse_json(text2)
                if isinstance(result2, dict) and result2.get("moat_profile"):
                    moat_result = result2
                    moat_status = "assessed"
                    logger.info(f"[{self.name}] Moat retry succeeded for {code}")
            except Exception:
                logger.warning(f"[{self.name}] Moat retry also failed for {code}")
                moat_status = "failed"
        except Exception as e:
            logger.warning(f"[{self.name}] Moat profiling failed for {code}: {e}")
            moat_status = "failed"

        # ★ 判断是否为数据不足导致的失败 (search_data is List[Dict], not dict)
        if moat_status != "assessed":
            has_node_context = bool(src_info and src_info.get("bottleneck_narrative"))
            has_search_results = bool(search_data and any(
                d.get("results") for d in search_data if isinstance(d, dict)))
            if not has_search_results and not has_node_context:
                moat_status = "insufficient_data"

        # 4. ValuationPricer (估值)
        valuation = {}
        try:
            from app.domain.research.agents.valuation_pricer import ValuationPricer
            pricer = ValuationPricer(provider=self.provider)
            stock_info = stock_info_map.get(code, {})
            valuation = await pricer.analyze({
                "stock_code": code,
                "stock_name": name,
                "industry": industry,
                "stage": stage_map.get(code, "startup"),
                "financial_data": fin_map.get(code, {}),
                "moat_profile": moat_result.get("moat_profile", {}),
                "market_capital": stock_info.get("market_capital"),
                "pe_ttm": stock_info.get("pe_ttm") or stock_info.get("pe"),
                "pb": stock_info.get("pb"),
            })
            # ★ 标准化估值字段, 补 LLM 可能缺失的嵌套结构
            if isinstance(valuation, dict) and not valuation.get("parse_error"):
                if "target_valuation" not in valuation or not valuation.get("target_valuation"):
                    valuation["target_valuation"] = {}
                tv = valuation["target_valuation"]
                tv.setdefault("base_case_mcap", None)
                tv.setdefault("bull_case_mcap", None)
                tv.setdefault("bear_case_mcap", None)
                tv.setdefault("upside_pct", None)
                tv.setdefault("downside_pct", None)

                if "position_suggest" not in valuation or not valuation.get("position_suggest"):
                    valuation["position_suggest"] = {}
                ps = valuation["position_suggest"]
                ps.setdefault("allocation_pct", None)
                ps.setdefault("entry_strategy", "")
                ps.setdefault("exit_trigger", "")

                if "scenarios" not in valuation or not valuation.get("scenarios"):
                    valuation["scenarios"] = {}
                if "quality_check" not in valuation or not valuation.get("quality_check"):
                    valuation["quality_check"] = {}
        except Exception as e:
            logger.warning(f"[{self.name}] Valuation failed for {code}: {e}")

        # 5. 分类 (★ 支持 moat_status, 评估失败时不降级)
        mp = moat_result.get("moat_profile", {})
        strong_count = sum(1 for v in mp.values() if isinstance(v, str) and v == "strong")
        has_emerging = any(v == "emerging" for v in mp.values() if isinstance(v, str))

        if moat_status == "assessed":
            if strong_count >= 4:
                category = "current_strong"
            elif has_emerging or strong_count >= 2:
                category = "future_strong"
            else:
                category = "watchlist"
        else:
            # 护城河评估失败/数据不足 → 不降级为 watchlist
            # 保留候选的默认分类, 标记 moat_status
            if audit.get("verdict") == "PASS":
                # 审计通过但护城河无法评估 → future_strong 待定
                category = "future_strong"
            else:
                category = "watchlist"

        # 附加审计标注
        risk_tags = []
        verdict = audit.get("verdict", "")
        if verdict == "FAIL":
            risk_tags.append("audit_fail")
        elif verdict == "CAUTION":
            risk_tags.append("audit_caution")

        result_dict = {
            "code": code,
            "name": name,
            "_source_type": candidate.get("_source_type", ""),
            "source_node": candidate.get("source_node", ""),
            "source_node_info": candidate.get("source_node_info", {}),
            "node_context": candidate.get("source_node_info", {}),
            "source": candidate.get("source", []),
            "flags": candidate.get("flags", []),
            "risk_tags": risk_tags,
            "company_stage": stage_map.get(code, "startup"),
            "stage_indicators": self._get_stage_indicators(stage_map.get(code, "startup")),
            "category": category,
            "verification": {
                "audit": audit,
                "moat_profile": mp,
                "moat_status": moat_status,  # ★ 新增: 护城河评估状态
                "profit_capture_thesis": moat_result.get("profit_capture_thesis", {}),
                "growth_asymmetry": moat_result.get("growth_asymmetry", {}),
                "thesis_breakers": moat_result.get("thesis_breakers", []),
                "roic": roic_val,
                "roiic": roiic_val,
                "valuation": valuation,
            },
        }

        logger.info(f"[{self.name}] Verified {code}: category={category}, "
                    f"audit={verdict}({audit.get('score',0)}), roic={roic_val}")
        return result_dict

    # ═══ 多轮淘汰赛 (4+家同源比较) ═════════════════

    async def _pairwise_tournament(self, comparator: "CandidateComparator",
                                    candidates: List[Dict], group: Dict) -> Dict:
        """4+候选时使用多轮淘汰, 避免一次 LLM 比较丢失所有信息。

        赛制: 配对初赛 (pairwise) → 胜者组决赛
        每轮只比 2 家, LLM 负载更轻, JSON 更小, 成功率更高。
        """
        cands = list(candidates)
        node_name = group.get("node", "")
        node_context = group.get("node_context", {})

        # 第1轮: 配对赛
        pairs = []
        i = 0
        while i < len(cands):
            a = cands[i]
            if i + 1 < len(cands):
                pairs.append((a, cands[i + 1]))
            else:
                pairs.append((a, None))  # 轮空
            i += 2

        winners = []
        for a, b in pairs:
            if b is None:
                winners.append(a)
                continue
            pair_result = await comparator.compare_within_source([a, b], node_context)
            ranked = pair_result.get("ranked", [])
            if ranked:
                winners.append(next((c for c in [a, b] if c.get("code") == ranked[0].get("code")), a))
            else:
                winners.append(a)

        # 第2轮: 决赛 (胜者组排序)
        if len(winners) <= 3:
            final_result = await comparator.compare_within_source(winners, node_context)
        else:
            # 超过3个胜者再打一轮
            final_result = await self._pairwise_tournament(comparator, winners, group)

        final_result["source"] = node_name
        final_result["_tournament"] = True
        return final_result

    # ═══ Phase A: LLM 快速筛选 ═════════════════

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
        step2_only = ctx.get("step2_only", False)
        step2_output = ctx.get("step2_output", {})

        # ── Path A: Step 2 only (保留原有逻辑) ──
        if step2_only:
            candidates = await self._aggregate_candidates_from_step2(step2_output, trace=trace)
            # 沿用旧的简化流程 (无比较排名, 只有基础验证)
            return await self._legacy_step2_flow(candidates, industry, ctx, trace)

        step3 = ctx.get("step3_output", ctx.get("supply_chain_map_ctx", {}))
        step4 = ctx.get("step4_output", {})
        step5 = ctx.get("step5_output", {})

        logger.info(f"[{self.name}] === V5.15 4-Phase Screening: {industry} ===")

        # ═══ Phase 1: 线索汇总 ═════════════════════
        clues = await self._collect_all_clues(industry, step3, step4, step5)

        # ═══ Phase 2: 搜索 ═══════════════════════════
        # 取前12条 search_clues (按优先级: a_share_equivalent > asset_search_query > human_capital > tag)
        priority_map = {"asset_search_query": 0, "human_capital": 1}
        def _sort_key(c):
            base = priority_map.get(c.get("_source_type", ""), 99)
            mt = c.get("mapping_type", "direct")
            # a_share_equivalent 需要深度搜索, 排在最前面
            mapping_bonus = -1 if mt == "a_share_equivalent" else 0
            return (base + mapping_bonus)
        search_clues = sorted(clues["search_clues"], key=_sort_key)[:12]
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

        # ── 加载财务数据 + 硬过滤器 + LLM 生命周期分类 ──
        from app.domain.research.services.financial_data_loader import load_financials as _load_fin
        from app.domain.research.services.screening_gate import hard_filter
        from app.framework.finance.financial_data_view import build_financial_data_view
        from app.framework.finance.stage_classifier import StageClassifier

        codes = [c["code"] for c in deduped[:20]]
        stock_info_map = await data_loader.load_fundamentals(codes) if codes else {}
        cycle_position = (step3 if isinstance(step3, dict) else {}).get("cycle_position", "")
        fin_map = {}
        for code in codes[:10]:
            try:
                fin_data = await _load_fin(code, periods=8, mode="auto")
                if fin_data and fin_data.get("quarters"):
                    fin_map[code] = fin_data
            except Exception:
                pass

        # 硬过滤器: 只排除 ST / 低流动性
        passed, filtered = hard_filter(deduped, stock_info_map)
        if not passed:
            logger.warning(f"[{self.name}] All {len(deduped)} candidates filtered by hard_filter")
            return self._empty_result(industry, filtered=filtered, cycle_position=cycle_position)

        # LLM 生命周期分类 (每个候选独立判定)
        classifier = StageClassifier(provider=self.provider)
        stage_map = {}
        for c in passed:
            code = c["code"]
            quarters = fin_map.get(code, {}).get("quarters", [])
            if quarters:
                try:
                    fv = build_financial_data_view(quarters)
                    result = await classifier.classify(fv, {
                        "stock_code": code,
                        "stock_name": c.get("name", ""),
                        "industry": industry,
                        "cycle_position": cycle_position,
                    })
                    stage_map[code] = result.get("stage", "startup")
                except Exception:
                    stage_map[code] = "startup"
            else:
                stage_map[code] = "startup"

        # ═══ Phase 3a: 分组 → Phase A筛选 → Phase B比较 ════
        from app.domain.research.agents.candidate_comparator import CandidateComparator
        comparator = CandidateComparator(provider=self.provider)
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
                        "company_stage": stage_map.get(cand["code"], "startup"),
                        "category": "watchlist",
                        "verification": {},
                    }
                    v.setdefault("_tags", []).append("overflow_audit_pass")
                    verified.append(v)
                else:
                    v = await self._verify_single(cand, industry, stock_info_map, fin_map, stage_map, trace)
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
                    "company_stage": stage_map.get(cand["code"], "startup"),
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

    # ═══ 旧流程 (Path A: step2_only) ═══════════════

    async def _legacy_step2_flow(self, candidates, industry, ctx, trace) -> Dict:
        """Path A 简化流程: 无比较排名"""
        if not candidates:
            return self._empty_result(industry)

        from app.domain.research.services.screening_gate import hard_filter
        from app.framework.finance.financial_data_view import build_financial_data_view
        from app.framework.finance.stage_classifier import StageClassifier
        cycle_position = ""

        codes = [c["code"] for c in candidates[:20]]
        stock_info_map = await data_loader.load_fundamentals(codes) if codes else {}
        fin_map = {}
        from app.domain.research.services.financial_data_loader import load_financials as _load_fin
        for code in codes[:10]:
            try:
                fin_data = await _load_fin(code, periods=8, mode="auto")
                if fin_data and fin_data.get("quarters"):
                    fin_map[code] = fin_data
            except Exception:
                pass

        # 硬过滤器 + LLM 生命周期分类
        passed, filtered = hard_filter(candidates, stock_info_map)
        if not passed:
            return self._empty_result(industry, filtered=filtered)

        classifier = StageClassifier(provider=self.provider)
        stage_map = {}
        for c in passed:
            code = c.get("code", "")
            quarters = fin_map.get(code, {}).get("quarters", [])
            if quarters:
                try:
                    fv = build_financial_data_view(quarters)
                    result = await classifier.classify(fv, {
                        "stock_code": code,
                        "stock_name": c.get("name", ""),
                        "industry": industry,
                    })
                    stage_map[code] = result.get("stage", "startup")
                except Exception:
                    stage_map[code] = "startup"
            else:
                stage_map[code] = "startup"

        from app.domain.research.agents.financial_auditor import FinancialAuditor
        auditor = FinancialAuditor(provider=self.provider)
        for c in passed[:10]:
            code = c["code"]
            try:
                audit = await auditor.analyze({"stock_code": code, "stock_name": c.get("name", ""), "industry": industry})
                if audit and audit.get("verdict"):
                    c["audit"] = {"verdict": audit["verdict"], "score": audit.get("score", 0)}
            except Exception:
                pass

            search_data = await self._search_adaptive([[
                f"{c.get('name','')} {code} 行业地位 市场份额 竞争壁垒 护城河",
                f"{c.get('name','')} {code} 定价权 毛利率 客户 认证",
            ]], num=3, trace=trace)
            prompt = self._build_moat_prompt(c.get("name", code), code, industry, c.get("source", []), search_data)
            try:
                text = await self.provider.chat_flash(prompt, max_tokens=4096, timeout=90)
                if trace: trace.record_llm(prompt, text, model="deepseek-v4-flash")
                result = self.parse_json(text)
                if isinstance(result, dict) and result.get("moat_profile"):
                    c.update(result)
            except Exception:
                pass

        future_strong = [c for c in passed if c.get("category") in ("future_strong", "current_strong")]
        watchlist_out = [c for c in passed if c.get("category") == "watchlist"]
        logger.info(f"[{self.name}] Step2-only done: {len(future_strong)} future, {len(watchlist_out)} watchlist")

        return {
            "agent": self.name,
            "confidence": "medium",
            "lifecycle_gate": {"cycle_position": "", "gate_mode": "auto"},
            "candidate_pool": {"total_collected": len(candidates), "after_prescreen": len(passed), "ranked": len(future_strong)},
            "ranked_stocks": [],
            "future_strong_candidates": future_strong,
            "watchlist": watchlist_out,
            "comparisons": [],
            "source_detail": {"step2_only": len(candidates)},
            "step3_backfill": {},
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

    async def _aggregate_candidates_from_step2(self, step2_output: Dict, trace=None) -> List[Dict]:
        """Path A: 从 Step 2 的 transmission_order 节点直接挖掘标的"""
        propagation = step2_output.get("propagation", {}) if isinstance(step2_output, dict) else {}
        transmission_order = propagation.get("transmission_order", [])
        node_names = [node.get("node", "") for node in transmission_order if node.get("node", "")]

        tags = list(set(node_names))
        if not tags:
            logger.warning(f"[{self.name}] step2_only: no transmission_order nodes found")
            return []

        logger.info(f"[{self.name}] step2_only: extracted {len(tags)} nodes from transmission_order: {tags}")
        catalysts = [c.get("catalyst", "") for c in (step2_output.get("catalysts", []) or [])[:3]]
        search_context = " ".join(catalysts) if catalysts else ""
        search_queries = [f"A股 {' '.join(tags[:3])} 龙头企业 核心标的 2026"]
        if search_context:
            search_queries.append(f"A股 {search_context} 龙头股票 上市公司")
        search_queries.append(f"A股 {' '.join(tags[:2])} 核心卡脖子标的")
        search_data = await self._search_adaptive([search_queries], num=5, trace=trace)
        return await self._llm_tag_to_stock_mapping(tags, search_data, " / ".join(tags[:3]), trace=trace)

    async def _llm_tag_to_stock_mapping(self, tags: List[str], search_data: List[Dict],
                                         industry: str, trace=None) -> List[Dict]:
        """将 value node tags 通过 LLM 分批映射为具体股票代码"""
        if not tags:
            return []

        batch_size = 8
        batches = [tags[i:i+batch_size] for i in range(0, len(tags), batch_size)]
        all_candidates = []

        for batch_idx, tag_batch in enumerate(batches):
            logger.info(f"[{self.name}] Tag batch {batch_idx + 1}/{len(batches)}: {len(tag_batch)} tags")
            batch_prompt = f"""找出 {industry} 行业以下价值节点标签对应的 A 股核心标的。
价值节点标签: {tag_batch}
搜索参考: {_j(search_data)}
输出纯JSON数组，每项格式: [{{"code":"600000","name":"公司名","tags":["匹配的标签"]}}]
最多输出 8 只真正属于这些核心卡脖子节点的标的。
只输出JSON数组，不要包含其他文字。"""

            batch_result = None
            for attempt in range(2):
                try:
                    text = await self.provider.chat_flash(batch_prompt, max_tokens=2048, timeout=90)
                    if trace: trace.record_llm(batch_prompt, text, model="deepseek-v4-flash")
                    if not text or not text.strip():
                        continue
                    batch_result = self.parse_json(text)
                    if batch_result is not None:
                        break
                except Exception as e:
                    logger.warning(f"[{self.name}] Batch {batch_idx + 1} attempt {attempt + 1} failed: {e}")

            raw_list = []
            if isinstance(batch_result, list):
                raw_list = batch_result
            elif isinstance(batch_result, dict):
                for key in ("core_stocks", "stocks", "candidates", "data", "results", "stock_list", "assets", "all_assets"):
                    raw_list = batch_result.get(key, [])
                    if raw_list:
                        break
            for r in raw_list:
                if isinstance(r, dict) and "code" in r and r["code"] not in {c["code"] for c in all_candidates}:
                    all_candidates.append({
                        "code": r["code"], "name": r.get("name", r["code"]),
                        "_source_type": "tag",
                        "source": [{"step": "step6_mining", "field": "tags", "role": ",".join(r.get("tags", []))}],
                    })

        logger.info(f"[{self.name}] Tags->stocks: {len(all_candidates)} candidates from {len(batches)} batches")
        return all_candidates

    # ═══ 公司阶段判定 + 指标 ═══════════════════════

    @staticmethod
    def _get_stage_indicators(stage: str) -> dict:
        return {
            "startup":    {"primary": ["burn_rate_months", "rd_intensity", "rd_to_opex", "contract_liability_yoy"],
                           "note": "研发期: 关注现金跑道和研发投入效率, 财务阈值大幅放宽"},
            "inflection": {"primary": ["gross_margin", "gross_margin_trend", "revenue_yoy", "revenue_acceleration",
                                        "rd_to_revenue_trend", "contract_liability_yoy", "profit_turnaround", "revenue_qoq"],
                           "note": "拐点期: '研发→收益'验证窗口, 4个真拐点信号(毛利率上升+合同负债爆发+研发费率下降+营收加速)"},
            "growth":     {"primary": ["roiic", "roic", "gross_margin_trend", "operating_leverage", "revenue_yoy"],
                           "note": "成长期: 验证扩张质量, ROIIC应>当前ROIC"},
            "mature":     {"primary": ["roic", "roic_stability", "fcf_conversion", "gross_margin", "operating_margin_stability",
                                        "working_capital_efficiency", "inventory_revenue_ratio"],
                           "note": "成熟期: 验证护城河是否还在, 利润稳定性+现金回报率"},
            "decline":    {"primary": ["revenue_yoy", "fcf_conversion", "gross_margin_trend", "inventory_revenue_ratio"],
                           "note": "衰退期: 关注收入下滑速度和现金流退化"},
        }.get(stage, {"primary": [], "note": "未知阶段"})

    # ═══ Prompt: 六维权力画像 (增强版) ═════════════

    def _build_moat_prompt(self, name, code, industry, sources, search_data,
                            node_context=None, roic=None) -> str:
        source_str = ", ".join(
            f"{s['step']}/{s['field']}" + (f"({s['role']})" if s.get("role") else "")
            for s in sources) if sources else ""

        search_summary = ""
        for sd in search_data:
            search_summary += f"\n### {sd['query']}\n"
            for r in sd["results"][:3]:
                search_summary += f"  - {r['title']}: {r['snippet'][:150]}\n"

        # 节点上下文 (可选)
        node_block = ""
        if node_context:
            node_block = f"""
## 该候选所在瓶颈环节背景 (Step 3)
- 环节: {node_context.get('name', '')}
- 利润池: {node_context.get('profit_pool', '?')}  | 市场量级: {node_context.get('value_magnitude', '?')}
- 供给刚性: {node_context.get('supply_rigidity', '?')}
- 国产替代率: {node_context.get('china_substitution_rate', '?')}
- 竞争结构: {node_context.get('competitive_structure', '?')}
- 瓶颈描述: {node_context.get('bottleneck_narrative', '')[:200]}
"""

        roic_block = f"\n- ROIC(投入资本回报率): {roic}%" if roic is not None else ""

        return f"""你是产业竞争分析专家。评估 {name}({code}) 在 {industry} 赛道中的六维产业权力。

上游来源: {source_str}{node_block}

## 搜索证据
{search_summary}

## 财务参考{roic_block}

## 六维权力判断 (每维: strong/medium/weak/emerging, 必须基于搜索证据, 禁止空想)

{{
  "moat_profile": {{
    "position_power": "strong/medium/weak/emerging",
    "position_evidence": ["证据: 是否产业链必经节点? 客户能否绕过?"],
    "pricing_power": "strong/medium/weak/emerging",
    "pricing_evidence": ["证据: 能否涨价? 毛利率趋势? 占客户成本比例?"],
    "expansion_power": "strong/medium/weak/emerging",
    "expansion_evidence": ["证据: 产能能否扩张? 在建工程? 设备锁定?"],
    "certification_power": "strong/medium/weak/emerging",
    "certification_evidence": ["证据: 客户认证周期? 切换成本? 已进入哪些大客户?"],
    "resource_power": "strong/medium/weak/emerging",
    "resource_evidence": ["证据: 掌握稀缺资源/产能/人才/配额?"],
    "cognitive_power": "strong/medium/weak/emerging",
    "cognitive_evidence": ["证据: 是否比市场更早押对技术路线/提前布局?"]
  }},
  "profit_capture_thesis": {{
    "why_it_captures_profit": ["为什么这家公司能把产业景气变成自己的利润"],
    "future_profit_driver": ["未来利润增长的核心驱动力"]
  }},
  "growth_asymmetry": {{
    "growth_type": "nonlinear_breakout/inflection_point/linear/cyclical/unknown",
    "triggers": ["催化剂事件"],
    "current_stage": "当前所处阶段"
  }},
  "thesis_breakers": ["什么条件会推翻以上判断"]
}}

## 规则
- 每维至少1条 evidence, 没有证据→标记 weak/emerging 并说明"搜索证据不足"
- 禁止输出股票代码以外的投资建议
- 不要编造没有搜索证据支撑的判断"""

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
        fin_map = {}
        stage_map = {}
        try:
            codes = [stock_code]
            stock_info_map = await self.data_loader.load_fundamentals(codes) if codes else {}
        except Exception:
            pass

        logger.info(f"[{self.name}] Patch verify {stock_code}: re-running verification")
        v = await self._verify_single(cand, industry, stock_info_map, fin_map, stage_map, trace)

        # 2. 只更新 verification 部分
        cand["verification"] = v.get("verification", {})
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
