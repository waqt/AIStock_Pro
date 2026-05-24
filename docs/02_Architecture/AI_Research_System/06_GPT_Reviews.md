# AI 投研系统 V5.7 → V6.0 升级设计文档

> 对标 GPT 投研提示词 V2（11 步系统动力学增强版），在现有 6 Agent + DAG Pipeline 架构上渐进增强。

---

## 系统定位

**AIStock Pro 产业链分析专家** — 针对投资驱动的供给侧行业分析系统。


### GPT 评审反馈已吸收的设计增量

**增量 1**: 受损方分析 (victims) — system_dynamics 输出
**增量 2**: 产业相变预测 (equilibrium_forecast) — Step 4 输出
**增量 3**: 验证框架 (thesis_validation) — 每个推演绑定领先指标/证伪信号/时间窗
**增量 4**: 时间序列瓶颈预测 (bottleneck_timeline) — Step 4 输出
**增量 5**: 六个强制问题 — Step 3+4 prompt 尾缀
**增量 6**: system_dynamics 统一输出块 — 报告二.五节末尾

```json
"system_dynamics": {
  "resource_migration": [{"from":"低端DDR","to":"HBM产线","victim":"二线DRAM厂涨价受益","A_stock":"688XXX"}],
  "supply_constraints": [{"node":"CoWoS封装","rigidity":9,"reason":"台积电独家,扩产需18个月"}],
  "bottleneck_chain": ["GPU->HBM->先进封装->电力->铜->变压器->液冷"],
  "profit_pool_migration": [{"from":"硬件制造","to":"AI算力服务","timeline":"2026-2028"}],
  "hidden_beneficiaries": [{"sector":"成熟制程测试厂","reason":"先进制程受限->成熟制程爆满->测试需求激增"}],
  "next_bottleneck_prediction": {"current":"CoWoS","next_12m":"HBM3E产能","next_24m":"数据中心电力","next_36m":"液冷散热"},
  "victims": [{"segment":"服务器OEM","why":"HBM涨价侵蚀BOM","margin_impact":"-8pct","market_awareness":"低"}],
  "equilibrium_forecast": {"current_state":"供给短缺","capex_response":"全球扩产+180%","expected_relief":"2027Q3","overcapacity_risk":"2028H1"},
  "falsification_signals": [{"thesis":"HBM持续紧缺","counter_signal":"三星HBM产能翻倍+交期下降","watch":"三星季度财报CAPEX指引"}],
  "thesis_breakers": [{"thesis":"CoWoS紧缺至2028","break_condition":"台积电CoWoS产能翻倍+交期缩短","watch":"台积电月度营收"}]
}
```

---


### 增量 6: 验证框架 (Thesis Validation) — 工程基础设施

**GPT 评审最核心的建议**: 「产业推演系统最危险的是幻觉式正确——看起来极其合理，实际完全错。你现在最缺的不是更多功能，而是验证系统。」

每个推演结论绑定:

```json
"thesis_validation": [
  {
    "thesis": "HBM 持续紧缺至 2027",
    "leading_indicators": ["HBM 现货价", "GPU 交期(周)", "CoWoS 交期(月)", "SK Hynix 稼动率"],
    "falsification_signals": ["HBM 价连续 3 月下跌", "CoWoS 交期缩短至 2 个月以下", "三星 HBM3E 良率突破 80%"],
    "time_window": "6-18 个月",
    "confidence": 75,
    "last_validated": null,
    "validation_status": "待验证 — 需人工确认领先指标方向"
  }
]
```

**实现路径** (分两期):
- 一期: Prompt 输出结构 + 报告展示 (本期交付)
- 二期: 领先指标数据接入 + 自动贝叶斯更新 (未来基础设施)


### 不纳入本期范围 (未来架构)

| 方向 | 原因 |
|------|------|
| CapitalFlowAgent (资金行为) | 需要 ETF/北向/融资盘等数据源, 当前无管线 |
| 动态反馈 DAG | 架构重构, 影响面太大, V7.0 考虑 |
| 产业验证数据库 | 需要持续运营, 不适合一次性交付 |


### 设计评分 (GPT 评审基准校准)

```
宏观框架: 8.5  结构化: 9    CAPEX: 8.5   产业映射: 8
系统动力学: 7.0 (加入推演六步+十问+供应方分析)
供给深度: 7.5 (加入 supply_rigidity + victims + equilibrium)
利润迁移: 7.0 (加入 profit_pool + resource_migration)
验证体系: 4.0 (thesis_validation 框架刚起步)
```

---

## 三、实施优先级与依赖

```
Phase 1 (基础 — 无依赖, 可并行)
  Step 1: GlobalCapexScanner prompt 重写
  Step 2: MarketScanner prompt 增强 (定性判断)
  Step 3: SupplyChainHacker Phase 1 prompt 重写

Phase 2 (核心 — 依赖 Phase 1)
  Step 4+5: 第二层思维重构 (案例库 + scarcity_ranking)
  Step 6: 核心资产筛选质量加权

Phase 3 (增量 — 依赖 Phase 2)
  Step 7: FinancialAuditor 盈利释放判断
  Step 9: ExpectationGapAgent 新建 * 最关键
  Step 10: 风险分析增强

Phase 4 (收尾 — 依赖 Phase 3)
  Step 11: 报告模板补预期差章节
```

## 四、文件变更总览

| Step | 文件 | 操作 | 改动量 |
|------|------|------|--------|
| 1 | global_capex_scanner.py | Prompt + 搜索重写 | ~60行 |
| 2 | market_scanner.py | Prompt 增强 (定性判断) | ~80行 |
| 3 | supply_chain_hacker.py | Phase 1 prompt 重写 + scarcity/rigidity/value | ~60行 |
| 4+5 | supply_chain_hacker.py | _second_level_analysis 彻底重写 + scarcity_ranking | ~130行 |
| 6 | dag_orchestrator.py | top_picks 质量加权 | ~15行 |
| 7 | financial_auditor.py | 盈利释放判断 | ~20行 |
| 9 | expectation_gap.py | **新建 Agent** | ~150行 |
| 9 | dag_orchestrator.py | DAG 编排 +1 Agent | ~5行 |
| 10 | dag_orchestrator.py | 风险 prompt 增强 | ~10行 |
| 11 | dag_orchestrator.py | 报告模板 +预期差节 | ~30行 |

**总计**: 4 个文件修改 + 1 个新文件, ~560 行变更

## 五、不受影响的部分

- Pipeline 注册表 (pipelines.py)
- API 路由 (routes.py)
- 前端 (research.html)
- 数据库 schema
- 任务引擎 (tasks.py)

## 六、验收标准

每 Phase 完成后:
1. py_compile 全部文件通过
2. curl 单 Agent 端点 -> 返回结构化数据含新字段
3. 完整 Pipeline 跑一次 -> 报告含新章节
4. 第二层思维不再输出空数组

## 七、设计原则

1. 渐进增强: 不改架构, Agent 内部升级 prompt/逻辑
2. LLM 定性, 程序化定量: Step 2 归类, Step 3-8 算分
3. 案例驱动: V2 产业案例嵌入 Agent few-shot 模板
4. 可独立测试: 每个 Agent 单独 curl 验证
5. 确定性优先: 关键结论程序化生成, LLM 只做辅助推演

### 当前设计评级

```
宏观框架: 8.5  结构化: 9    CAPEX: 8.5   产业映射: 8
系统动力学: 7.0 (↑ 原 5.5, 加入推演六步+十问+供应方分析)
供给深度: 7.5 (↑ 原 6.0, 加入 supply_rigidity + victims + equilibrium)
利润迁移: 7.0 (↑ 原 5.0, 加入 profit_pool + resource_migration)
验证体系: 4.0 (↓ 新识别, thesis_validation 框架刚起步)
```

```
Phase 1 (基础 — 无依赖, 可并行)
├── Step 1: GlobalCapexScanner prompt 重写
├── Step 2: MarketScanner prompt 增强
└── Step 3: SupplyChainHacker Phase 1 prompt 重写

Phase 2 (核心升级 — 依赖 Phase 1 完成)
├── Step 4+5: 第二层思维重构 (含案例库)
└── Step 6: 核心资产筛选质量加权

Phase 3 (增量 — 依赖 Phase 2)
├── Step 7: FinancialAuditor 盈利释放判断
├── Step 9: ExpectationGapAgent 新建 ★ 最关键
└── Step 10: 风险分析增强

Phase 4 (收尾 — 依赖 Phase 3)
└── Step 11: 报告模板补预期差章节
```

## 四、文件变更总览

| Step | 文件 | 操作 | 改动量 |
|------|------|------|--------|
| 1 | `global_capex_scanner.py` | Prompt + 搜索重写 | ~60行 |
| 2 | `market_scanner.py` | Prompt 增强 + prosperity_type + scarcity_indicators | ~45行 |
| 3 | `supply_chain_hacker.py` | Phase 1 prompt 重写 + profit_pool/pricing_power/supply_rigidity | ~55行 |
| 4+5 | `supply_chain_hacker.py` | _second_level_analysis 彻底重写 + scarcity_ranking | ~130行 |
| 6 | `dag_orchestrator.py` | top_picks 质量加权 (ROE/股息/增速) | ~15行 |
| 7 | `financial_auditor.py` | 盈利释放判断 | ~20行 |
| 9 | `expectation_gap.py` | **新建 Agent** | ~150行 |
| 9 | `dag_orchestrator.py` | DAG 编排 +1 Agent | ~5行 |
| 10 | `dag_orchestrator.py` | 风险 prompt 增强 (概率×影响×定价) | ~10行 |
| 11 | `dag_orchestrator.py` | 报告模板 +预期差节 | ~30行 |

**总计**: 4 个文件修改 + 1 个新文件，~520 行变更。

## 五、不影响的部分

- ✅ Pipeline 注册表 (pipelines.py) — 不需要改
- ✅ API 路由 (routes.py) — 不需要改
- ✅ 前端 (research.html) — 不需要改
- ✅ 数据库 schema — 不需要改
- ✅ 任务引擎 (tasks.py) — 不需要改
- ✅ 估值模块 (valuation_pricer.py) — 不需要改

## 六、验收标准

每 Phase 完成后验证:
1. `python -m py_compile` 全部修改文件通过
2. curl 单个 Agent 端点 → 返回结构化数据包含新字段
3. 完整 Pipeline 跑一次 → 报告包含新章节
4. 第二层思维不再输出空数组

## 七、设计原则

1. **渐进增强**: 不改架构，只在 Agent 内部升级 prompt/逻辑
2. **案例驱动**: V2 提示词中的产业案例直接嵌入 Agent 的 few-shot 模板
3. **程序化优先**: 能用代码计算的 (如盈利释放判断、质量加权) 不用 LLM
4. **可独立测试**: 每个 Agent 可单独 curl 验证，互不阻塞
5. **确定性优先**: 关键结论由程序化逻辑生成，LLM 只做辅助推演



