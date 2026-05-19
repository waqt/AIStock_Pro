"""决策API — 单股/批量决策 + 历史信号查询/清理/重跑"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import date
from app.domain.quant.decision.center import DecisionCenter
from app.framework.logger import logger

router = APIRouter(prefix="/api/quant", tags=["Quant-Decision"])


@router.post("/decide/{stock_code}")
async def decide_single(stock_code: str):
    """单股即时决策 — 运行全部策略, 返回完整DecisionReport"""
    from app.framework.ai.providers.deepseek import DeepSeekProvider
    provider = DeepSeekProvider()
    center = DecisionCenter(provider=provider)
    reports = await center.decide([stock_code])
    if not reports:
        raise HTTPException(status_code=500, detail="决策失败")
    return {"success": True, "data": reports[0].model_dump()}


@router.post("/decide/portfolio")
async def decide_portfolio():
    """全部持仓批量决策"""
    from app.framework.ai.providers.deepseek import DeepSeekProvider
    from app.framework.database.session import async_session
    from app.models.models import Position
    from sqlalchemy import select

    async with async_session() as db:
        res = await db.execute(select(Position.stock_code))
        codes = [r[0] for r in res.all()]

    if not codes:
        return {"success": True, "data": [], "message": "无持仓"}

    provider = DeepSeekProvider()
    center = DecisionCenter(provider=provider)
    reports = await center.decide(codes)
    return {"success": True, "data": [r.model_dump() for r in reports]}


@router.get("/signals")
async def query_signals(
    stock_code: Optional[str] = None,
    decision_date: Optional[str] = None,
    strategy_name: Optional[str] = None,
    limit: int = Query(default=50, le=200),
):
    """查询历史信号 (可按股票/日期/策略筛选)"""
    from app.framework.database.session import async_session
    from app.models.models import StrategySignal
    from sqlalchemy import select

    async with async_session() as db:
        q = select(StrategySignal).order_by(StrategySignal.generated_at.desc())
        if stock_code:
            q = q.where(StrategySignal.stock_code == stock_code)
        if decision_date:
            q = q.where(StrategySignal.decision_date == date.fromisoformat(decision_date))
        if strategy_name:
            q = q.where(StrategySignal.strategy_name == strategy_name)
        q = q.limit(limit)
        res = await db.execute(q)
        rows = res.scalars().all()
        return {"success": True, "data": [
            {"id": r.id, "stock_code": r.stock_code, "strategy_name": r.strategy_name,
             "signal": r.signal, "confidence": r.confidence, "reasoning": r.reasoning,
             "decision_date": str(r.decision_date) if r.decision_date else None,
             "generated_at": str(r.generated_at) if r.generated_at else None}
            for r in rows
        ]}


@router.delete("/signals")
async def clear_signals(
    stock_code: Optional[str] = None,
    decision_date: Optional[str] = None,
):
    """清理指定日期/股票的历史信号"""
    from app.framework.database.session import async_session
    from app.models.models import StrategySignal
    from sqlalchemy import delete

    async with async_session() as db:
        q = delete(StrategySignal)
        if stock_code:
            q = q.where(StrategySignal.stock_code == stock_code)
        if decision_date:
            q = q.where(StrategySignal.decision_date == date.fromisoformat(decision_date))
        else:
            raise HTTPException(status_code=400, detail="必须指定 stock_code 或 decision_date")
        result = await db.execute(q)
        await db.commit()
        return {"success": True, "message": f"Deleted {result.rowcount} signal(s)"}


@router.post("/signals/rerun")
async def rerun_signals(decision_date: str = None):
    """重跑指定日期的全部策略 (先清理, 再跑)"""
    if not decision_date:
        decision_date = date.today().isoformat()
    # 清理旧数据
    from app.framework.database.session import async_session
    from app.models.models import StrategySignal
    from sqlalchemy import delete
    async with async_session() as db:
        await db.execute(
            delete(StrategySignal).where(StrategySignal.decision_date == date.fromisoformat(decision_date)))
        await db.commit()
    # 重跑
    from app.framework.ai.providers.deepseek import DeepSeekProvider
    from app.models.models import Position
    from sqlalchemy import select
    async with async_session() as db:
        res = await db.execute(select(Position.stock_code))
        codes = [r[0] for r in res.all()]
    provider = DeepSeekProvider()
    center = DecisionCenter(provider=provider)
    reports = await center.decide(codes)
    return {"success": True, "data": [r.model_dump() for r in reports]}
