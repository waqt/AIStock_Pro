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


class ResearchRequest(BaseModel):
    question: str = ""
    stock_codes: List[str] = []
    industry: Optional[str] = None
    include_portfolio: bool = True
    analysis_type: Optional[str] = None  # supply_chain | macro_cycle | founder_audit | valuation_scan


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


@router.post("/supply-chain-hacker")
async def supply_chain_hacker_analysis(req: ResearchRequest):
    """V4.0 供应链降维穿透 — 纯瓶颈定位 + 标的映射 (不含财务/估值)"""
    try:
        from app.framework.ai.providers.deepseek import DeepSeekProvider
        provider = DeepSeekProvider()
        hacker = SupplyChainHacker(provider=provider)
        context = {"question": req.question, "stock_codes": req.stock_codes,
                   "industry": req.industry or req.question, "include_portfolio": req.include_portfolio}
        result = await hacker.analyze(context)
        save_report("SupplyChainHacker", req.industry or req.question, result)
        return {"success": True, "data": result, "freshness": ResearchAgent.freshness_stamp()}
    except Exception as e:
        logger.error(f"[❌] Supply chain hacker failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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


@router.post("/scan")
async def market_scan():
    """市场主动扫描 — 自动识别热门赛道 + 标的 + 每日简报 (无需参数)"""
    try:
        from app.framework.ai.providers.deepseek import DeepSeekProvider
        scanner = MarketScanner(provider=DeepSeekProvider())
        result = await scanner.analyze({})
        save_report("MarketScanner", "每日扫描", result)
        return {"success": True, "data": result, "freshness": ResearchAgent.freshness_stamp()}
    except Exception as e:
        logger.error(f"[❌] Market scan failed: {e}")
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
