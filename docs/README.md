# AIStock Pro 文档索引

> 最后更新: 2026-05-17

---

## 目录结构

```
docs/
├── README.md                              ← 你在这里
├── 01_Requirements/                       需求与路线图
│   ├── MASTER_STRATEGY.md                 产品迭代路线图 (V1.0 → V2.0 → V3.0)
│   └── 2026-05-16_Task_V5_Spec.md         任务管理引擎 V5.0 需求规格 (Gemini)
├── 02_Architecture/                       架构设计
│   ├── architecture_v2.md                 系统核心拓扑与 DDD 分层设计
│   └── Task_V5_Engine_Design.md           任务引擎 V5.0 详细设计
├── 03_API_Specifications/                 API 与模块技术规格
│   └── data_sync_spec.md                  数据同步模块规格书 V2.0 (含 API 端点清单)
├── 04_Frontend_UI/                        前端设计
│   └── (待填充)
├── 05_Engineering/                        工程规范
│   └── engineering_standards.md           核心工程标准 V2.0 (含自检清单)
├── 06_Quant_Research/                     量化研究
│   └── (待填充)
└── Archive/                               历史归档
    └── data_sync_spec_V1.md               数据同步规格书 V1.0 (已废弃, 参考用)
```

---

## 按阅读场景导航

### 新人快速了解项目
1. `01_Requirements/MASTER_STRATEGY.md` — 这个项目要做什么
2. `02_Architecture/architecture_v2.md` — 系统怎么设计的
3. `05_Engineering/engineering_standards.md` — 代码怎么写的

### 开始一个模块开发
1. 在 `01_Requirements/` 确认需求是否已有文档
2. 在 `02_Architecture/` 确认架构约束
3. 在 `03_API_Specifications/` 查找或新建模块规格书
4. 开发时严格遵守 `05_Engineering/engineering_standards.md`

### 提交前自检
1. 对照 `05_Engineering/engineering_standards.md` §9 检查清单逐项过
2. 如有新的 API/模块，在 `03_API_Specifications/` 补规格文档

---

## 文档模板

新增文档时，文件名遵循 `<日期或版本>_<主题>.md` 格式，放在对应目录下：

| 文档类型 | 放入目录 | 示例文件名 |
|----------|----------|------------|
| 功能需求 | `01_Requirements/` | `2026-05-17_Data_Sync_Requirements.md` |
| 架构设计 | `02_Architecture/` | `Plugin_System_Design.md` |
| 模块规格 | `03_API_Specifications/` | `Position_Management_Spec.md` |
| 前端设计 | `04_Frontend_UI/` | `Dashboard_UI_Redesign.md` |
| 量化研究 | `06_Quant_Research/` | `VAP_Algorithm_Research.md` |
