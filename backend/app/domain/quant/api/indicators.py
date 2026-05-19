"""指标API — 查询/计算指标"""
from fastapi import APIRouter, Query
from typing import Optional, List
from app.domain.quant.indicators import INDICATOR_REGISTRY

router = APIRouter(prefix="/api/quant/indicators", tags=["Quant-Indicators"])


@router.get("/registry")
async def list_indicators():
    """所有已注册的指标算子列表"""
    result = []
    for key, cls in INDICATOR_REGISTRY.items():
        result.append(cls.meta())
    return {"success": True, "data": result}


# ═══ 指标计算 (POST 路由, 优先级高于 GET) ═══

@router.post("/compute/{stock_code}")
async def compute_indicators(
    stock_code: str,
    names: Optional[str] = Query(None, description="逗号分隔的指标名, 空=全部"),
    mode: str = Query("snapshot", description="snapshot(快照)|historical(全量历史)|incremental(增量)"),
):
    """计算单只股票指标: snapshot=仅今日, historical=逐日全量, incremental=增量补算"""
    from app.domain.quant.engine.indicator_runner import IndicatorRunner
    indicator_names = [n.strip() for n in names.split(",") if n.strip()] if names else None
    if mode == "historical":
        result = await IndicatorRunner.compute_historical(stock_code, indicator_names)
    elif mode == "incremental":
        result = await IndicatorRunner.compute_incremental(stock_code, indicator_names)
    else:
        result = await IndicatorRunner.compute_snapshot(stock_code, indicator_names)
    return {"success": True, "data": result}


@router.post("/compute")
async def compute_indicators_batch(
    codes: Optional[str] = Query(None, description="逗号分隔的股票代码"),
    names: Optional[str] = Query(None, description="逗号分隔的指标名, 空=全部"),
    mode: str = Query("snapshot", description="snapshot|historical|incremental"),
):
    """批量计算指标 — 默认全部持仓"""
    from app.domain.quant.engine.indicator_runner import IndicatorRunner
    from app.framework.database.session import async_session
    from app.models.models import Position
    from sqlalchemy import select

    if codes:
        stock_codes = [c.strip() for c in codes.split(",") if c.strip()]
    else:
        async with async_session() as db:
            res = await db.execute(select(Position.stock_code))
            stock_codes = [r[0] for r in res.all()]

    if not stock_codes:
        return {"success": True, "data": {"message": "无持仓或无指定股票"}}

    indicator_names = [n.strip() for n in names.split(",") if n.strip()] if names else None
    result = await IndicatorRunner.compute_batch(stock_codes, mode, indicator_names)
    return {"success": True, "data": result}


@router.delete("/data/{stock_code}")
async def clear_indicators(stock_code: str):
    """清理单只股票的全部指标数据"""
    from app.domain.quant.engine.indicator_runner import IndicatorRunner
    r = await IndicatorRunner.clear_and_recompute(stock_code)
    return {"success": True, "data": r}


@router.get("/data/{stock_code}/coverage")
async def indicator_coverage(stock_code: str):
    """查询某只股票的指标覆盖日期范围"""
    from app.framework.database.session import async_session
    from app.models.models import StockIndicator
    from sqlalchemy import select, func
    async with async_session() as db:
        res = await db.execute(
            select(func.min(StockIndicator.analysis_date),
                   func.max(StockIndicator.analysis_date),
                   func.count(StockIndicator.id))
            .where(StockIndicator.stock_code == stock_code))
        r = res.first()
        return {"success": True, "data": {
            "stock_code": stock_code,
            "earliest": str(r[0]) if r and r[0] else None,
            "latest": str(r[1]) if r and r[1] else None,
            "days_covered": r[2] if r else 0,
        }}


# ═══ 单股查询 (放在最后, 避免拦截 /data/ 等前缀路由) ═══

@router.get("/{stock_code}")
async def get_stock_indicators(stock_code: str):
    """单股全量最新指标快照"""
    from app.framework.database.session import async_session
    from app.models.models import StockIndicator
    from sqlalchemy import select
    async with async_session() as db:
        res = await db.execute(
            select(StockIndicator)
            .where(StockIndicator.stock_code == stock_code)
            .order_by(StockIndicator.analysis_date.desc())
            .limit(1)
        )
        row = res.scalars().first()
        if not row:
            return {"success": True, "data": None, "message": f"No indicators for {stock_code}"}
        return {
            "success": True, "data": {
                "stock_code": row.stock_code,
                "analysis_date": str(row.analysis_date) if row.analysis_date else None,
                "indicators": row.data_json,
                "patterns": row.logic_chain,
            }
        }
