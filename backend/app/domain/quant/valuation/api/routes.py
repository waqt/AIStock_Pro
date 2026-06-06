"""估值 API — /api/quant/valuation/*

与 /api/quant/indicators/* 风格一致: {"success": true, "data": ...}
"""
from fastapi import APIRouter, Query
from typing import Optional, List
from pydantic import BaseModel
from app.domain.quant.valuation import VALUATION_REGISTRY
from app.framework.logger import logger

router = APIRouter(prefix="/api/quant/valuation", tags=["Quant-Valuation"])


# ═══ 注册表 ═════════════════════════════════════

@router.get("/registry")
async def list_methods():
    """所有已注册的估值方法列表"""
    result = [cls.meta() for cls in VALUATION_REGISTRY.values()]
    return {"success": True, "data": result}


@router.get("/catalog")
async def get_catalog():
    """估值字段数据字典 (按 category 分组)"""
    groups = {}
    for cls in VALUATION_REGISTRY.values():
        cat = cls.category or "other"
        if cat not in groups:
            groups[cat] = {"category": cat, "methods": []}
        groups[cat]["methods"].append(cls.meta())
    return {"success": True, "data": list(groups.values())}


# ═══ 计算 ═══════════════════════════════════════

@router.post("/compute/{stock_code}")
async def compute_single(
    stock_code: str,
    mode: str = Query("snapshot", description="snapshot|incremental|historical"),
):
    """计算单只股票的全部估值方法"""
    from app.domain.quant.valuation.engine.runner import valuation_runner
    try:
        result = await valuation_runner.compute(stock_code, mode)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"[ValuationAPI] {stock_code} compute failed: {e}")
        return {"success": False, "error": str(e)}


@router.post("/compute")
async def compute_batch(
    codes: Optional[str] = Query(None, description="逗号分隔的股票代码, 空=全部持仓+自选"),
    mode: str = Query("snapshot", description="snapshot|incremental|historical"),
):
    """批量计算估值 — 默认全部持仓 + 自选股"""
    from app.domain.quant.valuation.engine.runner import valuation_runner
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

    results = await valuation_runner.compute_batch(stock_codes, mode)
    return {"success": True, "data": results}


# ═══ 查询 ═══════════════════════════════════════

@router.get("/{stock_code}")
async def get_valuation(stock_code: str):
    """获取单只股票的最新估值快照"""
    from app.domain.quant.valuation.engine import store as vstore
    row = vstore.get_latest(stock_code)
    if not row:
        return {"success": True, "data": {"stock_code": stock_code, "message": "暂无估值数据, 请先 POST /compute"}}
    return {"success": True, "data": dict(row)}


@router.get("/history/{stock_code}")
async def get_valuation_history(
    stock_code: str,
    fields: Optional[str] = Query(None, description="逗号分隔的字段名"),
    days: int = Query(120, description="回溯天数"),
):
    """估值时间序列"""
    from app.domain.quant.valuation.engine import store as vstore
    field_list = [f.strip() for f in fields.split(",") if f.strip()] if fields else None
    hist = vstore.get_history(stock_code, field_list, days)
    return {"success": True, "data": hist}


@router.get("/percentile/{stock_code}")
async def get_percentile_chart(stock_code: str):
    """PE/PB 百分位图表数据 (当前值 + min/25%/50%/75%/max)"""
    from app.domain.quant.valuation.engine import store as vstore
    row = vstore.get_latest(stock_code)
    if not row:
        return {"success": True, "data": {"stock_code": stock_code, "message": "暂无估值数据"}}

    result = {"stock_code": stock_code}

    for key, label in [("pe_percentile", "PE"), ("pb_percentile", "PB"), ("ps_percentile", "PS")]:
        if row.get(key) is not None:
            pct = row[key]
            status = "高估" if pct > 80 else ("低估" if pct < 20 else "合理")
            result[key] = {
                "current_percentile": pct,
                "status": status,
                "median": row.get(f"{key.replace('_percentile', '_median')}"),
                "min": row.get(f"{key.replace('_percentile', '_min')}"),
                "max": row.get(f"{key.replace('_percentile', '_max')}"),
            }

    # 综合评分
    if row.get("valuation_score") is not None:
        result["valuation_score"] = row["valuation_score"]
        result["valuation_verdict"] = row.get("valuation_verdict")

    return {"success": True, "data": result}


# ═══ 对比 ═══════════════════════════════════════

class _CompareRequest(BaseModel):
    codes: List[str]
    fields: Optional[List[str]] = None

@router.post("/compare")
async def compare_valuation(req: _CompareRequest):
    """多只股票估值对比"""
    from app.domain.quant.valuation.engine import store as vstore
    rows = vstore.get_latest_for_codes(req.codes)
    if req.fields:
        filtered = []
        for r in rows:
            filtered.append({k: v for k, v in r.items() if k in req.fields or k in ("stock_code", "trade_date")})
        return {"success": True, "data": filtered}
    return {"success": True, "data": rows}
