"""MonitorStore — 监控计划 + 信号事件 SQLite CRUD

使用与 ObservationStore 相同的 observations.db, 但管理独立的表。
"""
import sqlite3, os, threading, uuid, json
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from app.framework.logger import logger
from .models import MONITOR_PLANS_DDL, SIGNAL_EVENTS_DDL, MONITOR_INDEXES

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'data', 'observations.db')

_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, 'mon_conn') or _local.mon_conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _local.mon_conn = sqlite3.connect(DB_PATH)
        _local.mon_conn.execute("PRAGMA journal_mode=WAL")
        _local.mon_conn.execute("PRAGMA synchronous=NORMAL")
        _local.mon_conn.row_factory = sqlite3.Row
    return _local.mon_conn


def init_db():
    """建表 + 索引 (幂等)"""
    conn = _get_conn()
    conn.execute(MONITOR_PLANS_DDL)
    conn.execute(SIGNAL_EVENTS_DDL)
    for idx in MONITOR_INDEXES:
        conn.execute(idx)
    conn.commit()
    logger.info(f"[MonitorStore] SQLite tables ready: monitor_plans + signal_events")


class MonitorStore:
    """监控计划 + 信号事件 CRUD"""

    def __init__(self):
        init_db()

    # ═══ 监控计划 CRUD ═══════════════════════════

    @staticmethod
    def _normalize_plan(p: dict) -> dict:
        now = datetime.now().isoformat(timespec='seconds')
        row = {
            'id': p.get('id', str(uuid.uuid4())),
            'name': p.get('name', ''),
            'description': p.get('description'),
            'source_report_id': p.get('source_report_id'),
            'source_run_id': p.get('source_run_id'),
            'source_step': p.get('source_step'),
            'linked_observation_id': p.get('linked_observation_id'),
            'source_summary': p.get('source_summary'),
            'level': p.get('level', 'stock'),
            'target_industry': p.get('target_industry'),
            'target_stock_code': p.get('target_stock_code'),
            'target_stock_name': p.get('target_stock_name'),
            'search_config': p.get('search_config', '[]'),
            'trigger_instruction': p.get('trigger_instruction'),
            'positive_keywords': p.get('positive_keywords', '[]'),
            'negative_keywords': p.get('negative_keywords', '[]'),
            'min_match_count': p.get('min_match_count', 1),
            'cascade_to_stocks': p.get('cascade_to_stocks', '[]'),
            'signal_direction': p.get('signal_direction', 'buy'),
            'signal_strength': p.get('signal_strength', 'medium'),
            'cooldown_days': p.get('cooldown_days', 30),
            'check_interval_hours': p.get('check_interval_hours', 168),
            'status': p.get('status', 'draft'),
            'total_checks': p.get('total_checks', 0),
            'last_check_at': p.get('last_check_at'),
            'last_triggered_at': p.get('last_triggered_at'),
            'created_by': p.get('created_by', 'manual'),
            'created_at': p.get('created_at', now),
            'updated_at': now,
            'notes': p.get('notes'),
        }
        return row

    def save_plan(self, plan: dict) -> str:
        """保存/更新单个监控计划"""
        conn = _get_conn()
        row = self._normalize_plan(plan)
        sql = """INSERT OR REPLACE INTO monitor_plans (
            id, name, description,
            source_report_id, source_run_id, source_step, linked_observation_id,
            source_summary, level,
            target_industry, target_stock_code, target_stock_name,
            search_config, trigger_instruction,
            positive_keywords, negative_keywords, min_match_count,
            cascade_to_stocks,
            signal_direction, signal_strength, cooldown_days,
            check_interval_hours, status,
            total_checks, last_check_at, last_triggered_at,
            created_by, created_at, updated_at, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        conn.execute(sql, [
            row['id'], row['name'], row['description'],
            row['source_report_id'], row['source_run_id'], row['source_step'],
            row['linked_observation_id'], row['source_summary'], row['level'],
            row['target_industry'], row['target_stock_code'], row['target_stock_name'],
            row['search_config'], row['trigger_instruction'],
            row['positive_keywords'], row['negative_keywords'], row['min_match_count'],
            row['cascade_to_stocks'],
            row['signal_direction'], row['signal_strength'], row['cooldown_days'],
            row['check_interval_hours'], row['status'],
            row['total_checks'], row['last_check_at'], row['last_triggered_at'],
            row['created_by'], row['created_at'], row['updated_at'], row['notes'],
        ])
        conn.commit()
        return row['id']

    def save_plans_batch(self, plans: List[dict]) -> List[str]:
        """批量保存监控计划"""
        return [self.save_plan(p) for p in plans]

    def get_plan(self, plan_id: str) -> Optional[dict]:
        conn = _get_conn()
        row = conn.execute("SELECT * FROM monitor_plans WHERE id=?", [plan_id]).fetchone()
        return dict(row) if row else None

    def list_plans(self, status: str = None, level: str = None,
                   stock_code: str = None, industry: str = None,
                   limit: int = 100, offset: int = 0) -> List[dict]:
        conn = _get_conn()
        clauses = []
        params = []
        if status:
            clauses.append("status=?")
            params.append(status)
        if level:
            clauses.append("level=?")
            params.append(level)
        if stock_code:
            clauses.append("target_stock_code=?")
            params.append(stock_code)
        if industry:
            clauses.append("target_industry=?")
            params.append(industry)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        sql = f"SELECT * FROM monitor_plans {where} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def update_plan_status(self, plan_id: str, status: str, **extra):
        """更新监控计划状态 + 可选字段"""
        conn = _get_conn()
        now = datetime.now().isoformat(timespec='seconds')
        sets = ["status=?", "updated_at=?"]
        vals = [status, now]
        for k, v in extra.items():
            if k in ('total_checks', 'last_check_at', 'last_triggered_at', 'notes',
                     'search_config', 'trigger_instruction', 'check_interval_hours'):
                sets.append(f"{k}=?")
                vals.append(v)
        vals.append(plan_id)
        conn.execute(f"UPDATE monitor_plans SET {', '.join(sets)} WHERE id=?", vals)
        conn.commit()

    def delete_plan(self, plan_id: str):
        """删除监控计划 (级联删除信号事件)"""
        conn = _get_conn()
        conn.execute("DELETE FROM signal_events WHERE plan_id=?", [plan_id])
        conn.execute("DELETE FROM monitor_plans WHERE id=?", [plan_id])
        conn.commit()

    def count_plans(self, status: str = None) -> int:
        conn = _get_conn()
        clauses, params = [], []
        if status:
            clauses.append("status=?")
            params.append(status)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        return conn.execute(f"SELECT COUNT(*) FROM monitor_plans {where}", params).fetchone()[0]

    # ═══ 信号事件 CRUD ═══════════════════════════

    @staticmethod
    def _normalize_signal(s: dict) -> dict:
        now = datetime.now().isoformat(timespec='seconds')
        row = {
            'id': s.get('id', str(uuid.uuid4())),
            'plan_id': s.get('plan_id', ''),
            'plan_name': s.get('plan_name'),
            'triggered_at': s.get('triggered_at', now),
            'signal_direction': s.get('signal_direction', 'neutral'),
            'signal_strength': s.get('signal_strength', 'medium'),
            'confidence': s.get('confidence', 'medium'),
            'title': s.get('title', ''),
            'description': s.get('description'),
            'evidence': s.get('evidence', '[]'),
            'related_stock_code': s.get('related_stock_code'),
            'related_stock_name': s.get('related_stock_name'),
            'target_industry': s.get('target_industry'),
            'status': s.get('status', 'pending_review'),
            'reviewed_by': s.get('reviewed_by'),
            'reviewed_at': s.get('reviewed_at'),
            'acted_at': s.get('acted_at'),
            'notes': s.get('notes'),
            'created_at': s.get('created_at', now),
        }
        return row

    def save_signal(self, signal: dict) -> str:
        """保存单个信号事件"""
        conn = _get_conn()
        row = self._normalize_signal(signal)
        sql = """INSERT OR REPLACE INTO signal_events (
            id, plan_id, plan_name,
            triggered_at, signal_direction, signal_strength, confidence,
            title, description, evidence,
            related_stock_code, related_stock_name, target_industry,
            status, reviewed_by, reviewed_at, acted_at, notes,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        conn.execute(sql, [
            row['id'], row['plan_id'], row['plan_name'],
            row['triggered_at'], row['signal_direction'], row['signal_strength'],
            row['confidence'], row['title'], row['description'], row['evidence'],
            row['related_stock_code'], row['related_stock_name'], row['target_industry'],
            row['status'], row['reviewed_by'], row['reviewed_at'], row['acted_at'],
            row['notes'], row['created_at'],
        ])
        conn.commit()
        return row['id']

    def save_signals_batch(self, signals: List[dict]) -> List[str]:
        """批量保存信号事件"""
        return [self.save_signal(s) for s in signals]

    def get_signal(self, signal_id: str) -> Optional[dict]:
        conn = _get_conn()
        row = conn.execute("SELECT * FROM signal_events WHERE id=?", [signal_id]).fetchone()
        return dict(row) if row else None

    def list_signals(self, plan_id: str = None, status: str = None,
                     stock_code: str = None, industry: str = None,
                     direction: str = None, limit: int = 100, offset: int = 0) -> List[dict]:
        conn = _get_conn()
        clauses = []
        params = []
        if plan_id:
            clauses.append("plan_id=?")
            params.append(plan_id)
        if status:
            clauses.append("status=?")
            params.append(status)
        if stock_code:
            clauses.append("related_stock_code=?")
            params.append(stock_code)
        if industry:
            clauses.append("target_industry=?")
            params.append(industry)
        if direction:
            clauses.append("signal_direction=?")
            params.append(direction)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        sql = f"SELECT * FROM signal_events {where} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def update_signal_status(self, signal_id: str, status: str, **extra):
        """更新信号状态"""
        conn = _get_conn()
        now = datetime.now().isoformat(timespec='seconds')
        sets = ["status=?"]
        vals = [status]
        if status == 'confirmed':
            sets.append("reviewed_at=COALESCE(reviewed_at, ?)")
            vals.append(now)
        elif status == 'dismissed':
            sets.append("reviewed_at=COALESCE(reviewed_at, ?)")
            vals.append(now)
        for k, v in extra.items():
            if k in ('reviewed_by', 'notes', 'acted_at'):
                sets.append(f"{k}=?")
                vals.append(v)
        vals.append(signal_id)
        conn.execute(f"UPDATE signal_events SET {', '.join(sets)} WHERE id=?", vals)
        conn.commit()

    # ═══ 统计 ═══════════════════════════════════

    def count_signals(self, status: str = None, direction: str = None) -> int:
        conn = _get_conn()
        clauses, params = [], []
        if status:
            clauses.append("status=?")
            params.append(status)
        if direction:
            clauses.append("signal_direction=?")
            params.append(direction)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        return conn.execute(f"SELECT COUNT(*) FROM signal_events {where}", params).fetchone()[0]

    def get_due_plans(self) -> List[dict]:
        """获取到该执行检查的 active 计划"""
        conn = _get_conn()
        rows = conn.execute(
            """SELECT * FROM monitor_plans
               WHERE status='active'
               AND (last_check_at IS NULL
                    OR datetime(last_check_at, '+' || check_interval_hours || ' hours') <= datetime('now'))
               ORDER BY last_check_at ASC"""
        ).fetchall()
        return [dict(r) for r in rows]

    def get_expired_plans(self) -> List[dict]:
        """获取已过期（不再需要监控）的计划 — 留空逻辑，给业务方决定"""
        # 暂不实现自动过期，由用户手动 archive
        return []
