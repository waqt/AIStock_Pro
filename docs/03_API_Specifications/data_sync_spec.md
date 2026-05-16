# AIStock Pro 数据同步模块技术规格书 V2.0

> 基于 AIStock_Pro V5.0 当前代码状态进行审计，结合 AISTOCK 上一代项目经验，制定完整的数据管理模块设计。

---

## 0. 现状审计 (Current State Audit)

### 已就绪

| 模块 | 文件 | 状态 |
|------|------|------|
| MarketData 模型 | `models/models.py:21-37` | ✅ 字段完整 (OHLCV + amount) |
| StockIndicator 模型 | `models/models.py:39-47` | ✅ JSON 存储，支持复杂结构 |
| 新浪财经异步抓取 | `core/data_service.py` | ✅ httpx async，A/H 股兼容 |
| 量化指标计算 | `quant/indicators.py` | ✅ MA/MACD/RSI/BB/Volume MA |
| 形态识别 | `quant/patterns.py` | ✅ Andy123/Joy底部/天量滞涨 |
| QuantEngine 批量分析 | `quant/engine.py` | ⚠️ 有 batch_analyze_positions，缺增量检测 |
| 任务调度引擎 V5.0 | `core/task_manager.py` + `scheduler.py` | ✅ 注册/调度/强杀/进度 |
| 任务执行历史 API | `api/tasks.py` | ✅ |
| 前端持仓 K 线图 | `frontend/positions.html` | ✅ ECharts candlestick |
| 前端数据中心页 | `frontend/data.html` | ⚠️ 有页面，但部分 API 返回模拟数据 |

### 缺失或假数据

| 问题 | 位置 | 严重度 |
|------|------|--------|
| 数据源健康 API 返回随机假数据 | `api/data.py:11-22` | 🔴 假数据 |
| 个股指标快照 API 返回写死的假数据 | `api/data.py:24-39` | 🔴 假数据 |
| 只有新浪一个数据源 | `core/data_service.py` | 🟡 单点 |
| 无增量同步精确逻辑 | `quant/engine.py:analyze_stock()` | 🟡 仅按日期 gap 判断 |
| MarketData 缺少 `change_pct` 字段 | `models/models.py:21-37` | 🟡 需补 |
| 无日线数据查询 API | — | 🔴 缺失 |
| 无指标查询/列表 API | — | 🔴 缺失 |
| 前端 K 线无指标叠加 | `positions.html` | 🟡 仅 K 线+成交量 |
| 无数据体检页面 | — | 🔴 缺失 |
| 无数据源优先级配置 | — | 🔴 缺失 |

---

## 1. 行情同步 (Market Data Sync)

### 1.1 同步内容

| 字段 | 说明 | 存储 |
|------|------|------|
| trade_date | 交易日 | `MarketData.trade_date` |
| open / high / low / close | 开高低收 | `MarketData` 对应字段 |
| volume | 成交量 (股) | `MarketData.volume` |
| amount | 成交额 (元) | `MarketData.amount` |
| change_pct | 涨跌幅 (%) | **新增字段** `MarketData.change_pct` |

### 1.2 同步策略

```
冷启动 (Cold Start)
  条件: 数据库中该股无任何日线记录
  动作: 抓取过去 2 年全量日线 → 逐批写入
  标志: mode = "FULL"

增量更新 (Incremental)
  条件: 数据库中有该股记录
  动作: 查询 MAX(trade_date)，从下一交易日抓取至最新
  标志: mode = "INCREMENTAL"

强制全量 (Force Full)
  条件: 用户手动触发
  动作: 同冷启动，覆盖式写入
  标志: mode = "FORCE_FULL"
```

### 1.3 同步规则

1. **唯一键**: `(stock_code, trade_date)` 联合唯一，重复插入自动跳过
2. **批量写入**: 使用 `insert().on_conflict_do_nothing()` 替代逐行 upsert
3. **限流保护**: 单次同步不超过 500 条/股，批次间间隔 0.2s
4. **错误隔离**: 单股失败不中断整批

### 1.4 后置触发链

```
行情同步完成
  ├→ 1. 更新 Position.current_price (= 最新 close)
  ├→ 2. 重算 Position.market_value / profit_loss / profit_loss_ratio
  └→ 3. 触发指标重算 (如用户选择)
```

### 1.5 数据模型变更

```python
# MarketData 新增字段
change_pct = Column(Float, nullable=True, comment="涨跌幅(%)")

# 新增联合唯一索引 (在 __table_args__ 中)
UniqueConstraint('stock_code', 'trade_date', name='uq_market_data_code_date')
```

---

## 2. 指标计算 (Indicator Engine)

### 2.1 指标注册表

系统内所有可用指标必须有一个统一注册表，前端可查询其定义和参数。

```python
# 指标元数据结构
INDICATOR_REGISTRY = {
    "ma": {
        "name": "移动平均线",
        "params": {"periods": [5, 10, 20, 60, 120, 250]},
        "category": "趋势",
        "description": "计算指定周期的收盘价简单移动平均"
    },
    "macd": {
        "name": "MACD",
        "params": {"fast": 12, "slow": 26, "signal": 9},
        "category": "动量",
        "output_fields": ["macd", "macd_signal", "macd_hist"]
    },
    "rsi": {
        "name": "相对强弱指数",
        "params": {"period": 14},
        "category": "超买超卖"
    },
    "bollinger": {
        "name": "布林带",
        "params": {"period": 20, "std_dev": 2},
        "category": "波动",
        "output_fields": ["bb_upper", "bb_mid", "bb_lower"]
    },
    "volume_ma": {
        "name": "成交量均线",
        "params": {"periods": [5, 10, 20]},
        "category": "量能"
    }
}
```

### 2.2 指标存储

`StockIndicator` 表使用 JSON 存储每条计算结果的完整结构：

```json
{
  "indicator_type": "ma",
  "data_json": {
    "ma5": 32.54,
    "ma10": 31.80,
    "ma20": 30.15,
    "ma60": 28.42,
    "ma120": 25.10,
    "ma250": 22.30
  },
  "analysis_date": "2026-05-16"
}
```

### 2.3 触发机制

| 触发方式 | 接口 | 说明 |
|----------|------|------|
| 手动触发 | `POST /api/data/indicators/calculate` | 传入 stock_code 列表 |
| 同步后自动 | 嵌入行情同步的后置链 | 可选是否连带计算 |
| 定时触发 | APScheduler | 每日收盘后自动执行 |

### 2.4 指标展示页面需求

- 展示所有已注册指标的名称、分类、参数定义
- 列出每个指标在各股票的最新数值快照
- 对于复杂指标（MA 多周期、MA CD 三线、布林带三轨），用 JSON 折叠展示
- 支持勾选指标叠加到 ECharts K 线图上（MA 线、布林带、MACD 副图）

---

## 3. 数据源展示 (Data Source Transparency)

### 3.1 多数据源架构

```
                    ┌──────────────┐
                    │  DataRouter  │  ← 新增组件，统一调度
                    └──────┬───────┘
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌──────────────┐ ┌──────────┐ ┌──────────────┐
    │ AkShareSource│ │SinaSource│ │EastMoneySource│
    │ (优先级 1)   │ │(优先级 2)│ │(优先级 3)    │
    └──────────────┘ └──────────┘ └──────────────┘
```

每个数据源实现统一接口：

```python
class DataSourceProtocol:
    async def get_daily_data(stock_code: str, days: int) -> pd.DataFrame
    async def get_realtime_quote(stock_code: str) -> dict
    async def health_check() -> bool
    def source_name() -> str
```

### 3.2 优先级与降级规则

- **优先级配置**: `settings.json` 或 `system_settings` 表中配置数据源优先级列表
- **自动降级**: 主数据源超时 2 次后自动切换到下一个
- **恢复探测**: 每 5 分钟探测一次高优先级数据源是否恢复
- **透明记录**: 每次同步的 `TaskExecution.result_msg` 记录实际使用的数据源

### 3.3 前端数据源看板

- 显示当前配置的数据源优先级链路（如 `AkShare > Sina > EastMoney`）
- 每个数据源的实时状态（在线/降级/离线）
- 延迟探测（ping 耗时）
- 本次或最近一次同步所用的数据源名称

---

## 4. 任务进度看板 (Task Progress Dashboard)

### 4.1 节点级追踪

当前 V5.0 TaskEngine 只追踪到任务级别。本次升级增加**节点级进度**：

```python
# 执行记录的 current_node 字段
"current_node": "FETCHING" | "CALCULATING" | "SAVING" | "UPDATING_POSITIONS"
```

同步任务的节点流转：

```
PENDING → FETCHING (抓取行情)
       → CALCULATING (计算指标)
       → SAVING (落库写入)
       → UPDATING_POSITIONS (更新持仓损益)
       → SUCCESS
```

### 4.2 前端看板需求

- **活跃任务浮窗**（已有，`common.js`）：显示当前 RUNNING/PENDING 任务
- **执行历史页**（已完成，`history.html`）：分页、筛选、清理
- **新增**：在 `data.html` 数据中心页内嵌实时任务进度条，显示当前节点名称 + 进度百分比

### 4.3 手动干预

- 支持 `DELETE /api/system/tasks/executions/{exec_id}` 终止任务（已有）
- 终止时触发 `CancelledError` → 回滚未提交数据 → 标记 `CANCELLED`（已有）

---

## 5. 数据健康检查 (Data Health Check)

### 5.1 行情体检

展示内容：
- 所有已同步股票的列表
- 每只股票的最新行情日期
- 每只股票的最新收盘价
- 数据断层检测（距离最新交易日超过 N 天标黄，超过 2N 天标红）
- 总览汇总：已同步股票数、最后同步时间

### 5.2 指标体检

展示内容：
- 每只股票已计算的指标项列表
- 每个指标项的最新计算日期
- 每个指标项的最新数值快照（复杂结构以 JSON 展示）
- 指标覆盖率 (已计算指标数 / 应计算指标数)

### 5.3 健康状态定义

| 状态 | 条件 | 颜色 |
|------|------|------|
| HEALTHY | 最新行情日期 = 最近交易日 | 绿 |
| STALE | 延迟 1-3 个交易日 | 黄 |
| GAP | 延迟 > 3 个交易日或无数据 | 红 |

---

## 6. API 端点设计 (完整清单)

### 6.1 行情同步

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| POST | `/api/data/sync/daily/auto` | 触发自动同步 (mode=AUTO/FULL/PRICE_ONLY) | ✅ 已有 |
| POST | `/api/data/sync/daily/{stock_code}` | 单股同步 | 🆕 新增 |
| GET | `/api/data/daily/{stock_code}?limit=500` | 获取日线数据 (JSON) | 🆕 新增 |

### 6.2 指标计算与查询

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| GET | `/api/data/indicators/registry` | 获取指标注册表 (所有可用指标+定义) | 🆕 新增 |
| POST | `/api/data/indicators/calculate` | 触发指标计算 | 🆕 新增 |
| GET | `/api/data/indicators/{stock_code}?limit=500` | 获取单股所有指标 | 🆕 新增 |
| GET | `/api/data/indicators/{stock_code}/{indicator_type}` | 获取单股特定指标 | 🆕 新增 |

### 6.3 数据源管理

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| GET | `/api/data/sources/status` | 获取所有数据源状态 (非假数据) | 🔧 重写 |
| GET | `/api/data/sources/priority` | 获取当前数据源优先级链路 | 🆕 新增 |
| PUT | `/api/data/sources/priority` | 修改数据源优先级顺序 | 🆕 新增 |

### 6.4 数据健康检查

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| GET | `/api/data/health/overview` | 全局数据健康总览 | 🆕 新增 |
| GET | `/api/data/health/stocks` | 各股票行情体检列表 | 🆕 新增 |
| GET | `/api/data/health/indicators` | 各股票指标体检列表 | 🆕 新增 |
| GET | `/api/data/health/{stock_code}` | 单股详细体检 | 🔧 重写 (去掉假数据) |
| GET | `/api/data/sources/status` | 数据源实时状态 (非假数据) | 🔧 重写 |

---

## 7. 数据模型变更汇总

### MarketData 表

```python
# 新增字段
change_pct = Column(Float, nullable=True, comment="涨跌幅(%)")

# 新增联合唯一约束
__table_args__ = (
    UniqueConstraint('stock_code', 'trade_date', name='uq_market_data_code_date'),
)
```

### 无需新增表

- 数据源优先级配置存储在 `SystemSetting` 表
- 指标定义由代码注册表管理（非 DB 表）

---

## 8. 实施阶段规划

### Phase 1: 补核心缺口 (预计 2-3 小时)

- [ ] 1.1 `MarketData` 模型加 `change_pct` + 唯一约束
- [ ] 1.2 接入 AkShare 数据源（类旧项目 `akshare_service.py`）
- [ ] 1.3 实现 DataRouter 多源调度器
- [ ] 1.4 实现增量同步精确逻辑 (MAX trade_date → 逐日补缺)
- [ ] 1.5 批量 upsert 替代逐行插入
- [ ] 1.6 新增 `GET /api/data/daily/{stock_code}` 端点
- [ ] 1.7 把 `data.py` 中所有假数据端点替换为真实现

### Phase 2: 指标管理体系 (预计 2 小时)

- [ ] 2.1 构造 `INDICATOR_REGISTRY` 注册表
- [ ] 2.2 实现 `GET /api/data/indicators/registry`
- [ ] 2.3 实现 `GET /api/data/indicators/{stock_code}` 系列端点
- [ ] 2.4 前端指标管理页 (展示注册表 + 各股指标快照)
- [ ] 2.5 ECharts K 线叠加 MA/布林带

### Phase 3: 数据体检与看板 (预计 1-2 小时)

- [ ] 3.1 实现 `GET /api/data/health/*` 系列端点
- [ ] 3.2 重写 `data.html` 数据体检面板
- [ ] 3.3 数据源实时状态展示

---

*Document: V2.0, 2026-05-17*
*基于 AIStock_Pro V5.0 代码审计 + AISTOCK 上一代经验编写*
