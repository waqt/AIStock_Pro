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


# ═══ 指标计算 ═══════════════════════════════

@router.post("/compute/{stock_code}")
async def compute_indicators(
    stock_code: str,
    names: Optional[str] = Query(None, description="逗号分隔的指标名, 空=全部"),
):
    """计算单只股票的指标 (可选择指定算子), 结果持久化到 StockIndicator"""
    from app.domain.quant.engine.indicator_runner import IndicatorRunner
    indicator_names = [n.strip() for n in names.split(",") if n.strip()] if names else None
    result = await IndicatorRunner.compute_single(stock_code, indicator_names)
    return {"success": True, "data": result}


@router.post("/compute")
async def compute_indicators_batch(
    codes: Optional[str] = Query(None, description="逗号分隔的股票代码"),
    names: Optional[str] = Query(None, description="逗号分隔的指标名, 空=全部"),
):
    """批量计算指标 — 默认全部持仓, 可选指定股票+指标"""
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
    result = await IndicatorRunner.compute_batch(stock_codes, indicator_names)
    return {"success": True, "data": result}
