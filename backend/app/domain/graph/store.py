"""产业知识图谱 SQLite 存储 — 复用 observation_store 的 thread-local 模式"""
import sqlite3, os, threading, uuid, json
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from app.framework.logger import logger

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'data', 'graph.db')

_local = threading.local()

def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, 'graph_conn') or _local.graph_conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _local.graph_conn = sqlite3.connect(DB_PATH)
        _local.graph_conn.execute("PRAGMA journal_mode=WAL")
        _local.graph_conn.execute("PRAGMA synchronous=NORMAL")
        _local.graph_conn.row_factory = sqlite3.Row
    return _local.graph_conn

# ═══ DDL ═══

CREATE_NODES_SQL = """
CREATE TABLE IF NOT EXISTS graph_nodes (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    node_type TEXT NOT NULL,
    subtype TEXT,
    run_id TEXT NOT NULL,
    step TEXT,
    industry TEXT,
    level INTEGER,
    centrality REAL DEFAULT 0,
    severity TEXT,
    properties TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
)"""

CREATE_EDGES_SQL = """
CREATE TABLE IF NOT EXISTS graph_edges (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    run_id TEXT NOT NULL,
    step TEXT,
    weight REAL DEFAULT 1.0,
    properties TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES graph_nodes(id),
    FOREIGN KEY (target_id) REFERENCES graph_nodes(id)
)"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_gn_run ON graph_nodes(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_gn_type ON graph_nodes(node_type)",
    "CREATE INDEX IF NOT EXISTS idx_gn_industry ON graph_nodes(industry)",
    "CREATE INDEX IF NOT EXISTS idx_ge_run ON graph_edges(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_ge_source ON graph_edges(source_id)",
    "CREATE INDEX IF NOT EXISTS idx_ge_target ON graph_edges(target_id)",
    "CREATE INDEX IF NOT EXISTS idx_ge_type ON graph_edges(edge_type)",
]

def init_db():
    conn = _get_conn()
    conn.execute(CREATE_NODES_SQL)
    conn.execute(CREATE_EDGES_SQL)
    for idx in CREATE_INDEXES:
        conn.execute(idx)
    conn.commit()
    logger.info(f"[GraphStore] SQLite ready: {DB_PATH}")


class GraphStore:
    """图谱 CRUD — 纯数据存取, 无业务逻辑"""

    def __init__(self):
        init_db()

    # ── 写 ────────────────────────────────────────

    def save_graph(self, run_id: str, step: str, nodes: List[dict], edges: List[dict]):
        """批量保存节点+边, 幂等 (先删后插)"""
        conn = _get_conn()
        now = datetime.now().isoformat(timespec='seconds')

        # 删除该 run+step 的旧数据
        conn.execute("DELETE FROM graph_edges WHERE run_id=? AND step=?", [run_id, step])
        conn.execute("DELETE FROM graph_nodes WHERE run_id=? AND step=?", [run_id, step])

        # 写节点
        node_rows = []
        for n in nodes:
            node_rows.append((
                n.get('id', str(uuid.uuid4())),
                n.get('label', ''),
                n.get('node_type', 'unknown'),
                n.get('subtype'),
                run_id,
                step,
                n.get('industry'),
                n.get('level'),
                n.get('centrality', 0),
                n.get('severity'),
                json.dumps(n.get('properties', {}), ensure_ascii=False),
                now,
            ))
        if node_rows:
            conn.executemany("""INSERT OR REPLACE INTO graph_nodes
                (id, label, node_type, subtype, run_id, step, industry, level, centrality, severity, properties, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", node_rows)

        # 写边
        edge_rows = []
        for e in edges:
            edge_rows.append((
                e.get('id', str(uuid.uuid4())),
                e.get('source_id', ''),
                e.get('target_id', ''),
                e.get('edge_type', 'related'),
                run_id,
                step,
                e.get('weight', 1.0),
                json.dumps(e.get('properties', {}), ensure_ascii=False),
                now,
            ))
        if edge_rows:
            conn.executemany("""INSERT OR REPLACE INTO graph_edges
                (id, source_id, target_id, edge_type, run_id, step, weight, properties, created_at)
                VALUES (?,?,?,?,?,?,?,?,?)""", edge_rows)

        conn.commit()
        logger.info(f"[GraphStore] {run_id}/{step}: {len(node_rows)} nodes, {len(edge_rows)} edges saved")

    def delete_run(self, run_id: str):
        """清理整个 run 的图谱数据"""
        conn = _get_conn()
        conn.execute("DELETE FROM graph_edges WHERE run_id=?", [run_id])
        conn.execute("DELETE FROM graph_nodes WHERE run_id=?", [run_id])
        conn.commit()
        logger.info(f"[GraphStore] Deleted run: {run_id}")

    # ── 读 ────────────────────────────────────────

    def get_graph(self, run_id: str) -> Tuple[List[dict], List[dict]]:
        """获取完整图谱 (nodes + edges)"""
        conn = _get_conn()
        nodes = [dict(r) for r in conn.execute(
            "SELECT * FROM graph_nodes WHERE run_id=? ORDER BY level, label", [run_id]
        ).fetchall()]
        edges = [dict(r) for r in conn.execute(
            "SELECT * FROM graph_edges WHERE run_id=? ORDER BY edge_type", [run_id]
        ).fetchall()]
        # Parse JSON properties
        for n in nodes:
            if isinstance(n.get('properties'), str):
                n['properties'] = json.loads(n['properties'])
        for e in edges:
            if isinstance(e.get('properties'), str):
                e['properties'] = json.loads(e['properties'])
        return nodes, edges

    def get_node(self, node_id: str) -> Optional[dict]:
        conn = _get_conn()
        row = conn.execute("SELECT * FROM graph_nodes WHERE id=?", [node_id]).fetchone()
        if row:
            d = dict(row)
            if isinstance(d.get('properties'), str):
                d['properties'] = json.loads(d['properties'])
            return d
        return None

    def list_runs(self) -> List[dict]:
        """列出有图谱数据的 run (去重)"""
        conn = _get_conn()
        rows = conn.execute(
            "SELECT run_id, COUNT(DISTINCT node_type) type_count, MAX(created_at) updated_at FROM graph_nodes GROUP BY run_id ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_nodes_by_type(self, run_id: str, node_type: str) -> List[dict]:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM graph_nodes WHERE run_id=? AND node_type=? ORDER BY centrality DESC", [run_id, node_type]
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if isinstance(d.get('properties'), str):
                d['properties'] = json.loads(d['properties'])
            result.append(d)
        return result
