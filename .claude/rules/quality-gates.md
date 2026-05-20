# 开发质量门禁

## 实施前 (Plan → Code)

### 1. 关联影响分析 (必须)
每次改动前，查阅 `docs/03_API_Specifications/System_Feature_Inventory.md`，回答三个问题：
- 这个改动影响了哪些已有功能？（如：改 sync 端点 → 检查前端调用、任务定义、健康检查）
- 这个改动涉及哪些关联模块？（如：加指标算子 → 策略是否声明了依赖？计算引擎是否加载？前端是否展示？）
- 数据模型是否受影响？（如：改 Position 字段 → Schema 是否同步？迁移脚本是否需要？）

### 2. 设计约束检查 (必须)
查阅对应的规则文件:
- 指标/策略 → `.claude/rules/quant-module.md`
- 前端 → `.claude/rules/frontend-pattern.md`
- 模型变更 → `.claude/rules/model-change.md`
- DDD 边界 → `.claude/rules/ddd-boundaries.md`
- 日志规范 → `.claude/rules/logging-standards.md`

### 3. 数据流追踪 (复杂改动必须)
对于涉及多个文件的改动, 画出数据流:
```
前端按钮 → API端点 → Service/Engine → DB表 → 返回 → 前端渲染
```
每步标注改动点, 确保不遗漏。

## 实施后 (Code → Commit)

### 4. 关联功能验证 (必须)
改动完成后, 对照 Inventory 文档, 逐一检查:
- [ ] 相关 API 端点是否正常？
- [ ] 相关前端页面是否正常？
- [ ] 数据表是否需要迁移？
- [ ] 文档是否需要更新？

### 5. 文档更新 (必须)
- `System_Feature_Inventory.md`: 新增/修改的功能点及时更新状态
- `CLAUDE.md`: 如架构变更, 同步更新
- `Data_Center_Design_V2.md`: 数据中心相关改动同步

### 6. 自测清单 (必须)

#### 6.1 语法与导入
- [ ] `python -m py_compile <changed_files>` 无错误
- [ ] 新增 import 路径有效 (IDE 或 `python -c "from app.xxx import yyy"`)

#### 6.2 API 接口测试 (轻量改动)
以下情况 curl 足够:
- 查询类端点 (GET): 返回数据结构正确即可
- 返回静态数据的端点

```bash
curl -s "http://127.0.0.1:8000/api/xxx" | python -c "assert 'key' in data"
```

#### 6.3 数据完整性测试 (数据写入类改动 ★ 必须)
涉及 **数据写入/更新/同步** 的改动, curl 验证 API 返回≠ 数据真正落库。必须写 `temp_lab/` 脚本验证:

```python
# temp_lab/test_xxx.py — 端到端验证模板
import asyncio, sys
sys.path.insert(0, r'E:\workspace\AIResearch\AIStock_Pro\backend')
from app.framework.database.session import async_session
from app.models.models import TargetTable
from sqlalchemy import select

async def main():
    async with async_session() as db:
        # 1. 触发操作 (或调 API)
        # 2. 查 DB 验证数据确实落库
        res = await db.execute(select(TargetTable).where(...))
        row = res.first()
        # 3. 打印验证结果
        print(f"Rows: {len(res.all())}  Expected: >0  PASS: {row is not None}")
        # 4. 验证字段值正确
        assert row.field is not None, "field should not be NULL"

asyncio.run(main())
```

**验证标准**: 不是"API返回success", 而是"DB中数据正确":
- [ ] 数据行数符合预期 (写入 N 行 → 查 count = N)
- [ ] 关键字段非空 (名称/价格/日期 ≠ NULL/空字符串)
- [ ] 日期正确 (latest_date 是今天/期望的日期)
- [ ] 关联表联动正确 (如 watchlist.name 与 stock_info.name 一致)

#### 6.4 前端链路测试
- [ ] 按钮点击 → 浏览器 DevTools Network 面板确认 API 调用成功
- [ ] 页面数据刷新后与 DB 一致
- [ ] 无 JS console 报错 (`undefined`, `is not a function` 等)

## 禁止事项

- ❌ 不查 Inventory 直接改 → 遗漏关联功能
- ❌ 改完不测试端到端 → 前端 JS 报错 `/by zero/undefined`
- ❌ 改完不更新文档 → 文档与代码脱节
- ❌ 假设字段存在 → TradeHistory.profit_loss 不存在
- ❌ 不注意 Decimal/Float 类型冲突 → MySQL ORM 常见坑
- ❌ 删除前端元素不检查 JS 引用 → `document.getElementById` 返回 null
- ❌ 用 curl 验证数据写入操作 → curl 只测API表面, 需查DB验证落库
