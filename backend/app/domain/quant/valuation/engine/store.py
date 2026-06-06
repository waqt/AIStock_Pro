"""估值指标 SQLite 宽表存储 — 与 indicator_store 同模式, 独立表

在 data/indicators.db 中新增 valuation_metrics 表:
  PRIMARY KEY (stock_code, trade_date)
  其余列由 VALUATION_REGISTRY 各方法的 output 自动推导
"""
import sqlite3, os, threading
from datetime import date
from typing import List, Optional, Dict, Any
from app.framework.logger import logger

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'data', 'indicators.db')
TABLE = "valuation_metrics"

_local = threading.local()
PRECISION = 4

# ═══ 缓存 ═══════════════════════════════════════
_cols_cache = None

def _reset_cols_cache():
    global _cols_cache
    _cols_cache = None

def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, 'conn') or _local.conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _local.conn = sqlite3.connect(DB_PATH)
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn.row_factory = sqlite3.Row
    return _local.conn

# ═══ 列推导 ═════════════════════════════════════

VALUATION_BASE_NUMERIC_COLS = ["price"]
VALUATION_BASE_TEXT_COLS = []

def _get_dynamic_cols() -> tuple:
    """从 VALUATION_REGISTRY 自动推导数值列和文本列"""
    global _cols_cache
    if _cols_cache is not None:
        return _cols_cache

    from app.domain.quant.valuation import VALUATION_REGISTRY
    if not VALUATION_REGISTRY:
        _cols_cache = (VALUATION_BASE_NUMERIC_COLS[:], VALUATION_BASE_TEXT_COLS[:])
        return _cols_cache

    numeric = set(VALUATION_BASE_NUMERIC_COLS)
    text = set(VALUATION_BASE_TEXT_COLS)
    for cls in VALUATION_REGISTRY.values():
        text_set = set(getattr(cls, 'text_output', []))
        for f in getattr(cls, 'output', []):
            if f in text_set:
                text.add(f)
            else:
                numeric.add(f)
    _cols_cache = (sorted(numeric), sorted(text))
    return _cols_cache


def NUMERIC_COLS() -> list:
    n, _ = _get_dynamic_cols()
    return n

def TEXT_COLS() -> list:
    _, t = _get_dynamic_cols()
    return t

def ALL_COLS() -> list:
    return NUMERIC_COLS() + TEXT_COLS()


def _col_defs() -> str:
    num, txt = _get_dynamic_cols()
    defs = []
    for c in num:
        defs.append(f"{c} REAL DEFAULT NULL")
    for c in txt:
        defs.append(f"{c} TEXT DEFAULT NULL")
    return ", ".join(defs)


def _normalize(results: dict) -> dict:
    all_cols = ALL_COLS()
    text_cols = TEXT_COLS()
    row = {}
    for c in all_cols:
        val = results.get(c)
        if val is None:
            row[c] = None
        elif c in text_cols:
            row[c] = str(val)
        else:
            try:
                row[c] = round(float(val), PRECISION)
            except (ValueError, TypeError):
                row[c] = None
    return row


def _get_insert_sql() -> str:
    cols = ALL_COLS()
    return (f"INSERT OR REPLACE INTO {TABLE} "
            f"(stock_code, trade_date, {', '.join(cols)}) "
            f"VALUES (?, ?, {', '.join('?' * len(cols))})")


# ═══ 初始化 ═════════════════════════════════════

def init_db():
    """建表 + 自动补充缺失列 (幂等)"""
    conn = _get_conn()
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            stock_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            PRIMARY KEY (stock_code, trade_date)
        )
    """)
    conn.commit()

    num, txt = _get_dynamic_cols()
    all_expected = set(num + txt)
    existing_cols = set()
    try:
        rows = conn.execute(f"PRAGMA table_info({TABLE})").fetchall()
        existing_cols = {r[1] for r in rows}
    except Exception:
        pass

    missing = sorted(all_expected - existing_cols)
    if missing:
        for col in missing:
            col_type = "TEXT" if col in txt else "REAL"
            try:
                conn.execute(f"ALTER TABLE {TABLE} ADD COLUMN {col} {col_type} DEFAULT NULL")
                logger.info(f"[ValuationStore] Added column: {col} ({col_type})")
            except Exception as e:
                logger.warning(f"[ValuationStore] Failed to add column {col}: {e}")
        conn.commit()
    logger.info(f"[ValuationStore] SQLite ready: {DB_PATH}.{TABLE} ({len(all_expected)} columns)")


# ═══ 写入 ═══════════════════════════════════════

def upsert_snapshot(stock_code: str, trade_date: date, results: dict, partial_cols: List[str] = None):
    """写入单日估值快照。partial_cols=None → 全量覆盖"""
    conn = _get_conn()
    all_cols = ALL_COLS()
    row = _normalize(results)
    sql = _get_insert_sql()
    if partial_cols is None:
        conn.execute(sql, [stock_code, str(trade_date)] + [row[c] for c in all_cols])
    else:
        upd = [c for c in partial_cols if c in all_cols]
        if not upd:
            conn.commit()
            return
        set_c = ', '.join(f"{c}=excluded.{c}" for c in upd)
        cols = ['stock_code', 'trade_date'] + upd
        ph = ', '.join('?' * len(cols))
        vals = [stock_code, str(trade_date)] + [row.get(c) for c in upd]
        conn.execute(f"INSERT INTO {TABLE} ({', '.join(cols)}) VALUES ({ph}) "
                     f"ON CONFLICT(stock_code, trade_date) DO UPDATE SET {set_c}", vals)
    conn.commit()


def insert_batch(batch: List[dict]):
    """批量写入 [{stock_code, trade_date, day_results}, ...]"""
    conn = _get_conn()
    all_cols = ALL_COLS()
    sql = _get_insert_sql()
    rows = []
    for item in batch:
        row = _normalize(item['day_results'])
        rows.append([item['stock_code'], str(item['trade_date'])] + [row[c] for c in all_cols])
    conn.executemany(sql, rows)
    conn.commit()


def delete_stock(stock_code: str):
    """删除单只股票全部估值记录"""
    conn = _get_conn()
    conn.execute(f"DELETE FROM {TABLE} WHERE stock_code = ?", [stock_code])
    conn.commit()


# ═══ 查询 ═══════════════════════════════════════

def get_latest(stock_code: str) -> Optional[dict]:
    """获取单股最新一条估值"""
    conn = _get_conn()
    row = conn.execute(
        f"SELECT * FROM {TABLE} WHERE stock_code = ? ORDER BY trade_date DESC LIMIT 1",
        [stock_code]).fetchone()
    return dict(row) if row else None


def get_history(stock_code: str, fields: List[str] = None, days: int = 120) -> dict:
    """获取估值时间序列"""
    conn = _get_conn()
    all_cols = ALL_COLS()
    if fields:
        safe = [c for c in fields if c in all_cols]
        if not safe:
            return {"dates": [], "fields": {}}
    else:
        safe = all_cols
    cols_str = ", ".join(safe)
    rows = conn.execute(
        f"SELECT trade_date, {cols_str} FROM {TABLE} "
        f"WHERE stock_code = ? ORDER BY trade_date DESC LIMIT ?",
        [stock_code, days]).fetchall()
    dates = [r['trade_date'] for r in rows]
    fields_data = {c: [r[c] for r in rows] for c in safe}
    return {"dates": dates, "fields": fields_data}


def get_latest_for_codes(codes: List[str]) -> List[dict]:
    """批量获取多只股票最新估值 (通过 MAX+GROUP BY 自连接)"""
    if not codes:
        return []
    conn = _get_conn()
    placeholders = ",".join("?" * len(codes))
    row = conn.execute(
        f"SELECT a.* FROM {TABLE} a INNER JOIN "
        f"(SELECT stock_code, MAX(trade_date) as max_date FROM {TABLE} "
        f"WHERE stock_code IN ({placeholders}) GROUP BY stock_code) b "
        f"ON a.stock_code = b.stock_code AND a.trade_date = b.max_date",
        codes).fetchall()
    return [dict(r) for r in row]


# ═══ 数据新鲜度 ═════════════════════════════════

def check_freshness(stock_code: str) -> dict:
    """检查估值数据是否存在及新鲜度"""
    conn = _get_conn()
    row = conn.execute(
        f"SELECT COUNT(*) as cnt, MAX(trade_date) as latest "
        f"FROM {TABLE} WHERE stock_code = ?", [stock_code]).fetchone()
    cnt = row['cnt'] if row else 0
    latest = row['latest'] if row else None
    return {
        "has_data": cnt > 0,
        "days": cnt,
        "latest_date": latest,
        "is_fresh": cnt >= 1,
    }
