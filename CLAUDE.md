# AIStock Pro — AI 量化分析与投研系统

## 项目身份

AIStock Pro 是一套 AI 驱动的量化分析与投资研究系统，面向 A 股 + 港股。系统采用 DDD 领域驱动 + 智能体架构，由 Python 3.10+ 异步引擎驱动。

- **架构风格**: DDD（领域驱动设计）+ Agent 智能体模式
- **版本**: V5.2
- **数据库名**: `aistock_pro`（MySQL, 与旧系统物理隔离）
- **conda 环境**: `aiteacher` (`D:\develop_env\python_related\anaconda\Anaconda3\envs\aiteacher`)
- **启动**: 双击 `run_backend.bat` → `http://127.0.0.1:8000`

## 技术栈

| 层 | 技术 |
|---|------|
| Web 框架 | FastAPI + Uvicorn (--reload 热加载) |
| 序列化/配置 | Pydantic V2 + pydantic-settings |
| ORM | SQLAlchemy 2.0 异步 (aiomysql) |
| 量化计算 | Pandas + NumPy |
| 前端 | 原生 HTML/CSS/JS + ECharts 5.5 + Font Awesome 6 |
| AI 提供者 | 豆包 Seed (主) / DeepSeek (Anthropic兼容) / Gemini Vision |
| 任务调度 | TaskEngine (自研) + APScheduler |
| 数据源 | httpx 异步 → 新浪/东方财富; akshare 库 (港股) |
| 图片处理 | Pillow (OCR 前压缩) |

## 目录结构

```
AIStock_Pro/
├── CLAUDE.md                              # ← 本文件
├── run_backend.bat                        # 启动脚本
├── backend/
│   ├── .env                               # 环境变量 (API Key, DB 连接)
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py                        # 入口: 路由注册 + 启动生命周期
│   │   ├── framework/                     # [基础设施] 可复用工具, 不包含业务逻辑
│   │   │   ├── config.py                  #   Settings (pydantic-settings)
│   │   │   ├── logger.py                  #   结构化日志 (loguru)
│   │   │   ├── database/
│   │   │   │   └── session.py             #   async engine + session + get_db
│   │   │   ├── tasks/
│   │   │   │   ├── engine.py              #   TaskEngine (注册/调度/强杀/进度)
│   │   │   │   ├── scheduler.py           #   APScheduler cron 管理
│   │   │   │   └── api.py                 #   /api/system/tasks/*
│   │   │   ├── ai/
│   │   │   │   ├── providers/             #   LLM 提供者
│   │   │   │   │   ├── base.py            #     AIProviderProtocol
│   │   │   │   │   ├── doubao.py          #     豆包 Seed API
│   │   │   │   │   ├── gemini.py          #     Gemini Vision API
│   │   │   │   │   └── deepseek.py        #     DeepSeek (Anthropic兼容)
│   │   │   │   └── ocr.py                 #   图片压缩/清理工具
│   │   │   └── agents/
│   │   │       └── base.py                #   BaseAgent (所有领域 Agent 的抽象)
│   │   ├── domain/                        # [领域层] 业务逻辑, 按功能域内聚
│   │   │   ├── market_data/               #   市场数据领域
│   │   │   │   ├── api/routes.py          #     /api/data/* + /api/data/health/* + /api/data/forex/*
│   │   │   │   ├── tasks/sync.py          #     sync_market 任务
│   │   │   │   ├── services/              #     行情同步 + 健康检查
│   │   │   │   └── sources/               #     DataSourceProtocol, DataRouter, Sina, AkShare
│   │   │   ├── portfolio/                 #   持仓管理领域
│   │   │   │   ├── api/                   #     /api/positions/* + /api/ai/*
│   │   │   │   ├── tasks/import_tasks.py  #     ai_recognize 任务
│   │   │   │   └── services/import_service.py # 批量导入写库
│   │   │   ├── quant/                     #   量化分析领域
│   │   │   │   ├── api/indicators.py      #     /api/data/indicators/*
│   │   │   │   ├── tasks/calc.py          #     calc_indicators 任务
│   │   │   │   ├── engine/                #     indicators, patterns, engine
│   │   │   │   └── agents/                #     量化智能体 (V2.0)
│   │   │   ├── research/                  #   投研领域 (V3.0)
│   │   │   │   └── agents/                #     ResearchAgent + supply_chain
│   │   │   └── strategy/                  #   量化策略领域 (V2.0)
│   │   │       └── agents/                #     StrategyAgent
│   │   ├── api/                           # [路由层] 向后兼容层, 逐渐迁入 domain/
│   │   │   ├── tasks.py
│   │   │   ├── data.py
│   │   │   ├── positions.py
│   │   │   └── import_api.py
│   │   ├── core/                          # [遗留] 迁入 framework/ + domain/ 中
│   │   ├── quant/                         # [遗留] 已迁入 domain/quant/engine/, 原文件保留兼容
│   │   └── models/                        # [数据模型层] 全局共享
│   │       ├── models.py                  #   8 张表: Position, MarketData, StockIndicator,
│   │       │                               #   TaskDefinition, TaskExecution, TradeHistory,
│   │       │                               #   ExchangeRate, SystemSetting
│   │       └── schemas.py                 #   Pydantic 响应/请求模型
│   ├── scripts/                           # 迁移、审计、烟雾测试
│   │   ├── smoke_test.py                  #   冒烟测试 (16 个关键 API)
│   │   └── migrate_v5.*.py                #   数据库迁移脚本
│   ├── logs/                              # 运行日志
│   └── temp_lab/                          # 实验脚本 (gitignore)
├── frontend/
│   ├── index.html                         # 指挥中心
│   ├── positions.html                     # 持仓管理 (ECharts K线)
│   ├── data.html                          # 数据中心
│   ├── history.html                       # 执行历史
│   ├── definitions.html                   # 任务定义
│   ├── import.html                        # 智能导入 (OCR+Excel+文本)
│   ├── suggestions.html                   # 调仓建议 (V2.0)
│   ├── research.html                      # AI 投研 (V3.0)
│   ├── css/style.css                      # 暗色主题样式
│   └── js/
│       ├── ui.js                          # 侧边栏+顶栏+市场跑马灯+页面初始化
│       ├── common.js                      # API_BASE + Modal + TaskMonitor
│       └── app.js                         # 指挥中心业务逻辑
└── docs/
    ├── README.md                          # 文档索引入口
    ├── 01_Requirements/                   # 需求与路线图
    ├── 02_Architecture/                   # 架构设计
    ├── 03_API_Specifications/             # API 规格 + 导入模块
    ├── 04_Frontend_UI/                    # 前端设计
    ├── 05_Engineering/                    # 工程规范 + 冒烟测试
    └── Archive/                           # 历史归档
```

## 架构约束 (硬规则)

### DDD 分层边界

```
framework/    → 纯基础设施: 配置/日志/DB/任务引擎/AI提供者/Agent基座。
                不依赖业务模块。允许被所有层导入。
domain/       → 业务逻辑, 按功能域内聚 (market_data/portfolio/quant/research/strategy)。
                每个 domain 内部 api/tasks/services/sources 自包含。
                不同 domain 之间禁止互相导入。编排逻辑在 main.py 处理。
models/       → ORM 模型 + Pydantic Schema。纯数据结构, 不依赖 framework/ 和 domain/。
api/          → [过渡期] API 路由文件仍在 api/ 下, 逐步迁入各 domain 的 api/ 子目录。
core/ + quant/ → [遗留] 原代码已迁入 framework/ + domain/, 原文件保留向后兼容。
```

### 依赖方向
```
domain/  →  framework/  →  models/
(domain/ 不 import 其他 domain/)
(api/ 路由 → domain/ 服务)
```

### 违规示例
- ❌ `api/` 里直接写 `pd.DataFrame` 加工逻辑
- ❌ `domain/quant/` import `domain/portfolio/`
- ❌ `framework/` import `domain/` 或 `models/` 做业务判断
- ❌ 裸 `asyncio.create_task()` 绕开 TaskEngine

## 编码规范

### 导入
- **绝对导入**: 一律 `from app.framework.config import settings`
- **导入顺序**: 标准库 → 第三方库 → 本地模块
- **新代码使用 framework/domain 路径**: `from app.domain.market_data.sources.router import data_router`

### 异步
- 所有 DB 操作使用 `async_session` / `AsyncSession`
- I/O 密集型操作（行情抓取、AI 调用）必须异步化
- 后台任务通过 `TaskEngine.run_task(task_code, params={...})` 启动

### 日志
```
[🚀] 系统/模块启动    [✅] 成功完成
[❌] 异常/错误        [⚠️] 逻辑警告
[🛑] 任务被强杀       [🧹] 清理/自愈
```

## 关键模块速查

### 任务引擎
```python
from app.framework.tasks.engine import task_manager
task_id = await task_manager.run_task("sync_market", params={"mode": "AUTO"})
```
已注册任务: `sync_market`(行情同步), `calc_indicators`(指标重算), `ai_recognize`(AI识别)

### 数据源
```python
from app.domain.market_data.sources.router import data_router
# 多源自动降级: AkShare → Sina
df = await data_router.get_daily_data(stock_code, days=120)
```

### AI 识别
```python
from app.core.ai_service import AIImportService  # 待迁入 domain/portfolio/services/
results = await AIImportService.recognize_stock_image(base64_image)
```

### 前端
- `Modal.alert(title, msg)` / `Modal.confirm(title, msg)` — 暗色弹窗 (common.js)
- `UI_COMPONENTS.updateMarketTicker()` — 刷新市场跑马灯 (ui.js)

## 冒烟测试

每次提交前:
```bash
python scripts/smoke_test.py
```
覆盖 16 个关键 API 端点, 全部 PASS 方可提交。

## 开发流程

1. 确认需求归属领域 (market_data/portfolio/quant/research/strategy)
2. 如需新表 → 修改 `models/models.py` → 写迁移脚本 `scripts/migrate_v5.X.py`
3. 业务逻辑 → `domain/<领域>/services/`
4. 暴露接口 → `domain/<领域>/api/` 或 `api/` (过渡期)
5. 前端页面 → 遵循模板: `<body data-page-id>` + sidebar + topbar + workspace
6. `main.py` 注册路由 (如有新增)
7. `smoke_test.py` 通过
8. `git commit`
