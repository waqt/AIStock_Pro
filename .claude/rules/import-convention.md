# 导入与代码规范

## 导入路径

- **绝对导入**: 一律使用 `from app.xxx import`, 禁止 `from ..xxx import`
- **新代码使用 framework 路径**: 
  - `from app.framework.config import settings`
  - `from app.framework.logger import logger`
  - `from app.framework.database.session import async_session`
  - `from app.framework.tasks.engine import task_manager`
- **旧路径已废弃**:
  - ~~`from app.core.config import`~~ → `from app.framework.config import`
  - ~~`from app.core.database import`~~ → `from app.framework.database.session import`
  - ~~`from app.core.logger import`~~ → `from app.framework.logger import`
  - ~~`from app.core.task_manager import`~~ → `from app.framework.tasks.engine import`

## 导入顺序

```python
# 1. 标准库
import asyncio, os, json

# 2. 第三方
import httpx
from sqlalchemy import select

# 3. 本地框架
from app.framework.config import settings
from app.framework.logger import logger

# 4. 本地领域
from app.domain.market_data.sources.router import data_router

# 5. 本地模型
from app.models.models import Position
```

## 命名

- 任务状态: `PENDING`, `RUNNING`, `SUCCESS`, `FAILED`, `CANCELLED`
- ORM 模型: 继承 `Base` (来自 `app.framework.database.session`)
- 异步函数: `async def`, I/O 必须异步化
- 路由函数: `async def` + 类型注解

## 禁止事项

- ❌ `print()` — 使用 `logger.info/warning/error`
- ❌ 裸 `asyncio.create_task()` — 使用 `task_manager.run_task()`
- ❌ `requests.get()` (同步) — 使用 `httpx.AsyncClient` (异步)
- ❌ 硬编码 API Key / 连接串 — 从 `settings` 或 `.env` 读取
