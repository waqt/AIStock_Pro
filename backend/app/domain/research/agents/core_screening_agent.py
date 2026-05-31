"""
CoreScreeningAgent V1.0 — Step 6: 核心资产筛选
定位: 发现段→判断段的桥梁。把上游定性发现转化为可投资股票池。
方法: GPT六维权力画像 + Gemini生命周期分轨
原则: FinancialAuditor标注不排除, 财务不是第一筛
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
    """核心资产筛选 V1.0 — 六维权力画像 + 生命周期分轨"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "CoreScreeningAgent"

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

    # ═══ 候选聚合 ═══════════════════════════════

    async def _aggregate_candidates(self, industry: str, step3: Dict, step4: Dict, step5: Dict, trace=None) -> List[Dict]:
        """聚合上游的价值节点标签，并通过 Web Search + LLM 映射为具体股票代码"""
        tags = set()

        # 提取 Step3 标签
        for node in (step3 or {}).get("supply_chain_map", []):
            for t in node.get("value_node_tags", []): tags.add(t)
        for item in (step3 or {}).get("sales_chain", []):
            for t in item.get("value_node_tags", []): tags.add(t)
        for item in (step3 or {}).get("expansion_chain", []):
            for t in item.get("value_node_tags", []): tags.add(t)

        tags = list(tags)
        if not tags: return []

        logger.info(f"[{self.name}] Extracted tags: {tags}")

        search_data = await self._search_adaptive([[
            f"A股 {industry} {' '.join(tags[:3])} 龙头企业 核心标的 2026",
            f"A股 {industry} 核心标的 龙头"
        ]], num=5, trace=trace)

        return await self._llm_tag_to_stock_mapping(tags, search_data, industry, trace=trace)

    async def _llm_tag_to_stock_mapping(self, tags: List[str], search_data: List[Dict],
                                         industry: str, trace=None) -> List[Dict]:
        """将 value node tags 通过 LLM 分批映射为具体股票代码 (共享方法, Path A 和原路径都调用)"""
        if not tags:
            return []

        # 分批：标签太多时 LLM 可能返回空，按 8 个一批分组
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

            # 最多重试 2 次
            batch_result = None
            for attempt in range(2):
                try:
                    text = await self.provider.chat_flash(batch_prompt, max_tokens=2048, timeout=90)
                    if trace: trace.record_llm(batch_prompt, text, model="deepseek-v4-flash")
                    if not text or not text.strip():
                        logger.warning(f"[{self.name}] Batch {batch_idx + 1} attempt {attempt + 1}: empty response, retrying...")
                        continue
                    batch_result = self.parse_json(text)
                    if batch_result is not None:
                        break
                    logger.warning(f"[{self.name}] Batch {batch_idx + 1} attempt {attempt + 1}: parse failed, retrying...")
                except Exception as e:
                    logger.warning(f"[{self.name}] Batch {batch_idx + 1} attempt {attempt + 1} failed: {e}")

            # 解析 batch 结果
            raw_list = []
            if isinstance(batch_result, list):
                raw_list = batch_result
            elif isinstance(batch_result, dict):
                for key in ("core_stocks", "stocks", "candidates", "data", "results", "stock_list", "assets", "all_assets"):
                    raw_list = batch_result.get(key, [])
                    if raw_list: break
            for r in raw_list:
                if isinstance(r, dict) and "code" in r and r["code"] not in {c["code"] for c in all_candidates}:
                    all_candidates.append({"code": r["code"], "name": r.get("name", r["code"]),
                                           "source": [{"step": "step6_mining", "field": "tags", "role": ",".join(r.get("tags", []))}]})

        logger.info(f"[{self.name}] Tags->stocks: {len(all_candidates)} candidates from {len(batches)} batches (total tags={len(tags)})")
        return all_candidates

    async def _aggregate_candidates_from_step2(self, step2_output: Dict, trace=None) -> List[Dict]:
        """Path A: 从 Step 2 的 transmission_order 节点直接挖掘标的, 跳过 Step 3"""
        propagation = step2_output.get("propagation", {}) if isinstance(step2_output, dict) else {}
        transmission_order = propagation.get("transmission_order", [])
        node_names = [node.get("node", "") for node in transmission_order if node.get("node", "")]

        tags = list(set(node_names))
        if not tags:
            logger.warning(f"[{self.name}] step2_only: no transmission_order nodes found")
            return []

        logger.info(f"[{self.name}] step2_only: extracted {len(tags)} nodes from transmission_order: {tags}")

        # 从 catalysts 取上下文
        catalysts = [c.get("catalyst", "") for c in (step2_output.get("catalysts", []) or [])[:3]]
        search_context = " ".join(catalysts) if catalysts else ""

        # Web search: 用节点名直接搜 A 股标的
        search_queries = [f"A股 {' '.join(tags[:3])} 龙头企业 核心标的 2026"]
        if search_context:
            search_queries.append(f"A股 {search_context} 龙头股票 上市公司")
        search_queries.append(f"A股 {' '.join(tags[:2])} 核心卡脖子标的")
        search_data = await self._search_adaptive([search_queries], num=5, trace=trace)

        return await self._llm_tag_to_stock_mapping(tags, search_data, " / ".join(tags[:3]), trace=trace)

    # ═══ 主入口 ═══════════════════════════════

    async def analyze(self, ctx: Dict[str, Any] = None, trace=None) -> Dict[str, Any]:
        ctx = await self.load_context(ctx or {})
        if not self.provider:
            return {"agent": self.name, "error": "No AI provider"}

        industry = ctx.get("industry", "未指定")
        step2_only = ctx.get("step2_only", False)
        step2_output = ctx.get("step2_output", {})

        # 1. 候选池聚合
        if step2_only:
            candidates = await self._aggregate_candidates_from_step2(step2_output, trace=trace)
        else:
            step3 = ctx.get("step3_output", ctx.get("supply_chain_map_ctx", {}))
            step4 = ctx.get("step4_output", {})
            step5 = ctx.get("step5_output", {})
            candidates = await self._aggregate_candidates(industry, step3, step4, step5, trace=trace)

        logger.info(f"[{self.name}] Screening: {industry} ({len(candidates)} candidates{' via step2_only' if step2_only else ''})")

        if not candidates:
            return {"agent": self.name, "confidence": "insufficient_data",
                    "confidence_note": "无候选股票, 上游未提供股票代码或search_queries",
                    "candidate_pool": {"total_collected": 0}, "ranked_stocks": [],
                    "future_strong_candidates": [], "filter_log": []}

        # 2. 生命周期分轨
        from app.domain.research.services.screening_gate import get_gate_mode, gate_prescreen
        cycle_position = ""
        if not step2_only:
            step3 = ctx.get("step3_output", ctx.get("supply_chain_map_ctx", {}))
            cycle_position = (step3 if isinstance(step3, dict) else {}).get("cycle_position", "")
        gate_mode = get_gate_mode(cycle_position)

        # 拉取财务数据 (投研模式: DB→akshare→web search 自动路由)
        from app.domain.research.services.financial_data_loader import load_financials as _load_fin
        codes = [c["code"] for c in candidates[:20]]  # 最多20只
        stock_info_map = await data_loader.load_fundamentals(codes) if codes else {}
        fin_map = {}
        for code in codes[:10]:  # 财务数据拉取限制10只, 控制耗时
            try:
                fin_data = await _load_fin(code, periods=8, mode="auto")
                if fin_data and fin_data.get("quarters"):
                    fin_map[code] = fin_data
            except Exception:
                pass

        # 公司阶段判定 (基于自身财务, 独立于行业周期)
        stage_map = {}
        for c in candidates:
            fin = fin_map.get(c["code"], {}).get("quarters", [])
            stage_map[c["code"]] = _classify_company_stage(fin, stock_info_map.get(c["code"], {}))
        # 统计
        stage_counts = {}
        for s in stage_map.values():
            stage_counts[s] = stage_counts.get(s, 0) + 1
        logger.info(f"[{self.name}] Company stages: {stage_counts}")

        passed, filtered = gate_prescreen(candidates, gate_mode, stock_info_map, fin_map)
        logger.info(f"[{self.name}] Prescreen: {len(passed)} passed, {len(filtered)} filtered out of {len(candidates)} candidates")
        if filtered:
            for f in filtered[:5]:
                logger.info(f"[{self.name}] Filtered: {f.get('code','?')} {f.get('name','?')} reasons={f.get('flags',[])}")
        if not passed:
            logger.warning(f"[{self.name}] All candidates filtered by prescreen! gate_mode={gate_mode}, stage_counts={stage_counts}")

        # 3. 调 FinancialAuditor 逐只标注 (不排除) + ROIC/ROIIC 计算落库
        from app.domain.research.agents.financial_auditor import FinancialAuditor
        from app.framework.finance.roiic import compute_roic, compute_roiic
        from app.domain.quant.engine.indicator_store import store_financial_indicator
        auditor = FinancialAuditor(provider=self.provider)
        audit_results = {}
        for c in passed[:10]:  # 最多审计10只
            code = c["code"]
            try:
                audit = await auditor.analyze({"stock_codes": [code], "industry": industry})
                if audit and audit.get("verdict"):
                    audit_results[code] = audit
            except Exception as e:
                logger.warning(f"[{self.name}] Audit failed for {code}: {e}")
            # ROIC/ROIIC 计算+落库
            fin = fin_map.get(code, {}).get("quarters", [])
            if fin and len(fin) >= 4:
                try:
                    recent_first = list(reversed(fin))  # data_loader 返回 oldest-first, 倒序
                    company_stage = stage_map.get(code, "startup")
                    capitalize_rd = company_stage in ["startup", "inflection", "growth"]

                    roic_data = compute_roic(recent_first, capitalize_rd=capitalize_rd)
                    roiic_data = compute_roiic(recent_first, capitalize_rd=capitalize_rd) if len(recent_first) >= 8 else {}
                    report_date = recent_first[0].get("report_date", "")[:10]
                    store_financial_indicator(code, report_date, {
                        "roic": roic_data.get("roic"),
                        "roic_pct": roic_data.get("roic_pct"),
                        "roiic": roiic_data.get("roiic"),
                        "roiic_pct": roiic_data.get("roiic_pct"),
                        "capitalized_rd": capitalize_rd
                    })
                except Exception as e:
                    logger.warning(f"[{self.name}] ROIC/ROIIC store failed for {code}: {e}")

        audit_count = len(audit_results)
        if audit_count == 0 and passed:
            logger.warning(f"[{self.name}] FinancialAuditor returned 0 results for {len(passed)} passed stocks! Check auditor input")
        elif audit_count > 0:
            verdicts = [a.get("verdict", "?") for a in audit_results.values()]
            logger.info(f"[{self.name}] Audit results: {audit_count}/{len(passed)} stocks, verdicts={verdicts}")

        # 4. 六维权力画像 (LLM)
        for c in passed:
            # 拉取搜索证据
            code = c["code"]
            name = c.get("name", code)
            search_data = await self._search_adaptive([[
                f"{name} {code} 行业地位 市场份额 竞争壁垒 护城河",
                f"{name} {code} 定价权 毛利率 客户 认证",
                f"{name} {code} moat competitive advantage 2026",
            ]], num=3, trace=trace)

            prompt = self._build_moat_prompt(name, code, industry, c["source"], search_data)

            try:
                text = await self.provider.chat_flash(prompt, max_tokens=2048, timeout=90)
                if trace: trace.record_llm(prompt, text, model="deepseek-v4-flash")
                result = self.parse_json(text)
                if isinstance(result, dict) and result.get("moat_profile"):
                    c["moat_profile"] = result["moat_profile"]
                    c["profit_capture_thesis"] = result.get("profit_capture_thesis", {})
                    c["growth_asymmetry"] = result.get("growth_asymmetry", {})
                    c["thesis_breakers"] = result.get("thesis_breakers", [])
            except asyncio.TimeoutError:
                logger.warning(f"[{self.name}] Moat profiling timeout for {code}")
            except Exception as e:
                logger.warning(f"[{self.name}] Moat profiling failed for {code}: {e}")

            # 附加审计标注
            aud = audit_results.get(code, {})
            if aud:
                c["risk_tags"] = c.get("risk_tags", [])
                verdict = aud.get("verdict", "")
                if verdict == "FAIL":
                    c["risk_tags"].append("audit_fail")
                elif verdict == "CAUTION":
                    c["risk_tags"].append("audit_caution")
                c["audit"] = {
                    "verdict": verdict,
                    "score": aud.get("score", 0),
                    "flags": aud.get("flags", []),
                    "beneish_m_score": aud.get("beneish", {}).get("m_score"),
                }

        # 5. 分级输出: current_strong / future_strong
        current_strong, future_strong, watchlist = [], [], []
        for c in passed:
            code = c["code"]
            c["company_stage"] = stage_map.get(code, "startup")
            c["stage_indicators"] = self._get_stage_indicators(c["company_stage"])
            mp = c.get("moat_profile", {})
            strong_count = sum(1 for v in mp.values() if isinstance(v, str) and v == "strong")
            has_emerging = any(v == "emerging" for v in mp.values() if isinstance(v, str))

            if strong_count >= 4:
                c["category"] = "current_strong"
                current_strong.append(c)
            elif has_emerging or strong_count >= 2:
                c["category"] = "future_strong"
                future_strong.append(c)
            else:
                c["category"] = "watchlist"
                watchlist.append(c)

        # 全军覆没降级处理
        if not current_strong and not future_strong and watchlist:
            future_strong = watchlist
            watchlist = []
            logger.warning(f"[{self.name}] No strong candidates found, demoting watchlist to future_strong")

        # 分类明细日志 (诊断 pipeline 空输出)
        for c in passed[:10]:
            mp = c.get("moat_profile", {})
            strong_count = sum(1 for v in mp.values() if isinstance(v, str) and v == "strong")
            aud = c.get("audit", {})
            logger.info(f"[{self.name}] Classify: {c['code']} {c.get('name','?')} → {c.get('category','?')} "
                        f"(strong_dim={strong_count}, stage={c.get('company_stage','?')}, "
                        f"audit={aud.get('verdict','?')} score={aud.get('score',0)})")

        # Step 3 回写数据准备
        backfill = {}
        for code, info in stock_info_map.items():
            if info.get("roe"):
                backfill[code] = {"actual_roe": info["roe"]}

        logger.info(f"[{self.name}] Done: {len(current_strong)} strong, {len(future_strong)} future, {len(filtered)} filtered")

        return {
            "agent": self.name,
            "confidence": "high" if current_strong else "medium",
            "lifecycle_gate": {"cycle_position": cycle_position, "gate_mode": gate_mode},
            "candidate_pool": {
                "total_collected": len(candidates),
                "after_prescreen": len(passed),
                "ranked": len(current_strong) + len(future_strong),
            },
            "ranked_stocks": current_strong,
            "future_strong_candidates": future_strong,
            "watchlist": watchlist,
            "step3_backfill": backfill,
            "filter_log": filtered,
        }

    # ═══ 公司阶段判定 ═══════════════════════════════

    @staticmethod
    def _get_stage_indicators(stage: str) -> dict:
        """返回该阶段应重点关注的指标列表"""
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

    # ═══ Prompt: 六维权力画像 ═══════════════════

    def _build_moat_prompt(self, name, code, industry, sources, search_data) -> str:
        source_str = ", ".join(
            f"{s['step']}/{s['field']}" + (f"({s['role']})" if s.get("role") else "")
            for s in sources)

        search_summary = ""
        for sd in search_data:
            search_summary += f"\n### {sd['query']}\n"
            for r in sd["results"][:3]:
                search_summary += f"  - {r['title']}: {r['snippet'][:150]}\n"

        return f"""你是产业竞争分析专家。评估 {name}({code}) 在 {industry} 赛道中的六维产业权力。

上游来源: {source_str}

## 搜索证据
{search_summary}

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

    # ═══ 基类 ═══════════════════════════════

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return await super().load_context(ctx)

    @staticmethod
    def build_prompt(ctx): return "CoreScreeningAgent V1.0"

    @staticmethod
    async def stream(ctx): yield "streaming not implemented"


def _classify_company_stage(quarters: list, stock_info: dict) -> str:
    """基于公司自身财务数据判定生命周期阶段"""
    if not quarters or len(quarters) < 4:
        return "startup"

    # 营收 (最近4Q, 亿元)
    rev_4q = sum(float(q.get("revenue", 0) or 0) for q in quarters[:4]) / 1e8
    # 归母净利润 (最近4Q)
    profit_4q = sum(float(q.get("profit", q.get("parent_profit", 0)) or 0) for q in quarters[:4])
    # 营收同比
    if len(quarters) >= 8:
        rev_prior = sum(float(q.get("revenue", 0) or 0) for q in quarters[4:8])
        rev_yoy = (rev_4q - rev_prior) / abs(rev_prior) * 100 if rev_prior else 0
    else:
        rev_yoy = 0
    # 研发费用率
    rd_4q = sum(float(q.get("rd_expense", 0) or 0) for q in quarters[:4])
    rd_intensity = (rd_4q / max(rev_4q, 0.01)) * 100 if rev_4q > 0.01 else 100
    # 毛利率
    cost_4q = sum(float(q.get("operate_cost", 0) or 0) for q in quarters[:4])
    gm = (rev_4q - cost_4q) / max(rev_4q, 0.01) * 100 if rev_4q > 0.01 else 0

    # 判定逻辑 (移除纯财务下降直接判定decline的逻辑)
    if rev_yoy < -10:
        if gm > 20 or rd_intensity > 10:
            return "inflection" # 可能是周期底部或者研发投入期
        return "cyclical_bottom"
    if rev_yoy > 20 and profit_4q > 0 and gm > 15:
        return "growth"
    if rev_yoy > 40 and rd_intensity > 15:
        return "inflection"
    if 0 <= rev_yoy <= 20 and profit_4q > 0:
        if gm > 20:
            return "mature"
        return "growth"
    # 默认
    return "startup"
