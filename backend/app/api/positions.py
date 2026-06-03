from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import List
from app.framework.database.session import get_db
from app.models.models import Position, StockMaster, StockValuation
from app.models.schemas import PositionResponse
from app.framework.logger import logger

router = APIRouter(prefix="/api/positions", tags=["Positions"])

@router.get("", response_model=List[PositionResponse])
async def list_positions(db: AsyncSession = Depends(get_db)):
    """获取所有持仓明细 + 估值数据 (PE/PB/市值)"""
    try:
        result = await db.execute(select(Position))
        positions = result.scalars().all()

        # 批量查询名称 (StockMaster) + 估值 (StockValuation)
        codes = [p.stock_code for p in positions]
        name_map = {}
        val_map = {}
        if codes:
            master_res = await db.execute(
                select(StockMaster.stock_code, StockMaster.stock_name)
                .where(StockMaster.stock_code.in_(codes)))
            name_map = {r[0]: r[1] for r in master_res.all()}

            val_res = await db.execute(
                select(StockValuation.stock_code, StockValuation.pe_ttm, StockValuation.pb, StockValuation.mcap_yi)
                .where(StockValuation.stock_code.in_(codes)))
            for row in val_res.all():
                val_map[row[0]] = {"pe_ttm": row[1], "pb": row[2], "mcap_yi": row[3]}

        # 构建带估值+名称的响应
        results = []
        for p in positions:
            d = {c.name: getattr(p, c.name) for c in p.__table__.columns}
            d["stock_name"] = name_map.get(p.stock_code, p.stock_code)
            v = val_map.get(p.stock_code, {})
            d["pe_ttm"] = v.get("pe_ttm")
            d["pb"] = v.get("pb")
            d["mcap_yi"] = v.get("mcap_yi")
            results.append(PositionResponse(**d))
        return results
    except Exception as e:
        logger.error(f"[❌] Database Query Failed (Positions): {e}")
        return JSONResponse(status_code=500, content={"message": f"数据库结构不匹配: {str(e)}"})

@router.get("/account/summary")
async def get_account_summary(db: AsyncSession = Depends(get_db)):
    """获取账户资产摘要"""
    result = await db.execute(select(Position))
    positions = result.scalars().all()
    
    total_market_value = sum(float(p.market_value or 0) for p in positions)
    total_pl = sum(float(p.profit_loss or 0) for p in positions)
    available_cash = 150000.0
    return {
        "total_capital": total_market_value + available_cash,
        "available_cash": available_cash,
        "market_value": total_market_value,
        "today_profit": total_pl
    }


@router.delete("/{stock_code}")
async def delete_position(stock_code: str, db: AsyncSession = Depends(get_db)):
    """删除单条持仓"""
    result = await db.execute(select(Position).where(Position.stock_code == stock_code))
    pos = result.scalars().first()
    if not pos:
        raise HTTPException(status_code=404, detail=f"持仓 {stock_code} 不存在")
    master = await db.get(StockMaster, stock_code)
    stock_name = master.stock_name if master else stock_code
    await db.execute(delete(Position).where(Position.stock_code == stock_code))
    await db.commit()
    logger.info(f"[🧹] Deleted position: {stock_code} {stock_name}")
    return {"message": f"已删除 {stock_code} {stock_name}"}


@router.post("/update-prices")
async def update_positions_prices(db: AsyncSession = Depends(get_db)):
    """刷新全部持仓的现价 + 盈亏 (用最新行情更新)"""
    from sqlalchemy import select as sa_select
    from app.models.models import MarketData

    result = await db.execute(sa_select(Position))
    positions = result.scalars().all()
    updated = 0
    for pos in positions:
        mr = await db.execute(
            sa_select(MarketData.close).where(MarketData.stock_code == pos.stock_code)
            .order_by(MarketData.trade_date.desc()).limit(1))
        row = mr.first()
        if not row or not row[0]:
            continue
        price = float(row[0])
        pos.current_price = price
        pos.market_value = float(pos.volume) * price
        cost = float(pos.volume) * float(pos.avg_cost)
        pos.profit_loss = pos.market_value - cost
        pos.profit_loss_ratio = round(pos.profit_loss / cost * 100, 2) if cost != 0 else None
        updated += 1
    await db.commit()
    logger.info(f"[Positions] Updated prices for {updated}/{len(positions)} stocks")
    return {"message": f"已刷新 {updated}/{len(positions)} 只持仓行情", "updated": updated}
