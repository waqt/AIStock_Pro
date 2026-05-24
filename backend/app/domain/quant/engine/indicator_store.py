"""指标宽表 SQLite 存储 — 每指标一列, 支持时间序列直接查询"""
import sqlite3, os, threading
from datetime import date
from typing import List, Optional, Dict, Any
import pandas as pd
from app.framework.logger import logger

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'data', 'indicators.db')

# 全局连接 (线程本地, FastAPI 单线程模型安全)
_local = threading.local()

def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, 'conn') or _local.conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _local.conn = sqlite3.connect(DB_PATH)
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn.row_factory = sqlite3.Row
    return _local.conn

# ═══ 表结构定义 ═══════════════════════════════

# 所有数值列 (排除 Series-of-object 和文本类型)
NUMERIC_COLS = [
    "price",
    # trend
    "ma5", "ma10", "ma20", "ma60", "ma120", "ma250",
    "macd", "macd_signal", "macd_hist", "k", "d", "j",
    # momentum
    "rsi", "atr", "cci",
    # volatility
    "bb_upper", "bb_mid", "bb_lower", "bb_width",
    # volume
    "obv", "v_ma5", "v_ma10", "v_ma20", "vwap",
    # crowding
    "turnover_20d", "turnover_120d", "crowding_ratio", "sharpe_60d",
    # chip numeric
    "chip_concentration", "chip_peak_price", "chip_avg_cost",
    "chip_is_single_peak",
]

TEXT_COLS = ["chip_pattern", "chip_signal"]

# 所有列 (按 CREATE TABLE 顺序)
ALL_COLS = NUMERIC_COLS + TEXT_COLS

def _col_defs() -> str:
    defs = []
    for c in NUMERIC_COLS:
        defs.append(f"{c} REAL DEFAULT NULL")
    for c in TEXT_COLS:
        defs.append(f"{c} TEXT DEFAULT NULL")
    return ", ".join(defs)

CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS indicators (
    stock_code TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    {_col_defs()},
    PRIMARY KEY (stock_code, trade_date)
)
"""

PRECISION = 4

def _normalize(results: dict) -> dict:
    row = {}
    for c in ALL_COLS:
        val = results.get(c)
        if val is None:
            row[c] = None
        elif c in TEXT_COLS:
            row[c] = str(val)
        else:
            try:
                row[c] = round(float(val), PRECISION)
            except (ValueError, TypeError):
                row[c] = None
    return row

INSERT_SQL = f"INSERT OR REPLACE INTO indicators (stock_code, trade_date, {', '.join(ALL_COLS)}) VALUES (?, ?, {', '.join('?' * len(ALL_COLS))})"

# ═══ 公开 API ═════════════════════════════════

def init_db():
    """建表 (幂等)"""
    conn = _get_conn()
    conn.execute(CREATE_TABLE_SQL)
    conn.commit()
    logger.info(f"[IndicatorStore] SQLite ready: {DB_PATH}")

def upsert_snapshot(stock_code: str, trade_date: date, results: dict, partial_cols: List[str] = None):
    """写入单日快照。partial_cols=None → 全量覆盖; 指定时只更新那些列"""
    conn = _get_conn()
    row = _normalize(results)
    if partial_cols is None:
        conn.execute(INSERT_SQL, [stock_code, str(trade_date)] + [row[c] for c in ALL_COLS])
    else:
        upd = [c for c in partial_cols if c in ALL_COLS]
        if not upd: conn.commit(); return
        set_c = ', '.join(f"{c}=excluded.{c}" for c in upd)
        cols = ['stock_code', 'trade_date'] + upd
        ph = ', '.join('?' * len(cols))
        vals = [stock_code, str(trade_date)] + [row.get(c) for c in upd]
        conn.execute(f"INSERT INTO indicators ({', '.join(cols)}) VALUES ({ph}) ON CONFLICT(stock_code, trade_date) DO UPDATE SET {set_c}", vals)
    conn.commit()

def insert_batch(batch: List[dict]):
    """批量写入每日行 [{stock_code, trade_date, day_results}, ...]"""
    conn = _get_conn()
    rows = []
    for item in batch:
        row = _normalize(item['day_results'])
        rows.append([item['stock_code'], str(item['trade_date'])] + [row[c] for c in ALL_COLS])
    conn.executemany(INSERT_SQL, rows)
    conn.commit()

def upsert_rows(batch: List[dict], partial_cols: List[str] = None):
    """批量写入或合并。
    partial_cols=None → INSERT OR REPLACE 全量覆盖 (executemany, 快)
    partial_cols 指定 → 先读现有行 → 内存合并 → executemany 全量写回 (2次SQL, 快)"""
    conn = _get_conn()
    if partial_cols is None:
        rows = []
        for item in batch:
            row = _normalize(item['day_results'])
            rows.append([item['stock_code'], str(item['trade_date'])] + [row[c] for c in ALL_COLS])
        conn.executemany(INSERT_SQL, rows)
        logger.debug(f"[IndicatorStore] upsert: {len(batch)} rows (full replace)")
    else:
        # 按 stock_code 分组, 每只股票一次 SELECT 读取全部现有行
        existing_map = {}
        seen_codes = set(item['stock_code'] for item in batch)
        for sc in seen_codes:
            for r in conn.execute("SELECT * FROM indicators WHERE stock_code=?", [sc]).fetchall():
                existing_map[(r['stock_code'], r['trade_date'])] = dict(r)

        rows = []
        for item in batch:
            sc, td = item['stock_code'], str(item['trade_date'])
            existing = existing_map.get((sc, td), {})
            new_vals = _normalize(item['day_results'])
            merged = existing
            merged.update({k: v for k, v in new_vals.items() if v is not None})
            merged.setdefault('stock_code', sc)
            merged.setdefault('trade_date', td)
            rows.append([sc, td] + [merged.get(c) for c in ALL_COLS])
        conn.executemany(INSERT_SQL, rows)
        logger.debug(f"[IndicatorStore] upsert: {len(batch)} rows (merge, cols={partial_cols})")
    conn.commit()

def delete_stock(stock_code: str):
    """删除单只股票全部指标"""
    conn = _get_conn()
    conn.execute("DELETE FROM indicators WHERE stock_code = ?", [stock_code])
    conn.commit()

def get_latest(stock_code: str) -> Optional[dict]:
    """获取单股最新一条指标"""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM indicators WHERE stock_code = ? ORDER BY trade_date DESC LIMIT 1",
        [stock_code]).fetchone()
    return dict(row) if row else None

def get_history(stock_code: str, fields: List[str], days: int = 120) -> dict:
    """获取单股指标时间序列 → {dates: [...], fields: {field: [...]}}"""
    conn = _get_conn()
    valid = [f for f in fields if f in ALL_COLS]
    if not valid:
        return {"stock_code": stock_code, "dates": [], "fields": {}}
    cols = "trade_date, " + ", ".join(valid)
    rows = conn.execute(
        f"SELECT {cols} FROM indicators WHERE stock_code = ? ORDER BY trade_date ASC",
        [stock_code]).fetchall()
    dates = []
    result_fields = {f: [] for f in valid}
    for r in rows:
        d = dict(r)
        dates.append(d['trade_date'])
        for f in valid:
            result_fields[f].append(d.get(f))
    return {"stock_code": stock_code, "dates": dates, "fields": result_fields}

def get_field_latest(field_name: str) -> List[dict]:
    """某指标字段在所有股票上的最新值 (按值降序)"""
    conn = _get_conn()
    if field_name not in ALL_COLS:
        return []
    sql = f"""
        SELECT i.stock_code, i.{field_name}, i.trade_date FROM indicators i
        INNER JOIN (
            SELECT stock_code, MAX(trade_date) as max_date FROM indicators
            WHERE {field_name} IS NOT NULL GROUP BY stock_code
        ) latest ON i.stock_code = latest.stock_code AND i.trade_date = latest.max_date
        ORDER BY i.{field_name} DESC
    """
    rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]

def get_latest_for_codes(codes: List[str], cutoff_date: str = None) -> List[dict]:
    """获取多只股票的最新指标 (通过 MAX + self-join)"""
    conn = _get_conn()
    if not codes:
        return []
    placeholders = ','.join('?' * len(codes))
    sql = f"""
        SELECT i.* FROM indicators i
        INNER JOIN (
            SELECT stock_code, MAX(trade_date) as max_date
            FROM indicators
            WHERE stock_code IN ({placeholders})
            GROUP BY stock_code
        ) latest ON i.stock_code = latest.stock_code AND i.trade_date = latest.max_date
    """
    rows = conn.execute(sql, codes).fetchall()
    return [dict(r) for r in rows]

def get_coverage(codes: List[str]) -> List[dict]:
    """覆盖检测: 每个股票指标天数"""
    conn = _get_conn()
    result = []
    for code in codes:
        r = conn.execute(
            "SELECT COUNT(*) as cnt, MAX(trade_date) as max_d FROM indicators WHERE stock_code = ?",
            [code]).fetchone()
        result.append({"code": code, "days": r['cnt'] or 0, "last_date": r['max_d']})
    return result

def get_counts() -> int:
    conn = _get_conn()
    return conn.execute("SELECT COUNT(*) FROM indicators").fetchone()[0]
