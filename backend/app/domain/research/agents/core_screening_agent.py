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

    @staticmethod
    def _aggregate_candidates(step3: Dict, step4: Dict, step5: Dict) -> List[Dict]:
        """聚合所有上游候选: 已有代码直通 + search_queries/target_profile 标记待映射"""
        candidates = {}  # code → {source, exposure}

        def add(code, name, source_step, source_field, role=""):
            if not code: return
            code = code.strip()
            if code not in candidates:
                candidates[code] = {"code": code, "name": name or code, "source": []}
            # 检查是否已有此来源
            existing_sources = [s["step"] + s["field"] for s in candidates[code]["source"]]
            src_key = source_step + source_field
            if src_key not in existing_sources:
                candidates[code]["source"].append({
                    "step": source_step, "field": source_field, "role": role,
                })

        # Step 3: core_stocks + assets
        for s in (step3 or {}).get("core_stocks", []):
            add(s.get("code"), s.get("name"), "step3", "core_stocks", s.get("role", ""))
        for node in (step3 or {}).get("supply_chain_map", []):
            for a in node.get("assets", []):
                add(a.get("code"), a.get("name"), "step3", "supply_chain_map.assets", a.get("role", ""))
        for item in (step3 or {}).get("sales_chain", []):
            for c in item.get("companies", []):
                add(c, c, "step3", "sales_chain")
        for item in (step3 or {}).get("expansion_chain", []):
            for c in item.get("companies", []):
                add(c, c, "step3", "expansion_chain")

        # Step 4: hidden_beneficiaries + resource_crowding (search_queries)
        sd = (step4 or {}).get("system_dynamics", step4 or {})
        for hb in sd.get("hidden_beneficiaries", []):
            for sq in hb.get("search_queries", []):
                # 标记为待标的映射
                pass  # search_queries 由标的映射工作流处理
        for rc in sd.get("resource_crowding", []):
            for sq in rc.get("search_queries", []):
                pass

        # Step 5: cross_industry_linkages (target_profile)
        for link in (step5 or {}).get("cross_industry_linkages", []):
            tp = link.get("target_profile", "")
            if tp:
                pass  # target_profile 由标的映射工作流处理

        return list(candidates.values())

    # ═══ 主入口 ═══════════════════════════════

    async def analyze(self, ctx: Dict[str, Any] = None, trace=None) -> Dict[str, Any]:
        ctx = await self.load_context(ctx or {})
        if not self.provider:
            return {"agent": self.name, "error": "No AI provider"}

        industry = ctx.get("industry", "未指定")
        step3 = ctx.get("step3_output", ctx.get("supply_chain_map_ctx", {}))
        step4 = ctx.get("step4_output", {})
        step5 = ctx.get("step5_output", {})

        # 1. 候选池聚合
        candidates = self._aggregate_candidates(step3, step4, step5)
        logger.info(f"[{self.name}] Screening: {industry} ({len(candidates)} candidates)")

        if not candidates:
            return {"agent": self.name, "confidence": "insufficient_data",
                    "confidence_note": "无候选股票, 上游未提供股票代码或search_queries",
                    "candidate_pool": {"total_collected": 0}, "ranked_stocks": [],
                    "future_strong_candidates": [], "filter_log": []}

        # 2. 生命周期分轨
        from app.domain.research.services.screening_gate import get_gate_mode, gate_prescreen
        cycle_position = (step3 if isinstance(step3, dict) else {}).get("cycle_position", "")
        gate_mode = get_gate_mode(cycle_position)

        # 拉取本地DB数据
        codes = [c["code"] for c in candidates[:20]]  # 最多20只
        stock_info_map = await data_loader.load_fundamentals(codes) if codes else {}
        fin_map = {}
        for code in codes[:10]:  # 财务数据拉取限制10只, 控制耗时
            try:
                fin_data = await data_loader.load_financial_statements(code, periods=8)
                if fin_data and fin_data.get("quarters"):
                    fin_map[code] = fin_data
            except Exception:
                pass

        passed, filtered = gate_prescreen(candidates, gate_mode, stock_info_map, fin_map)

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
                    roic_data = compute_roic(fin)
                    roiic_data = compute_roiic(fin) if len(fin) >= 8 else {}
                    report_date = fin[0].get("report_date", "")[:10]
                    store_financial_indicator(code, report_date, {
                        "roic": roic_data.get("roic"),
                        "roic_pct": roic_data.get("roic_pct"),
                        "roiic": roiic_data.get("roiic"),
                        "roiic_pct": roiic_data.get("roiic_pct"),
                    })
                except Exception as e:
                    logger.warning(f"[{self.name}] ROIC/ROIIC store failed for {code}: {e}")

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
                text = await asyncio.wait_for(
                    self.provider.chat_flash(prompt, max_tokens=2048), timeout=60)
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
        current_strong, future_strong = [], []
        for c in passed:
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
                c["category"] = "future_strong"  # 默认进future, 不丢弃
                future_strong.append(c)

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
            "step3_backfill": backfill,
            "filter_log": filtered,
        }

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
