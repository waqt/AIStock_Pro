# AI 投研系统 V5.7 → V6.0 升级设计文档

> 对标 GPT 投研提示词 V2（11 步系统动力学增强版），在现有 6 Agent + DAG Pipeline 架构上渐进增强。

---

## 系统定位

**AIStock Pro 产业链分析专家** — 针对投资驱动的供给侧行业分析系统。


### 分析哲学

核心能力:
- 宏观周期分析 / 产业链分析 / CAPEX 周期分析
- 系统动力学分析 / 供需分析 / 资源约束分析
- 利润池迁移分析 / 非线性产业链推演
- 全球竞争格局分析

必问问题:
1. **谁最缺** — 供给刚性最高的环节在哪？
2. **谁拥有定价权** — 利润池集中在谁手里？
3. **谁控制供给** — 产能扩张的决定权在谁？
4. **谁受益于供给收缩** — 产业瓶颈的隐藏受益者？
5. **谁受益于资源重新分配** — CAPEX/产能/利润的迁移方向？

寻找目标:
1. 高景气行业 → Step 2 (MarketScanner) + `prosperity_type` 判别
2. 核心利润池 → Step 3 (SupplyChainHacker) + `profit_pool_share` 量化
3. 产业瓶颈 → Step 3 (bottleneck) + Step 4 (scarcity_ranking)
4. 隐藏受益者 → Step 4+5 (_second_level_analysis)
5. 市场预期差 → Step 9 (ExpectationGapAgent)
6. 全球核心资产 → Step 6 (top_picks) + Step 8 (global_peer_comparison)

---

## 一、现状全景映射

```
GPT V2 11 步工作流                     AIStock Pro Agent              完成度    升级方向
══════════════════════════════════════════════════════════════════════════════════════
Step 1  宏观与全球资本周期              GlobalCapexScanner             30%      Prompt 重写
Step 2  行业景气度分析                  MarketScanner                   60%      Prompt 增强
Step 3  产业链系统拆解                  SupplyChainHacker (Phase 1)     70%      Prompt 重写
Step 4  系统动力学与资源约束分析         _second_level_analysis          10%      Prompt 彻底重写
Step 5  非线性产业链推演 (5层+)         _second_level_analysis (同上)   10%      合并到 Step 4
Step 6  核心资产筛选                    top_picks 程序化逻辑            90%      ✅ 已完成
Step 7  财务质量与盈利能力              FinancialAuditor                85%      小增强
Step 8  估值体系                        ValuationPricer                 85%      ✅ 已完成
Step 9  市场预期差与资金面              ❌ 不存在                        0%      新增 Agent
Step 10 风险分析                        LLM 合成 + 硬编码兜底           40%      Prompt 增强
Step 11 最终投资结论                    _synthesize_basic               80%      报告模板补一节
```

---

## 二、升级步骤详细设计


