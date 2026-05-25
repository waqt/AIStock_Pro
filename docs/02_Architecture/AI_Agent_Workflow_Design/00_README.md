# 智能投研分析智能体工作流 — 综合设计方案

> **版本**: V1.0 | **日期**: 2026-05-25
> **范围**: AIStock Pro V6.0 → V7.0 全栈演进
> **基线**: 现有 V5.7 系统 (6 Agent + DAG Pipeline + 14 张表 + 15 页前端)

---

## 系统定位

**AIStock Pro 产业链投研智能体** — 面向个人投资者的供给侧产业链深度分析系统。

核心差异化能力:
- **系统动力学推演**: 资源约束 → 供给重构 → 利润迁移 → 瓶颈预测
- **多智能体协作**: 11 个专业 Agent 按 DAG 编排, 各司其职
- **LLM 定性 + 程序化定量**: LLM 做归类推理, 代码做评分计算
- **产业链穿透分析**: L1-L4 瓶颈下钻, 隐性受益者发现
- **可追溯投研过程**: 每个结论可溯源到搜索结果/数据源/LLM 推理链

---

## 设计文档索引

| 文件 | 内容 |
|------|------|
| [01_System_Overview](01_System_Overview.md) | 系统全景、现状差距矩阵、技术栈、设计原则 |
| [02_Agent_Design](02_Agent_Design.md) | 8 个 Agent 详细设计: I/O Schema、协作数据流、推演方法论 |
| [03_Backend_Design](03_Backend_Design.md) | 后端 DDD 架构、新增模块、Pipeline 基础设施、API 设计 |
| [04_Database_Design](04_Database_Design.md) | 5 张新表 DDL、4 张表改造、数据流向、索引策略 |
| [05_Frontend_Design](05_Frontend_Design.md) | research.html 升级、2 个新页面 (pipeline/validation)、组件设计 |
| [06_Implementation_Roadmap](06_Implementation_Roadmap.md) | 4 阶段实施路线图、验收标准、风险评估 |

## 与现有文档的关系

| 现有文档 | 关系 |
|---------|------|
| [AI_Research_System/](../AI_Research_System/) | V5.7→V6.0 逐 Step 升级设计 (本方案的输入基线) |
| [AI_Research_System_V5.7_Upgrade_Design.md](../AI_Research_System_V5.7_Upgrade_Design.md) | 单一大文件版本的升级设计 (本方案拆分并扩展) |
| [AI_Research_System_V7.0_Future_Blueprint.md](../AI_Research_System_V7.0_Future_Blueprint.md) | V7.0 远景蓝图 (本方案预埋了数据库表) |
| [03_API_Specifications/AI_Research_Architecture.md](../../03_API_Specifications/AI_Research_Architecture.md) | 现有多智能体架构说明 |
| [03_API_Specifications/System_Feature_Inventory.md](../../03_API_Specifications/System_Feature_Inventory.md) | V5.6 全系统功能清单 (170+ 功能点) |

## 设计原则

1. **渐进增强**: 不改现有架构骨架, Agent 内部升级 prompt/逻辑
2. **LLM 定性, 程序化定量**: Step 2 做归类, Step 3-8 做计算
3. **案例驱动**: GPT 投研提示词 V2 的产业案例嵌入 Agent few-shot 模板
4. **可独立测试**: 每个 Agent 可单独 curl 验证, 互不阻塞
5. **确定性优先**: 关键结论由程序化逻辑生成, LLM 只做辅助推演
6. **可追溯**: 每个判断可回溯到搜索结果/DB 数据/LLM 推理链
7. **向后兼容**: 现有 API / 前端 / 数据库不受破坏性影响
