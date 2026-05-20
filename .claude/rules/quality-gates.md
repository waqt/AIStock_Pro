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
- [ ] Python 语法检查: `python -m py_compile <changed_files>`
- [ ] 新端点: curl 测试返回正确
- [ ] 前端: 按钮点击 → 网络请求 → 页面渲染 完整链路
- [ ] 数据库: 新表 `create_all` 自动建表

## 禁止事项

- ❌ 不查 Inventory 直接改 → 遗漏关联功能
- ❌ 改完不测试端到端 → 前端 JS 报错 `/by zero/undefined`
- ❌ 改完不更新文档 → 文档与代码脱节
- ❌ 假设字段存在 → TradeHistory.profit_loss 不存在
- ❌ 不注意 Decimal/Float 类型冲突 → MySQL ORM 常见坑
- ❌ 删除前端元素不检查 JS 引用 → `document.getElementById` 返回 null
