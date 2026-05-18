from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from typing import Optional, List
from sqlalchemy import select, func
from datetime import date, timedelta
import re

from app.framework.database.session import async_session
from app.models.models import MarketData, StockIndicator, Position, ExchangeRate, StockInfo
from app.domain.market_data.sources.router import data_router
from app.framework.tasks.engine import task_manager
from app.framework.logger import logger
from pydantic import BaseModel

router = APIRouter(prefix="/api/data", tags=["数据管理"])


class SyncRequest(BaseModel):
    type: str = "AUTO"


# ═══════════════════════════════════════════
# 行情数据
# ═══════════════════════════════════════════

@router.get("/daily/{stock_code}")
async def get_daily_data(stock_code: str, limit: int = Query(default=500, le=1000)):
    """获取个股日线数据 (JSON 数组, 按日期正序)"""
    async with async_session() as db:
        res = await db.execute(
            select(MarketData)
            .where(MarketData.stock_code == stock_code)
            .order_by(MarketData.trade_date.asc())
            .limit(limit)
        )
        rows = res.scalars().all()

        # 查持仓名称
        name_res = await db.execute(select(Position.stock_name).where(Position.stock_code == stock_code))
        stock_name = name_res.scalars().first() or ""

        return [
            {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "trade_date": str(r.trade_date),
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
                "amount": r.amount,
                "change_pct": r.change_pct
            }
            for r in rows
        ]


@router.post("/sync/daily/auto")
async def trigger_auto_sync(request: SyncRequest):
    """触发全量/增量同步任务 (经由 TaskEngine)"""
    try:
        exec_id = await task_manager.run_task("sync_market", {"mode": request.type})
        return {"message": "任务已加入执行队列", "task_id": exec_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/daily/{stock_code}")
async def trigger_single_sync(stock_code: str):
    """触发单股同步 + 指标计算"""
    exec_id = await task_manager.run_task("sync_market", {"mode": "AUTO", "target_codes": [stock_code]})
    return {"message": f"{stock_code} 同步已加入队列", "task_id": exec_id}


# ═══════════════════════════════════════════
# 数据源管理
# ═══════════════════════════════════════════

@router.get("/sources/status")
async def get_source_status():
    """获取所有数据源实时状态"""
    await data_router.probe_all()
    return {
        "sources": data_router.get_source_status(),
        "active_source": data_router.get_active_source(),
        "last_probe": str(date.today())
    }


@router.get("/sources/priority")
async def get_source_priority():
    """获取数据源优先级链路"""
    return {
        "chain": data_router.get_priority_chain(),
        "active": data_router.get_active_source()
    }


# ═══════════════════════════════════════════
# 数据健康检查
# ═══════════════════════════════════════════

@router.get("/health/overview")
async def get_health_overview():
    """全局数据健康总览"""
    async with async_session() as db:
        # 有行情数据的股票数
        stock_res = await db.execute(
            select(func.count(func.distinct(MarketData.stock_code)))
        )
        stock_count = stock_res.scalars().first() or 0

        # 最新同步时间
        latest_res = await db.execute(
            select(func.max(MarketData.trade_date))
        )
        latest_date = latest_res.scalars().first()

        # 有指标的股票数
        ind_res = await db.execute(
            select(func.count(func.distinct(StockIndicator.stock_code)))
        )
        ind_count = ind_res.scalars().first() or 0

        # 有估值数据的股票数
        val_res = await db.execute(
            select(func.count(StockInfo.stock_code)).where(StockInfo.pe_ttm.isnot(None))
        )
        val_count = val_res.scalars().first() or 0

        return {
            "synced_stocks": stock_count,
            "latest_sync_date": str(latest_date) if latest_date else None,
            "indicators_coverage": ind_count,
            "valuation_coverage": val_count,
            "status": "HEALTHY" if latest_date and (date.today() - latest_date).days <= 3 else "STALE"
        }


@router.get("/health/stocks")
async def get_stocks_health():
    """各股票行情体检列表"""
    async with async_session() as db:
        res = await db.execute(
            select(
                MarketData.stock_code,
                func.max(MarketData.trade_date).label("latest_date"),
                func.min(MarketData.trade_date).label("earliest_date"),
                func.count(MarketData.id).label("record_count")
            )
            .group_by(MarketData.stock_code)
            .order_by(func.max(MarketData.trade_date).desc())
        )
        rows = res.all()

        # 批量获取名称 (StockInfo > Position > stock_code)
        pos_res = await db.execute(select(Position.stock_code, Position.stock_name))
        pos_names = {p.stock_code: p.stock_name for p in pos_res if p.stock_name}
        info_res = await db.execute(select(StockInfo.stock_code, StockInfo.stock_name))
        info_names = {s.stock_code: s.stock_name for s in info_res}
        name_map = {**info_names, **pos_names}  # 持仓名称优先覆盖证券名称

        today = date.today()
        weekday = today.weekday()  # 0=Mon, 6=Sun
        result = []
        for r in rows:
            gap = (today - r.latest_date).days if r.latest_date else 999
            # 周末感知: 最近交易日是周五, 在周一gap=3仍是最新数据
            if gap <= 1:
                status = "HEALTHY"
            elif weekday == 0 and gap <= 3:  # 周一: 周五数据 gap=3 正常
                status = "HEALTHY"
            elif weekday == 1 and gap <= 4:  # 周二: 容忍周一假期场景
                status = "HEALTHY"
            elif gap <= 5:
                status = "STALE"
            else:
                status = "GAP"

            price_res = await db.execute(
                select(MarketData.close)
                .where(MarketData.stock_code == r.stock_code)
                .order_by(MarketData.trade_date.desc())
                .limit(1)
            )
            price = price_res.scalars().first()

            result.append({
                "stock_code": r.stock_code,
                "stock_name": name_map.get(r.stock_code, r.stock_code),
                "latest_date": str(r.latest_date) if r.latest_date else None,
                "earliest_date": str(r.earliest_date) if r.earliest_date else None,
                "record_count": r.record_count,
                "latest_price": price,
                "gap_days": gap,
                "status": status
            })
        return result


@router.get("/health/indicators")
async def get_indicators_health():
    """各股票指标体检列表"""
    async with async_session() as db:
        res = await db.execute(
            select(
                StockIndicator.stock_code,
                StockIndicator.indicator_type,
                func.max(StockIndicator.analysis_date).label("latest_date"),
                StockIndicator.data_json
            )
            .group_by(StockIndicator.stock_code, StockIndicator.indicator_type)
            .order_by(StockIndicator.stock_code, func.max(StockIndicator.analysis_date).desc())
        )
        rows = res.all()

        result = {}
        for r in rows:
            if r.stock_code not in result:
                result[r.stock_code] = {
                    "stock_code": r.stock_code,
                    "indicators": []
                }
            result[r.stock_code]["indicators"].append({
                "type": r.indicator_type,
                "latest_date": str(r.latest_date) if r.latest_date else None,
                "snapshot": r.data_json
            })
        return list(result.values())


@router.get("/health/{stock_code}")
async def get_stock_detail_health(stock_code: str):
    """单股详细体检 — 行情 + 指标完整快照"""
    async with async_session() as db:
        # 行情数据概览
        date_res = await db.execute(
            select(
                func.max(MarketData.trade_date),
                func.min(MarketData.trade_date),
                func.count(MarketData.id)
            ).where(MarketData.stock_code == stock_code)
        )
        date_info = date_res.first()

        # 最新行情
        latest_res = await db.execute(
            select(MarketData)
            .where(MarketData.stock_code == stock_code)
            .order_by(MarketData.trade_date.desc())
            .limit(1)
        )
        latest = latest_res.scalars().first()

        # 指标快照
        ind_res = await db.execute(
            select(StockIndicator)
            .where(StockIndicator.stock_code == stock_code)
            .order_by(StockIndicator.analysis_date.desc())
            .limit(1)
        )
        indicator = ind_res.scalars().first()

        return {
            "stock_code": stock_code,
            "data_range": {
                "from": str(date_info[1]) if date_info[1] else None,
                "to": str(date_info[0]) if date_info[0] else None,
                "records": date_info[2] or 0
            },
            "latest_quote": {
                "trade_date": str(latest.trade_date) if latest else None,
                "open": latest.open if latest else None,
                "high": latest.high if latest else None,
                "low": latest.low if latest else None,
                "close": latest.close if latest else None,
                "volume": latest.volume if latest else None,
                "change_pct": latest.change_pct if latest else None
            } if latest else None,
            "indicators": {
                "type": indicator.indicator_type if indicator else None,
                "analysis_date": str(indicator.analysis_date) if indicator else None,
                "snapshot": indicator.data_json if indicator else None,
                "findings": indicator.logic_chain if indicator else None
            } if indicator else None
        }


# ═══════════════════════════════════════════
# 指标注册与查询 (V5.1)
# ═══════════════════════════════════════════

from app.domain.quant.engine.indicators import INDICATOR_REGISTRY


@router.get("/indicators/registry")
async def get_indicator_registry():
    """获取所有已注册的量化指标及其定义"""
    return [
        {
            "code": code,
            "name": meta["name"],
            "category": meta["category"],
            "params": meta.get("params", {}),
            "description": meta.get("description", ""),
            "output_fields": meta.get("output_fields", []),
            "chart_overlay": meta.get("chart_overlay", False)
        }
        for code, meta in INDICATOR_REGISTRY.items()
    ]


@router.get("/indicators/{stock_code}")
async def get_stock_indicators(stock_code: str):
    """获取某只股票的最新指标快照"""
    async with async_session() as db:
        res = await db.execute(
            select(StockIndicator)
            .where(StockIndicator.stock_code == stock_code)
            .order_by(StockIndicator.analysis_date.desc())
            .limit(1)
        )
        row = res.scalars().first()
        if not row:
            return {"stock_code": stock_code, "indicators": None}

        return {
            "stock_code": stock_code,
            "analysis_date": str(row.analysis_date) if row.analysis_date else None,
            "indicator_type": row.indicator_type,
            "snapshot": row.data_json,
            "findings": row.logic_chain
        }


# ═══════════════════════════════════════════
# 汇率查询 (V5.2)
# ═══════════════════════════════════════════

@router.get("/forex/rates")
async def get_forex_rates():
    """获取汇率 + 宏观指数 (汇率/美元指数/金/银/油)"""
    async with async_session() as db:
        res = await db.execute(select(ExchangeRate))
        rows = res.scalars().all()
        return {
            r.code: {
                "name": r.name or r.code,
                "price": r.rate,
                "change_pct": r.change_pct,
                "updated_at": str(r.updated_at) if r.updated_at else None
            }
            for r in rows
        }


@router.post("/forex/sync")
async def sync_forex_rates():
    """手动触发宏观数据同步"""
    from app.domain.market_data.sources.router import data_router as dr
    result = await dr.sync_macro_data()
    return {"success": True, "data": result}


@router.post("/stock-list/sync")
async def sync_stock_list_endpoint(full: bool = False):
    """同步股票列表。full=true 从东财全量拉取5529只A股, false=增量补充"""
    from app.domain.market_data.services.stock_list import sync_stock_list, sync_a_stock_list_full
    if full:
        count = await sync_a_stock_list_full()
    else:
        count = await sync_stock_list()
    return {"success": True, "synced": count}


@router.post("/valuation/sync")
async def sync_valuation_endpoint():
    """手动触发估值同步 (PE/PB/市值)"""
    from app.domain.market_data.services.valuation import sync_valuation
    count = await sync_valuation()
    return {"success": True, "synced": count}


@router.get("/valuation/positions")
async def get_position_valuation():
    """获取持仓估值数据"""
    async with async_session() as db:
        res = await db.execute(
            select(StockInfo.stock_code, StockInfo.stock_name, StockInfo.pe_ttm,
                   StockInfo.pb, StockInfo.mcap_yi, StockInfo.float_mcap_yi,
                   StockInfo.turnover_pct, StockInfo.updated_at)
            .where(StockInfo.pe_ttm.isnot(None))
        )
        return [
            {"code": r[0], "name": r[1], "pe_ttm": r[2], "pb": r[3],
             "mcap_yi": r[4], "float_mcap_yi": r[5], "turnover_pct": r[6],
             "updated_at": str(r[7]) if r[7] else None}
            for r in res.all()
        ]


@router.get("/stock-list/search")
async def search_stocks(q: str = "", limit: int = 20):
    """搜索股票代码或名称 (自动补全)"""
    async with async_session() as db:
        res = await db.execute(
            select(StockInfo.stock_code, StockInfo.stock_name, StockInfo.exchange)
            .where(
                StockInfo.stock_code.like(f"%{q}%") | StockInfo.stock_name.like(f"%{q}%")
            )
            .limit(limit)
        )
        return [{"code": r[0], "name": r[1], "exchange": r[2]} for r in res.all()]


@router.post("/stock-list/import-csv")
async def import_stock_csv(file: UploadFile = File(...)):
    """上传股票列表 CSV (列: 代码,名称) 导入 stock_info"""
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="仅支持 .csv 格式")
    try:
        contents = await file.read()
        text = contents.decode('utf-8-sig')
        imported = 0
        async with async_session() as db:
            for line in text.strip().split('\n'):
                parts = [p.strip().strip('"') for p in line.split(',')]
                if len(parts) < 2:
                    continue
                code, name = parts[0], parts[1]
                if not code or not name or code == '代码':
                    continue
                # 标准化代码
                code = re.sub(r'[^0-9]', '', code)
                if not code:
                    continue
                if len(code) < 6:
                    code = code.zfill(6)
                code = code[:6]

                exchange = "SH" if code.startswith(('6','9')) else "SZ"
                existing = await db.get(StockInfo, code)
                if not existing:
                    db.add(StockInfo(stock_code=code, stock_name=name, exchange=exchange))
                    imported += 1
                elif not existing.stock_name or existing.stock_name == code:
                    existing.stock_name = name
                    imported += 1
            await db.commit()
        logger.info(f"[✅] CSV import: {imported} stocks")
        return {"success": True, "imported": imported}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")
