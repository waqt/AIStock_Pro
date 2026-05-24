# Pipeline 运营设计 — 多场景 / 失败恢复 / 溯源

## 场景矩阵

| # | 场景 | 频率 | 核心问题 |
|---|------|------|---------|
| 1 | 每日全量跑 | 日频 | 多组报告如何组织？历史报告如何对比？ |
| 2 | 跑到一半失败 | 偶发 | 如何从失败点继续？已完成的步骤如何复用？ |
| 3 | 结论有问题 | 高频 | 如何溯源到具体步骤？哪个 Agent 的输出有问题？ |
| 4 | 改了一个 Agent 重跑 | 高频 | 只重跑受影响的步骤，不动已完成的 |
| 5 | 同一行业反复分析 | 高频 | 如何避免每次从头搜索+LLM？ |

---

## 一、报告组织结构

### 1.1 目录规范

```
backend/data/pipeline_checkpoints/
└── {YYYYMMDD}_{industry_slug}/           ← 一次完整分析 run
    ├── _run_manifest.json                ← 本次 run 的元信息
    ├── step1_macro_{hash}.json           ← Phase 0: 宏观报告 (通常复用, 不存在这里)
    ├── step2_gatekeeper_{hash}.json      ← Phase 0.5: Gatekeeper 输出
    ├── step3_sc_hacker_{hash}.json       ← Phase 1: SupplyChainHacker
    ├── step4_second_level_{hash}.json    ← Phase 1.8: 第二层思维
    ├── step5_dag_audits_{hash}.json      ← Phase 2: DAG 审计+定价
    ├── step11_report_{hash}.json         ← Phase 3: 最终报告
    └── _run_log.txt                      ← 全流程日志
```

### 1.2 Run Manifest

每次 run 一个 `_run_manifest.json`：

```json
{
  "run_id": "20260525_CPU_v2",
  "industry": "CPU",
  "started_at": "2026-05-25T10:00:00",
  "completed_at": "2026-05-25T10:05:30",
  "status": "completed",
  "steps": {
    "step2_gatekeeper": {"hash": "a1b2c3", "status": "completed", "elapsed": 45},
    "step3_sc_hacker":  {"hash": "d4e5f6", "status": "completed", "elapsed": 120},
    "step4_second_level":{"hash": "g7h8i9", "status": "completed", "elapsed": 60},
    "step5_dag_audits": {"hash": "j0k1l2", "status": "completed", "elapsed": 180},
    "step11_report":    {"hash": "m3n4o5", "status": "completed", "elapsed": 30}
  },
  "report_file": "data/research_reports/20260525_101000_CPU.json",
  "parent_run": null
}
```

### 1.3 报告注册表记录

每份报告在 `report_registry` 表中记录 `run_id`，可回溯到完整的检查点链。

```sql
ALTER TABLE report_registry ADD COLUMN run_id VARCHAR(50);
ALTER TABLE report_registry ADD COLUMN parent_run_id VARCHAR(50);
```

---

## 二、失败恢复机制

### 2.1 逐 Step 检查点

每个 Step 独立缓存。Runner 启动时扫描 manifest，跳过已完成的 Step，从第一个失败的 Step 继续。

```
伪代码:
def run_pipeline(industry, run_id, force_from=None):
    manifest = load_or_create_manifest(run_id)

    steps = [
        ("step2_gatekeeper", run_step2),
        ("step3_sc_hacker",  run_step3),
        ("step4_second_level", run_step4),
        ("step5_dag_audits", run_step5),
        ("step11_report",    run_step11),
    ]

    for step_name, step_func in steps:
        if force_from and step_name < force_from:
            continue  # 跳过 force_from 之前的步骤

        if manifest.steps[step_name].status == "completed":
            print(f"[SKIP] {step_name} — already done")
            continue

        try:
            result = await step_func(industry)
            save_checkpoint(step_name, run_id, result)
            manifest.steps[step_name].status = "completed"
        except Exception as e:
            manifest.steps[step_name].status = "failed"
            manifest.steps[step_name].error = str(e)
            save_manifest(manifest)
            raise  # 终止, 保留已完成的步骤
```

### 2.2 恢复场景

| 失败点 | 已缓存 | 恢复方式 |
|--------|--------|---------|
| Step 3 失败 | Step 2 已缓存 | 修复代码后 → `force_from="step3_sc_hacker"` |
| Step 5 失败 | Step 2-4 已缓存 | 修复后 → `force_from="step5_dag_audits"` |
| DeepSeek API 超时 | 本 Step 没缓存 | 重试本 Step, 前序步骤不变 |
| 代码 bug 导致输出错误 | 缓存了错误结果 | `--force` 跳过缓存, 从该 Step 重跑 |

### 2.3 缓存失效策略

两种触发条件：
- **输入变化**: `hash_input(input_data)` 改变 → 缓存自动不命中, 重跑
- **代码更新**: `force_from="step_name"` 手动指定
- **宏观数据过期**: Step1 macro_report.json `valid_until` 过期 → 整个 run 重新开始

---

## 三、溯源机制

### 3.1 从结论反向追溯到源头

```
报告 Section 3 说: "688041 海光信息 FAIL(-10分), 剪刀差-32%"
  ↑ 来自: step11_report.json → _synthesize_basic → audits[688041]
  ↑ 来自: step5_dag_audits.json → FinancialAuditor 输出
  ↑ 来自: step5 输入: 8Q 财务数据 + Beneish 计算
  ↑ 来自: DB financial_statements 表
  ↑ 数据原始值: 2026Q1 report_date, revenue=..., profit=...

如果分析师怀疑 "-10分" 判错了:
  1. 打开 step5_dag_audits.json → 找到 688041.audits[0].financial
  2. 查看 scissor.latest_gap_pct = -32.24, beneish.m_score = -1.64
  3. 对 FinancialAuditor 逻辑有疑问 → 查看 financial_auditor.py 的 scoring 规则
  4. 对原始数据有疑问 → 查看 DB financial_statements WHERE code='688041'
```

### 3.2 每个检查点的元信息

```json
{
  "step": "step5_dag_audits",
  "run_id": "20260525_CPU_v2",
  "input_hash": "a1b2c3d4e5f6",
  "input_summary": "codes=['688041','688047','688012']",
  "saved_at": "2026-05-25T10:03:00",
  "elapsed_seconds": 180,
  "code_version": "git:592fa59",       // ← 生成此结果的代码版本
  "provider": "deepseek-v4-pro",       // ← LLM 模型版本
  "output": { ... }
}
```

`code_version` 通过 `git rev-parse --short HEAD` 在 Pipeline 启动时获取。

---

## 四、操作命令

### 4.1 全新分析

```bash
# 完整跑 (首次)
python temp_lab/run_pipeline.py --industry CPU --run-id 20260525_CPU_v1

# 每日跑 (新 run_id, Step1 复用缓存)
python temp_lab/run_pipeline.py --industry CPU --run-id 20260526_CPU_v1
```

### 4.2 从中断点继续

```bash
# Step 3 崩溃后, 从 Step 3 重跑
python temp_lab/run_pipeline.py --industry CPU --run-id 20260525_CPU_v1 --resume

# 指定从某个 Step 强制重跑 (改了 prompt 想重跑 Step 2)
python temp_lab/run_pipeline.py --industry CPU --run-id 20260525_CPU_v1 --force-from step2_gatekeeper
```

### 4.3 溯源

```bash
# 列出某次 run 的所有步骤
python temp_lab/run_pipeline.py --run-id 20260525_CPU_v1 --list

# 查看某个 Step 的输出
python temp_lab/run_pipeline.py --run-id 20260525_CPU_v1 --inspect step5_dag_audits

# 打开某个检查点 JSON
cat backend/data/pipeline_checkpoints/20260525_CPU_v1/step5_dag_audits_a1b2c3.json
```

### 4.4 查看历史

```bash
# 列出所有 run
python temp_lab/run_pipeline.py --history

# 输出:
# 20260526_CPU_v1     completed  5/5 steps  305s  2026-05-26 09:00
# 20260525_CPU_v2     completed  5/5 steps  435s  2026-05-25 14:00
# 20260525_CPU_v1     failed     3/5 steps  200s  2026-05-25 10:00  (step4 timeout)
```

---

## 五、run_id 命名规范

```
{YYYYMMDD}_{industry_slug}_{version}

示例:
  20260525_CPU_v1        ← 5月25日第一次分析CPU
  20260525_CPU_v2        ← 同一天重跑 (修了代码想对比)
  20260526_SOFC_v1       ← 第二天分析SOFC
  20260526_CPU_v3        ← 第二天继续分析CPU
```

`run_id` 存储在:
- 检查点目录名
- `_run_manifest.json`
- `report_registry.run_id`

---

## 六、实现优先级

| 优先级 | 内容 | 改动 |
|--------|------|------|
| P0 | Run manifest + 逐 Step 检查点 | `framework/pipeline/checkpoint.py` 扩展 |
| P0 | 失败恢复 (`--resume` / `--force-from`) | `temp_lab/run_pipeline.py` |
| P0 | `run_id` 命名规范 + 目录组织 | 约定 |
| P1 | `report_registry` 加 `run_id` / `parent_run_id` | migration + model |
| P1 | `code_version` 记录 | checkpoint.py + git |
| P2 | 溯源命令 (`--inspect` / `--list` / `--history`) | run_pipeline.py |

---

## 七、与现有系统的关系

| 现有基础设施 | 关系 |
|-------------|------|
| `macro_report.json` (30天缓存) | 不属于 run 目录, 独立缓存。run manifest 中保存引用 |
| `report_registry` 表 | 每份投研报告记录 `run_id`, 可反向查到检查点目录 |
| `research_reports/*.json` | 最终报告仍落这里, manifest 中记录 `report_file` 路径 |
| `pipeline_checkpoints/` | 新目录, 每个 run 一个子目录 |
