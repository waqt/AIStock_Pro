# AI 投研系统 V5.7 → V6.0 升级设计

> 对标 GPT 投研提示词 V2 (11 步系统动力学增强版)
>
> 当前快照: git log docs/02_Architecture/AI_Research_System_V5.7_Upgrade_Design.md

## 文档索引

| 文件 | 内容 |
|------|------|
| [00_Overview](00_Overview.md) | 系统定位、分析哲学、现状全景映射 |
| [01_Step1_Macro](01_Step1_Macro.md) | 宏观与全球资本周期 (含实施状态) |
| [02_Step2_Gatekeeper](02_Step2_Gatekeeper.md) | Pipeline 看门人 — 产业 Alpha 排序器 |
| [03_Step3_SupplyChain](03_Step3_SupplyChain.md) | 产业链系统拆解 |
| [04_Step4_SystemDynamics](04_Step4_SystemDynamics.md) | 系统动力学 + 非线性推演 + 核心资产筛选 |
| [05_Step7_11_Remaining](05_Step7_11_Remaining.md) | Steps 7-11: 财务→估值→预期差→风险→结论 |
| [06_GPT_Reviews](06_GPT_Reviews.md) | GPT 评审反馈、system_dynamics 输出、验证框架 |
| [07_Implementation](07_Implementation.md) | 实施优先级、文件变更、验收标准 |

## 设计原则

1. **LLM 定性, 程序化定量**: Step 2 做归类, Step 3-8 做计算
2. **渐进增强**: 不改架构, Agent 内部升级
3. **版本管理**: 每次改前 commit, Write/Edit 直写文件

## 相关文档

- [V7.0 未来蓝图](../AI_Research_System_V7.0_Future_Blueprint.md)
- [IDEA 优化库](../../99_IDEA_BACKLOG.md)
- [CLAUDE.md](../../../CLAUDE.md) — LLM Agent 设计原则
