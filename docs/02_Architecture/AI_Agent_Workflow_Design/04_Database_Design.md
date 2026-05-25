# 四、数据库表结构设计

> 本文档定义 V6.0 所需的 5 张新表 DDL、4 张现有表改造、数据流向和索引策略。

---

## 4.1 现有表总览

### 4.1.1 现有 14+1 张表 (保持不变)

| # | 表名 | 用途 | 记录数量级 | 变更 |
|---|------|------|-----------|------|
| 1 | `positions` | 当前持仓 | ~20 | 不变 |
| 2 | `market_data` | 日线行情 | ~500K | 不变 |
| 3 | `stock_info` | A+港股基础信息 | ~6K | 不变 |
| 4 | `financial_statements` | 季度财报 | ~50K | 不变 |
| 5 | `exchange_rates` | 汇率+宏观指数最新值 | ~20 | 不变 |
| 6 | `macro_history` | 宏观指标历史序列 | ~1K | 不变 |
| 7 | `report_registry` | 报告索引 | ~100 | ★ 加字段 |
| 8 | `task_definitions` | 任务注册表 | ~10 | 不变 |
| 9 | `task_executions` | 任务执行流水 | ~1K | 不变 |
| 10 | `trade_history` | 交易审计 | ~200 | 不变 |
| 11 | `watchlist` | 自选股 | ~50 | 不变 |
| 12 | `portfolio_snapshots` | 持仓快照 | ~5K | 不变 |
| 13 | `strategy_signals` | 策略信号 | ~10K | 不变 |
| 14 | `system_settings` | 系统配置 | ~5 | 不变 |
| S1 | SQLite: `indicators` | 量化指标宽表 (52列) | ~200K | 不变 |

---

## 4.2 新增表 (5 张)

### 4.2.1 `pipeline_runs` — Pipeline 运行记录

**用途**: 记录每次 Pipeline 运行的元信息, 支持历史查询和状态追踪。

```sql
CREATE TABLE pipeline_runs (
    -- 主键
    run_id              VARCHAR(80)   PRIMARY KEY 
                        COMMENT '运行标识, 如 20260525_CPU_v1',
    
    -- 基本信息
    industry            VARCHAR(80)   NOT NULL 
                        COMMENT '分析行业',
    mode                VARCHAR(20)   DEFAULT 'full' 
                        COMMENT '运行模式: full/quick/manual',
    stock_codes         JSON          NULL 
                        COMMENT '指定的股票代码列表 (可选)',
    
    -- 运行状态
    status              VARCHAR(20)   DEFAULT 'PENDING' 
                        COMMENT 'PENDING/RUNNING/COMPLETED/FAILED/CANCELLED',
    started_at          DATETIME      NOT NULL,
    completed_at        DATETIME      NULL,
    elapsed_seconds     INT           NULL 
                        COMMENT '总耗时(秒)',
    
    -- 步骤统计
    total_steps         INT           DEFAULT 0,
    completed_steps     INT           DEFAULT 0,
    failed_step         VARCHAR(50)   NULL 
                        COMMENT '失败的步骤名',
    error_message       TEXT          NULL 
                        COMMENT '错误信息',
    
    -- 关联
    report_id           VARCHAR(100)  NULL 
                        COMMENT '生成的报告 ID (关联 report_registry)',
    parent_run_id       VARCHAR(80)   NULL 
                        COMMENT '父 run (重跑时关联旧 run)',
    checkpoint_dir      VARCHAR(500)  NULL 
                        COMMENT '检查点目录路径',
    
    -- 环境信息
    code_version        VARCHAR(20)   NULL 
                        COMMENT 'git commit hash',
    provider_model      VARCHAR(80)   NULL 
                        COMMENT 'LLM 模型名称',
    
    -- 时间戳
    created_at          DATETIME      DEFAULT NOW()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 
  COMMENT='Pipeline 运行记录';

-- 索引
CREATE INDEX idx_pr_industry    ON pipeline_runs(industry);
CREATE INDEX idx_pr_status      ON pipeline_runs(status);
CREATE INDEX idx_pr_started     ON pipeline_runs(started_at);
```

**SQLAlchemy Model**:

```python
class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    run_id = Column(String(80), primary_key=True)
    industry = Column(String(80), nullable=False)
    mode = Column(String(20), default="full")
    stock_codes = Column(JSON, nullable=True)
    status = Column(String(20), default="PENDING")
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    elapsed_seconds = Column(Integer, nullable=True)
    total_steps = Column(Integer, default=0)
    completed_steps = Column(Integer, default=0)
    failed_step = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    report_id = Column(String(100), nullable=True)
    parent_run_id = Column(String(80), nullable=True)
    checkpoint_dir = Column(String(500), nullable=True)
    code_version = Column(String(20), nullable=True)
    provider_model = Column(String(80), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
```

---

### 4.2.2 `pipeline_steps` — Pipeline 步骤明细

**用途**: 记录 Pipeline 中每个步骤的执行状态和元信息, 支持细粒度溯源。

```sql
CREATE TABLE pipeline_steps (
    -- 主键
    id                  INT           AUTO_INCREMENT PRIMARY KEY,
    
    -- 关联
    run_id              VARCHAR(80)   NOT NULL 
                        COMMENT '关联 pipeline_runs',
    step_name           VARCHAR(50)   NOT NULL 
                        COMMENT '步骤名: step2_gatekeeper / step3_sc_hacker ...',
    step_order          INT           NOT NULL 
                        COMMENT '执行顺序 (1-based)',
    
    -- 执行状态
    status              VARCHAR(20)   DEFAULT 'PENDING' 
                        COMMENT 'PENDING/RUNNING/COMPLETED/FAILED/SKIPPED',
    started_at          DATETIME      NULL,
    completed_at        DATETIME      NULL,
    elapsed_seconds     INT           NULL,
    
    -- 数据指纹
    input_hash          VARCHAR(32)   NULL 
                        COMMENT '输入数据 MD5 (缓存命中判断)',
    output_hash         VARCHAR(32)   NULL 
                        COMMENT '输出数据 MD5',
    
    -- 文件路径
    checkpoint_file     VARCHAR(200)  NULL 
                        COMMENT '检查点 JSON 文件路径',
    trace_file          VARCHAR(200)  NULL 
                        COMMENT '追溯日志 .trace.txt 文件路径',
    
    -- 错误信息
    error_message       TEXT          NULL,
    
    -- LLM 使用
    provider_model      VARCHAR(80)   NULL 
                        COMMENT 'LLM 模型',
    token_usage         JSON          NULL 
                        COMMENT '{"prompt_tokens": 1200, "completion_tokens": 800}',
    search_count        INT           DEFAULT 0 
                        COMMENT '搜索次数',
    
    -- 约束
    FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id) ON DELETE CASCADE,
    UNIQUE KEY uq_run_step (run_id, step_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 
  COMMENT='Pipeline 步骤执行明细';
```

**SQLAlchemy Model**:

```python
class PipelineStep(Base):
    __tablename__ = "pipeline_steps"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(80), ForeignKey("pipeline_runs.run_id"), nullable=False)
    step_name = Column(String(50), nullable=False)
    step_order = Column(Integer, nullable=False)
    status = Column(String(20), default="PENDING")
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    elapsed_seconds = Column(Integer, nullable=True)
    input_hash = Column(String(32), nullable=True)
    output_hash = Column(String(32), nullable=True)
    checkpoint_file = Column(String(200), nullable=True)
    trace_file = Column(String(200), nullable=True)
    error_message = Column(Text, nullable=True)
    provider_model = Column(String(80), nullable=True)
    token_usage = Column(JSON, nullable=True)
    search_count = Column(Integer, default=0)
    
    __table_args__ = (UniqueConstraint('run_id', 'step_name', name='uq_run_step'),)
```

---

### 4.2.3 `thesis_records` — 投资论点追踪 (V7.0 预埋)

**用途**: 跨报告追踪投资论点的生命周期, 支持置信度变更和验证状态管理。

```sql
CREATE TABLE thesis_records (
    -- 主键
    thesis_id           VARCHAR(36)   PRIMARY KEY 
                        COMMENT 'UUID',
    
    -- 论点内容
    thesis              VARCHAR(500)  NOT NULL 
                        COMMENT '论点描述, 如 "HBM持续紧缺至2027"',
    industry            VARCHAR(80)   NOT NULL 
                        COMMENT '所属行业',
    category            VARCHAR(30)   NULL 
                        COMMENT '分类: supply_shortage/profit_migration/bottleneck/...',
    
    -- 来源
    source_run_id       VARCHAR(80)   NULL 
                        COMMENT '首次提出的 Pipeline run_id',
    source_step         VARCHAR(50)   NULL 
                        COMMENT '首次提出的步骤 (step4_system_dynamics)',
    
    -- 验证状态
    status              VARCHAR(20)   DEFAULT 'active' 
                        COMMENT 'active/validated/partially_validated/falsified/expired',
    confidence          INT           DEFAULT 50 
                        COMMENT '置信度 0-100',
    
    -- 验证要素
    leading_indicators  JSON          NULL 
                        COMMENT '领先指标列表: ["HBM现货价", "GPU交期(周)"]',
    falsification_signals JSON        NULL 
                        COMMENT '证伪信号: ["HBM价连续3月下跌"]',
    time_window         VARCHAR(50)   NULL 
                        COMMENT '预测时间窗: "6-18个月"',
    
    -- 验证历史
    last_validated      DATETIME      NULL 
                        COMMENT '上次验证时间',
    validation_notes    TEXT          NULL 
                        COMMENT '验证说明',
    
    -- 时间戳
    created_at          DATETIME      DEFAULT NOW(),
    updated_at          DATETIME      DEFAULT NOW() ON UPDATE NOW()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 
  COMMENT='投资论点追踪 (V7.0 预埋)';

CREATE INDEX idx_thesis_industry ON thesis_records(industry);
CREATE INDEX idx_thesis_status   ON thesis_records(status);
```

---

### 4.2.4 `thesis_confidence_log` — 论点置信度变更日志 (V7.0 预埋)

**用途**: 记录论点置信度的每一次变更, 形成历史趋势 (5月75%→8月60%→11月90%)。

```sql
CREATE TABLE thesis_confidence_log (
    id                  INT           AUTO_INCREMENT PRIMARY KEY,
    thesis_id           VARCHAR(36)   NOT NULL,
    confidence_old      INT           NOT NULL,
    confidence_new      INT           NOT NULL,
    reason              TEXT          NULL 
                        COMMENT '变更原因',
    source              VARCHAR(50)   NULL 
                        COMMENT '变更来源: manual/auto/pipeline',
    logged_at           DATETIME      DEFAULT NOW(),
    
    FOREIGN KEY (thesis_id) REFERENCES thesis_records(thesis_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 
  COMMENT='论点置信度变更日志 (V7.0 预埋)';

CREATE INDEX idx_tcl_thesis ON thesis_confidence_log(thesis_id);
```

---

### 4.2.5 `industry_leading_indicators` — 行业高频指标 (V7.0 预埋)

**用途**: 存储行业高频领先指标 (HBM价格/GPU交期/CoWoS交期等), 支持手动录入和未来自动采集。

```sql
CREATE TABLE industry_leading_indicators (
    id                  INT           AUTO_INCREMENT PRIMARY KEY,
    indicator_code      VARCHAR(50)   NOT NULL 
                        COMMENT '指标代码: HBM_SPOT_PRICE',
    indicator_name      VARCHAR(100)  NOT NULL 
                        COMMENT '指标名称: "HBM 现货价"',
    industry            VARCHAR(80)   NOT NULL 
                        COMMENT '所属行业',
    value               FLOAT         NOT NULL,
    unit                VARCHAR(20)   NULL 
                        COMMENT '单位: "美元/GB"',
    obs_date            DATE          NOT NULL 
                        COMMENT '观测日期',
    source              VARCHAR(50)   NULL 
                        COMMENT '数据来源: manual/api/web_scrape',
    notes               TEXT          NULL,
    created_at          DATETIME      DEFAULT NOW(),
    
    UNIQUE KEY uq_indicator_date (indicator_code, obs_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 
  COMMENT='行业高频领先指标 (V7.0 预埋)';

CREATE INDEX idx_ili_code     ON industry_leading_indicators(indicator_code);
CREATE INDEX idx_ili_industry ON industry_leading_indicators(industry);
```

---

## 4.3 现有表改造

### 4.3.1 `report_registry` — 新增 3 个字段

```sql
ALTER TABLE report_registry 
    ADD COLUMN run_id       VARCHAR(80) NULL 
        COMMENT 'Pipeline run 关联',
    ADD COLUMN parent_run_id VARCHAR(80) NULL 
        COMMENT '父 run (重跑时的旧 run)',
    ADD COLUMN version      INT DEFAULT 1 
        COMMENT '同行业报告版本号';

-- 索引
CREATE INDEX idx_rr_run_id ON report_registry(run_id);
```

**影响评估**: 无破坏性变更, 新字段均为 nullable, 现有代码不受影响。

---

## 4.4 数据流向图

```
                                Pipeline 运行时数据流
═════════════════════════════════════════════════════════════════════

[Step 1 启动]
    exchange_rates + macro_history ──读取──→ GlobalCapexScanner
                                             │
                                             ▼
                                    macro_report.json (文件缓存)
                                             │
[Step 2]                                     ▼
    exchange_rates ──────────────→ MarketScanner
                                             │
                                             ▼
[Step 3]                            pipeline_checkpoints/{run_id}/
    web_search ─────────────────→ SupplyChainHacker     step2_gatekeeper.json
                                             │          step2_gatekeeper.trace.txt
                                             ▼
[Step 4+5]                          pipeline_checkpoints/
    web_search ─────────────────→ SystemDynamics        step3_sc_hacker.json
                                             │
                                             ▼
[Step 7/8/9]                        pipeline_checkpoints/
    financial_statements ───────→ FinancialAuditor      step4_system_dynamics.json
    stock_info ─────────────────→ ValuationPricer       step5_dag_audits.json
    web_search ─────────────────→ ExpectationGapAgent   step9_expectation_gap.json
                                             │
                                             ▼
[Step 11]                           research_reports/
    所有前序输出 ────────────────→ ReportSynthesizer    20260525_CPU.json
                                             │
                                             ▼
                                    report_registry (DB)
                                    pipeline_runs (DB)
                                    pipeline_steps (DB)
```

---

## 4.5 索引策略

### 4.5.1 查询场景与索引映射

| 查询场景 | SQL 模式 | 使用索引 |
|---------|---------|---------|
| Pipeline 历史列表 | `WHERE status=? ORDER BY started_at DESC` | `idx_pr_status + idx_pr_started` |
| 按行业查看 Pipeline | `WHERE industry=?` | `idx_pr_industry` |
| 查看某 Run 的步骤 | `WHERE run_id=?` | `uq_run_step` (覆盖索引) |
| 按行业查看论点 | `WHERE industry=? AND status='active'` | `idx_thesis_industry + idx_thesis_status` |
| 查看指标历史 | `WHERE indicator_code=? ORDER BY obs_date` | `uq_indicator_date` |
| 报告关联 Pipeline | `WHERE run_id=?` | `idx_rr_run_id` |

### 4.5.2 数据量估算

| 表 | 初始量 | 月增量 | 1 年后 |
|---|--------|--------|--------|
| `pipeline_runs` | 0 | ~30 | ~360 |
| `pipeline_steps` | 0 | ~210 (30×7步) | ~2,520 |
| `thesis_records` | 0 | ~10 | ~120 |
| `thesis_confidence_log` | 0 | ~20 | ~240 |
| `industry_leading_indicators` | 0 | ~50 (手动) | ~600 |

> 数据量极小, 无需分区或特殊优化。

---

## 4.6 迁移策略

### 4.6.1 执行顺序

```
1. 先建新表 (pipeline_runs → pipeline_steps → thesis_records → 
   thesis_confidence_log → industry_leading_indicators)
2. 再改旧表 (ALTER report_registry ADD COLUMN ...)
3. 最后加索引

所有操作均为 ADD 操作, 不会影响现有数据。
```

### 4.6.2 回滚方案

```sql
-- 回滚: 删除新表 (按反向依赖顺序)
DROP TABLE IF EXISTS thesis_confidence_log;
DROP TABLE IF EXISTS thesis_records;
DROP TABLE IF EXISTS industry_leading_indicators;
DROP TABLE IF EXISTS pipeline_steps;
DROP TABLE IF EXISTS pipeline_runs;

-- 回滚: 删除新增字段
ALTER TABLE report_registry 
    DROP COLUMN IF EXISTS run_id,
    DROP COLUMN IF EXISTS parent_run_id,
    DROP COLUMN IF EXISTS version;
```

### 4.6.3 自动建表

由于项目使用 SQLAlchemy 的 `Base.metadata.create_all()` 自动建表, 新增 Model 后重启服务即可自动创建表结构。ALTER 语句需要手动执行或通过迁移脚本。
