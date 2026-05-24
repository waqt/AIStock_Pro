# 量化指标体系 — 架构总结

> 基于 V5.X 迭代实战经验提炼。新增指标或修改计算逻辑时必读。

---

## 一、分层架构

```
┌─ 定义层 ─────────────────────────────────────────────┐
│ indicators/<category>/<name>.py                      │
│   @register + BaseIndicator                          │
│   name / label / output / requires / params / compute│
│   纯函数, 零 I/O, 向量化                              │
├─ 计算层 ─────────────────────────────────────────────┤
│ indicator_runner.py                                  │
│   _run_indicators (快照) / _run_indicators_full (历史)│
│   三轮处理 + ctx 上下文传递                            │
│   Series-of-object 识别 (list/dict 不进 all_series)   │
├─ 存储层 ─────────────────────────────────────────────┤
│ indicator_store.py (SQLite 宽表)                     │
│   每指标一列, 50+ 列数值 + 5 列文本                    │
│   upsert_rows: 全量=executemany / 部分=SELECT+executemany│
├─ 调度层 ─────────────────────────────────────────────┤
│ tasks.py → calculate_indicators_task                 │
│   参数: target_codes / mode / indicator_names         │
│   async create_task → semaphore 控制并发              │
├─ API 层 ─────────────────────────────────────────────┤
│ indicators.py: registry / compute / history / coverage│
│ data.py: alt/overview / alt/crowding/*                │
└─ 前端 ───────────────────────────────────────────────┤
│ indicator_compute.js — 统一组件                       │
│   render('id') / openModal(params) / submit(params)   │
└──────────────────────────────────────────────────────┘
```

---

## 二、四个设计准则

### 1. 单一真相源

- **指标注册表**：只有 `indicators/__init__.py` → `INDICATOR_REGISTRY`。删掉了旧 `engine/indicators.py` 和 `app/quant/indicators.py` 两套冗余注册表。
- **股票范围**：`Position ∪ WatchlistItem`。所有计算入口（任务、API、覆盖检测）统一从这个并集取值。
- **存储 schema**：`indicator_store.ALL_COLS` 是唯一字段定义。新增字段改这里 + 重建表（DROP/CREATE，SQLite 零成本）。
- **前端入口**：`IndicatorCompute` 是唯一触发组件。quant.html / alt.js / health.js 都通过它。

### 2. 新增指标不改 DDL

- 新指标只需写一个 `<name>.py`，加 `@register`，放对应分类目录。
- `output` 字段名全系统唯一。如果跟已有字段冲突，编译阶段就能发现。
- 新字段写入 SQLite 时，旧行自动 NULL，局部重算即可补齐。
- **不要**用 JSON blob。每个字段独立一列，时间序列查询直接是 DataFrame。

### 3. 持久化安全

- **全量重算**（无 indicator_names）→ `DELETE` + `executemany INSERT`。
- **部分重算**（指定 indicator_names）→ `SELECT` 读现有行 → 内存合并 → `executemany INSERT OR REPLACE`。**绝不删旧数据**。
- 快照模式同理：全量覆盖今天行，部分只 UPDATE 指定列（`ON CONFLICT DO UPDATE SET`）。

### 4. 可观测性

- `GET /quant/indicators/coverage` — 每只股票的指标天数 + 缺失字段列表。
- `GET /quant/indicators/registry` — 所有已注册指标（含中文 label）。
- `GET /data/health/overview` — `indicators_coverage` 汇总数字。
- 前端覆盖率直观展示：哪个股票缺哪些指标，一目了然。

---

## 三、八个踩坑记录

| # | 问题 | 根因 | 教训 |
|---|------|------|------|
| 1 | 三套注册表并存 | 旧代码未清理 | 删除要彻底，`grep -rn` 确认零引用后再删文件 |
| 2 | 筹码指标返回标量，全日期同值 | compute() 只算最后一次 | **所有指标必须返回 Series**（按日滚动计算），不是标量 |
| 3 | chip_pattern 永远 unknown | 字符串 Series 被误判为 object Series | `str(v.dtype)=='object'` 要区分 list/dict 和 string，检查样本值类型 |
| 4 | 两轮计算不够 | 下游指标排在依赖项前面 | 改为三轮处理，ctx 注入支持 Series 取值 |
| 5 | ctx 注入 Series 到单行失败 | `df.at[idx] = pd.Series(...)` 类型不匹配 | ctx 值是 Series 时取 `val.iloc[-1]`，不是整个 Series |
| 6 | 选部分指标重算，其他列全 NULL | DELETE + INSERT 覆盖了全行 | 部分指标用 SELECT + 内存合并 + executemany，不删旧行 |
| 7 | ON CONFLICT UPDATE 逐行太慢 | 每行一次 conn.execute | 部分指标也用 SELECT 一次全读 + executemany 一次全写 |
| 8 | label 脚本缩进混用导致启动崩溃 | tab/space 不一致 | 批量修改文件后必须 `py_compile` 全部检查，不能只看表面 |

---

## 四、新增指标检查清单

- [ ] 文件放在 `indicators/<category>/<name>.py`
- [ ] 继承 `BaseIndicator`，加 `@register`
- [ ] 设置 `name`（唯一）、`label`（中文）、`category`、`output`、`requires`、`params`
- [ ] `compute(cls, df)` 返回 `dict`，每个 value 是**与 df 等长的 Series**（不是标量）
- [ ] 字段名不与已有字段冲突（查 `ALL_COLS`）
- [ ] 如需依赖上游指标输出，声明在 `requires` 中
- [ ] 更新 `indicator_store.ALL_COLS` 添加新列
- [ ] 删除旧 SQLite 表或 ALTER TABLE ADD COLUMN
- [ ] `python -m py_compile` 通过
- [ ] 全量重算一只股票验证数据落库
- [ ] 更新 `.claude/rules/quant-indicator-standards.md` 的 schema
- [ ] 如前端有复选框列表，自动出现（从 registry API 动态加载）


## 五、研发方法论

### 新增量化指标/策略的标准流程

```
1. 搜索资料学习    — 搞清楚业界标准算法是什么（论文/书籍/通达信源码/开源库）
2. temp_lab/验算    — 脚本跑真实数据, 出图表, 跟参考标准比对（通达信/同花顺/手机软件）
3. 确认无误后写入系统 — 替换 indicators/ 下对应算子, 重算, 验证 coverage
```

### 本次筹码分布 COST 算法的验证经验

- 半衰期指数衰减模型：`decay = 0.5^(1/45)`（45 天半衰期, 与通达信 600699/300124 吻合）
- COST(N): 价格-成交量排序 + 累加, 取 N% 分位价格
- WINNER(P): 价格≤P 的累计筹码占比
- 90% 成本集中度: `(COST(90)-COST(10)) / COST(50) * 100`（越小越集中）
- 验证方式：`temp_lab/chart_chip_distribution.py` 生成 matplotlib 图, 与手机软件截图对比
- 验证通过后才替换 `indicators/chip/concentration.py` 等文件

### 策略开发同理

```
1. temp_lab/ 搜索 + 回测脚本   — 用真实数据跑一遍, 看胜率/盈亏比/最大回撤
2. 参数优化 & 多股票验证       — 调参, 确保不是过拟合
3. strategies/traditional/     — 写入策略文件, @register_strategy 注册
4. 决策中心集成                — 在 quant.html 看到策略信号, 确认与回测一致
```

---

## 五、性能基线

| 操作 | 数据量 | 耗时 | 瓶颈 |
|------|--------|------|------|
| 全量 historical 单股 | 400天 × 16指标 | ~3s | 筹码 COST 滚动计算 (O(天²)) |
| 全量 historical 28股 | 28×400 | ~90s | 串行循环 (可并行优化) |
| 增量 28股 | 0~5新天 | ~5s | MarketData 查询 |
| 部分 historical 单股 | 400天 × 2指标 | ~0.5s | 同上 |
| 快照 单股 | 仅今天 | ~0.2s | 同上 |
| SELECT 全量行 | 28股×400天 | <0.1s | SQLite 本地 I/O |
