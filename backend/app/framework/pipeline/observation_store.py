"""观察事件 SQLite 存储 — 与 indicators.db 同模式, 每字段一列"""
import sqlite3, os, threading, uuid
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from app.framework.logger import logger

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'observations.db')

# 全局连接 (线程本地, FastAPI 单线程模型安全)
_local = threading.local()

def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, 'obs_conn') or _local.obs_conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _local.obs_conn = sqlite3.connect(DB_PATH)
        _local.obs_conn.execute("PRAGMA journal_mode=WAL")
        _local.obs_conn.execute("PRAGMA synchronous=NORMAL")
        _local.obs_conn.row_factory = sqlite3.Row
    return _local.obs_conn

# ═══ 建表 DDL ═══════════════════════════════════

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY,
    source_step TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'industry',

    -- 核心内容
    title TEXT NOT NULL,
    description TEXT,
    category TEXT,

    -- 判断
    direction TEXT,
    confidence TEXT DEFAULT 'medium',

    -- 时间（绝对化）
    expected_date TEXT,
    window_description TEXT,
    window_start TEXT,
    window_end TEXT,

    -- 监控
    monitor_metric TEXT,
    trigger_threshold TEXT,
    data_source_hint TEXT,
    search_query TEXT,

    -- 关联
    related_stock_code TEXT,
    parent_id TEXT,
    industry TEXT,

    -- 扩展字段 (JSON)
    metadata TEXT,
    source_info TEXT,

    -- 生命周期
    status TEXT DEFAULT 'draft',
    activated_at TEXT,
    monitoring_at TEXT,
    triggered_at TEXT,
    confirmed_at TEXT,
    invalidated_at TEXT,
    expired_at TEXT,
    check_count INTEGER DEFAULT 0,
    notes TEXT,

    -- 元信息
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_obs_status ON observations(status)",
    "CREATE INDEX IF NOT EXISTS idx_obs_level ON observations(level)",
    "CREATE INDEX IF NOT EXISTS idx_obs_step ON observations(source_step)",
    "CREATE INDEX IF NOT EXISTS idx_obs_category ON observations(category)",
    "CREATE INDEX IF NOT EXISTS idx_obs_stock ON observations(related_stock_code)",
    "CREATE INDEX IF NOT EXISTS idx_obs_industry ON observations(industry)",
]

def init_db():
    """建表 + 索引 (幂等)"""
    conn = _get_conn()
    conn.execute(CREATE_TABLE_SQL)
    for idx in CREATE_INDEXES:
        conn.execute(idx)
    conn.commit()
    logger.info(f"[ObservationStore] SQLite ready: {DB_PATH}")


class ObservationStore:
    """观察事件 CRUD — 纯数据存取, 无业务逻辑"""

    def __init__(self):
        init_db()

    # ── 写操作 ─────────────────────────────────────

    @staticmethod
    def _normalize(obs: dict) -> dict:
        """确保字段存在、时间标准化"""
        now = datetime.now().isoformat(timespec='seconds')
        row = {
            'id': obs.get('id', str(uuid.uuid4())),
            'source_step': obs.get('source_step', ''),
            'level': obs.get('level', 'industry'),
            'title': obs.get('title', ''),
            'description': obs.get('description'),
            'category': obs.get('category'),
            'direction': obs.get('direction'),
            'confidence': obs.get('confidence', 'medium'),
            'expected_date': obs.get('expected_date'),
            'window_description': obs.get('window_description'),
            'window_start': obs.get('window_start'),
            'window_end': obs.get('window_end'),
            'monitor_metric': obs.get('monitor_metric'),
            'trigger_threshold': obs.get('trigger_threshold'),
            'data_source_hint': obs.get('data_source_hint'),
            'search_query': obs.get('search_query'),
            'related_stock_code': obs.get('related_stock_code'),
            'parent_id': obs.get('parent_id'),
            'industry': obs.get('industry'),
            'metadata': obs.get('metadata'),
            'source_info': obs.get('source_info'),
            'status': obs.get('status', 'draft'),
            'activated_at': obs.get('activated_at'),
            'monitoring_at': obs.get('monitoring_at'),
            'triggered_at': obs.get('triggered_at'),
            'confirmed_at': obs.get('confirmed_at'),
            'invalidated_at': obs.get('invalidated_at'),
            'expired_at': obs.get('expired_at'),
            'check_count': obs.get('check_count', 0),
            'notes': obs.get('notes'),
            'created_at': obs.get('created_at', now),
            'updated_at': now,
        }
        return row

    def save_batch(self, observations: List[dict]) -> List[str]:
        """批量保存观察事件, 返回 id 列表"""
        conn = _get_conn()
        ids = []
        rows = []
        for obs in observations:
            row = self._normalize(obs)
            ids.append(row['id'])
            rows.append((
                row['id'], row['source_step'], row['level'],
                row['title'], row['description'], row['category'],
                row['direction'], row['confidence'],
                row['expected_date'], row['window_description'],
                row['window_start'], row['window_end'],
                row['monitor_metric'], row['trigger_threshold'],
                row['data_source_hint'], row['search_query'],
                row['related_stock_code'], row['parent_id'], row['industry'],
                row['metadata'], row['source_info'],
                row['status'],
                row['activated_at'], row['monitoring_at'],
                row['triggered_at'], row['confirmed_at'],
                row['invalidated_at'], row['expired_at'],
                row['check_count'], row['notes'],
                row['created_at'], row['updated_at'],
            ))
        sql = """INSERT OR REPLACE INTO observations (
            id, source_step, level,
            title, description, category,
            direction, confidence,
            expected_date, window_description,
            window_start, window_end,
            monitor_metric, trigger_threshold,
            data_source_hint, search_query,
            related_stock_code, parent_id, industry,
            metadata, source_info,
            status,
            activated_at, monitoring_at,
            triggered_at, confirmed_at,
            invalidated_at, expired_at,
            check_count, notes,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        conn.executemany(sql, rows)
        conn.commit()
        logger.debug(f"[ObservationStore] saved {len(rows)} observations")
        return ids

    def update_status(self, obs_id: str, status: str, **extra_fields):
        """更新观察状态及对应时间戳 (自动设 activated_at/monitoring_at 等)"""
        conn = _get_conn()
        now = datetime.now().isoformat(timespec='seconds')
        status_timestamp_map = {
            'active': 'activated_at',
            'monitoring': 'monitoring_at',
            'triggered': 'triggered_at',
            'confirmed': 'confirmed_at',
            'invalidated': 'invalidated_at',
            'expired': 'expired_at',
        }
        sets = ["status=?", "updated_at=?"]
        vals = [status, now]
        ts_col = status_timestamp_map.get(status)
        if ts_col:
            sets.append(f"{ts_col}=COALESCE({ts_col}, ?)")
            vals.append(now)
        for k, v in extra_fields.items():
            if k in ('check_count', 'notes', 'description', 'category'):
                sets.append(f"{k}=?")
                vals.append(v)
        vals.append(obs_id)
        conn.execute(f"UPDATE observations SET {', '.join(sets)} WHERE id=?", vals)
        conn.commit()
        logger.info(f"[ObservationStore] {obs_id} → {status}")

    # ── 读操作 ─────────────────────────────────────

    def get(self, obs_id: str) -> Optional[dict]:
        """获取单条观察"""
        conn = _get_conn()
        row = conn.execute("SELECT * FROM observations WHERE id=?", [obs_id]).fetchone()
        return dict(row) if row else None

    def list(self, run_id: str = None, status: str = None, level: str = None,
             source_step: str = None, category: str = None,
             stock_code: str = None, industry: str = None,
             limit: int = 200, offset: int = 0) -> List[dict]:
        """筛选查询 — 所有条件 AND"""
        conn = _get_conn()
        clauses = []
        params = []

        if run_id:
            clauses.append("source_info LIKE ?")
            params.append(f'%{run_id}%')
        if status:
            clauses.append("status=?")
            params.append(status)
        if level:
            clauses.append("level=?")
            params.append(level)
        if source_step:
            clauses.append("source_step=?")
            params.append(source_step)
        if category:
            if '/' in category:
                clauses.append("category LIKE ?")
                params.append(f"{category}%")
            else:
                clauses.append("category=?")
                params.append(category)
        if stock_code:
            clauses.append("related_stock_code=?")
            params.append(stock_code)
        if industry:
            clauses.append("industry=?")
            params.append(industry)

        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        sql = f"SELECT * FROM observations {where} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_by_stock(self, stock_code: str, status: str = None) -> List[dict]:
        """特定股票的观察 (按时间倒序)"""
        return self.list(stock_code=stock_code, status=status, limit=100)

    def get_by_industry(self, industry_name: str, status: str = None) -> List[dict]:
        """特定行业的观察"""
        return self.list(industry=industry_name, status=status, limit=100)

    def count(self, status: str = None, level: str = None) -> int:
        """统计观察数量"""
        conn = _get_conn()
        clauses = []
        params = []
        if status:
            clauses.append("status=?")
            params.append(status)
        if level:
            clauses.append("level=?")
            params.append(level)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        return conn.execute(f"SELECT COUNT(*) FROM observations {where}", params).fetchone()[0]

    def get_expired_list(self) -> List[dict]:
        """获取所有 window_end 已过期的 active 观察"""
        conn = _get_conn()
        today = date.today().isoformat()
        rows = conn.execute(
            "SELECT * FROM observations WHERE status IN ('active','monitoring') AND window_end IS NOT NULL AND window_end < ? ORDER BY window_end ASC",
            [today]).fetchall()
        return [dict(r) for r in rows]

    def find_ids_by_run(self, run_id: str) -> set:
        """查找指定 run_id 已入库的观察 (title + step + industry 三元组)"""
        conn = _get_conn()
        rows = conn.execute(
            "SELECT title, source_step, industry FROM observations WHERE source_info LIKE ?",
            [f'%{run_id}%']
        ).fetchall()
        return {(r['title'], r['source_step'], r['industry'] or '') for r in rows}
