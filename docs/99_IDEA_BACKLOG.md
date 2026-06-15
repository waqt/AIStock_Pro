# 优化 IDEA 库

> 不紧急但值得做的小优化。排查 bug 或顺手重构时捡一个做掉。

---

## 待优化

### IDEA-025: System_Feature_Inventory.md 大版本同步
- **来源**: V5.16 全系统扫描
- **描述**: 文档严重落后于代码：声称 11 张表（实际 15 模型）、API 端点数低估（78→100+）、D1.4/D1.5 标记"待建设"但已实现、遗漏 StockMaster/StockValuation/PortfolioSnapshot/MacroHistory 等表、旧路由路径引用。需要全量校对，建议对齐到 V5.16 版本
- **优先级**: 中
- **状态**: 待开始

### IDEA-024: portfolio/api/ 下重复路由文件（死代码）
- **来源**: V5.16 全系统扫描
- **描述**: `domain/portfolio/api/import_routes.py` 和 `positions.py` 定义了与 `app/api/import_api.py` 和 `app/api/positions.py` 完全相同的路由，但未被 `main.py` 导入。属于死代码，应删除
- **文件**: `backend/app/domain/portfolio/api/import_routes.py`, `positions.py`
- **优先级**: 低
- **状态**: 待开始

### IDEA-023: CLAUDE.md 数据源描述过时同步
- **来源**: V5.16 全系统扫描
- **描述**: CLAUDE.md 第 252 行"push2 适配器用 requests.get（同步）+ asyncio.to_thread"已过时(push2.py 已改为 httpx.AsyncClient)，但 valuation.py 和 stock_info_adapter.py 仍有同步用法。需同步更新文档和修复遗留同步调用
- **优先级**: 低
- **状态**: 待开始

### IDEA-022: checkpoint.py print() 改为 logger
- **来源**: V5.16 全系统扫描
- **描述**: `framework/pipeline/checkpoint.py` 第 354/358/366 行有三处 `print()`，违反日志规范。改为 `logger.info()`。3 行改动的快速修复
- **文件**: `backend/app/framework/pipeline/checkpoint.py`
- **优先级**: 低
- **状态**: 待开始

### IDEA-021: 数据源双源同构 — 引入独立日线源
- **来源**: V5.16 全系统扫描
- **描述**: SinaSource 和 AkShareSource 对 A 股都走同一新浪接口 `money.finance.sina.com.cn`，港股都走 akshare。不是真正独立的冗余源。新浪挂了全挂。需引入真正的独立日线源（如腾讯日线或东方财富 API）
- **文件**: `backend/app/domain/market_data/sources/sina.py`, `akshare.py`, `router.py`
- **优先级**: 低
- **状态**: 待开始

### IDEA-020: sync_market 串行循环改并发
- **来源**: V5.16 全系统扫描
- **描述**: `engine.py:182` 的 `batch_sync_and_analyze` 用纯串行 for 循环同步 40 只股票，浪费异步能力。当前规模（~40 只）影响不大，扩展到数百只需加 `asyncio.gather` + 信号量控制并发
- **文件**: `backend/app/domain/quant/engine/engine.py`
- **优先级**: 低
- **状态**: 待开始

### IDEA-019: 多处静默吞异常（except: pass）清理
- **来源**: V5.16 全系统扫描
- **描述**: `report_store.py:163`、`global_capex_scanner.py:348/400`、`routes.py:570/588`、`tasks.py:177/288/307` 等处有 `except Exception: pass`。排查 bug 时造成困难。每处应至少打 `logger.warning`
- **优先级**: 低
- **状态**: 待开始

### IDEA-018: Monitor/Tracker 框架 — Pipeline 输出 → 量化追踪
- **来源**: Gemini 报告 + 架构讨论
- **描述**: 投研 Pipeline 负责"发现机会"（低频），Monitor 模块负责"盯盘追踪"（高频）。新建 `domain/monitor/` 目录，BaseTracker 抽象框架（订阅/轮询/阈值检查/告警），三个具体 Tracker：
  - KillConditionTracker: 消费 Step 2 的 kill_triggers，每日查数据源，突破阈值即告警
  - BottleneckTracker: 消费 Step 3 的 bottleneck_nodes，监控交期/产能利用率/价格变动
  - StockTracker: 消费 Step 3 的 core_stocks，监控毛利率/PE分位/换手率/浮盈比例
- **架构**:
  ```
  domain/monitor/
    base.py              BaseTracker + Alert/RiskAlert/CatalystAlert
    kill_tracker.py      证伪条件监控 (风险侧)
    catalyst_tracker.py  催化信号监控 (机会侧)
    bottleneck_tracker.py 瓶颈节点监控
    stock_tracker.py     标的多维监控 (财务+交易+催化)
    api/routes.py        GET /monitor/alerts, POST /monitor/subscribe
  ```
- **Tracker 双信号体系**:
  - 风险侧: kill_triggers → 证伪/衰退/泡沫信号 (KillConditionTracker)
  - 机会侧: catalysts → 业绩/产品/政策/产能/订单催化 (CatalystTracker)
  - 瓶颈侧: bottleneck_nodes → 交期/产能/替代进展 (BottleneckTracker)
  - 标的多维: core_stocks → 毛利率/PE/换手率/浮盈 (StockTracker)
- **优先级**: 中
- **状态**: 架构已设计, BaseTracker 待实现

### IDEA-017: kill_reasons 结构化输出 (Tracker 的前置依赖)
- **来源**: Gemini 投研框架评估报告
- **描述**: Step 2 的 kill_reasons 从纯文本改为 `{reason, monitor_signal, data_source_hint}` 结构，使 KillConditionTracker 可程序化消费
- **优先级**: 高
- **状态**: 待开始

### IDEA-016: 宏观数据多源降级
- **来源**: Gemini 投研框架评估报告
- **描述**: 4 个缺失 akshare 指标（US_CPI/CN_CPI/US_ISM_PMI/DXY）修复，并引入备用数据源。主数据源解析失败（如 biz_date NaN）时自动触发降级策略，调用备用宏观数据库
- **优先级**: 中
- **状态**: 待开始 (合并 IDEA-003/004/005)

### IDEA-015: 程序化利润池追踪
- **来源**: Gemini 投研框架评估报告
- **描述**: Step 3 输出的 profit_pool 目前是 LLM 定性判断。应程序化追踪各环节毛利率变动，自动锁定利润蓄水池。当某环节毛利率连续 2 季扩张且超过行业均值 1.5σ 时，自动标记为"利润汇聚节点"
- **优先级**: 中
- **状态**: 待开始

### IDEA-012: 全市场股票基础信息库
- **来源**: 日常讨论
- **描述**: 从 akshare 获取全市场 A 股+港股 代码/名称/行业/上市日期/PE/PB/市值 等基础信息，批量写入 `stock_info` 表。一次同步后增量更新。解决当前只有持仓+自选股有 stock_info，投研提取标的时经常查不到名称的问题
- **优先级**: 中
- **状态**: 待开始

### IDEA-009: CatalystCheckAgent — 催化剂自动扫描
- **来源**: 自选股备注设计讨论
- **描述**: 投研报告生成时将每只标的的催化因素抽提到备注字段。新增一个轻量 Agent，每天定时扫描自选股备注中的催化剂，web search 相关新闻/公告/数据，对比变化，标记「催化兑现」「催化失效」「催化延期」。前端自选股列表用颜色标记状态变化
- **依赖**: 任务调度 (APScheduler)、备注字段已就绪
- **优先级**: 中
- **状态**: 待开始

### IDEA-010: watchlist 催化状态列 + 筛选
- **来源**: IDEA-009 配套前端
- **描述**: 自选股列表增加「催化状态」标签列 (🟢催化兑现中 / 🟡待观察 / 🔴催化失效 / ⚪无催化)。筛选器增加按状态过滤
- **优先级**: 低 (依赖 IDEA-009)
- **状态**: 待开始

### IDEA-011: 报告→自选股备注自动写入
- **来源**: 投研报告工作流
- **描述**: 投研报告完成后，将每只推荐标的的核心催化因素、情景分析关键假设，自动写入对应自选股的备注字段。不做覆盖，追加时间戳标记
- **优先级**: 低
- **状态**: 待开始

### IDEA-001: 领先指标手动录入
- **来源**: Step 4 thesis_validation
- **描述**: macro 面板加手动输入框，录入行业高频数据（HBM价格/GPU交期/CoWoS交期/设备订单），存 DB，支持历史趋势查看
- **优先级**: 低
- **状态**: 待开始

### IDEA-002: thesis 历史追踪
- **来源**: Step 4 thesis_validation
- **描述**: 给每个 thesis 生成唯一 ID，跨报告追踪置信度变化（5月75%→8月60%→11月90%），可视化趋势线
- **优先级**: 低
- **状态**: 待开始

### IDEA-003: US_FED_RATE 数据源修复
- **来源**: Step 1 sync_macro
- **描述**: `ak.macro_bank_usa_interest_rate()` 列名乱码/NaN，当前 DB 停在 2025-07-31。验证 API 或换数据源
- **优先级**: 中
- **状态**: 待开始

### IDEA-004: CPI/ISM PMI 数据接入
- **来源**: Step 1 sync_macro
- **描述**: `macro_usa_cpi_yoy()`、`macro_china_cpi_yearly()`、`macro_usa_ism_pmi()` 静默失败，需逐个调列名。修完后 macro 面板 12→15 指标
- **优先级**: 中
- **状态**: 待开始

### IDEA-005: DXY 美元指数数据源
- **来源**: Step 1 sync_macro
- **描述**: Sina hf_DINIW 返回空，akshare currency_latest 需要第三方 API key。需替代源
- **优先级**: 低
- **状态**: 待开始

### IDEA-006: 研发占比显示双百分号
- **来源**: 报告模板
- **描述**: 人力资本行 研发占比显示 `46.38%%`（数据自带%），模板又加了%
- **优先级**: 低
- **状态**: 待开始

### IDEA-007: watchlist refresh_held 消息 bug
- **来源**: `app/api/data.py` line ~991
- **描述**: `refresh_watchlist_held_status` 返回消息硬编码为 "Added {stock_code}"，应该是 "Refreshed held status"
- **优先级**: 低
- **状态**: 待开始

### IDEA-008: watchlist N+1 查询优化
- **来源**: `app/api/data.py` list_watchlist
- **描述**: 行情和财务查询对每个代码单独查 DB，应改为批量查询
- **优先级**: 低
- **状态**: 待开始

---

## 已完成

(暂无, 做完移到这里)

---

**使用方式**: 顺手修了某条 → 移到「已完成」区域，标注日期。新增想法 → 追加到「待优化」顶部。
