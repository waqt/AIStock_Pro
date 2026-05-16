# AIStock Pro — AI 量化分析与投研系统

## 项目身份

AIStock Pro 是一套 AI 驱动的量化分析与投资研究系统，面向 A 股 + 港股。系统采用"量化计算 + 本地技能 + 远程 AI"混合动力架构，由 Python 3.10+ 异步引擎驱动。

- **架构风格**: DDD（领域驱动设计）+ Clean Architecture
- **版本**: 2.1.0
- **数据库名**: `aistock_pro`（MySQL, 与旧系统物理隔离）

## 技术栈

| 层 | 技术 |
|---|------|
| Web 框架 | FastAPI 0.110 + Uvicorn |
| 序列化/配置 | Pydantic V2 + pydantic-settings |
| ORM | SQLAlchemy 2.0 异步 (aiomysql) |
| 量化计算 | Pandas + NumPy |
| 前端 | 原生 HTML/CSS/JS + ECharts 5.5 + Font Awesome 6 |
| AI SDK | anthropic, openai, google-generativeai, langchain |
| 数据源 | httpx 异步客户端 → 新浪财经 API |

## 目录结构

```
AIStock_Pro/
├── CLAUDE.md                  # ← 本文件 (Claude Code 自动加载)
├── backend/
│   ├── app/
│   │   ├── api/               # [路由层] 参数校验、调用领域服务，禁止写业务逻辑
│   │   │   ├── tasks.py       #   /api/system/tasks/*
│   │   │   ├── data.py        #   /api/data/*
│   │   │   └── positions.py   #   /api/positions/*
│   │   ├── core/              # [基础设施层] 配置、DB、日志、任务管理器
│   │   │   ├── config.py      #   Settings (从 .env 加载)
│   │   │   ├── database.py    #   async engine + session + get_db 依赖
│   │   │   ├── logger.py      #   结构化日志
│   │   │   ├── state.py       #   全局内存状态 (task_stop_events)
│   │   │   ├── data_service.py#   异步行情数据抓取 (新浪财经)
│   │   │   └── task_manager.py#   异步任务生命周期管理
│   │   ├── domain/            # [领域层] 业务逻辑与跨域编排
│   │   │   └── task_service.py
│   │   ├── quant/             # [量化层] 指标计算 + 形态识别 + 分析引擎
│   │   │   ├── indicators.py  #   MA、MACD、RSI、布林带、成交量均线
│   │   │   ├── patterns.py    #   Andy 123、Joy 底部、顶部天量滞涨
│   │   │   ├── engine.py      #   QuantEngine: 单股分析 + 批量同步
│   │   │   └── tasks.py       #   领域任务: sync_market_data_task, calculate_indicators_task
│   │   ├── agents/            # [规划中] AI Orchestrator 与 Prompt 编排
│   │   ├── plugins/           # [规划中] 可下载的策略/Skill 插件
│   │   │   ├── quant/         #   量化算子插件
│   │   │   └── research/      #   投研分析 Skill
│   │   └── models/            # [数据模型层] SQLAlchemy ORM 模型
│   │       ├── models.py      #   Position, MarketData, StockIndicator, etc.
│   │       └── schemas.py     #   Pydantic 响应模型
│   ├── scripts/               # 数据库迁移、审计、诊断工具
│   ├── temp_lab/              # AI 生成实验脚本的临时存放区
│   ├── requirements.txt
│   └── .env                   # 环境变量 (DB 连接、API Key)
├── frontend/
│   ├── index.html             # 指挥中心首页
│   ├── positions.html         # 持仓管理 (含 ECharts K线)
│   ├── suggestions.html       # 调仓建议
│   ├── research.html          # AI 投研
│   ├── data.html              # 数据中心
│   ├── history.html           # 交易审计
│   ├── import.html            # 智能导入
│   ├── morning_report.html    # 早盘报告
│   ├── closing_report.html    # 收盘报告
│   ├── css/style.css
│   └── js/
│       ├── ui.js              # 通用 UI 组件 (侧边栏、顶栏、任务监控)
│       ├── common.js          # 全局常量 API_BASE + 任务轮询 + 账户摘要
│       └── app.js             # 指挥中心业务逻辑
└── docs/
    ├── architecture_v2.md     # 架构设计文档
    ├── roadmap_v2.md          # 迭代路线图 (V1.0 → V3.0)
    ├── data_sync_spec.md      # 数据同步规格书
    └── engineering_standards.md # 工程规范
```

## 架构约束 (硬规则)

### DDD 分层边界
```
api/          → 仅做参数校验 + 调用下层服务 + 返回响应。绝对不写业务逻辑。
domain/       → 业务编排、跨领域调用。依赖 core/、quant/、models/。
quant/        → 纯算法：指标计算、形态识别、分析引擎。不依赖 api/。
core/         → 基础设施：DB、日志、配置、外部 API。不依赖 api/、domain/、quant/。
models/       → 纯 ORM 模型 + Pydantic Schema。不依赖其他任何业务模块。
```

### 违规示例
- ❌ `api/data.py` 里直接写 `pd.DataFrame` 加工逻辑
- ❌ `quant/engine.py` 里直接操作 FastAPI `Response` 对象
- ❌ `core/database.py` 里 import `Position` 进行业务判断

## 编码规范

### 导入
- **绝对导入**：一律 `from app.core.database import ...`，禁止 `from ..core import ...`
- **导入顺序**：标准库 → 第三方库 → 本地模块

### 异步
- 所有数据库操作必须使用 `async_session` / `AsyncSession`
- I/O 密集型操作（行情抓取、AI 调用）必须异步化
- 后台任务必须通过 `TaskManager.start_task()` 启动，禁止裸 `asyncio.create_task()`

### 命名
- 任务状态限定值：`PENDING`、`RUNNING`、`SUCCESS`、`FAILED`、`CANCELLED`
- ORM 模型统一继承 `Base`（来自 `core.database`）
- API 路由函数以 `async def` 声明

### 日志
```
[🚀] 系统/模块启动
[✅] 成功完成
[❌] 异常/错误 (附带错误详情)
[⚠️] 逻辑警告
[🛑] 任务被强杀
[🧹] 清理/自愈
```

## 数据库规则

- **URL 格式**: `mysql+aiomysql://user:pass@host:port/aistock_pro`
- **数据库名**: 必须是 `aistock_pro`（与旧系统物理隔离）
- **引擎配置**: `pool_pre_ping=True`, `pool_size=10`, `max_overflow=20`
- **模型变更流程**:
  1. 修改 `backend/app/models/models.py`
  2. 系统启动时 `Base.metadata.create_all` 会自动建新表（但不做 ALTER）
  3. 如需 ALTER，在 `backend/scripts/` 中编写迁移脚本
- **唯一约束**: `Position.stock_code` 必须 unique；`MarketData(stock_code, trade_date)` 组合唯一

## 任务管理

所有后台任务**必须**通过 `TaskManager` 管理：
```python
task_id = await TaskManager.start_task(
    task_type="操作名称",
    coro_func=领域任务函数,
    mode="AUTO"  # 或其他参数
)
```
- 任务函数签名必须为 `async def func(task_id: str, **kwargs)`
- 任务函数内部必须定期 `await asyncio.sleep(0)` 以响应 KILL 信号
- 系统启动自愈：自动将残留 `RUNNING`/`PENDING` 任务标记为 `CANCELLED`

## 前端约束

- **加载顺序**: `ui.js` → `common.js` → 页面内联/业务 JS
- **API_BASE**: 全局变量 `const API_BASE = '/api'` (在 common.js 顶部定义)
- **页面模板**: 每个页面必须有 `<body data-page-id="xxx">` + `<aside class="sidebar">` + `<div class="top-bar">` + main 内 `<div class="workspace">`
- **任务监控**: 由 `common.js` 的 `initCommon()` 自动注入到 `body`
- **ECharts**: 在需要的页面单独引入 CDN script

## 常见陷阱

1. **路由未注册** — 新建 API 路由文件后必须在 `main.py` 中 `app.include_router()`
2. **脚本加载顺序** — 内联 `<script>` 不能引用还未加载的 `common.js` 中定义的变量
3. **TaskManager 幽灵任务** — 任务 KILL 后数据库状态必须为 `CANCELLED`，否则启动自愈会标记为 zombies
4. **httpx proxy** — DataService 必须显式设 `proxy=None` 避免系统代理干扰财经 API
5. **Pydantic V2** — 使用 `pydantic_settings.BaseSettings` 而非 `pydantic.BaseSettings`
6. **SQLAlchemy async** — 查询必须 `await db.execute(select(...))` 再 `.scalars().all()`

## 开发流程

### 新功能开发
1. 确认需求属于哪个 DDD 层
2. 如需新表 → 修改 `models.py`  -> 写迁移脚本
3. 核心逻辑 → `quant/` 或 `domain/`
4. 暴露接口 → `api/` 新增路由
5. 前端页面 → 遵循页面模板
6. `main.py` 注册路由
7. 端到端验证

### Bug 修复
1. 复现并定位到具体层 (api/domain/quant/core/models)
2. 检查是否有连锁影响（同一层的其他调用方）
3. 修复 + 验证
4. 如果 Bug 具有代表性 → 更新 `docs/engineering_standards.md`
