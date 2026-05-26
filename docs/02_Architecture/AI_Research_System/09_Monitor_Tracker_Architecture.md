# Monitor/Tracker 系统架构

> **定位**: Pipeline 负责"发现机会"（低频事件驱动），Tracker 负责"盯盘追踪"（高频数据驱动）。两者独立演进，通过结构化订阅接口连接。

---

## 系统关系

```
┌─ 投研 Pipeline (低频) ──────────────────────────┐
│  Step 1b → Step 2 → Step 3                       │
│                                                   │
│  输出:                                             │
│    core_stocks[]        → StockTracker 订阅        │
│    kill_triggers[]      → KillConditionTracker     │
│    bottleneck_nodes[]   → BottleneckTracker        │
└──────────────────┬────────────────────────────────┘
                   │ subscribe(pipeline_output)
                   ▼
┌─ Monitor/Tracker (高频) ─────────────────────────┐
│                                                   │
│  BaseTracker (抽象框架)                            │
│    ├── KillConditionTracker   风险信号 每日轮询     │
│    ├── CatalystTracker        催化信号 每日轮询     │
│    ├── BottleneckTracker      瓶颈信号 每周轮询     │
│    └── StockTracker           标的多维 每日轮询     │
│                                                   │
│  输出:                                          │
│    RiskAlert[{level, target, message, rule}]       │
│    CatalystAlert[{catalyst, due_date, status}]     │
└───────────────────────────────────────────────────┘
```

---

## BaseTracker 抽象框架

```python
# domain/monitor/base.py

@dataclass
class Alert:
    level: Literal["info", "warn", "critical"]
    target: str          # 标的代码 / 瓶颈节点名
    tracker: str          # 来源 Tracker
    message: str
    triggered_rule: str
    current_value: Optional[float] = None
    threshold: Optional[float] = None
    timestamp: str = ""

class BaseTracker(ABC):
    """监控追踪器基类"""
    name: str
    targets: List[Dict]   # 订阅的监控目标列表

    def subscribe(self, pipeline_output: dict):
        """从 Pipeline 输出中提取监控目标"""

    @abstractmethod
    async def poll(self) -> List[Alert]:
        """轮询数据源, 检查阈值, 返回告警列表"""

    def check(self, current: float, threshold: float, op: str) -> bool:
        """阈值比较: gt/gte/lt/lte/eq"""
```

---

## 三个具体 Tracker

### KillConditionTracker

| 属性 | 值 |
|------|------|
| 订阅源 | Step 2 `kill_reasons[{condition, monitor_signal, data_source_hint}]` |
| 轮询频率 | 每日 |
| 数据源 | exchange_rates / macro_history / Sina 实时报价 |
| 告警触发 | 监控值突破阈值 → Alert(level="critical") |

```json
// Step 2 输出 (结构化)
"kill_triggers": [
  {
    "condition": "碳酸锂现货价 > 150000 元/吨",
    "monitor_target": "碳酸锂现货价",
    "data_source": "exchange_rates.BRENT",
    "threshold": 150000,
    "operator": "gt",
    "action": "如果触发, 原景气逻辑失效, 建议重新评估"
  }
]
```

### CatalystTracker

| 属性 | 值 |
|------|------|
| 订阅源 | Step 2 `phase_switch_trigger` + Step 3 `future_outlook` + 用户手动添加 |
| 轮询频率 | 每日 |
| 数据源 | Web 搜索 + 新闻 + 财报日历 |
| 告警触发 | 催化兑现/延期/失效 |

催化分类:
| 类型 | 举例 | 信号 |
|------|------|------|
| 业绩催化 | Q2财报超预期 | 财报发布日 ±3天 → Alert(level="info") "财报窗口临近" |
| 产品催化 | 新品流片成功 | Web搜索到相关公告 → Alert(level="warn") "产品里程碑达成" |
| 政策催化 | 补贴政策落地 | 政策文件发布 → Alert(level="warn") "政策催化兑现" |
| 产能催化 | 新产线投产 | 公司公告产能投放 → 标记 bottleneck 缓解 |
| 订单催化 | 大客户订单落地 | 搜索到签约公告 → Alert(level="info") "订单催化兑现" |

```json
// Step 2/3 输出中预埋的催化信号
"catalysts": [
  {
    "catalyst": "Q2财报预计超预期",
    "type": "earnings",
    "expected_date": "2026-08",
    "watch_signal": "单季营收增速 > 30%",
    "status": "pending"
  }
]
```

### BottleneckTracker

| 属性 | 值 |
|------|------|
| 订阅源 | Step 3 `supply_chain_map[{supply_rigidity, future_outlook}]` |
| 轮询频率 | 每周 |
| 数据源 | Web 搜索 + 行业数据 |
| 告警触发 | lead_time 缩短 / 新增产能投放 / 替代方案出现 → Alert(level="warn") |

监控信号:
- 瓶颈环节交期是否缩短
- 是否有新的产能投放公告
- 替代方案/国产化进展是否加速

### StockTracker

| 属性 | 值 |
|------|------|
| 订阅源 | Step 3 `core_stocks[{code, segment, moat}]` |
| 轮询频率 | 每日 |
| 数据源 | stock_info / financial_statements / indicators (SQLite) |
| 告警触发 | 毛利率连续下降 / PE突破历史分位 / 换手率异动 / 浮盈比例过高 |

监控信号:
- 毛利率: 连续 2 季下降 → Alert(level="warn")
- PE 分位: > 历史 90% → Alert(level="warn")
- 换手率: > 20 日均值 3σ → Alert(level="info")
- 浮盈比例: > 15% → Alert(level="info")

---

## 目录结构

```
backend/app/domain/monitor/
├── __init__.py
├── base.py                # BaseTracker + Alert
├── kill_tracker.py        # KillConditionTracker
├── bottleneck_tracker.py  # BottleneckTracker
├── stock_tracker.py       # StockTracker
├── services/
│   └── scheduler.py       # APScheduler 定时触发 poll()
└── api/
    └── routes.py          # GET /monitor/alerts?tracker=xxx
                           # POST /monitor/subscribe  (从 pipeline 输出订阅)
                           # GET /monitor/dashboard    (告警面板数据)
```

---

## 前端

- 新增 `monitor.html` 页面：告警面板
- 或在 `research.html` 项目详情中增加"监控状态"标签
- 告警分级显示：🔴 critical / 🟡 warn / 🔵 info

## 实施计划

| 阶段 | 内容 | 依赖 |
|------|------|------|
| 1 | BaseTracker + Alert 数据类 | 无 |
| 2 | KillConditionTracker | Step 2 kill_reasons 结构化 (IDEA-017) |
| 3 | StockTracker | indicators.db 已有数据 |
| 4 | BottleneckTracker | Step 3 瓶颈节点监控 |
| 5 | 前端告警面板 | Tracker API 就绪 |
