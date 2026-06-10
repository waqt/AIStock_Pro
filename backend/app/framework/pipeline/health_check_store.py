"""健康体检快照 SQLite 存储 — 持久化 StockHealthChecker 结果"""
import sqlite3, os, threading, json
from datetime import datetime
from typing import List, Optional, Dict, Any
from app.framework.logger import logger

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'health_checks.db')

_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, 'hc_conn') or _local.hc_conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _local.hc_conn = sqlite3.connect(DB_PATH)
        _local.hc_conn.execute("PRAGMA journal_mode=WAL")
        _local.hc_conn.execute("PRAGMA synchronous=NORMAL")
        _local.hc_conn.row_factory = sqlite3.Row
    return _local.hc_conn


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS health_check_snapshots (
    id TEXT PRIMARY KEY,
    stock_code TEXT NOT NULL,
    stock_name TEXT DEFAULT '',
    verdict TEXT DEFAULT '',
    confidence TEXT DEFAULT '',
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hc_stock_code ON health_check_snapshots(stock_code);
CREATE INDEX IF NOT EXISTS idx_hc_created_at ON health_check_snapshots(created_at);
"""


def init_db():
    conn = _get_conn()
    for stmt in CREATE_TABLE_SQL.strip().split(";"):
        s = stmt.strip()
        if s:
            conn.execute(s)
    conn.commit()


def save_snapshot(stock_code: str, stock_name: str, result: dict) -> str:
    """保存体检结果, 返回 record id"""
    import uuid
    record_id = f"hc_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    overall = result.get("overall", {})
    verdict = overall.get("verdict", "")
    confidence = overall.get("confidence", "")
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO health_check_snapshots (id, stock_code, stock_name, verdict, confidence, result_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (record_id, stock_code, stock_name, verdict, confidence,
         json.dumps(result, ensure_ascii=False),
         datetime.now().isoformat())
    )
    conn.commit()
    logger.info(f"[HealthCheckStore] Saved {record_id} for {stock_code} ({stock_name})")
    return record_id


def get_history(stock_code: Optional[str] = None, limit: int = 50, offset: int = 0) -> tuple:
    """查询体检历史。stock_code=None 返回全部"""
    conn = _get_conn()
    if stock_code:
        rows = conn.execute(
            "SELECT id, stock_code, stock_name, verdict, confidence, created_at "
            "FROM health_check_snapshots WHERE stock_code=? "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (stock_code, limit, offset)
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) FROM health_check_snapshots WHERE stock_code=?",
            (stock_code,)
        ).fetchone()[0]
    else:
        rows = conn.execute(
            "SELECT id, stock_code, stock_name, verdict, confidence, created_at "
            "FROM health_check_snapshots ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) FROM health_check_snapshots"
        ).fetchone()[0]
    return [dict(r) for r in rows], total


def get_snapshot(record_id: str) -> Optional[dict]:
    """获取单条体检结果详情"""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM health_check_snapshots WHERE id=?", (record_id,)
    ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["result"] = json.loads(d.pop("result_json"))
    return d


def delete_snapshot(record_id: str) -> bool:
    """删除体检记录"""
    conn = _get_conn()
    cur = conn.execute("DELETE FROM health_check_snapshots WHERE id=?", (record_id,))
    conn.commit()
    return cur.rowcount > 0


def delete_all_for_stock(stock_code: str) -> int:
    """删除某只股票的全部体检记录"""
    conn = _get_conn()
    cur = conn.execute("DELETE FROM health_check_snapshots WHERE stock_code=?", (stock_code,))
    conn.commit()
    return cur.rowcount


# 初始化
init_db()
