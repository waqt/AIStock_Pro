"""投研分析 API"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.domain.research.agents.base import ResearchAgent
from app.domain.research.agents.coordinator import ResearchCoordinator
from app.domain.research.agents.industry_analyst import IndustryAnalyst
from app.domain.research.agents.supply_chain_analyst import SupplyChainAnalyst
from app.domain.research.agents.supply_chain_hacker import SupplyChainHacker
from app.domain.research.agents.financial_auditor import FinancialAuditor
from app.domain.research.agents.human_capital_detective import HumanCapitalDetective
from app.domain.research.agents.global_capex_scanner import GlobalCapexScanner
from app.domain.research.agents.dag_orchestrator import DAGOrchestrator
from app.domain.research.agents.market_scanner import MarketScanner
from app.domain.research.pipelines import PIPELINES
from app.domain.research.services.data_loader import data_loader
from app.domain.research.services.report_store import save_report, list_reports, get_report, delete_report
from app.framework.logger import logger

router = APIRouter(prefix="/api/research", tags=["投研分析"])

# Step 名称映射
STEP_LABELS = {
    "step1_macro": "宏观分析",
    "step1b_capital_flow": "资本流向扫描",
    "step2_gatekeeper": "行业看门人",
    "step3_sc_hacker": "产业链拆解",
    "step4_system_dynamics": "系统动力学推演",
    "step6_core_screening": "核心资产筛选",
    "step7_financial_audit": "财务质量审计",
    "step8_human_capital": "人力资本审计",
    "step8_valuation": "估值定价",
    "step9_expectation_gap": "市场预期差",
    "step10_risk_analysis": "风险分析",
    "step11_report": "综合报告",
}

# 统一完整 Pipeline（所有产业分析模式共享）
FULL_PIPELINE = [
    "step1_macro",
    "step1b_capital_flow",
    "step2_gatekeeper",
    "step3_sc_hacker",
    "step4_system_dynamics",
    "step6_core_screening",
    "step7_financial_audit",
    "step8_human_capital",
    "step8_valuation",
    "step9_expectation_gap",
    "step10_risk_analysis",
    "step11_report",
]

# 已实现的步骤
IMPLEMENTED_STEPS = {
    "step1_macro", "step1b_capital_flow", "step2_gatekeeper", "step3_sc_hacker"
}

# 可选步骤（不阻塞 pipeline）
OPTIONAL_STEPS = {"step8_human_capital"}


# ═══ 分析智能体注册表 ═══════════════════════
# 新增智能体只需在此加一条, 前端自动加载

AGENT_REGISTRY = [
    {
        "id": "supply_chain",
        "name": "产业链分析智能体",
        "desc": "产业链穿透 + 系统动力学 + CIO报告",
        "icon": "sitemap",
        "modes": [
            {"id": "auto_scan",          "name": "全局扫描",
             "desc": "全自动从宏观到报告，一站式产业链深度分析",
             "input_type": "none", "placeholder": "",
             "pipeline": FULL_PIPELINE},
            {"id": "manual_industry",    "name": "定性产业分析",
             "desc": "手动输入产业名称，展开全产业链穿透分析",
             "input_type": "industry", "placeholder": "输入行业关键词, 如: SOFC固体氧化物燃料电池",
             "pipeline": FULL_PIPELINE},
            {"id": "stock_deep",         "name": "公司深度分析",
             "desc": "输入股票代码或公司名，进行行业+公司双轨深度分析",
             "input_type": "stock_code", "placeholder": "输入6位代码或公司名, 如: 688012中微公司",
             "pipeline": FULL_PIPELINE},
            {"id": "stock_audit",        "name": "公司财务审计",
             "desc": "输入股票代码，仅运行财务质量审计(Step7)",
             "input_type": "stock_code", "placeholder": "输入6位代码, 如: 688012",
             "pipeline": ["step1_macro", "step7_financial_audit"]},
            {"id": "macro_only",        "name": "宏观周期分析",
             "desc": "独立运行宏观分析，生成宏观周期报告和路由决策",
             "input_type": "none", "placeholder": "",
             "pipeline": ["step1_macro"]},
            {"id": "capital_flow",       "name": "资本流向扫描",
             "desc": "从全球资本流向出发，识别产业机会并完成全链路分析",
             "input_type": "none", "placeholder": "",
             "pipeline": FULL_PIPELINE},  # 跳过 Step 1a, 从 Step 1b 跑全链
        ],
    },
    # 未来扩展:
    # {"id": "financial_analysis", "name": "财务分析智能体", ...},
    # {"id": "quant_trading", "name": "量化交易智能体", ...},
]


class ResearchRequest(BaseModel):
    question: str = ""
    stock_codes: List[str] = []
    industry: Optional[str] = None
    include_portfolio: bool = True
    analysis_type: Optional[str] = None  # supply_chain | macro_cycle | founder_audit | valuation_scan


class ScanRequest(BaseModel):
    """投研分析请求 — 支持多智能体 + 多模式"""
    agent_id: str = "supply_chain"   # 智能体ID
    mode_id: str = "manual_industry" # 模式ID
    target: str = ""                 # 行业名/股票代码 (根据 mode.input_type)
    mode: str = "auto"               # [废弃] 兼容旧参数
    target_industry: str = ""        # [废弃] 兼容旧参数
    question: str = ""               # [废弃] 兼容旧参数


# ── 初始化协调器 ───────────────────

def _get_coordinator():
    """创建协调器并注册分析师"""
    from app.framework.ai.providers.deepseek import DeepSeekProvider
    provider = DeepSeekProvider()
    coordinator = ResearchCoordinator(provider=provider)
    coordinator.register(IndustryAnalyst(provider=provider))
    return coordinator


# ── 端点 ────────────────────────────

@router.get("/analysts")
async def list_analysts():
    """列出所有可用的投研分析师类型"""
    result = []
    for name, info in PIPELINES.items():
        result.append({"type": name, "label": info["label"], "description": info["description"]})
    return {"success": True, "data": result}


@router.post("/analyze")
async def research_analyze(req: ResearchRequest):
    """统一投研入口 — 根据 analysis_type 选择 Pipeline"""
    from app.framework.ai.providers.deepseek import DeepSeekProvider
    provider = DeepSeekProvider()
    pipe_type = req.analysis_type or "supply_chain"
    pipeline = PIPELINES.get(pipe_type)
    if not pipeline:
        raise HTTPException(status_code=400, detail=f"Unknown analysis type: {pipe_type}")
    logger.info(f"[Analyze] Pipeline: {pipe_type} ({pipeline['label']}), industry={req.industry or req.question}")
    result = await pipeline["func"](industry=req.industry or req.question, provider=provider,
        params={"stock_codes": req.stock_codes, "include_portfolio": req.include_portfolio})
    save_report(pipeline["label"], req.industry or req.question, result)
    return {"success": True, "data": result, "freshness": ResearchAgent.freshness_stamp()}


@router.post("/analyze-v4")
async def research_analyze_v4(req: ResearchRequest, skip_phase1: bool = Query(False)):
    """V4.0 DAG 编排 — 分阶段执行, 支持断点续跑。
    skip_phase1=true → 读已有 Phase1 文件, 只重跑 Phase2 (审计+定价+报告)。适合修复审计/定价 bug 后快速验证。"""
    import os, json as _json, time as _time
    from app.framework.ai.providers.deepseek import DeepSeekProvider
    industry = req.industry or req.question
    slug = industry.replace(" ", "_")[:20]
    out_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "temp_lab")
    os.makedirs(out_dir, exist_ok=True)

    provider = DeepSeekProvider()
    t0 = _time.time()

    # ═══ Phase 1: 供应链扫描 → 落盘 ═══
    sc_path = os.path.join(out_dir, f"{slug}_phase1_sc.json")
    if skip_phase1 and os.path.exists(sc_path):
        hacker_result = _json.load(open(sc_path, "r", encoding="utf-8"))
        logger.info(f"[analyze-v4] Phase1 SKIPPED (loaded from cache): {len(hacker_result.get('core_stocks',[]))} stocks")
    else:
        hacker = SupplyChainHacker(provider=provider)
        hacker_result = await hacker.analyze({
            "industry": industry, "stock_codes": req.stock_codes,
            "include_portfolio": False})
        with open(sc_path, "w", encoding="utf-8") as f:
            _json.dump(hacker_result, f, ensure_ascii=False, indent=2)
        logger.info(f"[analyze-v4] Phase1 SC saved ({_time.time()-t0:.0f}s): {len(hacker_result.get('core_stocks',[]))} stocks")

    # ═══ Phase 2: 审计+定价 → 落盘 ═══
    core_stocks = hacker_result.get("core_stocks", [])
    codes = [s["code"] for s in core_stocks if s.get("code")]
    orchestrator = DAGOrchestrator(provider=provider)
    context = {
        "question": req.question, "stock_codes": codes, "industry": industry,
        "include_portfolio": req.include_portfolio,
        "_supply_chain_prefetched": hacker_result,
    }
    dag_result = await orchestrator.analyze(context)
    dag_path = os.path.join(out_dir, f"{slug}_phase2_dag.json")
    with open(dag_path, "w", encoding="utf-8") as f:
        _json.dump(dag_result, f, ensure_ascii=False, indent=2)
    logger.info(f"[analyze-v4] Phase2 DAG saved ({_time.time()-t0:.0f}s total)")

    # ═══ Phase 3: 组装报告 → 落盘 ═══
    dag_result["supply_chain"] = hacker_result
    save_report("DAGOrchestrator", industry, dag_result)
    return {"success": True, "data": dag_result, "freshness": ResearchAgent.freshness_stamp()}


@router.post("/report/{slug}")
async def regenerate_report(slug: str):
    """从已保存的 Phase1+Phase2 数据重新生成报告 (不改搜索和审计, 秒级迭代)"""
    import os, json as _json
    out_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "temp_lab")
    sc_path = os.path.join(out_dir, f"{slug}_phase1_sc.json")
    dag_path = os.path.join(out_dir, f"{slug}_phase2_dag.json")

    if not os.path.exists(sc_path):
        raise HTTPException(status_code=404, detail=f"Phase1 not found: {sc_path}")
    if not os.path.exists(dag_path):
        raise HTTPException(status_code=404, detail=f"Phase2 not found: {dag_path}")

    hacker = _json.load(open(sc_path, "r", encoding="utf-8"))
    dag = _json.load(open(dag_path, "r", encoding="utf-8"))
    dag["supply_chain"] = hacker

    return {"success": True, "data": dag,
            "note": f"Report from cached data. Edit _synthesize_basic in dag_orchestrator.py and retry this endpoint to iterate on report format."}


@router.post("/analyze-v3")
async def research_analyze_v3(req: ResearchRequest):
    """V3.0 多智能体联合投研分析 (同步, 向后兼容) — 路径 /analyze-v3"""
    try:
        coordinator = _get_coordinator()
        context = {"question": req.question, "stock_codes": req.stock_codes,
                   "industry": req.industry, "include_portfolio": req.include_portfolio}
        result = await coordinator.analyze(context)
        return {"success": True, "data": result, "freshness": ResearchAgent.freshness_stamp()}
    except Exception as e:
        logger.error(f"[❌] Research analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/search")
async def search_stocks(q: str = "", limit: int = 20):
    """搜索股票 (供投研 Agent 调用)"""
    return await data_loader.search_stocks(q, limit)


@router.get("/data/positions")
async def get_positions_data():
    """获取持仓数据"""
    return await data_loader.load_positions()


@router.get("/data/macro")
async def get_macro_data():
    """获取宏观数据"""
    return await data_loader.load_macro()


@router.post("/supply-chain")
async def supply_chain_analysis(req: ResearchRequest):
    """供应链深度分析 — 5步推理: 景气信号→供应链图谱→瓶颈→标的→估值"""
    try:
        from app.framework.ai.providers.deepseek import DeepSeekProvider
        provider = DeepSeekProvider()
        analyst = SupplyChainAnalyst(provider=provider)
        context = {"question": req.question, "stock_codes": req.stock_codes,
                   "industry": req.industry or req.question, "include_portfolio": req.include_portfolio}
        result = await analyst.analyze(context)
        save_report("SupplyChainAnalyst", req.industry or req.question, result)
        return {"success": True, "data": result, "freshness": ResearchAgent.freshness_stamp()}
    except Exception as e:
        logger.error(f"[❌] Supply chain analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class LevelAnalysisRequest(BaseModel):
    industry: str = ""
    level_name: str = ""
    level_info: Optional[Dict[str, Any]] = None


@router.post("/supply-chain-hacker/level")
async def supply_chain_level_analysis(req: LevelAnalysisRequest):
    """V4.0 供应链单层级深度穿透 — 找出该层所有高价值资产"""
    try:
        from app.framework.ai.providers.deepseek import DeepSeekProvider
        hacker = SupplyChainHacker(provider=DeepSeekProvider())
        result = await hacker.analyze_level(req.industry, req.level_name, req.level_info)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"[❌] Level analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# (旧的 /supply-chain-hacker 已迁移至 V5.8 版本 — 见下方 @router.post("/supply-chain-hacker"))


@router.post("/audit/human-capital")
async def audit_human_capital(req: ResearchRequest):
    """V4.0 人力资本审计 — 单只股票研发团队背景穿透"""
    code = (req.stock_codes or [None])[0]
    if not code:
        raise HTTPException(status_code=400, detail="需要至少一个 stock_code")
    try:
        from app.framework.ai.providers.deepseek import DeepSeekProvider
        detective = HumanCapitalDetective(provider=DeepSeekProvider())
        result = await detective.analyze({"stock_code": code, "stock_name": req.industry or code})
        return {"success": True, "data": result, "freshness": ResearchAgent.freshness_stamp()}
    except Exception as e:
        logger.error(f"[❌] Human capital audit failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/audit/financial/{stock_code}")
async def audit_financial(stock_code: str):
    """V4.0 财务审计 — 单只股票 8Q 剪刀差 + 四连击 (无需 AI)"""
    try:
        auditor = FinancialAuditor()
        result = await auditor.analyze({"stock_code": stock_code, "stock_name": stock_code})
        return {"success": True, "data": result, "freshness": ResearchAgent.freshness_stamp()}
    except Exception as e:
        logger.error(f"[❌] Financial audit failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/capex-scan")
async def global_capex_scan(req: ResearchRequest):
    """V4.0 全球 CapEx 扫描 — MAG7 资本开支计划 → 景气方向"""
    try:
        from app.framework.ai.providers.deepseek import DeepSeekProvider
        scanner = GlobalCapexScanner(provider=DeepSeekProvider())
        context = {"industry": req.industry or "", "question": req.question}
        result = await scanner.analyze(context)
        save_report("GlobalCapexScanner", req.industry or "全局", result)
        return {"success": True, "data": result, "freshness": ResearchAgent.freshness_stamp()}
    except Exception as e:
        logger.error(f"[❌] Global capex scan failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents")
async def list_agents():
    """返回已注册的分析智能体及其支持的模式"""
    return {"success": True, "data": AGENT_REGISTRY}


async def _do_scan(req: ScanRequest):
    """投研分析核心逻辑 (同步/异步模式复用)"""
    from app.framework.ai.providers.deepseek import DeepSeekProvider
    from app.framework.pipeline.checkpoint import (
        generate_run_id, hash_input, load_checkpoint,
        save_checkpoint, save_manifest,
    )
    from app.framework.pipeline.trace import TraceContext

    target = req.target or req.target_industry or req.question
    agent_id = req.agent_id
    mode_id = req.mode_id

    agent_def = next((a for a in AGENT_REGISTRY if a["id"] == agent_id), None)
    if not agent_def:
        raise HTTPException(status_code=400, detail=f"Unknown agent: {agent_id}")
    mode_def = next((m for m in agent_def["modes"] if m["id"] == mode_id), None)
    if not mode_def:
        raise HTTPException(status_code=400, detail=f"Unknown mode '{mode_id}' for agent '{agent_id}'")
    if mode_def["input_type"] != "none" and not target:
        raise HTTPException(status_code=400, detail=f"Mode '{mode_id}' requires input: {mode_def['input_type']}")

    scanner = MarketScanner(provider=DeepSeekProvider())

    if mode_id == "macro_only":
        target = "宏观周期分析-" + datetime.now().strftime("%Y%m%d-%H%M")
        from app.domain.research.agents.global_capex_scanner import GlobalCapexScanner
        gcs = GlobalCapexScanner(provider=DeepSeekProvider())
        macro_result = await gcs.synthesize_macro_report()
        return {"success": True, "data": macro_result, "run_id": generate_run_id(target),
                "freshness": ResearchAgent.freshness_stamp()}

    if mode_id in ("auto_scan", "capital_flow"):
        import os as _os, json as _json, glob as _glob
        hypothesis = []
        target = (mode_id == "auto_scan" and "全局扫描-" or "资本流向-") + datetime.now().strftime("%Y%m%d-%H%M")
        today = datetime.now().strftime("%Y%m%d")

        # Step 1b: 资本流向缓存或自动运行
        base_data = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "..", "..", "..", "data"))
        cf_pattern = _os.path.join(base_data, "pipeline_checkpoints", "*资本流向*", "step1b_capital_flow*.json")
        cf_runs = sorted(_glob.glob(cf_pattern), reverse=True)
        cf_loaded = False
        if cf_runs:
            try:
                with open(cf_runs[0], "r", encoding="utf-8") as f:
                    cf = _json.load(f)
                cf_date = (cf.get("saved_at", "") or "")[:10].replace("-", "")
                if cf_date == today:  # 当天有效
                    output = cf.get("output", {})
                    vectors = output.get("pressure_vectors", [])
                    # 降级: 旧格式 capex_vectors (无 pressure_vectors 时回退)
                    if not vectors:
                        vectors = output.get("capex_vectors", [])
                        logger.info(f"[MarketScanner] Using legacy capex_vectors format")
                    # 系统节点 → 候选产业映射 (Step 1b → Step 2 桥接)
                    pressure_map = {"power_infrastructure":["变压器","电网设备","铜"],"thermal_management":["液冷散热","服务器电源"],"memory_bandwidth":["HBM高带宽内存","先进封装"],"compute_chip":["AI芯片","GPU"],"optical_communication":["光模块","光芯片"],"energy_storage":["储能","锂电池"]}
                    for v in vectors:
                        node = v.get("system_node", "")
                        industries = pressure_map.get(node, [])
                        for ind in industries[:2]:
                                hypothesis.append({"sector": beneficiary, "name": beneficiary,
                                    "capex_initiator": v.get("initiator", ""), "target": v.get("target", "")})
                    if hypothesis:
                        cf_loaded = True
                        cf_cached_output = output  # 稍后复制到 run_id
                        logger.info(f"[MarketScanner] Using capital_flow cache: {len(hypothesis)} candidates")
                else:
                    logger.info(f"[MarketScanner] Capital flow cache expired ({cf_date} < {today})")
            except Exception:
                pass

        # 无当天缓存 → 自动跑 Step 1b
        if not cf_loaded:
            logger.info(f"[MarketScanner] Auto-running capital flow scan...")
            try:
                from app.domain.research.agents.capital_flow_scanner import CapitalFlowScanner
                from app.framework.pipeline.trace import TraceContext
                cf_scanner = CapitalFlowScanner(provider=DeepSeekProvider())
                cf_trace = TraceContext(generate_run_id("资本流向"))
                cf_result = await cf_scanner.analyze(ctx={}, trace=cf_trace)
                vectors = cf_result.get("capex_vectors", [])
                for v in vectors:
                    tt = v.get("theme_type", "")
                    if tt in ("industrial_capex", "commodity_cycle"):
                        for beneficiary in v.get("china_beneficiary", [])[:2]:
                            hypothesis.append({"sector": ind, "name": ind,
                                "pressure_node": node, "pressure_signals": v.get("pressure_signals", [])[:2]})
                # 保存 Step 1b checkpoint 到同一个 run_id
                ih = hash_input({"step": "capital_flow", "date": today})
                save_checkpoint("step1b_capital_flow", run_id, ih, cf_result, {"elapsed": 0})
                cf_trace.write("step1b_capital_flow")
                logger.info(f"[MarketScanner] Capital flow done, saved to {run_id}: {len(hypothesis)} candidates")
            except Exception as e:
                logger.warning(f"[MarketScanner] Capital flow auto-run failed: {e}")

        if not hypothesis:
            # Step 1b 失败 → 不退化到 legacy, 而是用搜索结果直接提取候选
            logger.warning(f"[MarketScanner] Capital flow returned no vectors, using raw search fallback")
            hypothesis = [{"sector": "AI算力基础设施", "name": "AI算力"},
                          {"sector": "半导体设备国产化", "name": "半导体设备"},
                          {"sector": "电力设备与电网升级", "name": "电网设备"}]
        ctx = {"mode": "auto", "hypothesis_sectors": hypothesis}
    else:
        ctx = {"mode": "manual" if mode_def["input_type"] != "none" else "auto"}
        if target: ctx["target_industry"] = target

    report_label = target if target else "每日扫描"
    step = "step2_gatekeeper"
    run_id = generate_run_id(report_label)
    # 如果从缓存加载了 Step 1b, 复制到当前 run_id
    if cf_loaded:
        try:
            ih = hash_input({"step": "capital_flow", "date": today})
            save_checkpoint("step1b_capital_flow", run_id, ih, cf_cached_output, {"elapsed": 0})
        except Exception: pass
    t0 = __import__("time").time()

    input_hash = hash_input({
        "mode": req.mode, "target": target,
        "date": __import__("datetime").datetime.now().strftime("%Y%m%d"),
        "agent_version": "market_scanner_v5.11",
    })
    cached = load_checkpoint(step, run_id, input_hash)
    if cached:
        logger.info(f"[MarketScanner] CACHE HIT: {run_id}/{step}")
        return {"success": True, "data": cached, "from_cache": True, "run_id": run_id,
                "freshness": ResearchAgent.freshness_stamp()}

    trace = TraceContext(run_id)
    result = await scanner.analyze(ctx, trace=trace)

    elapsed = round(__import__("time").time() - t0, 1)
    try:
        save_checkpoint(step, run_id, input_hash, result, {"elapsed": elapsed, "input_summary": f"mode={req.mode}, target={target}"})
        trace.write(step)
        save_manifest(run_id, {"run_id": run_id, "industry": report_label,
            "mode": "auto" if mode_id == "auto_scan" else "manual",
            "mode_id": mode_id, "agent_id": agent_id,
            "status": "completed", "started_at": trace.to_dict()["started_at"],
            "completed_at": __import__("datetime").datetime.now().isoformat(),
            "elapsed_seconds": elapsed, "step": step, "input_hash": input_hash})
    except Exception as e:
        logger.warning(f"[MarketScanner] Checkpoint save failed (non-fatal): {e}")

    save_report("MarketScanner", report_label, result)
    return {"success": True, "data": result, "run_id": run_id,
            "freshness": ResearchAgent.freshness_stamp()}


@router.post("/scan")
async def market_scan(req: ScanRequest = ScanRequest(), async_mode: bool = Query(default=False)):
    """投研分析入口 — ?async=true 后台执行, 立即返回 exec_id"""
    if async_mode:
        from app.framework.tasks.engine import TaskEngine
        from app.framework.pipeline.checkpoint import generate_run_id, save_manifest
        target = req.target or req.target_industry or req.question or ("全局扫描" if req.mode_id == "auto_scan" else "资本流向" if req.mode_id == "capital_flow" else "宏观分析" if req.mode_id == "macro_only" else "分析")
        run_id = generate_run_id(target)
        # 立即创建空白项目, 前端可见
        save_manifest(run_id, {"run_id": run_id, "industry": target, "mode": "auto" if req.mode_id in ("auto_scan","capital_flow") else "manual",
            "mode_id": req.mode_id, "agent_id": req.agent_id, "status": "pending",
            "started_at": datetime.now().isoformat()})
        exec_id = await TaskEngine.run_task("research_analyze", {
            "agent_id": req.agent_id, "mode_id": req.mode_id, "target": target,
        })
        return {"success": True, "data": {"exec_id": exec_id, "status": "PENDING", "run_id": run_id},
                "message": "任务已提交, 轮询 GET /system/tasks/executions/" + exec_id}
    try:
        return await _do_scan(req)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[MarketScanner] Scan failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class SupplyChainRequest(BaseModel):
    industry: str = ""
    step2_output: dict = None  # Step 2 的完整输出 (含 _step3_guidance)


@router.post("/supply-chain-hacker")
async def supply_chain_hacker(req: SupplyChainRequest = SupplyChainRequest(),
                                async_mode: bool = Query(default=False)):
    """Step 3: 产业链系统拆解 — ?async_mode=true 后台执行"""
    if async_mode:
        from app.framework.tasks.engine import TaskEngine
        exec_id = await TaskEngine.run_task("research_analyze", {
            "agent_id": "supply_chain", "mode_id": "step3_standalone",
            "target": req.industry, "step2_output": req.step2_output,
        })
        return {"success": True, "data": {"exec_id": exec_id, "status": "PENDING"},
                "message": "Step3任务已提交, 轮询 GET /system/tasks/executions/" + exec_id}
    try:
        from app.framework.ai.providers.deepseek import DeepSeekProvider
        from app.framework.pipeline.checkpoint import (
            generate_run_id, hash_input, load_checkpoint,
            save_checkpoint, save_manifest,
        )
        from app.framework.pipeline.trace import TraceContext

        industry = req.industry.strip()
        if not industry:
            raise HTTPException(status_code=400, detail="industry is required")

        hacker_instance = SupplyChainHacker(provider=DeepSeekProvider())
        step = "step3_sc_hacker"
        # 复用已有 run_id (如果来自同一个 industry), 否则新建
        run_id = generate_run_id(industry)
        t0 = __import__("time").time()

        # 提取 Step 2 指引
        step2 = (req.step2_output or {}).get("_step3_guidance", {}) if req.step2_output else {}
        ctx = {"industry": industry, "step2_guidance": step2}

        # 缓存
        input_hash = hash_input({
            "industry": industry,
            "step2_phase": step2.get("cycle_phase", ""),
            "date": __import__("datetime").datetime.now().strftime("%Y%m%d"),
            "agent_version": "supply_chain_hacker_v5.8",
        })
        cached = load_checkpoint(step, run_id, input_hash)
        if cached:
            logger.info(f"[SupplyChainHacker] CACHE HIT: {run_id}/{step}")
            return {"success": True, "data": cached, "from_cache": True, "run_id": run_id}

        trace = TraceContext(run_id)
        result = await hacker_instance.analyze(ctx, trace=trace)

        elapsed = round(__import__("time").time() - t0, 1)
        try:
            save_checkpoint(step, run_id, input_hash, result, {"elapsed": elapsed})
            trace.write(step)
            # 更新已有 manifest (追加 step3 信息)
            from app.framework.pipeline.checkpoint import load_manifest
            manifest = load_manifest(run_id) or {}
            manifest["step"] = step
            manifest["elapsed_seconds"] = (manifest.get("elapsed_seconds", 0) or 0) + elapsed
            save_manifest(run_id, manifest)
            logger.info(f"[SupplyChainHacker] Checkpoint saved: {run_id}/{step} ({elapsed}s)")
        except Exception as e:
            logger.warning(f"[SupplyChainHacker] Checkpoint save failed (non-fatal): {e}")

        save_report("SupplyChainHacker", industry, result)
        return {"success": True, "data": result, "run_id": run_id,
                "freshness": ResearchAgent.freshness_stamp()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[SupplyChainHacker] Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class IndustryDrilldownRequest(BaseModel):
    parent_run_id: str = ""
    industry_name: str = ""


@router.post("/scan/industry-drilldown")
async def industry_drilldown(req: IndustryDrilldownRequest):
    """全局扫描结果 → 选定行业 → 触发 Step 3"""
    try:
        from app.framework.pipeline.checkpoint import find_checkpoint_file, save_checkpoint
        from app.framework.pipeline.trace import TraceContext
        from app.framework.ai.providers.deepseek import DeepSeekProvider
        import json as _json

        # 从父 run 的 step2 检查点找该行业的输出
        cp_file = find_checkpoint_file(req.parent_run_id, "step2_gatekeeper")
        if not cp_file:
            raise HTTPException(status_code=404, detail=f"Parent run not found: {req.parent_run_id}")
        with open(cp_file, "r", encoding="utf-8") as f:
            step2 = _json.load(f)
        industries = step2.get("output", {}).get("industries", [])
        target = next((i for i in industries if i.get("industry") == req.industry_name), None)
        if not target:
            raise HTTPException(status_code=404, detail=f"Industry '{req.industry_name}' not found in run {req.parent_run_id}")

        # 调 Step 3
        hacker = SupplyChainHacker(provider=DeepSeekProvider())
        step2_guidance = target.get("_step3_guidance", {})
        ctx = {"industry": req.industry_name, "step2_guidance": step2_guidance}
        run_id = req.parent_run_id  # 保存到同一目录
        trace = TraceContext(run_id)
        result = await hacker.analyze(ctx, trace=trace)

        save_checkpoint("step3_sc_hacker", run_id, "drilldown", result, {"elapsed": 0})
        trace.write("step3_sc_hacker")
        logger.info(f"[Drilldown] Step3 done: {req.industry_name} → {len(result.get('supply_chain_map',[]))} layers")
        return {"success": True, "data": result, "run_id": run_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Drilldown] Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/capital-flow")
async def capital_flow_scan(async_mode: bool = Query(default=False)):
    """Step 1b: 全球资本流向扫描 — ?async_mode=true 后台执行"""
    if async_mode:
        from app.framework.tasks.engine import TaskEngine
        exec_id = await TaskEngine.run_task("research_analyze", {
            "agent_id": "supply_chain", "mode_id": "capital_flow",
            "target": "capital_flow",
        })
        return {"success": True, "data": {"exec_id": exec_id, "status": "PENDING"}}
    try:
        from app.framework.ai.providers.deepseek import DeepSeekProvider
        from app.domain.research.agents.capital_flow_scanner import CapitalFlowScanner
        from app.framework.pipeline.checkpoint import generate_run_id, hash_input, load_checkpoint, save_checkpoint, save_manifest
        from app.framework.pipeline.trace import TraceContext

        scanner = CapitalFlowScanner(provider=DeepSeekProvider())
        run_id = generate_run_id("资本流向")
        step = "step1b_capital_flow"
        t0 = __import__("time").time()

        input_hash = hash_input({
            "step": "capital_flow",
            "date": __import__("datetime").datetime.now().strftime("%Y%m%d"),
        })
        cached = load_checkpoint(step, run_id, input_hash)
        if cached:
            return {"success": True, "data": cached, "from_cache": True, "run_id": run_id}

        trace = TraceContext(run_id)
        result = await scanner.analyze(ctx={}, trace=trace)

        elapsed = round(__import__("time").time() - t0, 1)
        try:
            save_checkpoint(step, run_id, input_hash, result, {"elapsed": elapsed})
            trace.write(step)
            save_manifest(run_id, {"run_id": run_id, "industry": "资本流向", "status": "completed",
                "started_at": trace.to_dict()["started_at"],
                "completed_at": __import__("datetime").datetime.now().isoformat(),
                "elapsed_seconds": elapsed, "step": step})
        except Exception as e:
            logger.warning(f"[CapitalFlow] Checkpoint save failed (non-fatal): {e}")

        save_report("CapitalFlowScanner", "资本流向", result)
        return {"success": True, "data": result, "run_id": run_id}
    except Exception as e:
        logger.error(f"[CapitalFlow] Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stocks/batch-info")
async def batch_stock_info(codes: List[str]):
    """批量获取股票基本信息 (供投研标的提取面板使用)"""
    if not codes:
        return {"success": True, "data": []}
    from app.framework.database.session import async_session
    from app.models.models import StockInfo
    from sqlalchemy import select
    async with async_session() as db:
        res = await db.execute(
            select(StockInfo).where(StockInfo.stock_code.in_(codes[:30])))
        rows = {r.stock_code: r for r in res.scalars().all()}
        result = []
        for code in codes:
            s = rows.get(code)
            result.append({
                "code": code,
                "name": s.stock_name if s else code,
                "industry": s.industry if s else None,
                "pe_ttm": s.pe_ttm if s else None,
                "mcap_yi": s.mcap_yi if s else None,
            })
        return {"success": True, "data": result}


# ═══════════════════════════════════════════
# Pipeline 运维 API
# ═══════════════════════════════════════════

class ResumeRequest(BaseModel):
    from_step: str = "step3_sc_hacker"
    force: bool = False


@router.get("/pipeline/runs")
async def list_pipeline_runs(limit: int = Query(default=20, ge=1, le=100)):
    """列出所有 Pipeline run 历史"""
    try:
        from app.framework.pipeline.checkpoint import list_runs, make_display_name
        runs = list_runs()
        for r in runs:
            r["display_name"] = make_display_name(r["run_id"], r.get("industry", ""))
        return {"success": True, "data": runs[:limit], "total": len(runs)}
    except Exception as e:
        logger.error(f"[PipelineAPI] List runs failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipeline/{run_id}")
async def get_pipeline_run(run_id: str):
    """单 run 详情: manifest + 各 step 检查点列表 (含虚拟 Step1 宏观)"""
    try:
        from app.framework.pipeline.checkpoint import (
            load_manifest, list_checkpoints, CHECKPOINT_DIR, make_display_name
        )
        import os
        manifest = load_manifest(run_id)
        checkpoints = list_checkpoints(run_id)
        steps = {}
        for cp in checkpoints:
            s = cp.get("step", "unknown")
            steps[s] = {
                "step": s, "saved_at": cp.get("saved_at"),
                "elapsed_seconds": cp.get("elapsed"), "file": cp.get("file"),
            }
        run_dir = os.path.join(CHECKPOINT_DIR, run_id)
        for s in list(steps.keys()):
            tf = os.path.join(run_dir, f"{s}.trace.txt")
            if os.path.exists(tf):
                steps[s]["has_trace"] = True

        # 虚拟 Step 1: 宏观报告 (全局共享, 不在 run 目录下)
        macro_path = os.path.join(CHECKPOINT_DIR, "..", "macro_report.json")
        macro_path = os.path.abspath(macro_path)
        if os.path.exists(macro_path):
            macro_stat = os.stat(macro_path)
            steps["step1_macro"] = {
                "step": "step1_macro",
                "saved_at": __import__("datetime").datetime.fromtimestamp(macro_stat.st_mtime).isoformat(),
                "elapsed_seconds": 0,
                "file": macro_path,
                "has_trace": False,
                "is_shared": True,
            }
            steps = dict(sorted(steps.items()))

        # 根据 manifest 中的 mode_id 查找预期 pipeline
        mode_id = (manifest or {}).get("mode_id", "")
        mode = (manifest or {}).get("mode", "manual")
        pipeline_def = []
        # 从 AGENT_REGISTRY 精确匹配
        for agent in AGENT_REGISTRY:
            for m in agent.get("modes", []):
                if m["id"] == mode_id:
                    pipeline_def = m.get("pipeline", [])
                    break
            if pipeline_def: break
        # 降级: 根据 mode 推断
        if not pipeline_def:
            if mode == "auto":
                pipeline_def = ["step1_macro", "step1b_capital_flow", "step2_gatekeeper"]
            else:
                pipeline_def = ["step1_macro", "step2_gatekeeper", "step3_sc_hacker"]

        # 合并 pipeline 定义 + 实际完成状态 (三态: completed / pending / planned)
        full_steps = {}
        run_status = (manifest or {}).get("status", "pending")
        for s in pipeline_def:
            label = STEP_LABELS.get(s, s)
            implemented = s in IMPLEMENTED_STEPS
            optional = s in OPTIONAL_STEPS
            if s in steps:
                full_steps[s] = {**steps[s], "label": label, "status": "completed",
                                 "implemented": True, "optional": optional}
            elif not implemented:
                full_steps[s] = {"step": s, "label": label, "status": "planned",
                                 "elapsed_seconds": 0, "implemented": False, "optional": optional}
            else:
                full_steps[s] = {"step": s, "label": label, "status": "pending",
                                 "elapsed_seconds": 0, "implemented": True, "optional": optional}
        for s, info in steps.items():
            if s not in full_steps:
                full_steps[s] = {**info, "label": STEP_LABELS.get(s, s), "status": "completed",
                                 "implemented": True, "optional": s in OPTIONAL_STEPS}
        full_steps = dict(sorted(full_steps.items()))

        return {"success": True, "data": {
            "run_id": run_id,
            "display_name": make_display_name(run_id, manifest.get("industry", "") if manifest else ""),
            "manifest": manifest,
            "steps": full_steps,
            "pipeline": pipeline_def,
        }}
    except Exception as e:
        logger.error(f"[PipelineAPI] Get run failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipeline/{run_id}/trace/{step}")
async def get_pipeline_trace(run_id: str, step: str):
    """读取某 step 的溯源日志"""
    import os, json as _json
    from app.framework.pipeline.checkpoint import CHECKPOINT_DIR
    tp = os.path.join(CHECKPOINT_DIR, run_id, f"{step}.trace.txt")
    if not os.path.exists(tp):
        raise HTTPException(status_code=404, detail=f"Trace not found: {run_id}/{step}")
    events = []
    with open(tp, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(_json.loads(line))
                except Exception:
                    events.append({"raw": line[:500]})
    return {"success": True, "data": {"run_id": run_id, "step": step, "event_count": len(events), "events": events}}


@router.post("/pipeline/{run_id}/resume")
async def resume_pipeline_run(run_id: str, req: ResumeRequest = ResumeRequest()):
    """从指定 step 断点续跑"""
    try:
        from app.framework.pipeline.checkpoint import load_manifest
        manifest = load_manifest(run_id)
        if not manifest:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
        return {"success": True, "data": {
            "run_id": run_id, "from_step": req.from_step,
            "status": "not_implemented",
            "message": "PipelineRunner 尚未实现。手动操作: (1) 编辑 checkpoint JSON → (2) curl Agent 端点重跑下游",
            "manifest_industry": manifest.get("industry", ""),
        }}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PipelineAPI] Resume failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/pipeline/{run_id}/star")
async def toggle_star(run_id: str):
    """切换星标收藏"""
    try:
        from app.framework.pipeline.checkpoint import load_manifest, update_manifest
        manifest = load_manifest(run_id)
        if not manifest:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
        starred = not manifest.get("starred", False)
        update_manifest(run_id, {"starred": starred})
        return {"success": True, "data": {"run_id": run_id, "starred": starred}}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PipelineAPI] Star toggle failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/pipeline/{run_id}")
async def delete_pipeline_run(run_id: str):
    """删除项目及其所有检查点文件"""
    try:
        import shutil, os
        from app.framework.pipeline.checkpoint import CHECKPOINT_DIR
        run_dir = os.path.join(CHECKPOINT_DIR, run_id)
        if not os.path.isdir(run_dir):
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
        # 同时清理关联的 research_reports
        try:
            manifest = __import__("app.framework.pipeline.checkpoint", fromlist=["load_manifest"]).load_manifest(run_id)
            industry = (manifest or {}).get("industry", "")
        except Exception:
            industry = ""
        shutil.rmtree(run_dir)
        logger.info(f"[PipelineAPI] Deleted run: {run_id}")
        return {"success": True, "data": {"run_id": run_id, "deleted": True, "industry": industry}}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PipelineAPI] Delete run failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipeline/{run_id}/checkpoint/{step}")
async def get_checkpoint_output(run_id: str, step: str):
    """读取指定 step 的检查点 output 内容"""
    try:
        import json as _json, os
        from app.framework.pipeline.checkpoint import find_checkpoint_file

        # 虚拟 Step 1: 直接读 macro_report.json
        if step == "step1_macro":
            macro_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "data", "macro_report.json")
            macro_path = os.path.abspath(macro_path)
            if not os.path.exists(macro_path):
                raise HTTPException(status_code=404, detail="Macro report not found")
            with open(macro_path, "r", encoding="utf-8") as f:
                macro = _json.load(f)
            return {"success": True, "data": {
                "run_id": run_id, "step": "step1_macro",
                "output": {
                    "generated_at": macro.get("generated_at", ""),
                    "valid_until": macro.get("valid_until", ""),
                    "generated_by": macro.get("generated_by", ""),
                    "executive_summary": macro.get("data", {}).get("executive_summary", {}),
                    "top_3_themes": macro.get("data", {}).get("top_3_themes", []),
                },
                "saved_at": macro.get("generated_at", ""),
            }}

        cp_file = find_checkpoint_file(run_id, step)
        if not cp_file:
            raise HTTPException(status_code=404, detail=f"Checkpoint not found: {run_id}/{step}")
        with open(cp_file, "r", encoding="utf-8") as f:
            record = _json.load(f)
        return {"success": True, "data": {
            "run_id": run_id, "step": step,
            "output": record.get("output", {}),
            "saved_at": record.get("saved_at"),
        }}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PipelineAPI] Get checkpoint failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class CheckpointEditRequest(BaseModel):
    output: dict  # 新的 checkpoint output 内容


@router.put("/pipeline/{run_id}/checkpoint/{step}")
async def save_checkpoint_edit(run_id: str, step: str, body: CheckpointEditRequest):
    """保存手动编辑后的 checkpoint output"""
    try:
        from app.framework.pipeline.checkpoint import update_checkpoint_output
        result = update_checkpoint_output(run_id, step, body.output)
        if not result:
            raise HTTPException(status_code=404, detail=f"Checkpoint not found: {run_id}/{step}")
        logger.info(f"[PipelineAPI] Checkpoint edited: {run_id}/{step} → {result}")
        return {"success": True, "data": {"run_id": run_id, "step": step, "saved": result}}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PipelineAPI] Checkpoint edit failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/stock/{code}")
async def get_stock_data(code: str):
    """获取单只股票的完整投研数据"""
    market = await data_loader.load_market_data([code], days=30)
    fund = await data_loader.load_fundamentals([code])
    ind = await data_loader.load_indicators([code])
    return {
        "code": code,
        "market_data": market.get(code, []),
        "fundamentals": fund.get(code, {}),
        "indicators": ind.get(code, {}),
    }


# ═══════════════════════════════════════════
# 研报持久化
# ═══════════════════════════════════════════

@router.get("/reports")
async def list_research_reports(limit: int = 20):
    """列出历史研报 (摘要列表)"""
    return {"success": True, "data": list_reports(limit)}


@router.get("/reports/{report_id}")
async def get_research_report(report_id: str):
    """获取单篇研报完整内容"""
    report = get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return {"success": True, "data": report}


@router.post("/scrape")
async def scrape_url(url: str = None, urls: str = None):
    """抓取网页并抽取正文。传 url= 或 urls=(逗号分隔)"""
    if urls:
        url_list = [u.strip() for u in urls.split(",") if u.strip()]
        result = await data_loader.scrape_urls(url_list)
    elif url:
        result = await data_loader.scrape_url(url)
    else:
        raise HTTPException(status_code=400, detail="需要 url 或 urls 参数")
    return {"success": True, "data": result}


@router.post("/reports/{report_id}/regenerate")
async def regenerate_report_markdown(report_id: str):
    """用已存储的结构化数据重新生成完整中文 Markdown 报告。
    不改供应链扫描和审计数据, 只重跑 _synthesize_basic。
    适用于历史报告格式迁移或报告模板迭代。
    """
    report = get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

    data = report.get("data", {})
    detail = data.get("detail", {})
    hacker = detail.get("supply_chain") or data.get("supply_chain", {})
    capex = detail.get("capex", {})
    audits = detail.get("audits", [])
    prices = detail.get("prices", [])
    industry = report.get("industry", "")

    if not hacker:
        raise HTTPException(status_code=400, detail="Report has no supply_chain data, cannot regenerate")

    from app.domain.research.agents.dag_orchestrator import DAGOrchestrator
    orchestrator = DAGOrchestrator(provider=None)  # _synthesize_basic 不需要 provider
    basic = await orchestrator._synthesize_basic(industry, capex, hacker, audits, prices)

    # 更新报告
    data["cio_report"] = basic["cio_report"]
    data["top_picks"] = basic.get("top_picks", data.get("top_picks", []))
    data["final_summary"] = basic.get("final_summary", "")
    data["key_risks"] = basic.get("key_risks", [])
    data["catalysts_to_watch"] = basic.get("catalysts_to_watch", [])

    import os, json as _json
    from app.domain.research.services.report_store import REPORTS_DIR
    # 直接覆盖原文件
    filepath = os.path.join(REPORTS_DIR, f"{report_id}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        report["data"] = data
        _json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    return {"success": True, "message": f"Report {report_id} regenerated", "data": report}


@router.delete("/reports/{report_id}")
async def delete_research_report(report_id: str):
    """删除单篇研报"""
    ok = delete_report(report_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return {"success": True, "message": f"Deleted {report_id}"}
