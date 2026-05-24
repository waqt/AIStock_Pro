"""
投研 Pipeline 注册表 — 每种分析类型一个函数
每个 Pipeline 签名: async def xxx_pipeline(industry, provider, params) -> dict
返回: {"cio_report": "...", "top_picks": [...], "detail": {...}}
"""
import asyncio, os, json, time

# ═══ Pipeline 注册表 ═══════════════════════════════

PIPELINES = {}

def register(name: str, label: str, description: str):
    """装饰器: 注册 Pipeline"""
    def decorator(func):
        PIPELINES[name] = {"func": func, "label": label, "description": description}
        return func
    return decorator


# ═══ 已注册 Pipeline ═════════════════════════════════

@register("supply_chain", "产业链穿透", "高景气产业链深度分析: 供应链穿透+标的审计+估值定价+综合报告")
async def supply_chain_pipeline(industry: str, provider=None, params: dict = None):
    """产业链穿透分析 (当前 analyze-v4 逻辑)"""
    from app.domain.research.agents.supply_chain_hacker import SupplyChainHacker
    from app.domain.research.agents.dag_orchestrator import DAGOrchestrator

    slug = industry.replace(" ", "_")[:20]
    out_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "temp_lab")
    os.makedirs(out_dir, exist_ok=True)

    t0 = time.time()
    sc_path = os.path.join(out_dir, f"{slug}_phase1_sc.json")
    skip_phase1 = (params or {}).get("skip_phase1", False)

    # Phase 0: 读取/更新宏观报告
    macro = None
    try:
        from app.domain.research.agents.global_capex_scanner import GlobalCapexScanner
        macro = GlobalCapexScanner.load_macro_cache()
        if macro is None:
            scanner = GlobalCapexScanner(provider=provider)
            macro = await scanner.synthesize_macro_report()
            logger.info(f"[Pipeline] Macro report: {'generated' if macro else 'cached'}")
    except Exception as _e:
        logger.warning(f"[Pipeline] Macro report skipped: {_e}")

    # Phase 0.5 (Step 2): Pipeline Gatekeeper — 筛选最值得深挖的行业
    gatekeeper_result = None
    try:
        from app.domain.research.agents.market_scanner import MarketScanner
        scanner = MarketScanner(provider=provider)
        if macro and macro.get("data", {}).get("benefited_sectors"):
            # auto: 从 Step1 benefited_sectors 验证
            gatekeeper_result = await scanner._scan_auto(
                macro["data"]["benefited_sectors"])
        elif industry:
            # manual: 用户指定行业, 做深度全景
            gatekeeper_result = await scanner._deep_dive_manual(industry)
        if gatekeeper_result:
            industries = gatekeeper_result.get("industries", [gatekeeper_result])
            top = [i for i in industries if i.get("verdict", {}).get("enter_step3")]
            top.sort(key=lambda i: {"高": 0, "中": 1, "低": 2}.get(
                i.get("verdict", {}).get("priority", "低"), 3))
            if top:
                industry = top[0].get("industry", industry)
            logger.info(f"[Pipeline] Step2 Gatekeeper: {len(industries)} industries, "
                        f"{len(top)} passed filter, selected: {industry}")
    except Exception as _e:
        logger.warning(f"[Pipeline] Step2 Gatekeeper skipped: {_e}")

    # Phase 1: 供应链扫描
    if skip_phase1 and os.path.exists(sc_path):
        hacker_result = json.load(open(sc_path, "r", encoding="utf-8"))
    else:
        hacker = SupplyChainHacker(provider=provider)
        hacker_result = await hacker.analyze({"industry": industry, "include_portfolio": False})
        with open(sc_path, "w", encoding="utf-8") as f:
            json.dump(hacker_result, f, ensure_ascii=False, indent=2)

    # 同步目标标的行情+估值 (确保定价数据新鲜)
    core_stocks = hacker_result.get("core_stocks", [])
    codes = [s["code"] for s in core_stocks if s.get("code")]
    if codes:
        try:
            from app.domain.market_data.services.valuation import sync_valuation
            from app.domain.quant.engine.engine import QuantEngine
            from app.framework.database.session import async_session as _as
            async with _as() as _db:
                eng = QuantEngine(_db)
                await eng.sync_prices_only(target_codes=codes)
            await sync_valuation(target_codes=codes)
        except Exception as _e:
            pass  # 同步失败不阻塞分析
    orchestrator = DAGOrchestrator(provider=provider)
    context = {
        "stock_codes": codes, "industry": industry,
        "include_portfolio": False,
        "_supply_chain_prefetched": hacker_result,
        "_macro_report": macro.get("data") if macro else None,
        "_gatekeeper": gatekeeper_result.get("industries", [gatekeeper_result]) if gatekeeper_result else None,
    }
    dag_result = await orchestrator.analyze(context)
    dag_result["supply_chain"] = hacker_result

    # 落盘
    dag_path = os.path.join(out_dir, f"{slug}_phase2_dag.json")
    with open(dag_path, "w", encoding="utf-8") as f:
        json.dump(dag_result, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - t0
    dag_result["pipeline"] = {"name": "supply_chain", "elapsed": f"{elapsed:.0f}s"}
    return dag_result


@register("macro_cycle", "宏观周期", "宏观经济周期、流动性与资本市场周期分析")
async def macro_cycle_pipeline(industry: str = "", provider=None, params: dict = None):
    """宏观周期分析 — MarketScanner + GlobalCapexScanner 深度版"""
    from app.domain.research.agents.market_scanner import MarketScanner
    from app.domain.research.agents.global_capex_scanner import GlobalCapexScanner

    scanner = MarketScanner(provider=provider)
    capex = GlobalCapexScanner(provider=provider)
    scan, capex_result = await asyncio.gather(
        scanner.analyze({}), capex.analyze({"industry": "全球宏观"}))

    # LLM 合成
    summary_parts = []
    if capex_result.get("global_summary"):
        summary_parts.append(capex_result["global_summary"])
    if scan.get("briefing"):
        summary_parts.append(scan["briefing"])

    cio = "\n\n".join(summary_parts) if summary_parts else "暂无宏观分析数据"
    return {
        "cio_report": f"# 宏观周期分析报告\n\n{cio}",
        "top_picks": [],
        "detail": {"market_scan": scan, "capex": capex_result},
        "pipeline": {"name": "macro_cycle"},
    }


@register("founder_audit", "创始人审计", "核心团队背景、专利质量、股权激励穿透审计")
async def founder_audit_pipeline(codes_str: str = "", provider=None, params: dict = None):
    """创始人深度审计 — 对指定股票列表运行 HumanCapitalDetective"""
    from app.domain.research.agents.human_capital_detective import HumanCapitalDetective

    codes = [c.strip() for c in (codes_str or "").split(",") if c.strip()] if codes_str else []
    if not codes:
        return {"cio_report": "# 创始人审计报告\n\n未指定股票代码", "top_picks": [], "detail": {}}

    detective = HumanCapitalDetective(provider=provider)
    tasks = [detective.analyze({"stock_code": c}) for c in codes]
    results = await asyncio.gather(*tasks)

    lines = ["# 创始人审计报告", ""]
    for r in results:
        c = r.get("stock_code", "?")
        fb = r.get("founder_background", {})
        lines.append(f"## {c}")
        if fb.get("name"): lines.append(f"创始人: {fb['name']}, {fb.get('education','?')}")
        if fb.get("prior_experience"): lines.append(f"履历: {fb['prior_experience'][:200]}")
        lines.append("")

    return {
        "cio_report": "\n".join(lines),
        "top_picks": [],
        "detail": {"audits": results},
        "pipeline": {"name": "founder_audit"},
    }


@register("valuation_scan", "估值扫描", "批量估值定价, 识别低估/高估标的")
async def valuation_scan_pipeline(codes_str: str = "", provider=None, params: dict = None):
    """估值批量扫描"""
    from app.domain.research.agents.valuation_pricer import ValuationPricer

    codes = [c.strip() for c in (codes_str or "").split(",") if c.strip()] if codes_str else []
    if not codes:
        return {"cio_report": "# 估值扫描报告\n\n未指定股票代码", "top_picks": [], "detail": {}}

    pricer = ValuationPricer(provider=provider)
    tasks = [pricer.analyze({"stock": {"code": c, "name": c}, "financial": {}, "human_capital": {}}) for c in codes]
    results = await asyncio.gather(*tasks)

    lines = ["# 估值扫描报告", "", "| 代码 | 评级 | 上行空间 | 护城河(年) |", "|------|------|---------|-----------|"]
    for r in results:
        c = r.get("code", "?")
        v = r.get("verdict", "?")
        up = r.get("target_valuation", {}).get("upside_pct", "?")
        mw = r.get("moat_window", {}).get("years", "?")
        lines.append(f"| {c} | {v} | {up}% | {mw} |")

    return {
        "cio_report": "\n".join(lines),
        "top_picks": [],
        "detail": {"prices": results},
        "pipeline": {"name": "valuation_scan"},
    }
