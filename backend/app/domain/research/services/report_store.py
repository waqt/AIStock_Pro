"""
研报持久化存储 — JSON 文件 + DB registry 双层索引
"""
import json, os, re, glob, asyncio as _a
from datetime import datetime
from typing import List, Dict, Optional
from app.framework.logger import logger

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "data", "research_reports")
REPORTS_DIR = os.path.abspath(REPORTS_DIR)


def _sanitize(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '_', s)[:30]


def _guess_type(agent: str) -> str:
    a = str(agent).lower()
    if "market" in a: return "market_scan"
    if "capex" in a: return "capex_scan"
    return "supply_chain"


async def _upsert_registry(report_type: str, report_id: str, **fields):
    """写入 report_registry, 失败不阻塞"""
    try:
        from app.framework.database.session import async_session
        from app.models.models import ReportRegistry
        from sqlalchemy import select
        async with async_session() as db:
            existing = await db.execute(
                select(ReportRegistry).where(ReportRegistry.report_id == report_id))
            row = existing.scalars().first()
            if row:
                for k, v in fields.items():
                    if v is not None and hasattr(row, k):
                        setattr(row, k, v)
                row.status = "regenerated"
            else:
                kwargs = {k: v for k, v in fields.items() if v is not None}
                db.add(ReportRegistry(report_type=report_type, report_id=report_id,
                                      status="valid", **kwargs))
            await db.commit()
    except Exception:
        pass


def _sync_upsert(report_type: str, report_id: str, **fields):
    """非异步环境下的安全调用"""
    try:
        loop = _a.get_event_loop()
        if loop.is_running():
            _a.ensure_future(_upsert_registry(report_type, report_id, **fields))
        else:
            _a.run(_upsert_registry(report_type, report_id, **fields))
    except RuntimeError:
        _a.run(_upsert_registry(report_type, report_id, **fields))


def save_report(agent: str, industry: str, data: Dict) -> str:
    """保存研报, 返回 report_id"""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{ts}_{agent}_{_sanitize(industry)}.json"
    filepath = os.path.join(REPORTS_DIR, filename)
    report_id = filename.replace(".json", "")

    record = {
        "report_id": report_id, "agent": agent, "industry": industry,
        "created_at": datetime.now().isoformat(), "data": data,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"[ReportStore] Saved: {filename}")

    _sync_upsert(
        report_type=_guess_type(agent), report_id=report_id,
        title=data.get("title") or industry, industry=industry, agent=agent,
        filepath=f"data/research_reports/{filename}",
        generated_at=record["created_at"],
        summary=(data.get("final_summary") or "")[:200],
    )
    return report_id


def list_reports(limit: int = 20) -> List[Dict]:
    """列出最近的研报 (优先从 registry, 兜底扫文件)"""
    try:
        from app.framework.database.session import async_session
        from app.models.models import ReportRegistry
        from sqlalchemy import select

        async def _q():
            async with async_session() as db:
                res = await db.execute(
                    select(ReportRegistry)
                    .where(ReportRegistry.report_type.in_(
                        ["supply_chain", "market_scan", "capex_scan"]))
                    .order_by(ReportRegistry.generated_at.desc()).limit(limit))
                return res.scalars().all()
        loop = _a.get_event_loop()
        if loop.is_running():
            # running loop: try to run in it
            import concurrent.futures
            fut = _a.ensure_future(_q())
            # can't await here, fallback to file scan
            raise RuntimeError("loop running, fallback")
        rows = _a.run(_q())
        if rows:
            return [{
                "report_id": r.report_id, "agent": r.agent, "industry": r.industry,
                "title": r.title or r.industry or "?", "created_at": str(r.generated_at),
                "summary": r.summary or "", "stocks_count": 0, "stocks": [],
            } for r in rows]
    except Exception:
        pass
    # Fallback: scan files
    os.makedirs(REPORTS_DIR, exist_ok=True)
    files = sorted(glob.glob(os.path.join(REPORTS_DIR, "*.json")), reverse=True)[:limit]
    reports = []
    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                r = json.load(f)
            data = r.get("data", {})
            core_stocks = data.get("core_stocks", [])
            reports.append({
                "report_id": r.get("report_id", ""), "agent": r.get("agent", ""),
                "industry": r.get("industry", ""),
                "title": data.get("title") or r.get("industry", "?"),
                "created_at": r.get("created_at", ""),
                "summary": (data.get("final_summary") or "")[:150],
                "stocks_count": len(core_stocks),
                "stocks": [{"code": s.get("code"), "name": s.get("name")} for s in core_stocks[:5]],
            })
        except Exception as e:
            logger.warning(f"[ReportStore] Failed to read {fp}: {e}")
    return reports


def get_report(report_id: str) -> Optional[Dict]:
    filepath = os.path.join(REPORTS_DIR, f"{report_id}.json")
    if not os.path.exists(filepath): return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def delete_report(report_id: str) -> bool:
    filepath = os.path.join(REPORTS_DIR, f"{report_id}.json")
    if not os.path.exists(filepath): return False
    os.remove(filepath)
    # 标记 registry
    try:
        from app.framework.database.session import async_session
        from app.models.models import ReportRegistry
        from sqlalchemy import select
        async def _del():
            async with async_session() as db:
                res = await db.execute(select(ReportRegistry).where(ReportRegistry.report_id == report_id))
                row = res.scalars().first()
                if row: row.status = "expired"; await db.commit()
        _a.run(_del())
    except Exception: pass
    logger.info(f"[ReportStore] Deleted: {report_id}")
    return True
