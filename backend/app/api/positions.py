from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import List
from app.framework.database.session import get_db
from app.models.models import Position
from app.models.schemas import PositionResponse
from app.framework.logger import logger

router = APIRouter(prefix="/api/positions", tags=["Positions"])

@router.get("", response_model=List[PositionResponse])
async def list_positions(db: AsyncSession = Depends(get_db)):
    """获取所有持仓明细 (增加异常捕获以诊断 500 错误)"""
    try:
        result = await db.execute(select(Position))
        return result.scalars().all()
    except Exception as e:
        logger.error(f"[❌] Database Query Failed (Positions): {e}")
        # 如果是因为字段缺失，这里会打印出具体的字段名
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
    await db.execute(delete(Position).where(Position.stock_code == stock_code))
    await db.commit()
    logger.info(f"[🧹] Deleted position: {stock_code} {pos.stock_name}")
    return {"message": f"已删除 {stock_code} {pos.stock_name}"}
