"""指标API — 查询指标库和单股指标"""
from fastapi import APIRouter
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
