# AI 投研系统 V5.7 → V6.0 升级设计

> 对标 GPT 投研提示词 V2（11 步系统动力学增强版），在现有 6 Agent + DAG Pipeline 架构上渐进增强。

---

## 系统定位

**AIStock Pro 产业链分析专家** — 针对投资驱动的供给侧行业分析系统。

### 分析哲学

核心能力: 宏观周期 / 产业链 / CAPEX 周期 / 系统动力学 / 供需 / 资源约束 / 利润池迁移 / 非线性推演 / 全球竞争格局

必问问题:
1. **谁最缺** — 供给刚性最高的环节在哪？
2. **谁拥有定价权** — 利润池集中在谁手里？
3. **谁控制供给** — 产能扩张的决定权在谁？
4. **谁受益于供给收缩** — 产业瓶颈的隐藏受益者？
5. **谁受益于资源重新分配** — CAPEX/产能/利润的迁移方向？

---

## 实施进度

| Step | 名称 | 设计 | 实现 | 备注 |
|------|------|------|------|------|
| 1 | 宏观与全球资本周期 | ✅ 完成 | ⚠️ 80% | 12/16 指标入库，macro_report 合成+缓存已交付；缺 4 个 akshare 指标 + server biz_date 修复未加载 |
| 2 | Pipeline 看门人 | ✅ 完成 | ✅ 完成 | analyze() 支持 auto/manual 双模式, 6块定性输出, 已通过 manual 模式测试 |
| 3 | 产业链系统拆解 | ⚠️ 草稿 | ❌ 0% | 待按 Step 2 格式重写设计文档 |
| 4+5 | 系统动力学 + 非线性推演 | ⚠️ 草稿 | ❌ 0% | 待详细设计 |
| 6 | 核心资产筛选 | ✅ 完成 | ✅ 已完成 | ROE/股息/增速质量加权已加入 |
| 7 | 财务质量 | ⚠️ 草稿 | ❌ 0% | 待详细设计 |
| 8 | 估值体系 | ✅ 完成 | ✅ 已完成 | VALUATION_MODEL_MAP + 三情景 + 全球对标 |
| 9 | 市场预期差 | ⚠️ 草稿 | ❌ 0% | 待新建 ExpectationGapAgent |
| 10 | 风险分析 | ⚠️ 草稿 | ❌ 0% | 待 prompt 增强 |
| 11 | 最终投资结论 | ✅ 完成 | ✅ 已完成 | 报告模板已补全 |

### Step 1 详细状态

```
已完成:
  ✅ 结构化数据管线: 12/16 指标入 exchange_rates + macro_history
  ✅ US10YT 数据修复: 0.49(中国利差) → 4.56(美国10Y)
  ✅ 中文日期解析: _parse_biz_date() 已添加
  ✅ 宏观报告合成: synthesize_macro_report() → backend/data/macro_report.json
  ✅ 30天缓存: load_macro_cache()
  ✅ Pipeline Phase 0 集成: supply_chain_pipeline 自动读取/更新
  ✅ 报告注册表: report_registry 表 + 38份历史报告回填
  ✅ 前端: macro 面板 16 张卡片 + 中文释义 + biz_date 显示

剩余:
  ❌ 4 个 akshare 指标: US_CPI_YOY / CN_CPI_YOY / US_ISM_PMI / DXY
  ❌ Server 未重启加载 _parse_biz_date 修复 (CN_M2_YOY/CN_PMI biz_date 仍为NULL 通过 API)
  ❌ biz_date 已通过直接 DB 更新绕过
```

### Step 2 详细状态

```
已完成:
  ✅ 设计文档: I/O contract、输出 schema、行为规范、上下游接口
  ✅ market_scanner.py: analyze() 重构 + _scan_auto + _deep_dive_manual + _evaluate_industry
  ✅ Prompt 重写: 6块定性 JSON (cycle_position/prosperity/payoff/propagation/verdict/kill_reasons)
  ✅ 双模式: auto(验证Step1假设)/manual(用户指定行业)
  ✅ 测试通过: manual 模式 "AI电力基础设施" 返回完整6块结构

待集成:
  ❌ Pipeline Phase 0 → Step2 数据流: macro_report.benefited_sectors → _scan_auto()
  ❌ scan API 端点未适配新参数 (当前仅 legacy 模式)
```

---

## 设计原则

1. **LLM 定性, 程序化定量**: Step 2 做归类, Step 3-8 做计算
2. **渐进增强**: 不改架构, Agent 内部升级 prompt/逻辑
3. **版本管理**: 每次改前 git commit, Write/Edit 直写文件, 不通过 bash 传复杂文本

## 文档索引

| 文件 | 内容 |
|------|------|
| [01_Step1_Macro](01_Step1_Macro.md) | 宏观与全球资本周期 (含实施状态) |
| [02_Step2_Gatekeeper](02_Step2_Gatekeeper.md) | Pipeline 看门人 — 产业 Alpha 排序器 |
| [03_Step3_SupplyChain](03_Step3_SupplyChain.md) | 产业链系统拆解 |
| [04_Step4_SystemDynamics](04_Step4_SystemDynamics.md) | 系统动力学 + 非线性推演 + 核心资产筛选 |
| [05_Step7_11_Remaining](05_Step7_11_Remaining.md) | Steps 7-11: 财务→估值→预期差→风险→结论 |
| [06_GPT_Reviews](06_GPT_Reviews.md) | GPT 评审反馈、system_dynamics 统一输出 |
| [07_Implementation](07_Implementation.md) | 实施优先级、文件变更、验收标准 |

## 相关文档

- [V7.0 未来蓝图](../AI_Research_System_V7.0_Future_Blueprint.md)
- [IDEA 优化库](../../99_IDEA_BACKLOG.md)
- [CLAUDE.md](../../../CLAUDE.md) — LLM Agent 设计原则 + 版本管理铁律
