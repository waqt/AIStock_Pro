# AIStock Pro 核心工程标准 (V2.0)

## 1. 架构原则 (Architecture)

本项目遵循 **领域驱动设计 (DDD)** 与 **整洁架构 (Clean Architecture)** 原则。

| 层 | 目录 | 职责 | 禁止 |
|----|------|------|------|
| 路由接入层 | `api/` | 参数校验、调用应用服务、返回响应 | 禁止包含任何业务逻辑 |
| 应用服务层 | `domain/` | 业务编排、跨领域调用 | 禁止直接操作 HTTP 对象 |
| 领域逻辑层 | `quant/` | 核心算法、量化策略、数据加工 | 禁止依赖 `api/` |
| 基础设施层 | `core/` | 数据库、任务管理器、外部 SDK | 禁止依赖业务模块 |
| 数据模型层 | `models/` | ORM 模型、Pydantic Schema | 禁止依赖任何其他模块 |

**依赖方向**: `api` → `domain` → `quant` → `core` ← `models` (单向，不可逆)

---

## 2. 开发前置检查清单 (Pre-Development Checklist)

每次开始编码前，必须确认以下事项：

- [ ] **需求归属层**: 明确本次改动属于哪个 DDD 层（api/domain/quant/core/models）
- [ ] **影响范围**: 列出会受影响的文件清单（路由、模型、前端页面）
- [ ] **是否需要新表/改表**: 如需变更数据模型 → 先设计 schema 再写代码
- [ ] **是否需要新 API 路由**: 如新增端点 → 确认 `main.py` 注册
- [ ] **前端联动**: 如有新增/变更 API → 同步更新前端调用
- [ ] **是否破坏现有功能**: 检查改动是否影响已有接口的返回结构

---

## 3. API 路由开发规范 (API Route Spec)

### 3.1 路由注册
- 每个路由文件必须在 `backend/app/main.py` 中 `app.include_router()` 注册
- 路由 prefix 命名规则: `/api/<领域>/<资源>`
- 使用 tags 参数分组，方便 Swagger 文档归类

### 3.2 端点设计原则
- **GET**: 只读查询，使用 `Depends(get_db)` 注入 session
- **POST**: 触发操作/任务，返回 `{message, task_id}`
- **DELETE**: 取消/清理，需确认 TaskManager 状态同步
- **响应模型**: 查询类接口必须定义 Pydantic `response_model`

### 3.3 参数校验
- 使用 Pydantic V2 `BaseModel` 定义请求体
- 复杂参数使用 `Field()` 添加约束
- 路径参数使用类型注解 (如 `task_id: str`)

### 3.4 错误处理
```python
try:
    result = await domain_service.do_something()
except DomainError as e:
    raise HTTPException(status_code=400, detail=str(e))
except Exception as e:
    logger.error(f"[❌] ...: {e}")
    raise HTTPException(status_code=500, detail="内部服务错误")
```

---

## 4. 数据库变更规范 (Database Migration Rules)

### 4.1 模型变更流程
1. **修改 `models.py`** — 添加/修改/删除 ORM 模型或字段
2. **启动验证** — `Base.metadata.create_all` 自动处理新表（不会 ALTER 已有表）
3. **迁移脚本** — 涉及 ALTER/DROP/数据迁移时，在 `backend/scripts/` 编写独立迁移脚本
4. **数据完整性检查** — 迁移后运行 `check_integrity.py` 验证

### 4.2 必须遵守的规则
- **禁止直接修改生产库** — 所有 DDL 变更必须可追溯
- **新字段必须有默认值** — 或允许 NULL，否则历史数据插入报错
- **唯一约束** — `Position.stock_code` 必须 unique；`MarketData(stock_code, trade_date)` 组合唯一
- **JSON 字段** — `StockIndicator.data_json` 和 `logic_chain` 使用 JSON 类型，写入前确保可序列化

### 4.3 迁移脚本模板
```python
# backend/scripts/migrate_<描述>.py
import asyncio
from app.core.database import async_session, engine
from app.core.logger import logger

async def migrate():
    async with engine.begin() as conn:
        # DDL 操作
        pass
    logger.info("[✅] Migration complete.")

if __name__ == "__main__":
    asyncio.run(migrate())
```

---

## 5. 任务管理组件 (TaskManager)

所有后台异步任务**必须**通过 `backend/app/core/task_manager.py` 进行生命周期管理。

- **启动**: 调用 `TaskManager.start_task(name, coro_func, ...)`
- **运行**: 任务函数签名 `async def func(task_id: str, **kwargs)`
- **强杀**: `TaskManager.stop_task(task_id)` → 触发 `asyncio.CancelledError`
- **自愈**: 系统启动时自动将残留 `RUNNING`/`PENDING` 标记为 `CANCELLED`
- **检查点**: 任务函数内部必须定期 `await asyncio.sleep(0)` 以响应取消信号

### 任务状态机
```
PENDING → RUNNING → SUCCESS
                 → FAILED
                 → CANCELLED
```
状态限定值: `PENDING`, `RUNNING`, `SUCCESS`, `FAILED`, `CANCELLED`（不允许其他值）

---

## 6. 前端开发规范 (Frontend Standards)

### 6.1 页面模板
每个 HTML 页面必须包含以下结构：
```html
<body data-page-id="xxx">  <!-- 页面标识，ui.js 用来高亮当前导航 -->
  <div class="app-container">
    <aside class="sidebar"></aside>          <!-- 由 ui.js 自动填充 -->
    <main class="main-content">
      <div class="top-bar"></div>            <!-- 由 ui.js 自动填充 -->
      <div class="workspace"><!-- 正文 --></div>
    </main>
  </div>
  <script src="js/ui.js"></script>          <!-- 第一加载 -->
  <script src="js/common.js"></script>      <!-- 第二加载: API_BASE, initCommon -->
  <!-- 页面业务 JS 放在最后 -->
</body>
```

### 6.2 JS 加载顺序 (关键！)
```
1. ui.js       → 定义 UI_COMPONENTS, initPageComponents()
2. common.js   → 定义 API_BASE, initCommon(), updateTaskList()
3. 页面 JS     → 此时所有依赖已就绪，可安全引用 API_BASE
```

### 6.3 API 调用约定
- 所有 API 路径以 `API_BASE` 开头: `` `${API_BASE}/positions` ``
- 数据获取: `async/await` + `try/catch`
- 错误处理: `console.error()` + 用户可见的提示（alert 或状态区）
- 加载态: 按钮禁用 + spinner 动画 + 完成后恢复

### 6.4 页面状态检查清单
新增前端页面时确认：
- [ ] `<body data-page-id>` 与 `ui.js` 中的 menuItems id 对应
- [ ] CSS 类名使用项目变量 (`var(--bg-card)`, `var(--text-dim)` 等)
- [ ] 任务监控按钮由 `common.js` 自动注入，不需要手动加
- [ ] 如果用 ECharts，在 `<head>` 引入 CDN，容器设置宽高
- [ ] 响应式: 使用 `var(--font-mono)` 做数字格式化

---

## 7. 命名与代码规范

- **导入**: 统一绝对路径导入，如 `from app.core.database import async_session`
- **数据库会话**: 统一使用 `async_session` 进行异步操作
- **异步函数**: I/O 操作一律 `async def`
- **任务函数**: 必须接收 `task_id: str` 作为第一个参数
- **模型字段**: 使用 `snake_case`；数据库列名由 SQLAlchemy 自动映射

---

## 8. 日志规范 (Structured Logging)

> 目标是让日志可直接 grep 并定位问题，不需要阅读上下文代码。

| 场景 | 前缀 | 示例 |
|------|------|------|
| 系统/模块启动 | `[🚀]` | `[🚀] AIStock_Pro System Initializing...` |
| 成功完成 | `[✅]` | `[✅] TaskManager: Finished. 42 stocks analyzed.` |
| 异常/错误 | `[❌]` | `[❌] TaskManager: Error: {exception}` (必须附 trace) |
| 逻辑警告 | `[⚠️]` | `[⚠️] Domain: Stock 600000 缺少行情数据，已跳过` |
| 任务强杀 | `[🛑]` | `[🛑] Task {id} was physically cancelled.` |
| 清理/自愈 | `[🧹]` | `[🧹] Found 3 zombie tasks. Cleaning up...` |

---

## 9. 自测与代码审查检查清单 (Self-Check Before Commit)

### 代码质量
- [ ] 无 `print()` 残留（全部使用 `logger`）
- [ ] 无 `import pdb; pdb.set_trace()` 残留
- [ ] 无注释掉的死代码块
- [ ] 新增代码遵循 DDD 分层，没有跨层违规
- [ ] 导入全部使用绝对路径

### 功能正确性
- [ ] 新 API 端点已在 `main.py` 注册
- [ ] 数据库模型变更后 `create_all` 不会报错
- [ ] 前端新增/变更的 API 路径与后端一致
- [ ] JSON 序列化字段类型与前端期望一致

### 安全
- [ ] 无硬编码密码/API Key（从 `.env` 或 `settings` 读取）
- [ ] SQL 查询使用参数化（SQLAlchemy ORM 自动保证）
- [ ] 前端无 XSS（不使用 `innerHTML` 插入用户输入内容）

### 性能
- [ ] 大数据量查询有分页/limit
- [ ] 批量操作使用原子事务而非逐条 commit
- [ ] 无阻塞同步调用（如 `requests.get` 应改为 `httpx.AsyncClient`）

---

## 10. 任务分类与执行流程 (Workflow)

### A. 功能迭代类
1. **需求整理**: 明确业务目标与边界
2. **架构评审**: 评估对现有 DDD 模型的影响，确认归属层
3. **详细设计**: 确定接口协议、数据表变动、领域任务逻辑
4. **代码开发**: 遵循 DDD 规范编写代码
5. **自测检查**: 通过日志和终端验证核心链路（必须过第 9 节检查清单）
6. **上线发布**: 合并代码并更新文档

### B. Bug 修复类
1. **确认缺陷**: 捕获报错日志或复现截图
2. **RCA 根因分析**: 定位故障发生的具体代码层
3. **修复方案**: 针对性修复，评估连锁影响
4. **开发与自测**: 修复并验证
5. **规范迭代**: 如该 Bug 具有代表性 → 更新本规范以防止重复

---

*Document Updated: 2026-05-16 (V2.0)*
*V2.0 新增: 开发前置检查清单、API 路由规范、数据库变更流程、前端开发规范、自测检查清单*
