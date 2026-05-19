"""投研分析 API"""
from fastapi import APIRouter, HTTPException
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
from app.domain.research.services.data_loader import data_loader
from app.domain.research.services.report_store import save_report, list_reports, get_report, delete_report
from app.framework.logger import logger

router = APIRouter(prefix="/api/research", tags=["投研分析"])


class ResearchRequest(BaseModel):
    question: str = ""
    stock_codes: List[str] = []
    industry: Optional[str] = None
    include_portfolio: bool = True


# ── 初始化协调器 ───────────────────

def _get_coordinator():
    """创建协调器并注册分析师"""
    from app.framework.ai.providers.deepseek import DeepSeekProvider
    provider = DeepSeekProvider()
    coordinator = ResearchCoordinator(provider=provider)
    coordinator.register(IndustryAnalyst(provider=provider))
    return coordinator


# ── 端点 ────────────────────────────

@router.post("/analyze-v4")
async def research_analyze_v4(req: ResearchRequest):
    """V4.0 DAG 编排 — 5专家并行管道, 完整投研报告"""
    try:
        from app.framework.ai.providers.deepseek import DeepSeekProvider
        provider = DeepSeekProvider()
        orchestrator = DAGOrchestrator(provider=provider)
        context = {"question": req.question, "stock_codes": req.stock_codes,
                   "industry": req.industry or req.question, "include_portfolio": req.include_portfolio}
        result = await orchestrator.analyze(context)
        save_report("DAGOrchestrator", req.industry or req.question, result)
        return {"success": True, "data": result, "freshness": ResearchAgent.freshness_stamp()}
    except Exception as e:
        logger.error(f"[❌] DAG pipeline failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze")
async def research_analyze(req: ResearchRequest):
    """V3.0 多智能体联合投研分析 (同步, 向后兼容)"""
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


@router.delete("/reports/{report_id}")
async def delete_research_report(report_id: str):
    """删除单篇研报"""
    ok = delete_report(report_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return {"success": True, "message": f"Deleted {report_id}"}
