"""投研分析 API"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from app.domain.research.agents.coordinator import ResearchCoordinator
from app.domain.research.agents.industry_analyst import IndustryAnalyst
from app.domain.research.agents.supply_chain_analyst import SupplyChainAnalyst
from app.domain.research.services.data_loader import data_loader
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

@router.post("/analyze")
async def research_analyze(req: ResearchRequest):
    """多智能体联合投研分析 (同步)"""
    try:
        coordinator = _get_coordinator()
        context = {"question": req.question, "stock_codes": req.stock_codes,
                   "industry": req.industry, "include_portfolio": req.include_portfolio}
        result = await coordinator.analyze(context)
        return {"success": True, "data": result}
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
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"[❌] Supply chain analysis failed: {e}")
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
