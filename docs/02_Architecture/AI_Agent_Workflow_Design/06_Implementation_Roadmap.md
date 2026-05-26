# 六、实施路线图

> 本文档定义 4 阶段实施计划、验收标准和风险评估。

---

## 6.1 总体时间线

```
Phase 1                Phase 2                Phase 3              Phase 4
基础补全               核心增量                前端升级              稳定收尾
(1-2周)               (1-2周)                (1周)                (1周)
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Step 3 重写   │  │ Step 9 新建   │  │ research.html│  │ 数据源修复    │
│ Step 4+5 重构 │  │ PipelineRunner│  │ pipeline.html│  │ E2E 测试     │
│ Step 7 增强   │  │ Checkpoint   │  │ 3个渲染块     │  │ 性能优化     │
│ Step 10 增强  │  │ TraceLogger  │  │ 追溯Tab       │  │ 报告质量评审  │
│ Step 11 模板  │  │ Pipeline API │  │ 侧边栏       │  │              │
│ DB 迁移       │  │ DAG 编排     │  │              │  │              │
└──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘

可选 Phase 5: V7.0 预埋 (2-3周)
┌──────────────┐
│ thesis CRUD   │
│ 指标录入      │
│ validation页  │
│ data.html升级 │
└──────────────┘
```

---

> **⚠️ 实施状态更新 (2026-05-26)**：Phase 1 部分完成（Step 2/3 已实现并优化至 V5.10/V5.9），Phase 2 Pipeline 基础设施 (checkpoint/trace/API) 已完成，CapitalFlowScanner (Step 1b) 已交付。宏观分析 (Step 1a) 已从 pipeline 中独立。SystemDynamicsAgent 和 ExpectationGapAgent 尚未实现。新架构为 12 步序列化 FULL_PIPELINE，取代原 DAG 设计。

## 6.2 Phase 1: 基础补全 (1-2 周)

### 6.2.1 任务清单

| # | 任务 | 文件 | 改动量 | 依赖 | 验证方式 |
|---|------|------|--------|------|---------|
| 1.1 | Step 3 Prompt 重写 | `supply_chain_hacker.py` | ~60行 | 无 | curl 单 Agent → 返回新字段 |
| 1.2 | Step 4+5 独立新建 | `system_dynamics_agent.py` ★ | ~200行 | 无 | curl 单独调用 → 非空输出 |
| 1.3 | Step 7 盈利释放判断 | `financial_auditor.py` | ~20行 | 无 | 输出含 earnings_release |
| 1.4 | Step 10 风险 Prompt 增强 | `dag_orchestrator.py` | ~10行 | 无 | 风险含概率/影响/定价 |
| 1.5 | Step 11 报告模板 +3 节 | `dag_orchestrator.py` | ~30行 | 1.1-1.4 | 报告含 8 节 |
| 1.6 | DB 迁移: pipeline_runs | `models.py` | ~40行 | 无 | 表创建成功 |
| 1.7 | DB 迁移: pipeline_steps | `models.py` | ~30行 | 无 | 表创建成功 |
| 1.8 | DB 迁移: report_registry 加字段 | `models.py` + SQL | ~10行 | 无 | ALTER 成功 |
| 1.9 | DB 迁移: thesis_records (V7.0 预埋) | `models.py` | ~30行 | 无 | 表创建成功 |
| 1.10 | DB 迁移: thesis_confidence_log (V7.0 预埋) | `models.py` | ~15行 | 无 | 表创建成功 |
| 1.11 | DB 迁移: industry_leading_indicators (V7.0 预埋) | `models.py` | ~20行 | 无 | 表创建成功 |

### 6.2.2 验收标准

```
✅ py_compile 全部修改文件通过
✅ curl Step 3 → 返回 profit_pool_share + pricing_power + supply_rigidity
✅ curl Step 4+5 (SystemDynamicsAgent 独立端点) → system_dynamics 不再输出空数组
✅ curl Step 7 → 返回 earnings_release.stage
✅ Step 11 报告含 8 节 (原 5 节 + 推演/预期差/验证)
✅ 5 张新表 + 1 张改造表在 DB 中存在 (含 V7.0 预埋 3 张)
```

### 6.2.3 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| Step 4+5 Prompt 质量差 | 中 | 推演输出空洞 | 用 3 个行业案例逐个调试 |
| LLM 输出格式不稳定 | 中 | JSON 解析失败 | 增强 parse_result 容错 |

---

## 6.3 Phase 2: 核心增量 (1-2 周)

### 6.3.1 任务清单

| # | 任务 | 文件 | 改动量 | 依赖 | 验证方式 |
|---|------|------|--------|------|---------|
| 2.1 | ExpectationGapAgent 新建 | `expectation_gap.py` ★ | ~150行 | Phase 1 | curl → 返回 gap_summary |
| 2.2 | DAG 编排接入 Step 9 | `dag_orchestrator.py` | ~5行 | 2.1 | Pipeline 含 Step 9 |
| 2.3 | PipelineRunner 新建 | `pipeline_runner.py` ★ | ~200行 | Phase 1 | run() 完整跑通 |
| 2.4 | CheckpointManager 新建 | `checkpoint.py` ★ | ~150行 | 无 | 文件正确生成 |
| 2.5 | TraceLogger 新建 | `trace_logger.py` ★ | ~100行 | 无 | .trace.txt 正确生成 |
| 2.6 | RunManifest 新建 | `manifest.py` ★ | ~80行 | 无 | manifest 正确记录 |
| 2.7 | Pipeline API 端点 | `api/research.py` | ~80行 | 2.3 | POST/GET 端点可用 |

### 6.3.2 验收标准

```
✅ ExpectationGapAgent 单独 curl → 返回完整 gap_summary
✅ Pipeline 端到端跑通 1 个行业 (如 CPU)
✅ 检查点文件正确生成 (data/pipeline_checkpoints/{run_id}/)
✅ .trace.txt 包含搜索查询 + LLM 调用 + 关键证据
✅ 失败恢复可用 (人为中断 → --resume 继续)
✅ Pipeline API: POST /pipeline/run → GET /pipeline/{run_id} 返回进度
✅ pipeline_runs + pipeline_steps 表有记录
```

### 6.3.3 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| Pipeline 耗时过长 (>15min) | 中 | 用户体验差 | Step 5 并行审计; 搜索超时控制 |
| 检查点数据量过大 | 低 | 磁盘占用 | 30天自动清理策略 |
| 跨 Step 数据传递出错 | 中 | Pipeline 中断 | 每步验证输出 Schema |

---

## 6.4 Phase 3: 前端升级 (1 周)

### 6.4.1 任务清单

| # | 任务 | 文件 | 改动量 | 依赖 | 验证方式 |
|---|------|------|--------|------|---------|
| 3.1 | Pipeline 运行面板 | `research.html` + JS | ~150行 | Phase 2 | 面板显示 7 步状态 |
| 3.2 | system_dynamics 渲染块 | `research.html` | ~80行 | Phase 1 | 报告显示推演章节 |
| 3.3 | expectation_gap 渲染块 | `research.html` | ~50行 | Phase 2 | 报告显示预期差表 |
| 3.4 | thesis_validation 渲染块 | `research.html` | ~40行 | Phase 1 | 报告显示论点验证 |
| 3.5 | 追溯 Tab | `research.html` | ~80行 | Phase 2 | Tab 切换显示 trace |
| 3.6 | pipeline.html | `pipeline.html` ★ | ~400行 | Phase 2 | 独立页面可访问 |
| 3.7 | 侧边栏更新 | `index.html` + 各页面 | ~10行 | 3.6 | 新入口可点击 |

### 6.4.2 验收标准

```
✅ Pipeline 面板实时更新 (8s 轮询)
✅ 完成时自动加载报告
✅ 失败时显示"从失败点继续"按钮
✅ 报告渲染新增 3 个章节 (推演/预期差/验证)
✅ 追溯 Tab 可查看每步 trace log
✅ pipeline.html 独立页面功能完整
✅ 侧边栏有 Pipeline 和论点验证入口
```

---

## 6.5 Phase 4: 稳定收尾 (1 周)

### 6.5.1 任务清单

| # | 任务 | 说明 | 依赖 |
|---|------|------|------|
| 4.1 | 修复 4 个 akshare 指标 | US_CPI_YOY / CN_CPI_YOY / US_ISM_PMI / DXY | 无 |
| 4.2 | E2E 测试: CPU 行业 | 完整 Pipeline 跑通 + 报告质量审阅 | Phase 1-3 |
| 4.3 | E2E 测试: SOFC 行业 | 不同行业验证泛化能力 | Phase 1-3 |
| 4.4 | E2E 测试: AI电力基础设施 | 验证长传导链行业 | Phase 1-3 |
| 4.5 | 性能优化 | 并行审计延迟; 搜索超时; LLM token 控制 | Phase 2 |
| 4.6 | Prompt 迭代 | 根据 3 份报告反馈优化 Step 3/4/9 prompt | 4.2-4.4 |
| 4.7 | 文档更新 | 更新 System_Feature_Inventory.md | 全部 |

### 6.5.2 验收标准

```
✅ 3 个行业 Pipeline 全部跑通 (CPU / SOFC / AI电力)
✅ 报告可读性 > 券商研报初稿水平
✅ 每个数字/判断可追溯到数据源 (通过 trace log)
✅ Pipeline 总耗时 < 10 分钟/行业
✅ 无 Python 未捕获异常
✅ 16/16 宏观指标全部入库
```

---

## 6.6 Phase 5: V7.0 预埋 (2-3 周, 已确认纳入)

### 6.6.1 任务清单

| # | 任务 | 文件 | 依赖 |
|---|------|------|------|
| 5.1 | thesis_records 表 + CRUD API | models.py + api | Phase 1 |
| 5.2 | thesis_confidence_log 表 + API | models.py + api | 5.1 |
| 5.3 | industry_leading_indicators 表 + 录入 API | models.py + api | 无 |
| 5.4 | validation.html 页面 | validation.html | 5.1-5.3 |
| 5.5 | data.html 宏观报告卡片 | data.html | Phase 1 |
| 5.6 | data.html 领先指标录入 | data.html | 5.3 |
| 5.7 | Pipeline 自动创建 thesis | pipeline_runner.py | 5.1 |

---

## 6.7 整体验收

### 6.7.1 功能验收

```
█ Pipeline 完整性
  ✅ 11 步 Pipeline 端到端跑通
  ✅ auto 模式 (Step1→Step2→自动选行业→深研)
  ✅ manual 模式 (用户指定行业→直接深研)
  ✅ 报告包含 8 大章节 (宏观/产业链/推演/审计/估值/预期差/风险/验证)

█ Pipeline 运营
  ✅ 逐 Step 检查点 (失败恢复)
  ✅ 追溯日志 (每步搜索+LLM+证据)
  ✅ Run 历史 (DB + 文件)
  ✅ 前端 Pipeline 面板 (实时进度)

█ 预期差分析
  ✅ ExpectationGapAgent 新建
  ✅ 市场共识 vs 我们的判断
  ✅ 拥挤度评估
  ✅ 催化剂时间线

█ 系统动力学推演
  ✅ 推演六步 + 十问 + 6 案例模板
  ✅ 资源迁移 / 瓶颈链 / 受损方 / 隐性受益者
  ✅ 相变预测 / 瓶颈迁移时间线
  ✅ scarcity_ranking 排序
```

### 6.7.2 质量验收

```
█ 报告质量
  ✅ 可读性 > 券商研报初稿水平
  ✅ 每个数字/判断可追溯到数据源
  ✅ LLM 幻觉可通过 trace log 发现
  ✅ 核心结论有程序化计算支撑 (非纯 LLM)

█ 差异化验证
  ✅ system_dynamics 输出非空且有洞察
  ✅ hidden_beneficiaries 至少发现 1 个隐性受益者
  ✅ scarcity_ranking 排序合理
  ✅ gap_summary 每维度有差异描述
```

### 6.7.3 工程验收

```
█ 代码质量
  ✅ py_compile 全部通过
  ✅ 向后兼容 (现有 API 不受影响)
  ✅ DDD 分层规范 (无跨层引用)
  ✅ 新增 6 文件 + 修改 6 文件

█ 数据完整性
  ✅ 5 张新表创建成功
  ✅ report_registry 加 3 字段
  ✅ 16/16 宏观指标入库
  ✅ 检查点/溯源文件正确生成

█ 性能
  ✅ Pipeline 耗时 < 10 分钟/行业
  ✅ 搜索超时控制 (单轮 < 30s)
  ✅ LLM 调用 < 15 次/Pipeline
```

---

## 6.8 变更影响总览

### 6.8.1 代码变更

| 类别 | 数量 | 详情 |
|------|------|------|
| 新建文件 | 6 | expectation_gap.py, pipeline_runner.py, checkpoint.py, trace_logger.py, manifest.py, pipeline.html |
| 修改文件 | 6 | supply_chain_hacker.py, dag_orchestrator.py, financial_auditor.py, valuation_pricer.py, models.py, research.html |
| 新建前端文件 | 3 | pipeline.html, validation.html, pipeline.css/js |
| **后端总行数** | **~1,125** | 新建 685 + 修改 440 |
| **前端总行数** | **~1,385** | |

### 6.8.2 不受影响的部分

```
✅ pipelines.py — Pipeline 注册表
✅ api/data.py — 数据中心 API (46KB)
✅ api/tasks.py — 任务 API
✅ api/positions.py — 持仓 API
✅ api/import_api.py — 导入 API
✅ framework/agents/base.py — BaseAgent
✅ framework/database/ — 数据库连接
✅ framework/providers/ — AI Provider
✅ domain/market_data/ — 行情数据领域
✅ domain/portfolio/ — 持仓领域
✅ domain/quant/ — 量化策略领域 (16 算子 + 8 策略)
✅ domain/strategy/ — 策略领域
✅ 全部现有 API 端点
✅ 全部现有数据库表 (仅 report_registry 加字段)
✅ indicators.db — 量化指标 SQLite
```

---

## 6.9 决策记录

| # | 决策 | 选项 | 选择 | 理由 |
|---|------|------|------|------|
| D1 | Step 4+5 实现位置 | 独立 Agent / 嵌入 SupplyChainHacker | **独立 Agent** ✅ | 可单独调试/测试, 符合单一职责 |
| D2 | 进度推送方式 | 8s 轮询 / WebSocket | **8s 轮询** ✅ | 延续现有架构, 简单可靠 |
| D3 | V7.0 预埋表时机 | 现在建 / V7.0 再建 | **现在预埋** ✅ | 方便后续直接使用, 无迁移成本 |
| D4 | Pipeline 执行模式 | 同步等待 / 异步任务 | 异步任务 | 耗时 5-10 分钟, 必须异步 |
| D5 | 检查点存储 | 文件系统 / DB | 文件系统 | JSON 输出较大, 文件更灵活 |
| D6 | 报告格式 | JSON / Markdown / 双格式 | JSON | 延续现有方案, 前端渲染 |
