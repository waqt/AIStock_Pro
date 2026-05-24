# AI 投研系统 V5.7 → V6.0 升级设计文档

> 对标 GPT 投研提示词 V2（11 步系统动力学增强版），在现有 6 Agent + DAG Pipeline 架构上渐进增强。

---

## 系统定位

**AIStock Pro 产业链分析专家** — 针对投资驱动的供给侧行业分析系统。


### Step 7: 财务质量 (FinancialAuditor 盈利释放判断)

新增程序化判断:
```python
if consecutive_yoy_hits >= 4 and scissor_is_expanding and ocf_health == "healthy":
    release_stage = "盈利释放期"
elif scissor_gap < -20 and not four_quarters_hit:
    release_stage = "盈利承压期"
else:
    release_stage = "过渡期"
```

**文件**: backend/app/domain/research/agents/financial_auditor.py (~20行)



### Step 8: 估值体系 (已完成, 仅补 pay-off asymmetry)

**从 Step 2 移入**: payoff_structure 个股级非对称性

```json
// ValuationPricer 输出新增:
"payoff_asymmetry": {
  "type": "强非对称 / 对称 / 负非对称",
  "narrative": "若国产替代兑现->利润3x; 若证伪->政策支撑底线, 下行有限",
  "asymmetric_score": "高"
}
```

注意与 Step 2 区分: Step 2 做行业级赔率(定性), Step 8 做个股级(带定量价格)

**文件**: backend/app/domain/research/agents/valuation_pricer.py (~10 行)



### Step 9: 市场预期差与资金面 (新增 ExpectationGapAgent + 拥挤度)

**这是本次升级最关键的增量**

**从 Step 2 移入**: crowding 定性分析

```json
// ExpectationGapAgent 输出新增:
"crowding_assessment": {
  "level": "拥挤 / 正常 / 冷门",
  "evidence": ["券商覆盖30+家", "公募重仓TOP10", "北向持续增持"],
  "alpha_implication": "高拥挤->即使景气兑现, 股价上行空间被压缩"
}
```

**原有设计**:
- Agent: ExpectationGapAgent
- 对比维度: 估值预期差 / 盈利预期差 / 风险预期差 / 护城河预期差
- 输出: market_consensus vs our_view + gap_summary
- DAG 编排: 放在 ValuationPricer 之后, _synthesize_report 之前

**新增文件**: backend/app/domain/research/agents/expectation_gap.py (~150行)
**修改**: dag_orchestrator.py (编排+3行, 模板+1节)



### Step 10: 风险分析增强

每条风险标注概率 * 影响程度 * 是否已被市场定价:

```json
"key_risks": [
  {"risk": "风险描述", "probability": "中", "impact": "重大", "priced_in": "部分"}
]
```

**文件**: dag_orchestrator.py (~10行 prompt 替换)



### Step 11: 最终投资结论 (报告模板 +预期差节)

```markdown
## 六、预期差与投资建议
| 维度 | 市场共识 | 我们的判断 | 差异 |
|------|---------|-----------|------|
| 估值 | 目标市值2400亿 | 2850亿 | +19% |
| 盈利 | 增速20% | 35% | 超预期 |
```

**文件**: dag_orchestrator.py (~30行)


---


