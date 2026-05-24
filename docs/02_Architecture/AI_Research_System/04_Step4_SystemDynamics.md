# AI 投研系统 V5.7 → V6.0 升级设计文档

> 对标 GPT 投研提示词 V2（11 步系统动力学增强版），在现有 6 Agent + DAG Pipeline 架构上渐进增强。

---

## 系统定位

**AIStock Pro 产业链分析专家** — 针对投资驱动的供给侧行业分析系统。


### Step 4+5: 系统动力学 + 非线性推演 (第二层思维重构) * 核心

**分析哲学对应**: 回答谁受益于供给收缩、谁受益于资源重新分配、隐藏受益者。

**目标**: 6 个案例模板驱动 + 推演六步 + scarcity_ranking + thesis_breakers。

---

#### 从 Step 2 移入: thesis_breakers (行业失败条件)

```json
"thesis_breakers": [
  {
    "thesis": "CoWoS 持续紧缺至2028",
    "break_condition": "台积电 CoWoS 产能从120K翻至250K wpm + 交期缩短至2个月以下",
    "current_probability": "低(15%概率在2027年前发生)",
    "watch_indicator": "台积电月度营收 + 资本开支指引"
  },
  {
    "thesis": "AI电力需求推动电网设备超级周期",
    "break_condition": "MAG7 capex增速放缓至个位数 + AI推理效率大幅提升降低电力需求",
    "current_probability": "中低(25%)",
    "watch_indicator": "微软/谷歌/亚马逊季度capex增速"
  }
]
```

---

#### 推演方法论 (嵌入 Prompt 的思维纲领)

链式推演模板: 需求变化 -> 资源变化 -> 供给变化 -> 价格变化 -> 利润变化 -> CAPEX变化 -> 再平衡

**推演六步** (嵌入 _second_level_analysis System Prompt):
1. 确定主驱动力 — 真正的驱动变量是什么？
2. 寻找约束条件 — 什么东西最先不够？
3. 分析资源迁移 — 高利润会吸走谁的资源？
4. 分析系统再平衡 — 什么时候供给会恢复？
5. 寻找利润池迁移 — 利润最终会流向谁？
6. 寻找最后被市场发现的人 — Alpha 来源

**案例模板 6 个** (嵌入 Prompt 作为 few-shot):
1. 资源挤占: HBM消耗3x晶圆 -> 挤占DDR产能 -> DRAM涨价 -> 二线DRAM厂受益
2. 联产经济学: 炼油减产 -> 硫磺供给收缩 -> 磷肥飞涨 -> 化肥企业受益
3. 瓶颈迁移: GPU短缺 -> 云厂自研芯片 -> CoWoS成为新瓶颈 -> 封装设备受益
4. CAPEX错配: 成熟制程CAPEX不足 -> MCU缺货2年 -> 成熟制程代工厂暴利
5. 利润池迁移: AI从硬件 -> 软件 -> 云服务 -> 应用, 利润流向不同阶段
6. 供给刚性: 高纯石英砂只有北卡矿 -> 光伏扩产 -> 石英砂2年涨价10倍

**推演十问** (每轮LLM分析末尾强制回答):
1.真正驱动力？2.哪个资源最稀缺？3.高利润会吸走谁的资源？4.谁会供给下降？5.谁会意外涨价？
6.谁拥有定价权？7.哪个瓶颈最难扩产？8.利润会迁移到哪里？9.市场还没发现谁？10.什么信号会证伪我？

**scarcity_ranking** — 综合稀缺分排序, 直接回答谁最缺:

```json
"scarcity_ranking": [
  {"rank": 1, "segment": "CoWoS封装", "scarcity_score": 9.2, "supply_rigidity": 9, "pricing_power": 9,
   "why_scarce": "台积电独家,扩产需18个月,需求3年翻3倍", "beneficiary_A_stocks": ["688012中微公司","002371北方华创"]}
]
```

**文件**: backend/app/domain/research/agents/supply_chain_hacker.py
**改动量**: ~130 行



### Step 6: 核心资产筛选 (质量加权增强)

**当前状态**: top_picks 程序化 — PASS+score>=60->BUY, PASS+score>=40->HOLD

**增强**: ROE/股息率/盈利增速 质量加分

```python
quality_bonus = 0
if roe and roe > 15: quality_bonus += 5
if dividend_yield and dividend_yield > 2: quality_bonus += 3
if eps_growth and eps_growth > 20: quality_bonus += 5
adjusted_score = score + quality_bonus
```

**文件**: backend/app/domain/research/agents/dag_orchestrator.py (~15行)



