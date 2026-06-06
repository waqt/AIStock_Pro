"""监控计划 + 信号事件 — SQLite DDL"""

MONITOR_PLANS_DDL = """
CREATE TABLE IF NOT EXISTS monitor_plans (
    id TEXT PRIMARY KEY,

    -- 计划名称/描述
    name TEXT NOT NULL,
    description TEXT,

    -- 关联溯源 (从哪份研报/观察来的)
    source_report_id TEXT,
    source_run_id TEXT,
    source_step TEXT,
    linked_observation_id TEXT,
    source_summary TEXT,

    -- 监控目标
    level TEXT NOT NULL DEFAULT 'stock',
    target_industry TEXT,
    target_stock_code TEXT,
    target_stock_name TEXT,

    -- ═══ 监控协议 ═══
    -- JSON array: [{"engine":"brave","query":"...","interval_days":7,"lang":"zh"}]
    search_config TEXT NOT NULL DEFAULT '[]',

    -- LLM instruction: 怎么判断"命中"
    trigger_instruction TEXT,

    -- 关键词辅助
    positive_keywords TEXT DEFAULT '[]',
    negative_keywords TEXT DEFAULT '[]',
    min_match_count INTEGER DEFAULT 1,

    -- 行业级联到个股
    cascade_to_stocks TEXT DEFAULT '[]',

    -- ═══ 信号配置 ═══
    signal_direction TEXT DEFAULT 'buy',
    signal_strength TEXT DEFAULT 'medium',
    cooldown_days INTEGER DEFAULT 30,

    -- ═══ 执行配置 ═══
    check_interval_hours INTEGER DEFAULT 168,
    status TEXT DEFAULT 'draft',

    -- ═══ 执行统计 ═══
    total_checks INTEGER DEFAULT 0,
    last_check_at TEXT,
    last_triggered_at TEXT,

    -- ═══ 元信息 ═══
    created_by TEXT DEFAULT 'manual',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    notes TEXT
)
"""

SIGNAL_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS signal_events (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    plan_name TEXT,

    -- 触发信息
    triggered_at TEXT NOT NULL,
    signal_direction TEXT NOT NULL,
    signal_strength TEXT NOT NULL,
    confidence TEXT DEFAULT 'medium',
    title TEXT NOT NULL,
    description TEXT,

    -- 证据 (JSON array)
    evidence TEXT NOT NULL DEFAULT '[]',

    -- 关联
    related_stock_code TEXT,
    related_stock_name TEXT,
    target_industry TEXT,

    -- 状态
    status TEXT DEFAULT 'pending_review',
    reviewed_by TEXT,
    reviewed_at TEXT,
    acted_at TEXT,
    notes TEXT,

    created_at TEXT NOT NULL
)
"""

MONITOR_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_signal_plan_id ON signal_events(plan_id)",
    "CREATE INDEX IF NOT EXISTS idx_signal_status ON signal_events(status)",
    "CREATE INDEX IF NOT EXISTS idx_signal_stock ON signal_events(related_stock_code)",
    "CREATE INDEX IF NOT EXISTS idx_signal_industry ON signal_events(target_industry)",
    "CREATE INDEX IF NOT EXISTS idx_plan_status ON monitor_plans(status)",
    "CREATE INDEX IF NOT EXISTS idx_plan_level ON monitor_plans(level)",
    "CREATE INDEX IF NOT EXISTS idx_plan_stock ON monitor_plans(target_stock_code)",
    "CREATE INDEX IF NOT EXISTS idx_plan_industry ON monitor_plans(target_industry)",
]
