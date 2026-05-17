# 数据模型变更规则

## 修改 models.py 时的强制步骤

1. **修改 `backend/app/models/models.py`** — 添加/修改 ORM 字段
2. **同步 `backend/app/models/schemas.py`** — Pydantic 响应/请求模型
   - 如果字段允许 NULL → Schema 中用 `Optional[type] = None`
   - 如果字段改名 → 检查所有引用方
3. **写迁移脚本** `backend/scripts/migrate_v5.X.py`
   - 使用 `ALTER TABLE ... ADD COLUMN` (MySQL 不支持 IF NOT EXISTS)
   - 用 try/except 捕获 "Duplicate column" 跳过已存在的列
4. **运行迁移**: `python scripts/migrate_v5.X.py`
5. **检查前端** — 如果字段变更影响 API 返回结构, 同步更新 JS 渲染代码

## 字段规则

- **可为空**: 用 `nullable=True`, Schema 用 `Optional`
- **默认值**: 数字用 `default=0.0`, 字符串用 `default=""`, 不要用 `None` + `nullable=True`
- **Float → DB**: 使用 `Float` (MySQL DOUBLE), 不要用 `DECIMAL` (SQLAlchemy 2.0 异步兼容问题)
- **Unique 约束**: 用 `UniqueConstraint('col1', 'col2', name='uq_xxx')`

## 常见错误

- ❌ 只改 models.py 不写迁移脚本 → `create_all` 不 ALTER 已有表, 新列不会被创建
- ❌ 给必填字段设 `nullable=False` 但无默认值 → 历史数据 INSERT 报错
- ❌ DB 字段 `NULL` 但 Schema `float` (不能为 None) → API 500
- ❌ 改表后不冒烟测试 → 生产才发现前端报错

## 新增整表的流程

1. 在 `models.py` 定义 ORM 类 (继承 `Base`)
2. `Base.metadata.create_all` (启动时自动执行) 会自动建新表
3. 如果已有历史数据需要迁移 → 在迁移脚本中 `INSERT ... SELECT`
