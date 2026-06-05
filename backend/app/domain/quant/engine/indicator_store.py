"""指标宽表 SQLite 存储 — 每指标一列, 支持时间序列直接查询"""
import json, sqlite3, os, threading
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

# 基础种子列 (非指标产出, 由计算引擎直接写入)
INDICATOR_BASE_NUMERIC_COLS = ["price"]
INDICATOR_BASE_TEXT_COLS = []

# 缓存: 避免每次调用都重新推导
_ind_cols_cache = None

def _reset_indicator_cols_cache():
    global _ind_cols_cache
    _ind_cols_cache = None

def _get_dynamic_indicator_cols() -> tuple:
    """从 INDICATOR_REGISTRY 自动推导数值列和文本列"""
    global _ind_cols_cache
    if _ind_cols_cache is not None:
        return _ind_cols_cache

    from app.domain.quant.indicators import INDICATOR_REGISTRY
    if not INDICATOR_REGISTRY:
        _ind_cols_cache = (INDICATOR_BASE_NUMERIC_COLS[:], INDICATOR_BASE_TEXT_COLS[:])
        return _ind_cols_cache

    numeric = set(INDICATOR_BASE_NUMERIC_COLS)
    text = set(INDICATOR_BASE_TEXT_COLS)
    for cls in INDICATOR_REGISTRY.values():
        text_set = set(getattr(cls, 'text_output', []))
        for f in getattr(cls, 'output', []):
            if f in text_set:
                text.add(f)
            else:
                numeric.add(f)
    _ind_cols_cache = (sorted(numeric), sorted(text))
    return _ind_cols_cache


def INDICATOR_NUMERIC_COLS() -> list:
    num, _ = _get_dynamic_indicator_cols()
    return num


def INDICATOR_TEXT_COLS() -> list:
    _, txt = _get_dynamic_indicator_cols()
    return txt


def INDICATOR_ALL_COLS() -> list:
    return INDICATOR_NUMERIC_COLS() + INDICATOR_TEXT_COLS()


def _col_defs() -> str:
    num, txt = _get_dynamic_indicator_cols()
    defs = []
    for c in num:
        defs.append(f"{c} REAL DEFAULT NULL")
    for c in txt:
        defs.append(f"{c} TEXT DEFAULT NULL")
    return ", ".join(defs)

PRECISION = 4

def _normalize(results: dict) -> dict:
    all_cols = INDICATOR_ALL_COLS()
    text_cols = INDICATOR_TEXT_COLS()
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
    cols = INDICATOR_ALL_COLS()
    return f"INSERT OR REPLACE INTO indicators (stock_code, trade_date, {', '.join(cols)}) VALUES (?, ?, {', '.join('?' * len(cols))})"

# ═══ 公开 API ═════════════════════════════════

def init_db():
    """建表 + 自动补充缺失列 (幂等, 新增指标后重启自动加列)"""
    conn = _get_conn()
    # 只建基础表 (PK 列), 指标列通过 ALTER TABLE 动态补充
    conn.execute("""
        CREATE TABLE IF NOT EXISTS indicators (
            stock_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            PRIMARY KEY (stock_code, trade_date)
        )
    """)
    conn.commit()

    # 自动补充全部注册指标字段
    num, txt = _get_dynamic_indicator_cols()
    all_expected = set(num + txt)

    # 检查现有列
    existing_cols = set()
    try:
        rows = conn.execute("PRAGMA table_info(indicators)").fetchall()
        existing_cols = {r[1] for r in rows}
    except Exception:
        pass

    # 只补充缺少的列, 不 DROP 表
    missing = sorted(all_expected - existing_cols)
    if missing:
        for col in missing:
            col_type = "TEXT" if col in txt else "REAL"
            try:
                conn.execute(f"ALTER TABLE indicators ADD COLUMN {col} {col_type} DEFAULT NULL")
                logger.info(f"[IndicatorStore] Added indicator column: {col} ({col_type})")
            except Exception as e:
                logger.warning(f"[IndicatorStore] Failed to add column {col}: {e}")
        conn.commit()

    logger.info(f"[IndicatorStore] SQLite ready: {DB_PATH} ({len(all_expected)} columns)")

def upsert_snapshot(stock_code: str, trade_date: date, results: dict, partial_cols: List[str] = None):
    """写入单日快照。partial_cols=None → 全量覆盖; 指定时只更新那些列"""
    conn = _get_conn()
    all_cols = INDICATOR_ALL_COLS()
    row = _normalize(results)
    sql = _get_insert_sql()
    if partial_cols is None:
        conn.execute(sql, [stock_code, str(trade_date)] + [row[c] for c in all_cols])
    else:
        upd = [c for c in partial_cols if c in all_cols]
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
    all_cols = INDICATOR_ALL_COLS()
    sql = _get_insert_sql()
    rows = []
    for item in batch:
        row = _normalize(item['day_results'])
        rows.append([item['stock_code'], str(item['trade_date'])] + [row[c] for c in all_cols])
    conn.executemany(sql, rows)
    conn.commit()

def upsert_rows(batch: List[dict], partial_cols: List[str] = None):
    """批量写入或合并。
    partial_cols=None → INSERT OR REPLACE 全量覆盖 (executemany, 快)
    partial_cols 指定 → 先读现有行 → 内存合并 → executemany 全量写回 (2次SQL, 快)"""
    conn = _get_conn()
    all_cols = INDICATOR_ALL_COLS()
    sql = _get_insert_sql()
    if partial_cols is None:
        rows = []
        for item in batch:
            row = _normalize(item['day_results'])
            rows.append([item['stock_code'], str(item['trade_date'])] + [row[c] for c in all_cols])
        conn.executemany(sql, rows)
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
            rows.append([sc, td] + [merged.get(c) for c in all_cols])
        conn.executemany(sql, rows)
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
    """获取单股指标时间序列 → {dates: [...], fields: {field: [...]}}
    days: 返回最近 N 条记录 (默认 120), 0 或 None 返回全部
    """
    conn = _get_conn()
    all_cols = INDICATOR_ALL_COLS()
    valid = [f for f in fields if f in all_cols]
    if not valid:
        return {"stock_code": stock_code, "dates": [], "fields": {}}
    cols = "trade_date, " + ", ".join(valid)
    if days and days > 0:
        rows = conn.execute(
            f"SELECT {cols} FROM indicators WHERE stock_code = ? ORDER BY trade_date DESC LIMIT ?",
            [stock_code, days]).fetchall()
        rows.reverse()
    else:
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
    if field_name not in INDICATOR_ALL_COLS():
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


# ═══ 财务指标存储 (独立表, 不在 Indicators 宽表中) ═══════════════════

# 静态基础字段 (非指标产出, 由计算引擎直接写入)
FINANCIAL_BASE_NUMERIC_COLS = []  # 目前没有引擎直接写入的数字元字段
FINANCIAL_BASE_TEXT_COLS = ["source"]  # 数据来源标记 (db/web)


def _get_dynamic_financial_cols() -> tuple:
    """从 FINANCIAL_REGISTRY 自动推导数值列和文本列清单。
    避免手写 FINANCIAL_NUMERIC_COLS 与注册表脱节的问题。
    """
    from app.domain.quant.indicators.fundamental import FINANCIAL_REGISTRY
    if not FINANCIAL_REGISTRY:
        # 模块首次加载时注册表可能尚未填充, 返回空种子
        # 实际调用 _init_financial_table 时会二次检查
        return FINANCIAL_BASE_NUMERIC_COLS[:], FINANCIAL_BASE_TEXT_COLS[:]

    numeric = set(FINANCIAL_BASE_NUMERIC_COLS)
    text = set(FINANCIAL_BASE_TEXT_COLS)
    for cls in FINANCIAL_REGISTRY.values():
        text_set = set(cls.text_output)
        for f in cls.output:
            if f in text_set:
                text.add(f)
            else:
                numeric.add(f)
    return sorted(numeric), sorted(text)


def FINANCIAL_NUMERIC_COLS() -> list:
    """动态属性 — 每次调用从注册表推导 (lazy, 注册表加载后生效)"""
    num, _ = _get_dynamic_financial_cols()
    return num


def FINANCIAL_TEXT_COLS() -> list:
    """动态属性"""
    _, txt = _get_dynamic_financial_cols()
    return txt


def FINANCIAL_ALL_COLS() -> list:
    return FINANCIAL_NUMERIC_COLS() + FINANCIAL_TEXT_COLS()


# 缓存: 避免每次写操作都重新推导
_fin_cols_cache = None


def _get_financial_cols_cached() -> tuple:
    global _fin_cols_cache
    if _fin_cols_cache is None:
        _fin_cols_cache = _get_dynamic_financial_cols()
    return _fin_cols_cache


def _reset_financial_cols_cache():
    """测试/热加载时清空缓存"""
    global _fin_cols_cache
    _fin_cols_cache = None

def _fin_col_defs():
    num, txt = _get_financial_cols_cached()
    defs = []
    for c in num:
        defs.append(f"{c} REAL DEFAULT NULL")
    for c in txt:
        defs.append(f"{c} TEXT DEFAULT NULL")
    return ", ".join(defs)


def _init_financial_table():
    conn = _get_conn()
    # 先确保表存在 (初始创建, 无字段约束)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS financial_indicators (
            stock_code TEXT NOT NULL,
            report_date TEXT NOT NULL,
            PRIMARY KEY (stock_code, report_date)
        )
    """)
    conn.commit()

    # 自动推导所有需要的列
    num, txt = _get_financial_cols_cached()
    all_expected = set(num + txt)

    # 检查现有列
    existing_cols = set()
    try:
        rows = conn.execute("PRAGMA table_info(financial_indicators)").fetchall()
        existing_cols = {r[1] for r in rows}
    except Exception:
        pass

    # 只补充缺少的列 (ALTER TABLE ADD COLUMN), 不 DROP 表
    missing = sorted(all_expected - existing_cols)
    if missing:
        for col in missing:
            col_type = "TEXT" if col in txt else "REAL"
            try:
                conn.execute(f"ALTER TABLE financial_indicators ADD COLUMN {col} {col_type} DEFAULT NULL")
                logger.info(f"[IndicatorStore] Added financial column: {col} ({col_type})")
            except Exception as e:
                logger.warning(f"[IndicatorStore] Failed to add column {col}: {e}")
        conn.commit()


def _safe_val(v: Any) -> Any:
    """SQLite 安全值转换 — dict/list 自动 JSON 序列化, 避免 'unsupported type' 错误"""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    if v is not None and not isinstance(v, (int, float, str, bytes)):
        return str(v)
    return v


def store_financial_indicator(code: str, report_date: str, data: dict) -> bool:
    """存储单只股票的财务指标快照 (upsert by stock_code+report_date)"""
    conn = _get_conn()
    _init_financial_table()
    num, txt = _get_financial_cols_cached()
    all_cols = num + txt
    try:
        existing = conn.execute(
            "SELECT 1 FROM financial_indicators WHERE stock_code=? AND report_date=?",
            [code, report_date]).fetchone()
        if existing:
            sets = ", ".join(f"{c}=?" for c in all_cols if c in data)
            vals = [_safe_val(data.get(c)) for c in all_cols if c in data]
            if sets:
                conn.execute(
                    f"UPDATE financial_indicators SET {sets} WHERE stock_code=? AND report_date=?",
                    vals + [code, report_date])
        else:
            cols = ["stock_code", "report_date"] + [c for c in all_cols if c in data]
            placeholders = ",".join("?" * len(cols))
            vals = [code, report_date] + [data.get(c) for c in all_cols if c in data]
            conn.execute(
                f"INSERT INTO financial_indicators ({','.join(cols)}) VALUES ({placeholders})", vals)
        conn.commit()
        return True
    except Exception as e:
        logger.warning(f"[FinStore] Upsert failed for {code}@{report_date}: {e}")
        return False


def get_financial_latest(code: str) -> Optional[dict]:
    """获取单只股票最新财务指标"""
    conn = _get_conn()
    _init_financial_table()
    row = conn.execute(
        "SELECT * FROM financial_indicators WHERE stock_code=? ORDER BY report_date DESC LIMIT 1",
        [code]).fetchone()
    return dict(row) if row else None


def get_financial_history(code: str, fields: List[str] = None) -> List[dict]:
    """获取单只股票财务指标历史序列"""
    conn = _get_conn()
    _init_financial_table()
    num, txt = _get_financial_cols_cached()
    all_cols = num + txt
    safe_fields = fields if fields else all_cols
    safe_fields = [f for f in safe_fields if f in all_cols and f not in ("stock_code", "report_date")]
    if not safe_fields:
        return []
    cols = ", ".join(safe_fields)
    rows = conn.execute(
        f"SELECT stock_code, report_date, {cols} FROM financial_indicators "
        f"WHERE stock_code=? ORDER BY report_date DESC",
        [code]).fetchall()
    return [dict(r) for r in rows]


def get_financial_field_latest(field_name: str) -> List[dict]:
    """获取全股票某财务指标字段的最新排名"""
    num, txt = _get_financial_cols_cached()
    if field_name not in (num + txt):
        return []
    conn = _get_conn()
    _init_financial_table()
    sql = f"""
        SELECT f.* FROM financial_indicators f
        INNER JOIN (
            SELECT stock_code, MAX(report_date) as max_date
            FROM financial_indicators WHERE {field_name} IS NOT NULL
            GROUP BY stock_code
        ) latest ON f.stock_code=latest.stock_code AND f.report_date=latest.max_date
        ORDER BY f.{field_name} DESC
    """
    rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]


def get_financial_coverage_batch(codes: List[str]) -> Dict[str, dict]:
    """批量查询财务指标覆盖: {code: {count, latest_date}}
    一次性查询全部 codes, 避免 N+1。"""
    if not codes:
        return {}
    conn = _get_conn()
    placeholders = ",".join("?" * len(codes))
    rows = conn.execute(
        f"SELECT stock_code, COUNT(*) as cnt, MAX(report_date) as max_d "
        f"FROM financial_indicators WHERE stock_code IN ({placeholders}) GROUP BY stock_code",
        codes
    ).fetchall()
    return {r["stock_code"]: {"count": r["cnt"], "latest": r["max_d"]} for r in rows}


def get_indicator_coverage_batch(codes: List[str]) -> Dict[str, dict]:
    """批量查询价量指标覆盖: {code: {count, latest_date}}"""
    if not codes:
        return {}
    conn = _get_conn()
    placeholders = ",".join("?" * len(codes))
    rows = conn.execute(
        f"SELECT stock_code, COUNT(*) as cnt, MAX(trade_date) as max_d "
        f"FROM indicators WHERE stock_code IN ({placeholders}) GROUP BY stock_code",
        codes
    ).fetchall()
    return {r["stock_code"]: {"count": r["cnt"], "latest": r["max_d"]} for r in rows}
