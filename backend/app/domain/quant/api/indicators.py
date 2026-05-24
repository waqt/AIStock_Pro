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
    """批量计算指标 — 默认全部持仓 + 自选股"""
    from app.domain.quant.engine.indicator_runner import IndicatorRunner
    from app.framework.database.session import async_session
    from app.models.models import Position, WatchlistItem
    from sqlalchemy import select

    if codes:
        stock_codes = [c.strip() for c in codes.split(",") if c.strip()]
    else:
        async with async_session() as db:
            pos = await db.execute(select(Position.stock_code))
            wl = await db.execute(select(WatchlistItem.stock_code))
            stock_codes = list(set([r[0] for r in pos.all()] + [r[0] for r in wl.all()]))

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
    """查询某只股票的指标覆盖日期范围 (SQLite)"""
    from app.domain.quant.engine import indicator_store
    cov = indicator_store.get_coverage([stock_code])
    info = cov[0] if cov else {"days": 0, "last_date": None}
    return {"success": True, "data": {
        "stock_code": stock_code,
            "earliest": str(r[0]) if r and r[0] else None,
            "latest": str(r[1]) if r and r[1] else None,
            "days_covered": info.get("days", 0),
            "last_date": info.get("last_date"),
        }}


# ═══ 历史时间序列 (必须放在 /{stock_code} 之前) ═══

@router.get("/history/{stock_code}")
async def get_indicator_history(
    stock_code: str,
    fields: str = Query(default="crowding_ratio,sharpe_60d", description="逗号分隔指标字段"),
    days: int = Query(default=120, le=365)
):
    """单股指标历史时间序列 (SQLite 直读, 供 ECharts 渲染)"""
    from app.domain.quant.engine import indicator_store
    field_list = [f.strip() for f in fields.split(",") if f.strip()]
    data = indicator_store.get_history(stock_code, field_list, days)
    return {"success": True, "data": data}


# ═══ 覆盖检测 ═══

@router.get("/coverage")
async def get_indicator_coverage(scope: str = Query(default="all", description="all=持仓+自选股 | positions=仅持仓")):
    """检测需要指标计算的股票覆盖情况 (SQLite 查询)"""
    from app.framework.database.session import async_session
    from app.models.models import Position, WatchlistItem, StockInfo, MarketData
    from app.domain.quant.indicators import INDICATOR_REGISTRY
    from app.domain.quant.engine import indicator_store
    from sqlalchemy import select, func

    async with async_session() as db:
        pos = await db.execute(select(Position.stock_code))
        pos_codes = set(r[0] for r in pos.all())
        wl_codes = set()
        if scope != "positions":
            wl = await db.execute(select(WatchlistItem.stock_code))
            wl_codes = set(r[0] for r in wl.all())
        all_codes = sorted(pos_codes | wl_codes)

        name_res = await db.execute(select(StockInfo.stock_code, StockInfo.stock_name))
        name_map = {r[0]: r[1] or r[0] for r in name_res.all()}

        md_res = await db.execute(
            select(MarketData.stock_code, func.count(MarketData.id), func.max(MarketData.trade_date))
            .where(MarketData.stock_code.in_(all_codes))
            .group_by(MarketData.stock_code))
        md_map = {r[0]: (r[1], str(r[2]) if r[2] else None) for r in md_res.all()}

    # SQLite 覆盖
    cov_list = indicator_store.get_coverage(all_codes)
    cov_map = {c['code']: c for c in cov_list}

    all_fields = set()
    for cls in INDICATOR_REGISTRY.values():
        for f in cls.output:
            all_fields.add(f)
    all_fields.add("price")
    skip_fields = {"chip_peaks", "chip_valleys", "chip_is_single_peak", "chip_pattern_detail"}

    # 取一只样本股票的指标字段来判断缺失
    latest_map = {}
    if all_codes:
        rows = indicator_store.get_latest_for_codes(all_codes)
        latest_map = {r['stock_code']: r for r in rows}

    details = []
    stocks_with = 0
    for code in all_codes:
        md_info = md_map.get(code, (0, None))
        ind_data = latest_map.get(code, {})
        ind_days = cov_map.get(code, {}).get('days', 0)
        has_md = md_info[0] > 0
        has_ind = bool(ind_data)

        missing = []
        if has_ind:
            check_fields = all_fields - skip_fields
            for f in sorted(check_fields):
                if ind_data.get(f) is None:
                    missing.append(f)
        else:
            missing = sorted(all_fields - skip_fields)

        if has_ind and not missing:
            stocks_with += 1

        details.append({
            "code": code, "name": name_map.get(code, code),
            "has_market_data": has_md, "md_last_date": md_info[1],
            "indicator_days": ind_days,
            "missing_indicators": missing,
        })

    return {
        "success": True, "data": {
            "total_stocks": len(all_codes),
            "stocks_with_full_indicators": stocks_with,
            "missing": len(all_codes) - stocks_with,
            "indicator_fields_total": len(all_fields - skip_fields),
            "details": details,
        }
    }


# ═══ 筹码分布图 ═══

@router.get("/chip-dist/{stock_code}")
async def get_chip_distribution(stock_code: str):
    """返回筹码分布数据供前端渲染水平柱状图"""
    from app.framework.database.session import async_session
    from app.models.models import MarketData
    from sqlalchemy import select
    import numpy as np, pandas as pd

    async with async_session() as db:
        res = await db.execute(
            select(MarketData).where(MarketData.stock_code == stock_code)
            .order_by(MarketData.trade_date.asc()))
        rows = res.scalars().all()
    if not rows:
        return {"success": True, "data": None}

    close = np.array([float(r.close or 0) for r in rows], dtype=np.float64)
    high = np.array([float(r.high or 0) for r in rows], dtype=np.float64)
    low = np.array([float(r.low or 0) for r in rows], dtype=np.float64)
    volume = np.array([float(r.volume or 0) for r in rows], dtype=np.float64)
    n = len(close)

    w = 90; bins = 200; hl = 45
    decay = np.float64(0.5 ** (1.0 / hl))
    start = max(0, n - w)

    lo_w = low[start:]; hi_w = high[start:]; cl_w = close[start:]; vol_w = volume[start:]
    p_min = float(np.min(lo_w)); p_max = float(np.max(hi_w))
    cur = float(cl_w[-1])
    if cur > p_max: p_max = cur
    if cur < p_min: p_min = cur
    if p_max <= p_min: p_max = p_min + 0.01
    margin = (p_max - p_min) * 0.05
    p_min -= margin; p_max += margin
    bw = (p_max - p_min) / bins
    grid = np.array([p_min + (j + 0.5) * bw for j in range(bins)], dtype=np.float64)
    chip = np.zeros(bins, dtype=np.float64)

    for j in range(w):
        chip *= decay
        if vol_w[j] <= 0: continue
        lo = max(0, int((lo_w[j] - p_min) / bw))
        hi = min(bins - 1, int((hi_w[j] - p_min) / bw) + 1)
        if hi <= lo: continue
        mid_f = (cl_w[j] - p_min) / bw
        mid = max(lo, min(hi - 1, int(mid_f)))
        for k in range(lo, hi):
            weight = 1.0 - 0.7 * abs(k - mid) / max(hi - lo, 1)
            chip[k] += vol_w[j] * max(0.0, weight)

    total = float(chip.sum())
    if total <= 0:
        return {"success": True, "data": None}

    avg_cost = round(float(np.average(grid, weights=chip)), 2)
    chip_pct = (chip / total * 100).tolist()
    prices = [round(float(p), 2) for p in grid]

    si = np.argsort(grid)
    cum = np.cumsum(chip[si]) / total
    c5 = round(float(grid[si[min(np.searchsorted(cum, 0.05), bins - 1)]]), 2)
    c50 = round(float(grid[si[min(np.searchsorted(cum, 0.50), bins - 1)]]), 2)
    c95 = round(float(grid[si[min(np.searchsorted(cum, 0.95), bins - 1)]]), 2)
    winner = round(float(chip[grid <= cur].sum() / total * 100), 2)
    denom = c95 + c5
    conc = round((c95 - c5) / denom, 4) if denom > 0 else 0

    return {"success": True, "data": {
        "prices": prices, "chip_pct": chip_pct,
        "avg_cost": avg_cost, "close": round(cur, 2),
        "cost_5": c5, "cost_50": c50, "cost_95": c95,
        "winner_close": winner, "concentration_90": conc,
    }}


# ═══ 按指标字段查询 ═══

@router.get("/field/{field_name}")
async def get_field_values(field_name: str):
    """某指标字段在所有股票上的最新值排名 (如 /field/crowding_ratio)"""
    from app.domain.quant.engine import indicator_store
    from app.framework.database.session import async_session
    from app.models.models import StockInfo
    from sqlalchemy import select

    rows = indicator_store.get_field_latest(field_name)

    async with async_session() as db:
        codes = [r['stock_code'] for r in rows if r.get('stock_code')]
        info = {}
        if codes:
            res = await db.execute(select(StockInfo.stock_code, StockInfo.stock_name)
                .where(StockInfo.stock_code.in_(codes)))
            for r2 in res.all():
                info[r2[0]] = r2[1] or r2[0]

    result = []
    for r in rows:
        code = r.get('stock_code', '')
        result.append({
            "code": code,
            "name": info.get(code, code),
            "value": r.get(field_name),
            "date": r.get('trade_date'),
        })
    return {"success": True, "data": result, "field": field_name}


# ═══ 单股查询 (放在最后, 避免拦截 /data/ 等前缀路由) ═══

@router.get("/{stock_code}")
async def get_stock_indicators(stock_code: str):
    """单股全量最新指标快照 (SQLite 查询)"""
    from app.domain.quant.engine import indicator_store
    row = indicator_store.get_latest(stock_code)
    if not row:
        return {"success": True, "data": None, "message": f"No indicators for {stock_code}"}
    return {
        "success": True, "data": {
            "stock_code": row.get("stock_code", stock_code),
            "analysis_date": row.get("trade_date"),
            "indicators": row,
            "patterns": {},
        }
        }
