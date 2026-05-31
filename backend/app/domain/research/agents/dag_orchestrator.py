"""
DAG Orchestrator V4.0 — 图结构多Agent编排器
以 DAG 依赖图并行调度 5 专家, 替代 V3.0 的线性顺序调用

依赖图:
  GlobalCapexScanner ──┐
                        ├──→ [FOR EACH stock: FinancialAuditor || HumanCapital] ──→ ValuationPricer ──→ Report
  SupplyChainHacker ───┘
"""
import asyncio
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger


class DAGOrchestrator(ResearchAgent):
    """DAG 编排器 V4.0 — 专家委员会并行调度"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "DAGOrchestrator"

    # ═══ 主入口 ═══════════════════════════════════

    async def analyze(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await self.load_context(ctx)
        industry = ctx.get("industry", "")
        codes = ctx.get("stock_codes", [])
        hot_sectors = ctx.get("hot_sectors", [])  # 可选: MarketScanner 预扫描信号

        if not industry:
            return {"agent": self.name, "error": "No industry specified"}

        logger.info(f"[{self.name}] DAG pipeline starting for: {industry}"
                    + (f" (pre-scanned: {len(hot_sectors)} sectors)" if hot_sectors else ""))

        # ═══ Phase A: 顶层并行扫描 ═══
        logger.info(f"[{self.name}] Phase A: parallel top-down scan...")
        capex_task = self._run_capex_scanner(industry, hot_sectors)
        hacker_task = self._run_supply_chain_hacker(industry, codes)

        capex_result, hacker_result = await asyncio.gather(capex_task, hacker_task)
        logger.info(
            f"[{self.name}] Phase A complete: "
            f"capex_signals={len(capex_result.get('capex_signals', []))}, "
            f"core_stocks={len(hacker_result.get('core_stocks', []))}")

        core_stocks = hacker_result.get("core_stocks", [])
        if not core_stocks:
            return {
                "agent": self.name,
                "error": "No core stocks identified by SupplyChainHacker",
                "capex": capex_result,
                "supply_chain": hacker_result,
            }

        # ═══ Phase B: 每只标的并行审计 (Financial || HumanCapital) ═══
        logger.info(f"[{self.name}] Phase B: parallel audit for {len(core_stocks)} stocks...")
        audit_tasks = []
        for stock in core_stocks:
            audit_tasks.append(self._audit_stock(stock))

        audit_results = await asyncio.gather(*audit_tasks)
        logger.info(f"[{self.name}] Phase B complete: {len(audit_results)} stocks audited")

        # ═══ Phase C: 综合定价 ═══
        logger.info(f"[{self.name}] Phase C: pricing...")
        price_tasks = []
        for i, stock in enumerate(core_stocks):
            audits = audit_results[i] if i < len(audit_results) else {}
            price_tasks.append(self._price_stock(stock, audits))

        price_results = await asyncio.gather(*price_tasks)
        logger.info(f"[{self.name}] Phase C complete: {len(price_results)} stocks priced")

        # ═══ Phase D: 合成最终报告 ═══
        logger.info(f"[{self.name}] Phase D: synthesizing final report...")
        report = await self._synthesize_report(
            industry, capex_result, hacker_result, audit_results, price_results)

        report["agent"] = self.name
        report["industry"] = industry
        report["pipeline_stats"] = {
            "capex_signals": len(capex_result.get("capex_signals", [])),
            "supply_chain_layers": len(hacker_result.get("supply_chain_map", [])),
            "core_stocks": len(core_stocks),
            "stocks_audited": len(audit_results),
            "stocks_priced": len(price_results),
        }
        return report

    # ═══ Phase A: 并行顶层 ═══════════════════════

    async def _run_capex_scanner(self, industry: str, hot_sectors: list = None) -> Dict:
        from app.domain.research.agents.global_capex_scanner import GlobalCapexScanner
        scanner = GlobalCapexScanner(provider=self.provider)
        ctx = {"industry": industry}
        if hot_sectors:
            ctx["hot_sectors"] = hot_sectors  # 预扫描信号注入
        try:
            return await scanner.analyze(ctx)
        except Exception as e:
            logger.warning(f"[{self.name}] CapexScanner failed: {e}")
            return {"error": str(e), "agent": "GlobalCapexScanner"}

    async def _run_supply_chain_hacker(self, industry: str, codes: List[str]) -> Dict:
        from app.domain.research.agents.supply_chain_hacker import SupplyChainHacker
        hacker = SupplyChainHacker(provider=self.provider)
        try:
            return await hacker.analyze({
                "industry": industry, "stock_codes": codes,
                "include_portfolio": True})
        except Exception as e:
            logger.warning(f"[{self.name}] SupplyChainHacker failed: {e}")
            return {"error": str(e), "agent": "SupplyChainHacker", "core_stocks": []}

    # ═══ Phase B: 单股并行审计 ═══════════════════

    async def _audit_stock(self, stock: Dict) -> Dict:
        code = stock.get("code", "")
        name = stock.get("name", "")
        if not code:
            return {"code": code, "error": "No code"}

        # FinancialAuditor + HumanCapitalDetective 并行
        from app.domain.research.agents.financial_auditor import FinancialAuditor
        from app.domain.research.agents.human_capital_detective import HumanCapitalDetective

        auditor = FinancialAuditor(provider=self.provider)
        detective = HumanCapitalDetective(provider=self.provider)

        fin_task = auditor.analyze({"stock_code": code, "stock_name": name})
        hc_task = detective.analyze({"stock_code": code, "stock_name": name})

        fin_result, hc_result = await asyncio.gather(fin_task, hc_task)
        logger.info(
            f"[{self.name}] {code} audited: "
            f"FA={fin_result.get('verdict', '?')} "
            f"HC={hc_result.get('verdict', '?')}")

        return {
            "code": code, "name": name,
            "financial": fin_result,
            "human_capital": hc_result,
        }

    # ═══ Phase C: 单股定价 ═══════════════════════

    async def _price_stock(self, stock: Dict, audits: Dict) -> Dict:
        from app.domain.research.agents.valuation_pricer import ValuationPricer
        pricer = ValuationPricer(provider=self.provider)
        try:
            return await pricer.analyze({
                "stock": stock,
                "financial": audits.get("financial", {}),
                "human_capital": audits.get("human_capital", {}),
            })
        except Exception as e:
            logger.warning(f"[{self.name}] Pricer failed for {stock.get('code','?')}: {e}")
            return {"error": str(e), "verdict": "UNKNOWN"}

    # ═══ Phase D: 最终报告 ═══════════════════════


    # ═══ Phase D: 报告合成 ═══════════════════════

    async def _synthesize_report(self, industry, capex, hacker, audits, prices):
        if not self.provider:
            return self._synthesize_basic(industry, capex, hacker, audits, prices)
        has_audit = any(a and not a.get("error") for a in (audits or []))
        if not has_audit:
            return self._synthesize_basic(industry, capex, hacker, audits, prices)

        all_stocks = []
        for a in (audits or [])[:10]:
            code = a.get("code", "?")
            fin = a.get("financial", {})
            pr = next((p for p in (prices or []) if p.get("code") == code), {})
            all_stocks.append({
                "code": code, "name": a.get("name", "?"),
                "score": fin.get("score", 0), "verdict": fin.get("verdict", "?"),
                "upside": pr.get("target_valuation", {}).get("upside_pct"),
                "moat_years": pr.get("moat_window", {}).get("years"),
            })

        top_picks = []
        ranked = sorted(all_stocks, key=lambda s: -s["score"])
        for s in ranked:
            if s["verdict"] == "PASS" and s["score"] >= 40:
                t = "Audit_" + s["verdict"] + "_score_" + str(s["score"]) + "_upside_" + str(s.get("upside", "?")) + "_moat_" + str(s.get("moat_years", "?"))
                top_picks.append({"code": s["code"], "name": s["name"], "rank": len(top_picks) + 1,
                    "thesis": t, "verdict": "BUY" if s["score"] >= 60 else "HOLD",
                    "conviction": "HIGH" if s["score"] >= 60 else "MEDIUM"})
            elif s["verdict"] in ("PASS", "CAUTION") and s["score"] >= 25:
                t = "Audit_" + s["verdict"] + "_score_" + str(s["score"]) + "_upside_" + str(s.get("upside", "?")) + "_monitor"
                top_picks.append({"code": s["code"], "name": s["name"], "rank": len(top_picks) + 1,
                    "thesis": t, "verdict": "HOLD", "conviction": "MEDIUM"})
        if not top_picks:
            best = ranked[0] if ranked else {"code": "?", "name": "?", "verdict": "?", "score": 0}
            top_picks = [{"code": best["code"], "name": best["name"], "rank": 1,
                "thesis": "Audit_" + best["verdict"] + "_score_" + str(best["score"]),
                "verdict": "HOLD", "conviction": "LOW"}]

        w_map = {}
        for s in top_picks:
            a = next((x for x in all_stocks if x["code"] == s["code"]), None)
            if a:
                w_map[s["code"]] = 2.0 if a["verdict"] == "PASS" and a["score"] >= 60 else 1.0 if a["verdict"] == "PASS" else 0.5
        ws = sum(w_map.values()) or 1.0
        portfolio = [{"code": s["code"], "name": s["name"],
            "weight_pct": round(w_map.get(s["code"], 0) / ws * 100),
            "role": "Core" if w_map.get(s["code"], 0) > 1.0 else "Satellite"} for s in top_picks]

        import json as _json
        from decimal import Decimal

        class _E(_json.JSONEncoder):
            def default(self, o):
                return float(o) if isinstance(o, Decimal) else super().default(o)

        prompt = "你是投资委员会主席。基于以下审计数据用中文写投资结论。\\n行业: " + str(industry) + "\\n推荐标的 (系统判定): " + _json.dumps(top_picks, ensure_ascii=False, cls=_E) + "\\n组合配置: " + _json.dumps(portfolio, ensure_ascii=False, cls=_E) + "\\n审计汇总: " + _json.dumps(all_stocks[:8], ensure_ascii=False, cls=_E) + '\\n输出纯JSON: {"final_summary":"3-4句中文本结论","key_risks":["风险1","风险2","风险3"],"catalysts_to_watch":["催化1","催化2"],"timeline":"时间建议"}'
        try:
            text = await self.provider.chat_pro(prompt, max_tokens=2048, timeout=240)
            synthesis = self.parse_json(text)
            if isinstance(synthesis, dict):
                synthesis["top_picks"] = top_picks
                synthesis["portfolio_allocation"] = portfolio
                synthesis["detail"] = {"capex": capex, "supply_chain": hacker, "audits": audits, "prices": prices}
                # 始终用 _synthesize_basic 生成完整中文报告, 传入 LLM 风险/催化剂
                basic = self._synthesize_basic(industry, capex, hacker, audits, prices,
                    key_risks=synthesis.get("key_risks"),
                    catalysts=synthesis.get("catalysts_to_watch"))
                synthesis["cio_report"] = basic["cio_report"]
                synthesis["title"] = basic.get("title", "")
                # LLM 结构化字段优先, 回退到 basic
                synthesis["final_summary"] = synthesis.get("final_summary") or basic.get("final_summary", "")
                synthesis["key_risks"] = synthesis.get("key_risks") or basic.get("key_risks", [])
                synthesis["catalysts_to_watch"] = synthesis.get("catalysts_to_watch") or basic.get("catalysts_to_watch", [])
                return synthesis
        except Exception as e:
            logger.warning(f"[{self.name}] Synthesis failed: {e}")
        return self._synthesize_basic(industry, capex, hacker, audits, prices)

    async def _synthesize_basic(self, industry, capex, hacker, audits=None, prices=None,
                                 key_risks=None, catalysts=None):
        audits = audits or []; prices = prices or []
        stocks = hacker.get("core_stocks", [])
        layers = hacker.get("supply_chain_map", [])
        findings = hacker.get("raw_findings", [])
        # 新增: 双链路 + 生命周期字段
        sales_chain = hacker.get("sales_chain", [])
        expansion_chain = hacker.get("expansion_chain", [])
        chain_timeline = hacker.get("chain_timeline", {})
        second_order = hacker.get("second_order_effects", {})

        am = {}; pm = {}
        for a in audits: am[a.get("code","")] = a
        for p in prices:
            if p.get("code"): pm[p.get("code")] = p

        def _fi(t):
            t = str(t)
            if "剪刀差为负" in t: return ("Margin squeeze", "利润增速<营收增速, 利润率承压")
            if "剪刀差为正" in t: return ("Margin expand", "利润增速>营收, 经营杠杆正面")
            if "未达四连击" in t: return ("No 4Q streak", "营收+利润未连续4Q双增, 业绩有波动")
            if "四连击" in t and "连续" in t: return ("4Q streak", "连续4Q双增, 高景气确认")
            if "环比双增" in t or "季度环比" in t: return ("QoQ growth", "多季度环比增长, 短期动能强")
            if "Beneish M-Score" in t:
                if "灰色区域" in t: return ("M-Score gray", "财务造假风险中等, 需关注但非红旗")
                return ("M-Score alert", "财务造假风险较高, 需警惕")
            if "现金流/利润" in t: return ("Low cash flow", "经营现金流<利润50%, 利润含金量低")
            if "存货占比下降" in t: return ("Inventory down", "存货占比下降, 供不应求信号")
            if "合同负债" in t: return ("Prepayments up", "预收款大增, 在手订单充足")
            if "存货积压" in t: return ("Inventory up", "库存积压, 需求走弱或生产过剩")
            if "应收账款" in t: return ("Receivables risk", "回款恶化, 客户付款能力下降")
            if "scissor" in t.lower():
                if "neg" in t.lower(): return ("Margin squeeze", "Cost growing faster than revenue")
                return ("Margin expand", "Operating leverage positive")
            if "beneish" in t.lower() and "gray" in t.lower(): return ("M-Score gray", "Watch accounting quality")
            return ("--", str(t)[:60])

        def _ov(v, sc):
            if v == "PASS" and sc >= 60: return "STRONG: 财务健康, 业绩加速, 可重点关注"
            if v in ("PASS","CAUTION"): return "OK: 财务有亮点但存在关注项, 需持续跟踪"
            if sc >= 25: return "WEAK: 财务质量一般, 建议深入研究后再决策"
            return "HIGH RISK: 财务风险较高, 暂不建议重仓"

        # 从审计数据生成 top_picks
        top_picks = []
        for a in sorted(audits, key=lambda x: x.get("financial",{}).get("score",0), reverse=True):
            fin = a.get("financial",{})
            v=fin.get("verdict","?"); sc=fin.get("score",0)
            if v == "PASS" and sc >= 40:
                top_picks.append({"code": a["code"], "name": a.get("name","?"),
                    "verdict": "BUY" if sc>=60 else "HOLD", "conviction": "HIGH" if sc>=60 else "MEDIUM"})
            elif v in ("PASS","CAUTION") and sc >= 25:
                top_picks.append({"code": a["code"], "name": a.get("name","?"),
                    "verdict": "HOLD", "conviction": "MEDIUM"})

        L = []
        L.append("# " + str(industry) + " 产业投资深度研报")
        n_stocks = len(stocks); n_layers = len(layers); n_audits = len(audits)
        L.append("> 标的:" + str(n_stocks) + "只 | 供应链:" + str(n_layers) + "层 | 审计:" + str(n_audits) + "只")
        L.append("")

        # ---- 1. 行业景气全景 ----
        L.append("## 一、行业景气全景"); L.append("")
        gs = capex.get("global_summary","") if isinstance(capex,dict) else ""
        capex_signals = capex.get("capex_signals",[]) if isinstance(capex,dict) else []
        has_capex_data = gs or capex_signals

        if has_capex_data:
            if gs:
                L.append("### 景气驱动力"); L.append(str(gs)[:600]); L.append("")
            if capex_signals:
                L.append("### 全球 CapEx 信号"); L.append("")
                L.append("| 赛道 | 信号 | 规模 | 增速 | 确定性 |")
                L.append("|------|------|------|------|--------|")
                for c in capex_signals[:8]:
                    mag = str(c.get('magnitude','?'))
                    if mag.replace('.','').replace('-','').isdigit():
                        mag = "$"+str(int(float(mag)))+"亿" if float(mag)<10000 else "$"+str(round(float(mag)/10000,1))+"万亿"
                    L.append("| "+str(c.get('sector','?'))+" | "+str(c.get('signal','?'))+" | "+mag+" | "+str(c.get('growth_yoy','?'))+" | "+str(c.get('confidence','?'))+" |")
                L.append("")
        else:
            bottlenecks = [l.get("bottleneck","") for l in layers if l.get("bottleneck")]
            L.append("**行业阶段**: " + industry + "产业链已识别" + str(len(layers)) + "层关键环节")
            if bottlenecks: L.append("**核心瓶颈**: " + "; ".join(bottlenecks[:3])); L.append("")

        L.append("**投资逻辑**: 基于全球 CapEx 扩张趋势与产业链供需缺口，沿" + str(len(layers)) + "层产业链深度穿透，对" + str(len(stocks)) + "只核心标的进行全方位审计与估值定价。"); L.append("")

        # ---- 1.5 双链路时序分析 ----
        if sales_chain or expansion_chain:
            L.append("### 1.5 景气度传导时序"); L.append("")
            if chain_timeline.get("rotation_strategy"):
                L.append("**轮动策略**: " + str(chain_timeline["rotation_strategy"])); L.append("")
            if sales_chain:
                L.append("#### 销售链路 (直接受益, 先爆发)"); L.append("")
                L.append("| 环节 | 受益标的 | 传导逻辑 | 领先周期 |")
                L.append("|------|---------|---------|---------|")
                for sc in sales_chain:
                    L.append("| "+str(sc.get("segment","?"))+" | "+",".join(sc.get("companies",[]))+" | "+str(sc.get("reason","?"))+" | "+str(sc.get("lead_months","?"))+"个月 |")
                L.append("")
            if expansion_chain:
                L.append("#### 扩产链路 (滞后受益, 后爆发)"); L.append("")
                L.append("| 环节 | 受益标的 | 传导逻辑 | 滞后期 |")
                L.append("|------|---------|---------|--------|")
                for ec in expansion_chain:
                    L.append("| "+str(ec.get("segment","?"))+" | "+",".join(ec.get("companies",[]))+" | "+str(ec.get("reason","?"))+" | "+str(ec.get("lag_months","?"))+"个月 |")
                L.append("")

        # ---- 2. 产业链穿透 ----
        L.append("## 二、产业链穿透分析"); L.append("")
        L.append("> **审计方法**: 每只标的经过两轮独立审计 — ① **财务审计** (8季度剪刀差趋势 + Beneish M-Score 造假检测 + 四连击动量验证 + 经营现金流质量 + 合同负债/存货变动)；② **人力资本审计** (创始人背景/CTO履历/专利质量/股权激励/关键人风险)。审计结果在每层资产表中以标签标注。"); L.append("")
        for l in layers:
            L.append("### L"+str(l.get('level','?'))+": "+str(l.get('name','?')))
            L.append("**瓶颈**: "+str(l.get('bottleneck','?'))); L.append("")
            L.append("| 代码 | 名称 | 角色 | 审计 |"); L.append("|------|------|------|------|")
            for a in l.get('assets',[]):
                ac=a.get('code',''); au=am.get(ac,{})
                tag=au.get('financial',{}).get('verdict','--') if au else '--'
                L.append("| "+str(ac)+" | "+str(a.get('name','?'))+" | "+str(a.get('role','?'))+" | "+tag+" |")
            L.append("")

        # ---- 2.5 第二层思维: 隐性关联与次生效应 ----
        if second_order and (second_order.get("crowding_out") or second_order.get("io_linkages") or second_order.get("byproduct_effects")):
            L.append("## 二.五、第二层思维: 隐性关联与次生效应"); L.append("")
            if second_order.get("synthesis"):
                L.append("**核心洞察**: " + str(second_order["synthesis"])); L.append("")

            # 产能挤出效应
            co = second_order.get("crowding_out", [])
            if co:
                L.append("### 产能挤出效应"); L.append("")
                L.append("| 被挤占行业 | 被挤占资源 | 意外受益方 | 分析逻辑 | 关注标的 |")
                L.append("|-----------|-----------|-----------|---------|---------|")
                for c in co[:5]:
                    codes = ", ".join(c.get("a_stock_codes", [])) if c.get("a_stock_codes") else "--"
                    L.append("| "+str(c.get("victim_sector","?"))+" | "+str(c.get("resource","?"))+" | "+str(c.get("beneficiary","?"))+" | "+str(c.get("reasoning","?"))[:60]+" | "+codes+" |")
                L.append("")

            # 投入产出关联
            io = second_order.get("io_linkages", [])
            if io:
                L.append("### 投入产出关联"); L.append("")
                L.append("| 上游 | 下游 | 乘数 | 瓶颈程度 | 分析逻辑 | 关注标的 |")
                L.append("|------|------|------|---------|---------|---------|")
                for i in io[:5]:
                    codes = ", ".join(i.get("a_stock_codes", [])) if i.get("a_stock_codes") else "--"
                    L.append("| "+str(i.get("upstream","?"))+" | "+str(i.get("downstream","?"))+" | "+str(i.get("multiplier","?"))+" | "+str(i.get("bottleneck_level","?"))+" | "+str(i.get("reasoning","?"))[:60]+" | "+codes+" |")
                L.append("")

            # 副产品效应
            bp = second_order.get("byproduct_effects", [])
            if bp:
                L.append("### 副产品效应"); L.append("")
                L.append("| 主产品 | 副产品 | 副产品用途 | 供给弹性 | 影响行业 | 关注标的 |")
                L.append("|--------|--------|-----------|---------|---------|---------|")
                for b in bp[:5]:
                    codes = ", ".join(b.get("a_stock_codes", [])) if b.get("a_stock_codes") else "--"
                    L.append("| "+str(b.get("main_product","?"))+" | "+str(b.get("byproduct","?"))+" | "+str(b.get("byproduct_use","?"))+" | "+str(b.get("supply_elasticity","?"))+" | "+str(b.get("impact_on","?"))+" | "+codes+" |")
                L.append("")

        # ---- 3. 标的深度剖析 ----
        L.append("## 三、标的深度剖析"); L.append("")
        for s in stocks:
            c=s.get('code','?'); n=s.get('name','?')
            L.append("### "+c+" "+n)
            L.append("**产业链环节**: "+str(s.get('segment','?'))+" | **护城河**: "+str(s.get('moat','')))
            au=am.get(c,{}); fin=au.get('financial',{}); hc=au.get('human_capital',{})
            pr=pm.get(c,{})

            # ─ 护城河深度分析 ─
            if pr:
                mw = pr.get('moat_window', {})
                if mw.get('reasoning'):
                    L.append("**护城河深度**: " + str(mw.get('reasoning',''))[:200])
                # 竞争格局 (全球对标详情)
                peers = pr.get('global_peer_comparison', [])
                if peers:
                    comp_lines = []
                    for pp in peers[:3]:
                        pn = pp.get('name','?'); ppe = pp.get('pe','?')
                        pev = pp.get('ev_ebitda',''); pps = pp.get('ps','')
                        pd = pp.get('premium_discount','?')
                        metrics = "PE"+str(ppe)+"x"
                        if pev: metrics += " EV/EBITDA"+str(pev)+"x"
                        comp_lines.append("**" + pn + "**: " + metrics + " — " + str(pd)[:120])
                    if comp_lines: L.append("**竞争格局**: " + " | ".join(comp_lines))

            # ─ 估值快照 (一行) ─
            if pr:
                pv=pr.get('verdict'); up=pr.get('target_valuation',{}).get('upside_pct')
                tv=pr.get('target_valuation',{})
                mc=tv.get('base_case_mcap','?'); scs=pr.get('scenarios',{})
                bull_p=scs.get('bull',{}).get('target_price','?')
                base_p=scs.get('base',{}).get('target_price','?')
                bear_p=scs.get('bear',{}).get('target_price','?')
                if pv not in (None,'UNKNOWN','?'):
                    L.append("**估值**: "+str(pv)+" | 目标市值 "+str(mc)+"亿 | 上行 "+str(up)+"% | 目标价 看多"+str(bull_p)+"/基准"+str(base_p)+"/看空"+str(bear_p))
                L.append("")

            # ─ 财务审计摘要 (一行) ─
            if fin:
                v=fin.get('verdict','?'); sc=fin.get('score',0)
                parts = [v+"("+str(sc)+"分)"]
                bn=fin.get('beneish',{})
                if bn.get('m_score'):
                    parts.append("Beneish M="+str(round(bn['m_score'],2))+" "+str(bn.get('interpretation','?')))
                sx=fin.get('scissor',{})
                if sx.get('latest_gap_pct'):
                    direction="扩张" if sx.get('is_expanding') else "承压"
                    parts.append("剪刀差"+str(sx['latest_gap_pct'])+"% "+direction)
                mm=fin.get('momentum',{})
                if mm.get('consecutive_yoy_hits'):
                    streak="✅四连击" if mm.get('four_quarters_hit') else "⚠未达四连击("+str(mm['consecutive_yoy_hits'])+"季)"
                    parts.append(streak)
                L.append("**审计**: "+" | ".join(parts))
                L.append("| 审计信号 | 含义 | 解读 |"); L.append("|---------|------|------|")
                for fl in fin.get('flags',[])[:8]:
                    m,i=_fi(str(fl))
                    L.append("| "+str(fl)[:55]+" | "+m+" | "+i+" |")
                L.append(""); L.append("**综合评估**: "+_ov(v,sc))

            # ─ 人力资本 (2行) ─
            if hc:
                fb=hc.get('founder_background',{}); pat=hc.get('patent_quality',{})
                hc_parts = []
                fb_name=fb.get('name','')
                if fb_name:
                    edu=fb.get('education') or ''; yrs=fb.get('industry_years','')
                    note=fb.get('notable','')
                    fb_line=fb_name
                    if edu: fb_line += " | "+str(edu)
                    if yrs: fb_line += " | 从业"+str(yrs)+"年"
                    if note: fb_line += " | "+str(note)[:80]
                    hc_parts.append("**创始人**: "+fb_line)
                rd_ratio=hc.get('core_team',{}).get('rd_ratio_est') or ''
                pat_total=pat.get('total_patents_est') or ''
                if rd_ratio or pat_total:
                    rd_str="研发占比"+str(rd_ratio)+"%" if rd_ratio else ""
                    pat_str="专利"+str(pat_total)+"件" if pat_total else ""
                    hc_parts.append("**研发**: "+(" | ".join(filter(None,[rd_str,pat_str]))))
                tech_ind = pat.get('tech_independence','')
                if tech_ind: hc_parts.append("**技术独立性**: "+str(tech_ind))
                score=hc.get('human_capital_score') or '?'; verd=hc.get('verdict') or '?'
                kp_risk=hc.get('key_personnel_risk','')
                hc_parts.append("**人力评分**: "+str(verd)+"("+str(score)+"/10)"+ (" | 关键人风险: "+str(kp_risk)[:80] if kp_risk else ""))
                L.append("**人力资本**: "+" | ".join(hc_parts))

            # ─ 估值细节 ─
            if pr:
                vm=pr.get('valuation_method',{})
                if vm.get('primary'):
                    L.append("**估值模型**: "+vm['primary']+" — "+str(vm.get('reasoning',''))[:100])
                qc=pr.get('quality_check',{})
                if qc.get('quality_verdict'):
                    L.append("**质量**: "+qc['quality_verdict'])
                peers=pr.get('global_peer_comparison',[])
                if peers:
                    peer_lines=[]
                    for pp in peers[:3]:
                        pn=pp.get('name','?'); ppe=pp.get('pe','?')
                        pd=pp.get('premium_discount','?')
                        peer_lines.append(pn+" PE"+str(ppe)+"x — "+str(pd)[:60])
                    L.append("**全球对标**: "+" | ".join(peer_lines))
                ps=pr.get('position_suggest',{})
                if ps:
                    entry=ps.get('entry_strategy',''); exit_t=ps.get('exit_trigger','')
                    if entry: L.append("**建仓**: "+str(entry)[:120])
                    if exit_t: L.append("**退出**: "+str(exit_t)[:120])

            L.append("")

            # ─ 情景分析 ─
            if pr and pr.get("scenarios"):
                scs = pr["scenarios"]
                L.append("**情景分析**:")
                L.append("| 情景 | 目标价 | 涨跌幅 | 前提假设 |")
                L.append("|------|--------|--------|---------|")
                for sn, sv in [("bull", "看多"), ("base", "基准"), ("bear", "看空")]:
                    sd = scs.get(sn, {})
                    if sd:
                        price = sd.get("target_price","?")
                        chg = sd.get("upside_pct") or sd.get("downside_pct") or "?"
                        L.append("| "+sv+" | "+str(price)+" | "+str(chg)+"% | "+str(sd.get("assumptions","?"))+" |")
                L.append("")
        L.append("")

        # ---- 4. 结论与建议 ----
        L.append("## 四、核心结论与投资建议"); L.append("")
        final_summary = str(industry)+"产业链已识别"+str(n_stocks)+"只核心标的，"+str(n_audits)+"只完成审计。"
        if top_picks:
            buy_n = sum(1 for t in top_picks if t["verdict"]=="BUY")
            hold_n = sum(1 for t in top_picks if t["verdict"]=="HOLD")
            final_summary += " 推荐"+str(buy_n)+"只买入，"+str(hold_n)+"只关注。"
        L.append(final_summary); L.append("")
        if top_picks:
            L.append("### 推荐标的"); L.append("")
            for t in top_picks[:5]:
                au3=am.get(t['code'],{}); fin3=au3.get('financial',{})
                desc="审计"+fin3.get('verdict','?')+"("+str(fin3.get('score',0))+"分)"
                L.append("- **"+t['code']+" "+t['name']+"** ["+t.get('verdict','?')+"] "+desc)
            L.append("")

        # ---- 5. 风险与催化剂 ----
        L.append("## 五、风险与催化剂"); L.append("")
        # 优先使用 LLM 输出, 否则硬编码兜底
        risks = key_risks or ["技术替代风险","商业化进度不确定","产能扩张过快致供需失衡","地缘政治冲击供应链"]
        cats = catalysts or ["下游需求爆发式增长","政策补贴落地","国产替代突破"]
        if risks:
            L.append("### 主要风险")
            for r in risks: L.append("- "+str(r))
            L.append("")
        if cats:
            L.append("### 关注催化剂")
            for c in cats: L.append("- "+str(c))
            L.append("")
        L.append("---")
        L.append("*本报告由 AIStock Pro DAG 投研系统自动生成，仅供参考，不构成投资建议。*")

        return {
            "cio_report": "\n".join(L),
            "title": _gen_title(industry, top_picks),
            "final_summary": final_summary,
            "top_picks": top_picks if top_picks else [{"code":s["code"],"name":s["name"],"rank":i+1,"thesis":s.get("moat",""),"verdict":"HOLD","conviction":"MEDIUM"} for i,s in enumerate(stocks[:5])],
            "key_risks": ["技术替代风险","商业化进度不确定","产能扩张过快致供需失衡","地缘政治冲击供应链"],
            "catalysts_to_watch": ["SOFC数据中心部署","国内示范项目","政策支持落","国产替代突破"],
            "detail": {"supply_chain":hacker,"capex":capex},
        }

    async def load_context(self, ctx):
        ctx = await super().load_context(ctx)
        return ctx

    @staticmethod
    def build_prompt(ctx):
        return "DAGOrchestrator V4.0"

    @staticmethod
    async def stream(ctx):
        yield "streaming not implemented"


def _gen_title(industry, top_picks):
    """根据行业和推荐标的生成报告标题"""
    if not top_picks:
        return industry + "产业链深度研报"
    names = [p.get("name", p.get("code", "?")) for p in top_picks[:2]]
    if len(names) >= 2:
        return industry + "产业链深度研报 — " + "、".join(names) + "领衔"
    return industry + "产业链深度研报 — " + names[0]
