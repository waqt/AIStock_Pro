from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Body
from typing import Optional, List
from sqlalchemy import select, func
from datetime import date, timedelta
import re

from app.framework.database.session import async_session
from app.models.models import MarketData, Position, ExchangeRate, StockMaster, StockValuation, WatchlistItem, PortfolioSnapshot, FinancialStatement
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
        # 取最近 N 天: 倒序查 N 条 → Python 反转
        res = await db.execute(
            select(MarketData)
            .where(MarketData.stock_code == stock_code)
            .order_by(MarketData.trade_date.desc())
            .limit(limit)
        )
        rows = res.scalars().all()[::-1]  # 反转为正序

        # 查股票名称
        master = await db.get(StockMaster, stock_code)
        stock_name = master.stock_name if master else ""

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
    """单股同步 — mode=daily(当日最新-含盘中实时价) | historical(2年补齐缺失)"""
    from app.domain.quant.engine.engine import QuantEngine
    from app.domain.market_data.services.valuation import sync_valuation
    from app.models.models import WatchlistItem, MarketData
    import pandas as pd
    from datetime import date as dt_date

    async with async_session() as db:
        engine = QuantEngine(db)
        sync_mode = "AUTO" if mode == "daily" else "FULL"
        rows = await engine.sync_market_data(stock_code, mode=sync_mode)
        # 盘中实时价: K线不含今日数据, 通过实时行情补漏
        if mode == "daily":
            try:
                from app.domain.market_data.sources.router import data_router
                quotes = await data_router.get_realtime_quotes([stock_code])
                q = quotes.get(stock_code, {})
                if q.get('price') and q['price'] > 0:
                    today_str = dt_date.today().strftime('%Y-%m-%d')
                    # Upsert: 写入或更新今日行
                    from sqlalchemy import select as sa_select
                    existing = await db.execute(
                        sa_select(MarketData).where(
                            MarketData.stock_code == stock_code,
                            MarketData.trade_date == today_str
                        )
                    )
                    row = existing.scalars().first()
                    if row:
                        row.close = float(q['price'])
                        if q.get('volume'): row.volume = int(float(q['volume']))
                    else:
                        db.add(MarketData(
                            stock_code=stock_code, trade_date=today_str,
                            open=float(q.get('open', q['price'])),
                            close=float(q['price']),
                            high=float(q.get('high', q['price'])),
                            low=float(q.get('low', q['price'])),
                            volume=int(float(q.get('volume', 0)))
                        ))
                    await db.commit()
                    rows += 1
            except Exception as e:
                logger.warning(f"[Sync] Realtime price fail for {stock_code}: {e}")
        await sync_valuation(target_codes=[stock_code])
        # 同步基本信息 (行业/总股本/上市时间/名称)
        from app.domain.market_data.services.valuation import sync_stock_info as sync_info
        await sync_info(stock_code)

        # 查 StockMaster 补全前端展示用的名称（不存到 watchlist）
        master = await db.get(StockMaster, stock_code)
        display_name = master.stock_name if master else stock_code

        mr = await db.execute(
            select(MarketData.close, MarketData.change_pct)
            .where(MarketData.stock_code == stock_code)
            .order_by(MarketData.trade_date.desc()).limit(1))
        row = mr.first()

    return {
        "success": True, "stock_code": stock_code, "mode": mode,
        "new_rows": rows,
        "name": display_name,
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

        # 有指标的股票数 (SQLite)
        from app.domain.quant.engine import indicator_store
        ind_count = len(set(r['stock_code'] for r in indicator_store.get_latest_for_codes([]) if r.get('stock_code')))

        # 有估值数据的股票数
        val_res = await db.execute(
            select(func.count(StockValuation.stock_code)).where(StockValuation.pe_ttm.isnot(None))
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

        # 批量获取名称 (StockMaster)
        master_res = await db.execute(select(StockMaster.stock_code, StockMaster.stock_name))
        name_map = {r.stock_code: r.stock_name for r in master_res if r.stock_name}

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
    """各股票指标体检列表 (SQLite 查询)"""
    from app.domain.quant.engine import indicator_store
    async with async_session() as db:
        pos = await db.execute(select(Position.stock_code))
        wl = await db.execute(select(WatchlistItem.stock_code))
        all_codes = list(set([r[0] for r in pos.all()] + [r[0] for r in wl.all()]))
    rows = indicator_store.get_latest_for_codes(all_codes)
    result = {}
    for row in rows:
        code = row.get('stock_code')
        result[code] = {"stock_code": code, "indicators": [{"type": "DAILY", "latest_date": row.get('trade_date'), "snapshot": {
            k: row[k] for k in row.keys() if k not in ('stock_code', 'trade_date')
        }}]}
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

        from app.domain.quant.engine import indicator_store
        indicator = indicator_store.get_latest(stock_code) or {}

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
                "type": "DAILY",
                "analysis_date": indicator.get("trade_date"),
                "snapshot": indicator,
                "findings": {}
            } if indicator else None
        }


# ═══════════════════════════════════════════
# 指标注册与查询 (V5.1)
# ═══════════════════════════════════════════



@router.get("/indicators/{stock_code}")
async def get_stock_indicators(stock_code: str):
    """获取某只股票的最新指标快照 (SQLite)"""
    from app.domain.quant.engine import indicator_store
    row = indicator_store.get_latest(stock_code)
    if not row:
        return {"stock_code": stock_code, "indicators": None}

    return {
        "stock_code": stock_code,
        "analysis_date": row.get("trade_date"),
        "indicator_type": "DAILY",
        "snapshot": row,
            "findings": row.get("logic_chain", "")
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
    from app.domain.market_data.services.macro_sync import sync_macro_data
    result = await sync_macro_data()
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


class ValuationSyncRequest(BaseModel):
    target_codes: Optional[List[str]] = None

@router.post("/valuation/sync")
async def sync_valuation_endpoint(req: ValuationSyncRequest = ValuationSyncRequest()):
    """手动触发估值同步 (PE/PB/市值) — 支持 target_codes 批量指定"""
    from app.domain.market_data.services.valuation import sync_valuation
    count = await sync_valuation(target_codes=req.target_codes)
    return {"success": True, "synced": count}


@router.get("/valuation/positions")
async def get_position_valuation():
    """获取持仓估值数据"""
    async with async_session() as db:
        res = await db.execute(
            select(StockMaster.stock_code, StockMaster.stock_name,
                   StockValuation.pe_ttm, StockValuation.pb,
                   StockValuation.mcap_yi, StockValuation.float_mcap_yi,
                   StockValuation.turnover_pct, StockValuation.updated_at)
            .outerjoin(StockValuation, StockMaster.stock_code == StockValuation.stock_code)
            .where(StockValuation.pe_ttm.isnot(None))
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
            select(StockMaster.stock_code, StockMaster.stock_name, StockMaster.exchange)
            .where(
                StockMaster.stock_code.like(f"%{q}%") | StockMaster.stock_name.like(f"%{q}%")
            )
            .limit(limit)
        )
        return [{"code": r[0], "name": r[1], "exchange": r[2]} for r in res.all()]


@router.post("/stock-list/import-csv")
async def import_stock_csv(file: UploadFile = File(...)):
    """上传股票列表 CSV (列: 代码,名称) 导入 stock_master"""
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
                code = re.sub(r'[^0-9]', '', code)
                if not code:
                    continue
                if len(code) < 6:
                    code = code.zfill(6)
                code = code[:6]

                exchange = "SH" if code.startswith(('6','9')) else "SZ"
                existing = await db.get(StockMaster, code)
                if not existing:
                    db.add(StockMaster(stock_code=code, stock_name=name, exchange=exchange))
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
    from app.domain.market_data.services.macro_sync import sync_macro_data
    result = await sync_macro_data()
    return {"success": True, "data": result, "mode": mode}


@router.get("/macro/latest")
async def get_macro_latest():
    """获取全部宏观指标最新值"""
    async with async_session() as db:
        res = await db.execute(select(ExchangeRate))
        items = res.scalars().all()
        return {"success": True, "data": [
            {"code": i.code, "name": i.name, "rate": i.rate,
             "change_pct": i.change_pct,
             "biz_date": str(i.biz_date) if i.biz_date else None,
             "updated_at": str(i.updated_at) if i.updated_at else None}
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

        # 批量查名称 (StockMaster)
        name_map = {}
        if codes:
            name_res = await db.execute(
                select(StockMaster.stock_code, StockMaster.stock_name)
                .where(StockMaster.stock_code.in_(codes)))
            name_map = {r[0]: r[1] for r in name_res.all()}

        # 批量查最新行情
        price_map = {}
        if codes:
            for code in codes:
                mr = await db.execute(
                    select(MarketData.close, MarketData.change_pct)
                    .where(MarketData.stock_code == code)
                    .order_by(MarketData.trade_date.desc()).limit(1))
                row = mr.first()
                if row:
                    price_map[code] = {"price": float(row[0] or 0), "change_pct": float(row[1] or 0)}

            # 批量查估值 (StockValuation)
            val_res = await db.execute(
                select(StockValuation.stock_code, StockValuation.pe_ttm, StockValuation.mcap_yi)
                .where(StockValuation.stock_code.in_(codes)))
            val_map = {r[0]: {"pe_ttm": r[1], "mcap_yi": r[2]} for r in val_res.all()}
        else:
            val_map = {}

        # 批量查最新季度财务
        fin_map = {}
        if codes:
            for code in codes:
                fr = await db.execute(
                    select(FinancialStatement.revenue, FinancialStatement.parent_profit,
                           FinancialStatement.operate_cost, FinancialStatement.total_equity,
                           FinancialStatement.report_date)
                    .where(FinancialStatement.stock_code == code)
                    .order_by(FinancialStatement.report_date.desc()).limit(2))
                rows = fr.all()
                if rows:
                    fin_map[code] = {"revenue": float(rows[0][0] or 0), "profit": float(rows[0][1] or 0),
                                     "cost": float(rows[0][2] or 0), "equity": float(rows[0][3] or 0),
                                     "report_date": str(rows[0][4])}
                    if len(rows) >= 2:
                        fin_map[code]["prev_revenue"] = float(rows[1][0] or 0)
                        fin_map[code]["prev_profit"] = float(rows[1][1] or 0)

        return {"success": True, "data": [
            {"stock_code": i.stock_code, "stock_name": name_map.get(i.stock_code, i.stock_code),
             "group_tag": i.group_tag, "is_held": i.is_held,
             "notes": i.notes, "target_price_low": i.target_price_low,
             "target_price_high": i.target_price_high,
             "added_at": str(i.added_at) if i.added_at else None,
             "price": price_map.get(i.stock_code, {}).get("price"),
             "change_pct": price_map.get(i.stock_code, {}).get("change_pct"),
             "pe_ttm": val_map.get(i.stock_code, {}).get("pe_ttm"),
             "mcap_yi": val_map.get(i.stock_code, {}).get("mcap_yi"),
             "fin_revenue": fin_map.get(i.stock_code, {}).get("revenue"),
             "fin_profit": fin_map.get(i.stock_code, {}).get("profit"),
             "fin_cost": fin_map.get(i.stock_code, {}).get("cost"),
             "fin_equity": fin_map.get(i.stock_code, {}).get("equity"),
             "fin_date": fin_map.get(i.stock_code, {}).get("report_date"),
             "fin_revenue_qoq": (fin_map.get(i.stock_code, {}).get("revenue",0) / max(fin_map.get(i.stock_code, {}).get("prev_revenue",1), 1) - 1) * 100 if fin_map.get(i.stock_code, {}).get("prev_revenue") else None,
            }
            for i in items
        ]}


@router.post("/watchlist/add")
async def add_to_watchlist(stock_code: str, stock_name: str = "", group_tag: str = "默认",
                            notes: str = "", target_price_low: float = None,
                            target_price_high: float = None):
    """添加自选股 (自动补全名称+持仓标记 + 触发异步同步+指标回补)"""
    is_new = False
    async with async_session() as db:
        # 检查是否持仓
        pos = await db.get(Position, stock_code)
        is_held = pos is not None
        # Upsert (不存 stock_name, 展示时 join StockMaster)
        existing = await db.get(WatchlistItem, stock_code)
        if existing:
            existing.group_tag = group_tag
            existing.is_held = is_held
            if notes: existing.notes = notes
            if target_price_low is not None: existing.target_price_low = target_price_low
            if target_price_high is not None: existing.target_price_high = target_price_high
        else:
            is_new = True
            db.add(WatchlistItem(stock_code=stock_code,
                group_tag=group_tag, is_held=is_held,
                notes=notes, target_price_low=target_price_low,
                target_price_high=target_price_high))
        await db.commit()

    # 新自选股 → 触发异步行情同步+历史指标回补
    if is_new:
        try:
            sid = await task_manager.run_task("sync_market", {
                "mode": "AUTO", "target_codes": [stock_code]
            })
            logger.info(f"[Watchlist] {stock_code}: triggered sync_market (task={sid})")
        except Exception as e:
            logger.warning(f"[Watchlist] {stock_code}: failed to trigger sync: {e}")

    # 从 StockMaster 获取展示用名称
    async with async_session() as db2:
        master = await db2.get(StockMaster, stock_code)
        display_name = master.stock_name if master else (stock_name or stock_code)

    return {"success": True, "message": f"Added {stock_code}", "name": display_name, "is_held": is_held}


@router.post("/watchlist/import-positions")
async def import_positions_to_watchlist():
    """一键从持仓导入到自选股"""
    async with async_session() as db:
        res = await db.execute(select(Position.stock_code))
        positions = [r[0] for r in res.all()]
        count = 0
        for code in positions:
            existing = await db.get(WatchlistItem, code)
            if existing:
                existing.is_held = True
            else:
                db.add(WatchlistItem(stock_code=code, group_tag="持仓股", is_held=True))
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

            master = await db.get(StockMaster, pos.stock_code)
            val_info = await db.get(StockValuation, pos.stock_code)

            snapshots.append(PortfolioSnapshot(
                snap_date=today,
                stock_code=pos.stock_code, stock_name=master.stock_name if master else "",
                volume=int(vol), avg_cost=float(pos.avg_cost),
                current_price=today_price, market_value=pos.market_value,
                profit_loss=cumulative_pl, profit_loss_ratio=pos.profit_loss_ratio,
                pe_ttm=val_info.pe_ttm if val_info else None,
                pb=val_info.pb if val_info else None,
                mcap_yi=val_info.mcap_yi if val_info else None,
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


# ═══════════════════════════════════════════
# 财务报告中心
# ═══════════════════════════════════════════

@router.post("/financial/sync/{stock_code}")
async def sync_financial_statement(stock_code: str):
    """同步单只股票的财务报告"""
    from app.domain.market_data.services.financial_sync import sync_financials
    result = await sync_financials(stock_code)
    return {"success": "error" not in result, "data": result}


@router.post("/financial/sync")
async def sync_financial_statements_batch():
    """批量同步全部自选股的财务报告"""
    from app.domain.market_data.services.financial_sync import sync_financials_batch
    async with async_session() as db:
        res = await db.execute(select(WatchlistItem.stock_code))
        codes = [r[0] for r in res.all()]
    if not codes:
        return {"success": True, "message": "自选股为空"}
    result = await sync_financials_batch(codes)
    return {"success": True, "data": result}


@router.get("/financial/{stock_code}")
async def get_financial_statements(stock_code: str, periods: int = 8):
    """查询单只股票的财务报告 (最近N个季度)"""
    from app.models.models import FinancialStatement
    async with async_session() as db:
        res = await db.execute(
            select(FinancialStatement)
            .where(FinancialStatement.stock_code == stock_code)
            .order_by(FinancialStatement.report_date.desc())
            .limit(periods)
        )
        rows = res.scalars().all()
        return {"success": True, "data": [
            {"stock_code": r.stock_code, "report_date": str(r.report_date),
             "report_type": r.report_type, "revenue": r.revenue,
             "parent_profit": r.parent_profit, "operate_cost": r.operate_cost,
             "sale_expense": r.sale_expense, "manage_expense": r.manage_expense,
             "rd_expense": r.rd_expense, "op_cashflow": r.op_cashflow,
             "inventory": r.inventory, "contract_liability": r.contract_liability,
             "accounts_receivable": r.accounts_receivable, "total_assets": r.total_assets,
             "current_assets": r.current_assets, "fixed_assets": r.fixed_assets,
             "total_liabilities": r.total_liabilities, "total_equity": r.total_equity,
             "announce_date": str(r.announce_date) if r.announce_date else None}
            for r in rows  # 最新在前
        ]}


# ═══════════════════════════════════════════
# 原始财务数据查询 (FinancialRawDataService)
# ═══════════════════════════════════════════

@router.get("/financial-raw/catalog")
async def get_financial_raw_catalog():
    """原始财务数据字典: 21个字段的元数据 (名称/单位/分类/说明)"""
    from app.domain.market_data.services.financial_data_service import (
        FinancialRawDataService,
    )
    return {"success": True, "data": FinancialRawDataService.get_catalog()}


@router.post("/financial-raw/query")
async def query_financial_raw(
    code: str = Body(..., description="6位股票代码"),
    fields: Optional[List[str]] = Body(None, description="字段名列表, 默认全部"),
    periods: int = Body(4, description="返回的季度数"),
    latest_only: bool = Body(True, description="True=只返回最新一期"),
    start_date: Optional[str] = Body(None, description="起始日期 2025-01-01"),
    end_date: Optional[str] = Body(None, description="结束日期 2026-03-31"),
):
    """灵活查询原始财务数据"""
    from app.domain.market_data.services.financial_data_service import (
        FinancialRawDataService,
    )
    try:
        result = await FinancialRawDataService.query(
            code=code, fields=fields, periods=periods,
            latest_only=latest_only, start_date=start_date, end_date=end_date,
        )
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"[DataAPI] financial-raw query failed: {e}")
        return {"success": False, "error": str(e)}


@router.post("/financial-raw/query-bulk")
async def query_financial_raw_bulk(
    codes: List[str] = Body(..., description="股票代码列表"),
    fields: Optional[List[str]] = Body(None, description="字段名列表"),
    periods: int = Body(4, description="季度数"),
    latest_only: bool = Body(True, description="True=只返回最新一期"),
):
    """批量查询多只股票的原始财务数据"""
    from app.domain.market_data.services.financial_data_service import (
        FinancialRawDataService,
    )
    try:
        result = await FinancialRawDataService.query_bulk(
            codes=codes, fields=fields, periods=periods, latest_only=latest_only,
        )
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"[DataAPI] financial-raw bulk query failed: {e}")
        return {"success": False, "error": str(e)}


@router.post("/financial-raw/compare")
async def compare_financial_raw(
    code: str = Body(..., description="6位股票代码"),
    fields: Optional[List[str]] = Body(None, description="需要对比的字段, 默认前10个"),
    periods: int = Body(8, description="用于对比的季度数"),
):
    """周期对比: 同比 + 环比 + TTM 汇总"""
    from app.domain.market_data.services.financial_data_service import (
        FinancialRawDataService,
    )
    try:
        result = await FinancialRawDataService.compare(
            code=code, fields=fields, periods=periods,
        )
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"[DataAPI] financial-raw compare failed: {e}")
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════
# 基本面数据中心
# ═══════════════════════════════════════════

@router.get("/fundamental/overview")
async def get_fundamental_overview():
    """基本面总览: 行业分布 + PE/PB/市值统计"""
    async with async_session() as db:
        # 行业分布 (from StockMaster)
        ind_res = await db.execute(
            select(StockMaster.industry, func.count(), func.avg(StockValuation.pe_ttm), func.avg(StockValuation.mcap_yi))
            .outerjoin(StockValuation, StockMaster.stock_code == StockValuation.stock_code)
            .where(StockMaster.industry.isnot(None), StockMaster.industry != '')
            .group_by(StockMaster.industry).order_by(func.count().desc()))
        industries = [{"name": r[0], "count": r[1], "avg_pe": round(float(r[2] or 0),1), "avg_mcap": round(float(r[3] or 0),1)} for r in ind_res.all()]

        # PE分布 (from StockMaster + StockValuation)
        pe_res = await db.execute(
            select(StockMaster.stock_code, StockMaster.stock_name, StockMaster.industry,
                   StockValuation.pe_ttm, StockValuation.pb, StockValuation.mcap_yi)
            .outerjoin(StockValuation, StockMaster.stock_code == StockValuation.stock_code)
            .where(StockValuation.pe_ttm.isnot(None))
            .order_by(StockValuation.pe_ttm.asc()).limit(50))
        stocks = [{"code": r[0], "name": r[1], "pe_ttm": r[3], "pb": r[4], "mcap_yi": r[5], "industry": r[2] or "未知"} for r in pe_res.all()]

        return {"success": True, "data": {"industries": industries, "stocks": stocks}}


# ═══════════════════════════════════════════
# 另类数据中心
# ═══════════════════════════════════════════

@router.get("/alt/overview")
async def get_alt_overview():
    """另类数据总览: 筹码分布 + 拥挤度 (SQLite 直读)"""
    from app.domain.quant.engine import indicator_store
    from collections import defaultdict

    # 获取所有股票代码 (自选股+持仓)
    async with async_session() as db:
        pos_res = await db.execute(select(Position.stock_code))
        wl_res = await db.execute(select(WatchlistItem.stock_code))
        all_codes = list(set([r[0] for r in pos_res.all()] + [r[0] for r in wl_res.all()]))

        info_res = await db.execute(
            select(StockMaster.stock_code, StockMaster.stock_name)
            .where(StockMaster.stock_code.in_(all_codes)))
        name_map = {r[0]: r[1] or r[0] for r in info_res.all()}

    rows = indicator_store.get_latest_for_codes(all_codes)

    chip_stocks = []
    crowd_stocks = []
    for row in rows:
        code = row.get("stock_code")
        name = name_map.get(code, code)
        conc = row.get("chip_concentration")
        cr = row.get("crowding_ratio")
        if conc:
            chip_stocks.append({
                "code": code, "name": name,
                "date": row.get("trade_date"),
                "concentration": conc,
                "pattern": row.get("chip_pattern", "unknown"),
                "peak": row.get("chip_peak_price"),
            })
        if cr is not None:
            crowd_stocks.append({
                "code": code, "name": name,
                "date": row.get("trade_date"),
                "crowding_ratio": cr,
                "sharpe_60d": row.get("sharpe_60d"),
            })

    chip_stocks.sort(key=lambda x: x.get("concentration") or 0, reverse=True)
    crowd_stocks.sort(key=lambda x: x.get("crowding_ratio") or 0, reverse=True)

    return {"success": True, "data": {"chip": chip_stocks[:20], "crowding": crowd_stocks[:20]}}


@router.get("/alt/crowding/industry")
async def get_crowding_by_industry(days: int = Query(default=30, le=90)):
    """拥挤度行业聚合: 各行业 avg_crowding_ratio + top3 (SQLite)"""
    from collections import defaultdict
    from app.domain.quant.engine import indicator_store

    async with async_session() as db:
        pos_res = await db.execute(select(Position.stock_code))
        wl_res = await db.execute(select(WatchlistItem.stock_code))
        all_codes = list(set([r[0] for r in pos_res.all()] + [r[0] for r in wl_res.all()]))

        info_res = await db.execute(
            select(StockMaster.stock_code, StockMaster.stock_name, StockMaster.industry)
            .where(StockMaster.stock_code.in_(all_codes)))
        info_map = {}
        for r in info_res.all():
            info_map[r[0]] = {"name": r[1] or r[0], "industry": r[2] or "未知"}

    rows = indicator_store.get_latest_for_codes(all_codes)
    industry_data = defaultdict(list)
    for row in rows:
        code = row.get("stock_code")
        cr = row.get("crowding_ratio")
        if cr is None: continue
        info = info_map.get(code, {"name": code, "industry": "未知"})
        industry_data[info["industry"]].append({
            "code": code, "name": info["name"],
            "crowding_ratio": float(cr),
            "sharpe_60d": float(row["sharpe_60d"]) if row.get("sharpe_60d") else None,
        })

    result = []
    for industry, stocks in industry_data.items():
        avg_cr = sum(s["crowding_ratio"] for s in stocks) / len(stocks)
        sharpe_vals = [s["sharpe_60d"] for s in stocks if s["sharpe_60d"]]
        avg_sharpe = sum(sharpe_vals) / len(sharpe_vals) if sharpe_vals else 0.0
        top3 = sorted(stocks, key=lambda x: x["crowding_ratio"], reverse=True)[:3]
        result.append({
            "industry": industry, "count": len(stocks),
            "avg_crowding_ratio": round(avg_cr, 3),
            "avg_sharpe_60d": round(avg_sharpe, 3),
            "top_stocks": top3,
        })
    result.sort(key=lambda x: x["avg_crowding_ratio"], reverse=True)
    return {"success": True, "data": result}


@router.get("/alt/crowding/watchlist")
async def get_crowding_watchlist(days: int = Query(default=30, le=120)):
    """自选股拥挤度: 全部自选股 (SQLite 查询, 无数据显示null)"""
    from app.domain.quant.engine import indicator_store

    async with async_session() as db:
        wl_res = await db.execute(select(WatchlistItem.stock_code))
        wl_codes = [r[0] for r in wl_res.all()]
        if not wl_codes: return {"success": True, "data": []}

        # 从 StockMaster 获取名称
        name_res = await db.execute(
            select(StockMaster.stock_code, StockMaster.stock_name)
            .where(StockMaster.stock_code.in_(wl_codes)))
        wl_map = {r[0]: r[1] or r[0] for r in name_res.all()}
        # 兜底: StockMaster 中查不到的用原代码
        for code in wl_codes:
            if code not in wl_map: wl_map[code] = code

    rows = indicator_store.get_latest_for_codes(list(wl_map.keys()))
    ind_map = {r['stock_code']: r for r in rows}

    result = []
    for code in wl_map:
        name = wl_map[code]
        row = ind_map.get(code)
        if row:
            cr = row.get("crowding_ratio")
            result.append({
                "code": code, "name": name,
                "crowding_ratio": float(cr) if cr else None,
                "sharpe_60d": float(row["sharpe_60d"]) if row.get("sharpe_60d") else None,
                "date": row.get("trade_date"),
            })
        else:
            result.append({"code": code, "name": name, "crowding_ratio": None, "sharpe_60d": None, "date": None})

    result.sort(key=lambda x: (x.get("crowding_ratio") is not None, x.get("crowding_ratio") or 0), reverse=True)
    return {"success": True, "data": result}


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
async def update_watchlist(stock_code: str, group_tag: str = None,
                            notes: str = None, target_price_low: float = None,
                            target_price_high: float = None):
    """更新自选股 (分组/备注/目标价) — 名称统一从 StockMaster 获取"""
    async with async_session() as db:
        item = await db.get(WatchlistItem, stock_code)
        if not item:
            raise HTTPException(status_code=404, detail="Not in watchlist")
        if group_tag is not None: item.group_tag = group_tag
        if notes is not None: item.notes = notes
        if target_price_low is not None: item.target_price_low = target_price_low
        if target_price_high is not None: item.target_price_high = target_price_high
        await db.commit()
        # 从 StockMaster 获取展示用名称
        master = await db.get(StockMaster, stock_code)
        display_name = master.stock_name if master else stock_code
        return {"success": True, "message": f"Updated {stock_code}", "name": display_name}


@router.post("/watchlist/sync")
async def sync_watchlist(mode: str = "daily"):
    """同步全部自选股行情+估值 — mode=daily(当日10天)|historical(2年补全)"""
    from app.domain.market_data.services.valuation import sync_valuation
    from app.domain.quant.engine.engine import QuantEngine

    async with async_session() as db:
        res = await db.execute(select(WatchlistItem.stock_code))
        codes = [r[0] for r in res.all()]
    if not codes:
        return {"success": True, "message": "Watchlist empty"}

    engine = QuantEngine(db)
    total_rows = 0
    for code in codes:
        try:
            # daily=强制拉当日(跳过gap检查), historical=全量500天
            sync_mode = "FULL" if mode == "historical" else "FORCE"
            rows = await engine.sync_market_data(code, mode=sync_mode)
            total_rows += rows
        except Exception as e:
            logger.warning(f"[WatchlistSync] {code} failed: {e}")
    await db.commit()  # 持久化行情数据

    await sync_valuation(target_codes=codes)

    return {"success": True, "synced": len(codes), "total_rows": total_rows}


@router.get("/stock-center/list")
async def get_stock_center_list(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, le=500),
    search: str = Query(default=None),
):
    """股票中心: 全部股票 + 6 维数据完整度"""
    from app.domain.quant.engine.indicator_store import (
        get_financial_coverage_batch, get_indicator_coverage_batch)

    limit = page_size
    offset = (page - 1) * page_size

    async with async_session() as db:
        # 1. 查询 StockMaster (分页)
        base_q = select(StockMaster)
        count_q = select(func.count(StockMaster.stock_code))
        if search:
            like = f"%{search}%"
            base_q = base_q.where(
                StockMaster.stock_code.like(like) | StockMaster.stock_name.like(like))
            count_q = count_q.where(
                StockMaster.stock_code.like(like) | StockMaster.stock_name.like(like))

        total = (await db.execute(count_q)).scalar() or 0
        rows = await db.execute(base_q.order_by(StockMaster.stock_code).offset(offset).limit(limit))
        masters = rows.scalars().all()

        codes = [m.stock_code for m in masters]

        # 2. 批量查询各维度
        val_map = {}  # code -> StockValuation
        pos_set = set()  # codes in position
        wl_set = set()  # codes in watchlist
        md_map = {}  # code -> {days, latest}
        fs_map = {}  # code -> {quarters, latest}

        if codes:
            # 估值
            val_rows = await db.execute(
                select(StockValuation).where(StockValuation.stock_code.in_(codes)))
            for v in val_rows.scalars().all():
                val_map[v.stock_code] = v

            # 持仓
            pos_rows = await db.execute(
                select(Position.stock_code).where(Position.stock_code.in_(codes)))
            pos_set = {r[0] for r in pos_rows.all()}

            # 自选
            wl_rows = await db.execute(
                select(WatchlistItem.stock_code).where(WatchlistItem.stock_code.in_(codes)))
            wl_set = {r[0] for r in wl_rows.all()}

            # 行情 (group by) — 使用 ORM select 避免 collation/IN 参数问题
            md_rows = await db.execute(
                select(MarketData.stock_code, func.count().label("md_days"),
                       func.max(MarketData.trade_date).label("md_latest"))
                .where(MarketData.stock_code.in_(codes))
                .group_by(MarketData.stock_code)
            )
            for r in md_rows:
                md_map[r.stock_code] = {"days": r.md_days, "latest": r.md_latest}

            # 财报
            fs_rows = await db.execute(
                select(FinancialStatement.stock_code,
                       func.count(func.distinct(FinancialStatement.report_date)).label("fs_quarters"),
                       func.max(FinancialStatement.report_date).label("fs_latest"))
                .where(FinancialStatement.stock_code.in_(codes))
                .group_by(FinancialStatement.stock_code)
            )
            for r in fs_rows:
                fs_map[r.stock_code] = {"quarters": r.fs_quarters, "latest": r.fs_latest}

    # 3. SQLite 批量查询: 财务指标 + 价量指标
    fin_cov = get_financial_coverage_batch(codes) if codes else {}
    ind_cov = get_indicator_coverage_batch(codes) if codes else {}

    # 4. 组装结果
    result = []
    for m in masters:
        code = m.stock_code
        v = val_map.get(code)
        md = md_map.get(code, {})
        fs = fs_map.get(code, {})
        fi = fin_cov.get(code, {})
        ii = ind_cov.get(code, {})
        result.append({
            "code": code,
            "name": m.stock_name,
            "exchange": m.exchange,
            "industry": m.industry,
            "status": {
                "basic_finance": {
                    "ok": bool(fs.get("quarters")),
                    "quarters_count": fs.get("quarters") or 0,
                    "latest_date": fs.get("latest"),
                },
                "financial_indicators": {
                    "ok": bool(fi.get("count")),
                    "report_count": fi.get("count") or 0,
                    "latest_report_date": fi.get("latest"),
                },
                "dynamic_info": {
                    "ok": v is not None and v.pe_ttm is not None,
                    "pe": v.pe_ttm if v else None,
                    "pb": v.pb if v else None,
                    "mcap_yi": v.mcap_yi if v else None,
                },
                "market_data": {
                    "ok": bool(md.get("days")),
                    "days": md.get("days") or 0,
                    "latest_date": md.get("latest"),
                },
                "price_indicators": {
                    "ok": bool(ii.get("count")),
                    "record_count": ii.get("count") or 0,
                    "latest_date": ii.get("latest"),
                },
                "industry": {
                    "ok": bool(m.industry),
                    "name": m.industry,
                },
            },
            "in_position": code in pos_set,
            "in_watchlist": code in wl_set,
        })

    return {"success": True, "data": {
        "total": total, "page": page, "page_size": limit, "stocks": result,
    }}


class BatchSyncRequest(BaseModel):
    codes: List[str] = []
    mode: str = "daily"


@router.post("/stock-center/batch-sync")
async def stock_center_batch_sync(req: BatchSyncRequest):
    """股票中心批量同步 — 按 codes 同步行情 + 估值 + 基本信息"""
    from app.domain.quant.engine.engine import QuantEngine
    from app.domain.market_data.services.valuation import sync_valuation, sync_stock_info
    from datetime import date as dt_date

    codes = req.codes
    mode = req.mode
    if not codes:
        raise HTTPException(status_code=400, detail="codes required")

    logger.info(f"[StockCenter] Batch sync: {len(codes)} stocks, mode={mode}")
    async with async_session() as db:
        engine = QuantEngine(db)
        sync_mode = "AUTO" if mode == "daily" else "FULL"
        total_rows = 0
        for code in codes:
            try:
                rows = await engine.sync_market_data(code, mode=sync_mode)
                total_rows += rows
                # 盘中实时价
                if mode == "daily":
                    try:
                        from app.domain.market_data.sources.router import data_router
                        quotes = await data_router.get_realtime_quotes([code])
                        q = quotes.get(code, {})
                        if q.get('price') and q['price'] > 0:
                            today_str = dt_date.today().strftime('%Y-%m-%d')
                            existing = await db.execute(
                                select(MarketData).where(
                                    MarketData.stock_code == code,
                                    MarketData.trade_date == today_str))
                            row = existing.scalars().first()
                            if row:
                                row.close = float(q['price'])
                                if q.get('volume'): row.volume = int(float(q['volume']))
                            else:
                                db.add(MarketData(
                                    stock_code=code, trade_date=today_str,
                                    open=float(q.get('open', q['price'])),
                                    close=float(q['price']),
                                    high=float(q.get('high', q['price'])),
                                    low=float(q.get('low', q['price'])),
                                    volume=int(float(q.get('volume', 0)))))
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"[StockCenter] Batch sync fail: {code} | {e}")
        await db.commit()
    # 估值 + 基本信息 (批量调用)
    await sync_valuation(target_codes=codes)
    for code in codes:
        try:
            await sync_stock_info(code)
        except Exception:
            pass
    logger.info(f"[StockCenter] Batch sync done: {len(codes)} codes, {total_rows} rows")
    return {"success": True, "synced": len(codes), "rows": total_rows}
