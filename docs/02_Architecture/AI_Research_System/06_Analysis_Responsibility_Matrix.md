# 分析职责矩阵 — Web Search / LLM / Local Function

> **目的**: 明确 Pipeline 全链路中每个动作由谁执行，防止 LLM 做不该做的事（算数/输出股票代码），防止代码做 LLM 该做的事（定性判断/逻辑推演）。

---

## 一、三个角色的边界

```
┌─────────────────────────────────────────────────────────────┐
│  Web Search  ───→  LLM 定性归类  ───→  Local 定量计算     │
│  找信息            做判断             算结果               │
│                    输出搜索线索         DB数据/纯函数        │
│                    (而非最终结论)      (不可替代LLM)        │
└─────────────────────────────────────────────────────────────┘
```

| 角色 | 擅长 | 不擅长 | 典型错误 |
|------|------|--------|---------|
| **Web Search** | 获取实时/外部/多维信息 | 判断信息真伪/重要性 | 返回噪声/PDF残片/低质内容 |
| **LLM** | 定性归类/模式识别/逻辑推演/叙事合成 | 数值计算/精确记忆/事实准确性 | 幻觉股票代码/编造数字/过度自信 |
| **Local Function** | 数学计算/DB查询/正则匹配/枚举校验 | 语义理解/模糊判断/跨领域联想 | 无法处理非结构化信息 |

---

## 二、全链路职责矩阵

### 发现段 (Discovery Phase: Step 1-5)

| Step | 动作 | Web Search | LLM | Local Function |
|------|------|:---:|:---:|:---:|
| **1a** 宏观周期 | 搜索全球CAPEX/PMI/利率/库存周期 | ✅ 搜索12类宏观指标 | ✅ chat_pro 合成宏观报告 + 判断 regime | ✅ 读 DB macro_history 表 |
| | 落盘 | — | — | ✅ checkpoint → macro_report.json |
| **1b** 资本流向 | 5链并行搜索 (由用户行业动态生成, 不预设赛道) | ✅ 5×4=20条搜索 | ✅ chat_flash 提取 pressure_vectors + constraint_vectors | ✅ 读 Step 1a 缓存; `_build_search_chains(industry)` 生成搜索链 |
| | 落盘 | — | — | ✅ checkpoint |
| **2** 行业看门人 | 验证/发现候选行业 | ✅ 自适应搜索 (1-3轮) | ✅ chat_pro 6-block 定性输出 | ✅ 读 Step 1b pressure_map |
| | 粒度过滤 + 错配分析 | — | ✅ LLM 定性过滤 (不评分) | ✅ glossary 枚举注入 |
| | 落盘 | — | — | ✅ checkpoint + trace |
| **3** 产业链拆解 | Round 1: 全景+瓶颈定位 | ✅ 搜索 | ✅ chat_pro 提取 findings + gaps | ✅ Step 2 标签驱动 query 选择 |
| | Round 2: 缺口补搜 | ✅ 搜索 | ✅ chat_pro 校验+判断是否继续 | — |
| | Round 3: 深度补搜 (条件) | ✅ 搜索 | ✅ chat_pro 最终校验 | — |
| | 结构化输出 | — | ✅ chat_pro (480s) 输出 supply_chain_map | ✅ glossary 注入 |
| | 股票代码提取 | — | — | ✅ **正则提取** (6位代码) → LLM补充 → 正则兜底 |
| | margin_level 估计 | — | ✅ LLM 从搜索片段估计 | ✅ 标记 margin_estimated=true |
| | 落盘 | — | — | ✅ checkpoint + trace |
| **4** 系统动力学 | 瓶颈迁移+隐藏受益者搜索 | ✅ 2轮自适应搜索 | — | ✅ 读 Step 3 checkpoint |
| | **Step 3 反向校验** | — | ✅ chat_pro 强制质疑 1-2 个判断 | — |
| | 六步链式推演 + 十问自检 | — | ✅ chat_pro (480s) | — |
| | 输出 search_queries | — | ✅ LLM 生成精准搜索词 | ✅ 枚举约束注入 |
| | 落盘 | — | — | ✅ checkpoint + trace |
| **5** 跨产业关联 | 3轮×N节点搜索 | ✅ 搜索共享约束/挤占/溢出 | — | ✅ 读 Step 3 + Step 4 checkpoint |
| | Step 3+4 反向校验 | — | ✅ chat_pro 质疑上游 | — |
| | 5种推演方法 | — | ✅ chat_pro | ✅ 枚举约束 |
| | 输出 affected_sector + target_profile | — | ✅ LLM (不输出股票代码) | — |
| | 落盘 | — | — | ✅ checkpoint + trace |

### 判断段 (Judgment Phase: 标的映射 + Step 6-11)

| Step | 动作 | Web Search | LLM | Local Function |
|------|------|:---:|:---:|:---:|
| **标的映射** | A. Query Generation | — | ✅ 从 target_profile 生成检索词 | — |
| (共享工作流) | B. Extraction | ✅ 执行搜索, Top 5 | ✅ 提取候选股票名称 | — |
| | C. Cross-Validation | ✅ 搜索 "{股票} {业务} 布局 产能 营收" | ✅ 判断 exposure_type: core/emerging/speculative | ✅ **白名单域名** (仅此阶段) |
| **6** 核心资产筛选 | 圈定股票池 | ✅ 从 target_profile 搜索 | — | ✅ 读 StockInfo/Watchlist/Positions DB |
| | 财务清洗 | — | — | ✅ **8Q剪刀差 + Beneish M-Score** |
| | 营收敞口验证 | ✅ 搜索财报/公告 | ✅ LLM 阅读摘要判断营收占比 | ✅ 读 financial_statements 表 |
| **7** 人才/专利审计 | 搜索创始人/CTO/专利 | ✅ 搜索 | ✅ LLM 评估技术壁垒 | ✅ 读 DB |
| **8** 估值定价 | 模型选择 | — | — | ✅ match_asset_type() → 估值模型 |
| | 估值计算 | — | — | ✅ PE/PB/PS/FCF/EV_EBITDA **纯函数** |
| | 情境加权 | — | — | ✅ scenario_weighted() + adjust |
| | Step 3 回写 | — | — | ✅ 真实 margin 回写 checkpoint |
| **9** 预期差 | 量价数据读取 | — | — | ✅ 读 SQLite 指标库 (换手率/拥挤度/动量) |
| | 预期差判断 | — | ✅ LLM 对比"市场定价" vs "推演结论" | ✅ 算截面动量 |
| | visibility 交叉验证 | — | — | ✅ 换手率/crowding_ratio 量化校验 |
| **10** 风险分析 | 风险识别 | ✅ 搜索黑天鹅/政策 | ✅ LLM 综合风险叙事 | ✅ 读 thesis_breakers |
| **11** 综合报告 | 全量合成 | — | ✅ LLM 综合所有 Step | ✅ 读所有 checkpoint |

---

## 三、分工原则

### Web Search 的职责

```
✅ 搜: 外部实时信息 (新闻/研报/公告/产业链动态)
✅ 搜: 本地 DB 没有的信息 (新兴行业/海外/最新政策)
✅ 搜: 标的映射中的候选圈定 + 交叉验证
✅ 搜: 多源并行 (Brave + Tavily) + DDG 兜底

❌ 不算: 数学计算
❌ 不存: 数据持久化
❌ 不校验: 枚举/格式
❌ 不评: 信息质量 (由 LLM 判断 quality.level)
```

### LLM 的职责

```
✅ 定性归类: severity / linkage_type / attention_quality / cycle_position
✅ 模式识别: 周期阶段 / 竞争格局 / 供给刚性类型 / 跨产业关联
✅ 逻辑推演: 六步链式 / 五跨产业 / 十问自检 / 反向校验
✅ 叙事合成: impact_narrative / alpha_narrative / bottleneck_narrative
✅ 信息提取: 从搜索片段 → 结构化 JSON (findings / gaps / pressure_vectors)
✅ 搜索词生成: search_queries / 自适应下一轮 query

❌ 不算: 数值评分 (禁止 scarcity_score / alpha_score)
❌ 不编: 股票代码 (china_stocks 已删除, 改用 search_queries / target_profile)
❌ 不算: 数学 (PE/PB/Beneish/Sharpe 交给 Local Function)
❌ 不存: 不写 DB (checkpoint/Trace 由 Local Function 负责)

关键约束:
- chat_flash: 信息提取/简单归类 (Step 1b/3 round1-3)
- chat_pro + thinking: 深度推演/复杂推理 (Step 2/3/4/5)
- max_tokens: 6144-8192 (防截断)
- timeout: 60s (flash) / 480s (pro+thinking)
```

### Local Function 的职责

```
✅ 数学计算: PE/PB/PS/FCF/Beneish/COST/Sharpe/换手率/拥挤度
✅ DB 读写: 财务数据/行情/持仓/checkpoint/trace/manifest
✅ 正则提取: 股票代码 (6位模式匹配) — Step 3 股票提取
✅ 枚举校验: glossary 注入 + parse_json 后验证枚举值
✅ 调度控制: TaskEngine (信号量/去重/异步) / Pipeline (断点续跑)
✅ 域名白名单: 标的映射 C 阶段 site: 过滤
✅ 数据格式化: pd.read_sql() / DataFrame 向量化计算

❌ 不判: 不做定性判断 (这是 LLM 的核心价值)
❌ 不联想: 不做跨产业联想
❌ 不生成: 不做叙事/文本生成
❌ 不搜索: 不自行构造搜索词
```

---

## 四、底线规则

### 规则 1: LLM 不输出股票代码

```
❌ 禁止: "china_stocks": ["688525", "佰维存储"]
✅ 替代: "search_queries": ["ABF基板 替代材料 A股 上市公司"]
✅ 替代: "target_profile": "主营压电陶瓷元件, 下游半导体设备, 营收<50亿, 毛利率>35%"
→ 由标的映射工作流 (A→B→C) 负责将搜索线索转化为股票列表
```

### 规则 2: LLM 不做数值评分

```
❌ 禁止: "scarcity_score": 9.2, "alpha_score": 92
✅ 替代: "severity": "extreme", "attention_quality": "profit_real"
→ 枚举值从 glossary 注入, LLM 只做归类不做量化
```

### 规则 3: 过滤不删除

```
旧: impact_materiality=low → 硬删除 → 不可回溯
新: impact_materiality=low → 标记 materiality_low → 进入下游但排序靠后
→ 最终决策在 Step 11 综合所有标签, 不在中间环节删除
```

### 规则 4: 每步质疑上一步

```
Step 4 必须质疑 Step 3 (step3_sanity_check)
Step 5 必须质疑 Step 3 + Step 4
→ 防止 LLM 自强化偏差 (GIGO 级联放大)
```

### 规则 5: 数据不足时标记, 不丢弃

```
confidence=insufficient_data → 保留所有数据, 等待补全后重跑
→ 不因数据不足而硬编结果, 也不因数据不足而丢弃分析对象
```

---

## 五、搜索偏向控制

### Step 1b 搜索链生成 (V1.1)

搜索链由用户指定的 `industry` 动态生成，不预设任何赛道：

```
用户指定 "AI电力基础设施" → 搜 "AI电力基础设施 全球 资本开支..."
用户指定 "生物制药"       → 搜 "生物制药 全球 资本开支..."
无指定                   → 宽泛扫描 "2026 全球 资本开支 CAPEX 投资 趋势"
```

**旧问题 (V1.0)**: 搜索链硬编码 AI/电力/芯片 → 后续分析被锁定在 AI 赛道
**修复 (V1.1)**: `_build_search_chains(industry)` 由用户输入驱动，完全行业无关

### 通用搜索偏向检查清单

| 检查项 | 说明 |
|--------|------|
| 搜索链是否由用户输入驱动？ | 不预设赛道，不硬编码行业关键词 |
| 搜索结果是否在 prompt 中按链均衡展示？ | 每链取 top 3, 不因某链结果多而放大权重 |
| 下游 Step 是否用自己的搜索独立验证？ | Step 2 不盲信 Step 1b, Step 4 质疑 Step 3 |
