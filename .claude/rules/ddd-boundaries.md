# DDD 分层边界规则

## 依赖方向

```
domain/*  →  framework/*  →  models/
(main.py 编排所有层, 是唯一可以跨层导入的地方)
```

## 各层允许的导入

### framework/ — 纯基础设施
- ✅ `from app.framework.config import settings`
- ✅ `from app.framework.logger import logger`
- ✅ `from app.framework.database.session import async_session, get_db`
- ✅ `from app.framework.tasks.engine import task_manager`
- ✅ `from app.framework.ai.providers.* import`
- ❌ 禁止 `from app.domain.* import` (框架不能依赖业务)
- ❌ 禁止 `from app.models.* import` 做业务判断

### domain/<领域>/ — 业务逻辑
- ✅ `from app.framework.* import`
- ✅ `from app.models.models import` (领域内模型)
- ❌ 禁止 `from app.domain.<其他领域> import` (领域间不能互相依赖)
- ❌ 禁止 `from fastapi import` (路由逻辑在 api/ 子目录)

### models/ — 纯数据结构
- ✅ `from app.framework.database.session import Base`
- ❌ 禁止 import framework/ 或 domain/ 的任何其他模块

## 检查方式

每次改动后, 在 backend/ 目录下执行:
```bash
# 检查 domain 间互相引用 (违规)
grep -rn "from app\.domain\." app/domain/ --include="*.py" | grep -v "domain.*from app\.domain\.\w*\.\w* import"
# 检查 framework 依赖 domain (违规)
grep -rn "from app\.domain\." app/framework/ --include="*.py"
```

## 新增 domain

1. `domain/<name>/api/` — FastAPI 路由
2. `domain/<name>/tasks/` — @task_manager.register 任务
3. `domain/<name>/services/` — 业务逻辑
4. `domain/<name>/agents/` — Agent 实现 (继承 BaseAgent)
5. `domain/<name>/sources/` — 外部数据源接口 (如有)
