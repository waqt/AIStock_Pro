from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from typing import Optional, List
from sqlalchemy import select, func
from datetime import date, timedelta
import re

from app.framework.database.session import async_session
from app.models.models import MarketData, StockIndicator, Position, ExchangeRate, StockInfo, WatchlistItem, PortfolioSnapshot
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
async def trigger_single_sync(stock_code: str, mode: str = "daily"):
    """单股同步 — mode=daily(当日最新) | historical(2年补齐缺失)"""
    from app.domain.quant.engine.engine import QuantEngine
    from app.domain.market_data.services.valuation import sync_valuation
    from app.models.models import WatchlistItem
    import pandas as pd

    async with async_session() as db:
        engine = QuantEngine(db)
        sync_mode = "AUTO" if mode == "daily" else "FULL"
        rows = await engine.sync_market_data(stock_code, mode=sync_mode)
        await sync_valuation(target_codes=[stock_code])
        # 同步基本信息 (行业/总股本/上市时间)
        from app.domain.market_data.services.valuation import sync_stock_info as sync_info
        await sync_info(stock_code)

        wl = await db.get(WatchlistItem, stock_code)
        if wl and not wl.stock_name:
            info = await db.get(StockInfo, stock_code)
            if info and info.stock_name:
                wl.stock_name = info.stock_name
            await db.commit()

        mr = await db.execute(
            select(MarketData.close, MarketData.change_pct)
            .where(MarketData.stock_code == stock_code)
            .order_by(MarketData.trade_date.desc()).limit(1))
        row = mr.first()

    return {
        "success": True, "stock_code": stock_code, "mode": mode,
        "new_rows": rows,
        "name": wl.stock_name if wl else "",
        "price": float(row[0]) if row and row[0] else None,
        "change_pct": float(row[1]) if row and row[1] else None,
    }


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


# ═══════════════════════════════════════════
# 宏观数据中心
# ═══════════════════════════════════════════

@router.post("/macro/sync")
async def sync_macro(mode: str = "daily"):
    """同步宏观数据 — mode=daily(当日最新) | historical(2年历史序列)"""
    from app.domain.market_data.sources.router import data_router
    result = await data_router.sync_macro_data()
    return {"success": True, "data": result, "mode": mode}


@router.get("/macro/latest")
async def get_macro_latest():
    """获取全部宏观指标最新值"""
    async with async_session() as db:
        res = await db.execute(select(ExchangeRate))
        items = res.scalars().all()
        return {"success": True, "data": [
            {"code": i.code, "name": i.name, "rate": i.rate,
             "change_pct": i.change_pct, "updated_at": str(i.updated_at) if i.updated_at else None}
            for i in items
        ]}


@router.get("/macro/history")
async def get_macro_history(code: str, days: int = Query(default=365, le=730)):
    """获取单个宏观指标的历史序列"""
    from app.models.models import MacroHistory
    async with async_session() as db:
        res = await db.execute(
            select(MacroHistory)
            .where(MacroHistory.code == code)
            .order_by(MacroHistory.obs_date.desc())
            .limit(days)
        )
        rows = res.scalars().all()
        return {"success": True, "data": [
            {"date": str(r.obs_date), "value": r.value} for r in reversed(rows)
        ]}


# ═══════════════════════════════════════════
# 自选股中心
# ═══════════════════════════════════════════

@router.get("/watchlist")
async def list_watchlist():
    """自选股列表 (按分组排列, 含实时行情+估值)"""
    async with async_session() as db:
        res = await db.execute(
            select(WatchlistItem).order_by(WatchlistItem.group_tag, WatchlistItem.sort_order))
        items = res.scalars().all()
        codes = [i.stock_code for i in items]

        # 批量查最新行情
        price_map = {}
        if codes:
            from sqlalchemy import and_
            for code in codes:
                mr = await db.execute(
                    select(MarketData.close, MarketData.change_pct)
                    .where(MarketData.stock_code == code)
                    .order_by(MarketData.trade_date.desc()).limit(1))
                row = mr.first()
                if row:
                    price_map[code] = {"price": float(row[0] or 0), "change_pct": float(row[1] or 0)}

            # 批量查估值
            val_res = await db.execute(
                select(StockInfo.stock_code, StockInfo.pe_ttm, StockInfo.mcap_yi)
                .where(StockInfo.stock_code.in_(codes)))
            val_map = {r[0]: {"pe_ttm": r[1], "mcap_yi": r[2]} for r in val_res.all()}
        else:
            val_map = {}

        return {"success": True, "data": [
            {"stock_code": i.stock_code, "stock_name": i.stock_name,
             "group_tag": i.group_tag, "is_held": i.is_held,
             "added_at": str(i.added_at) if i.added_at else None,
             "price": price_map.get(i.stock_code, {}).get("price"),
             "change_pct": price_map.get(i.stock_code, {}).get("change_pct"),
             "pe_ttm": val_map.get(i.stock_code, {}).get("pe_ttm"),
             "mcap_yi": val_map.get(i.stock_code, {}).get("mcap_yi"),
            }
            for i in items
        ]}


@router.post("/watchlist/add")
async def add_to_watchlist(stock_code: str, stock_name: str = "", group_tag: str = "默认"):
    """添加自选股 (自动补全名称+持仓标记)"""
    async with async_session() as db:
        # 自动补全名称
        if not stock_name:
            info = await db.get(StockInfo, stock_code)
            if info and info.stock_name:
                stock_name = info.stock_name
        # 检查是否持仓
        pos = await db.get(Position, stock_code)
        is_held = pos is not None
        # Upsert
        existing = await db.get(WatchlistItem, stock_code)
        if existing:
            existing.group_tag = group_tag
            if stock_name: existing.stock_name = stock_name
            existing.is_held = is_held
        else:
            db.add(WatchlistItem(stock_code=stock_code, stock_name=stock_name,
                group_tag=group_tag, is_held=is_held))
        await db.commit()
        return {"success": True, "message": f"Added {stock_code}", "name": stock_name, "is_held": is_held}


@router.post("/watchlist/import-positions")
async def import_positions_to_watchlist():
    """一键从持仓导入到自选股"""
    async with async_session() as db:
        res = await db.execute(select(Position.stock_code, Position.stock_name))
        positions = res.all()
        count = 0
        for code, name in positions:
            existing = await db.get(WatchlistItem, code)
            if existing:
                existing.is_held = True
                if name and not existing.stock_name: existing.stock_name = name
            else:
                db.add(WatchlistItem(stock_code=code, stock_name=name, group_tag="持仓股", is_held=True))
                count += 1
        await db.commit()
        return {"success": True, "imported": count, "message": f"Imported {count} new, updated existing"}


@router.post("/portfolio/snapshot")
async def compute_portfolio_snapshot():
    """计算当日持仓切片: 当日盈亏 + 累计盈亏 + 历史快照"""
    from app.models.models import PortfolioSnapshot
    from datetime import date as d, timedelta

    async with async_session() as db:
        # 1. 查询全部持仓
        pos_res = await db.execute(select(Position))
        positions = pos_res.scalars().all()
        if not positions:
            return {"success": True, "message": "无持仓", "count": 0}

        today = d.today()
        yesterday = today - timedelta(days=1)
        snapshots = []
        total_mv = 0.0
        total_pl = 0.0       # 累计盈亏
        total_daily_pl = 0.0 # 当日盈亏

        for pos in positions:
            # 取最近两天行情
            mr = await db.execute(
                select(MarketData.close, MarketData.trade_date)
                .where(MarketData.stock_code == pos.stock_code)
                .order_by(MarketData.trade_date.desc()).limit(2))
            rows = mr.all()
            if not rows:
                continue

            today_price = float(rows[0][0] or 0)
            yesterday_price = float(rows[1][0] or 0) if len(rows) > 1 else today_price
            vol = float(pos.volume)

            # 当日盈亏 = 持仓量 × (今日收盘 - 昨日收盘)
            daily_pl = vol * (today_price - yesterday_price) if yesterday_price > 0 else 0

            # 累计盈亏 = 市值 - 成本
            cost_basis = vol * float(pos.avg_cost)
            cumulative_pl = vol * today_price - cost_basis

            # 更新持仓
            pos.current_price = today_price
            pos.market_value = float(vol * today_price)
            pos.profit_loss = float(cumulative_pl)
            pos.profit_loss_ratio = round(cumulative_pl / cost_basis * 100, 2) if cost_basis != 0 else None

            total_mv += pos.market_value
            total_pl += cumulative_pl
            total_daily_pl += daily_pl

            info = await db.get(StockInfo, pos.stock_code)

            snapshots.append(PortfolioSnapshot(
                snap_date=today,
                stock_code=pos.stock_code, stock_name=pos.stock_name or "",
                volume=int(vol), avg_cost=float(pos.avg_cost),
                current_price=today_price, market_value=pos.market_value,
                profit_loss=cumulative_pl, profit_loss_ratio=pos.profit_loss_ratio,
                pe_ttm=info.pe_ttm if info else None,
                pb=info.pb if info else None,
                mcap_yi=info.mcap_yi if info else None,
            ))

        # 2. 已实现盈亏: TradeHistory 记录单笔交易无直接盈亏字段, 需配对计算(后续实现)
        realized_pl = 0.0

        # 3. 清理今日已有快照, 写入新快照
        from sqlalchemy import delete as sqla_delete
        await db.execute(
            sqla_delete(PortfolioSnapshot).where(PortfolioSnapshot.snap_date == today))
        db.add_all(snapshots)
        await db.commit()

        logger.info(f"[Portfolio] Snapshot: {len(snapshots)} stocks, MV={total_mv:.0f}, DailyPL={total_daily_pl:.0f}, CumPL={total_pl:.0f}")
        return {
            "success": True,
            "count": len(snapshots),
            "total_market_value": round(total_mv, 2),
            "daily_profit_loss": round(total_daily_pl, 2),     # 当日盈亏
            "cumulative_profit_loss": round(total_pl, 2),       # 累计盈亏 (持仓)
            "realized_profit_loss": round(realized_pl, 2),      # 已实现盈亏 (清仓)
            "total_profit_loss": round(realized_pl + total_pl, 2), # 历史总盈亏
        }


@router.get("/portfolio/snapshots")
async def get_portfolio_snapshots(days: int = 30):
    """查询最近N天的持仓切片"""
    from app.models.models import PortfolioSnapshot
    async with async_session() as db:
        res = await db.execute(
            select(PortfolioSnapshot)
            .order_by(PortfolioSnapshot.snap_date.desc(), PortfolioSnapshot.stock_code)
            .limit(days * 20))
        rows = res.scalars().all()
        return {"success": True, "data": [
            {"snap_date": str(r.snap_date), "stock_code": r.stock_code,
             "stock_name": r.stock_name, "volume": r.volume,
             "avg_cost": r.avg_cost, "current_price": r.current_price,
             "market_value": r.market_value, "profit_loss": r.profit_loss,
             "profit_loss_ratio": r.profit_loss_ratio}
            for r in rows
        ]}


@router.post("/stock-info/sync/{stock_code}")
async def sync_single_stock_info(stock_code: str):
    """同步单只股票的基本信息 (行业/总股本/上市时间)"""
    from app.domain.market_data.services.valuation import sync_stock_info
    ok = await sync_stock_info(stock_code)
    return {"success": ok, "stock_code": stock_code}


@router.post("/stock-info/sync")
async def sync_all_stock_info():
    """批量同步全部持仓+自选股的基本信息"""
    from app.domain.market_data.services.valuation import sync_stock_info
    async with async_session() as db:
        pos_res = await db.execute(select(Position.stock_code))
        wl_res = await db.execute(select(WatchlistItem.stock_code))
        codes = list(set([r[0] for r in pos_res.all()] + [r[0] for r in wl_res.all()]))
    ok = 0
    for code in codes:
        if await sync_stock_info(code):
            ok += 1
    return {"success": True, "synced": ok, "total": len(codes)}


@router.post("/watchlist/refresh-held")
async def refresh_watchlist_held_status():
    """刷新所有自选股的持仓状态"""
    async with async_session() as db:
        pos_res = await db.execute(select(Position.stock_code))
        held_codes = {r[0] for r in pos_res.all()}
        wl_res = await db.execute(select(WatchlistItem))
        updated = 0
        for item in wl_res.scalars().all():
            new_status = item.stock_code in held_codes
            if item.is_held != new_status:
                item.is_held = new_status
                updated += 1
        await db.commit()
        return {"success": True, "updated": updated}
        return {"success": True, "message": f"Added {stock_code}"}


@router.delete("/watchlist/{stock_code}")
async def remove_from_watchlist(stock_code: str):
    """删除自选股"""
    async with async_session() as db:
        item = await db.get(WatchlistItem, stock_code)
        if not item:
            raise HTTPException(status_code=404, detail="Not in watchlist")
        await db.delete(item)
        await db.commit()
        return {"success": True, "message": f"Removed {stock_code}"}


@router.put("/watchlist/{stock_code}")
async def update_watchlist(stock_code: str, group_tag: str = None, stock_name: str = None):
    """更新自选股分组或名称"""
    async with async_session() as db:
        item = await db.get(WatchlistItem, stock_code)
        if not item:
            raise HTTPException(status_code=404, detail="Not in watchlist")
        if group_tag: item.group_tag = group_tag
        if stock_name: item.stock_name = stock_name
        # 如果名字为空，尝试从 StockInfo 补全
        if not item.stock_name:
            info = await db.get(StockInfo, stock_code)
            if info and info.stock_name:
                item.stock_name = info.stock_name
        await db.commit()
        return {"success": True, "message": f"Updated {stock_code}", "name": item.stock_name}


@router.post("/watchlist/sync")
async def sync_watchlist():
    """同步全部自选股行情+估值 (不限于持仓)"""
    from app.domain.market_data.services.valuation import sync_valuation
    async with async_session() as db:
        res = await db.execute(select(WatchlistItem.stock_code))
        codes = [r[0] for r in res.all()]
    if not codes:
        return {"success": True, "message": "Watchlist empty"}
    # 同步行情
    from app.domain.quant.engine.indicator_runner import IndicatorRunner
    await data_router.sync_macro_data()
    for code in codes:
        try:
            await data_router.get_daily_data(code, days=10)
        except Exception:
            pass
    await sync_valuation(target_codes=codes)
    return {"success": True, "synced": len(codes)}
