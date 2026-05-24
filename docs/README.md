# AIStock Pro 文档索引

> 版本 V5.6 | 最后更新: 2026-05-21

---

## 目录结构

```
docs/
├── README.md                              ← 你在这里
├── 01_Requirements/                       需求与路线图
│   ├── MASTER_STRATEGY.md                 产品迭代路线图
│   ├── 2026-05-16_Task_V5_Spec.md         任务管理引擎需求规格
│   └── project_retrospective.md           项目复盘
├── 02_Architecture/                       架构设计
│   ├── architecture_v2.md                 系统核心拓扑与 DDD 分层设计
│   └── Task_V5_Engine_Design.md           任务引擎 V5.0 详细设计
├── 03_API_Specifications/                 API 与模块技术规格
│   ├── System_Feature_Inventory.md         ★ 系统功能清单 (主力文档)
│   ├── Data_Center_Design_V2.md           数据中心 V2.0 设计
│   ├── AI_Research_Architecture.md         AI 投研架构
│   ├── data_sync_spec.md                  行情同步规格
│   └── import_spec.md                     智能导入规格
├── 04_Frontend_UI/                        前端设计
├── 05_Engineering/                        工程规范
│   └── engineering_standards.md           核心工程标准 (含自检清单)
├── 06_Quant_Research/                     量化研究
│   └── quant_indicator_system.md           ★ 量化指标体系完整文档
└── Archive/                               历史归档
    └── data_sync_spec_V1.md               数据同步 V1.0 (已废弃)
```

---

## 按场景导航

### 新人入门
1. `01_Requirements/MASTER_STRATEGY.md` — 项目愿景
2. `02_Architecture/architecture_v2.md` — 系统架构
3. `05_Engineering/engineering_standards.md` — 编码规范

### 量化指标开发 (高优先级, 已成熟)
1. `06_Quant_Research/quant_indicator_system.md` — ★ 指标体系完整说明
2. `.claude/rules/quant-architecture.md` — 架构总结 + 踩坑记录
3. `.claude/rules/quant-indicator-standards.md` — 新增指标检查清单

### AI 开发工具接续
1. 根目录 `CLAUDE.md` — 项目全局上下文 (技术栈/目录结构/模块速查)
2. `.claude/rules/` — DDD边界 / 前端规范 / 日志标准 / 量化架构
3. `03_API_Specifications/System_Feature_Inventory.md` — 功能清单

### 开始新模块开发
1. `03_API_Specifications/System_Feature_Inventory.md` 确认功能是否已有
2. `02_Architecture/architecture_v2.md` 确认架构约束 (DDD 单向依赖)
3. `.claude/rules/ddd-boundaries.md` 确认导入规则
4. 开发后更新 `System_Feature_Inventory.md`

### 提交前自检
1. `05_Engineering/engineering_standards.md` §9 检查清单
2. `py_compile` 通过所有改动文件
3. `smoke_test.py` 16 API 通过
4. 如有架构变更, 更新 `CLAUDE.md`

---

## 文档模板

新增文档放入对应目录:

| 文档类型 | 目录 | 命名示例 |
|----------|------|---------|
| 功能需求 | `01_Requirements/` | `YYYY-MM-DD_主题_Requirements.md` |
| 架构设计 | `02_Architecture/` | `子系统_设计.md` |
| 模块规格 | `03_API_Specifications/` | `模块名_Spec.md` |
| 前端设计 | `04_Frontend_UI/` | `页面_UI_Redesign.md` |
| 量化研究 | `06_Quant_Research/` | `策略名_研究报告.md` |
