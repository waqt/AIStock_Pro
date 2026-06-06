# Step 6a: 核心资产筛选 — 智能体设计 (V5.16)

> **定位**: 不是"选财务最好看的公司"，而是"找出最可能把产业利润变成自己利润的公司"。
> **方法**: 四阶段流程 — 线索汇总 → 搜索 → 先比较后验证 → 全局排名
> **原则**: LLM 自主分析，无预设维度；FinancialAuditor 不固定调用；淘汰者留根 (watchlist)

---

## I/O 合约

### 输入 (来自 Step 3 + Step 4 + Step 5)

| 来源 | 字段 | 用途 |
|------|------|------|
| Step 3 | `supply_chain_map[].sub_processes[].a_stock_mapping[]` | 直通候选 (已由 Step3 映射的 A 股标的) |
| Step 3 | `bottleneck_inversions[].decomposed_components[].a_stock_candidates[]` | 瓶颈拆解的 A 股机会候选 |
| Step 3 | `asset_search_queries[]` | 搜索结果 → LLM 提取标的 |
| Step 3 | `competitive_landscape[].china_substitution_rate + global_leaders` | 人力资本线索 (低国产化率时搜索前员工创业公司) |
| Step 4 | `system_dynamics.asset_search_queries[]` | 含 spillover / hidden beneficiary 搜索项 |
| Step 4 | `system_dynamics.*` (other fields) | 供 _verify_single 中 LLM 自主使用 |
| 本地DB | `StockInfo` 表 | PE/PB/ROE/行业/市值 |
| 本地DB | `FinancialStatement` 表 | 8Q 财务数据 (LLM 通过 `query_financial_data` 工具自主查询) |

### 输出

```json
{
  "agent": "CoreScreeningAgent",
  "confidence": "high",

  "lifecycle_gate": {
    "cycle_position": "bottleneck_formation",
    "gate_mode": "auto"
  },

  "candidate_pool": {
    "total_collected": 45,
    "after_prescreen": 38,
    "ranked": 5
  },

  "ranked_stocks": [
    {
      "rank": 1,
      "code": "688012",
      "name": "中微公司",
      "category": "current_strong",
      "company_stage": "growth",
      "why": "处于晶圆制造必经节点, 客户无法绕过",
      "verification": {
        "analysis_dimensions": [
          {
            "dimension": "客户锁定深度",
            "rating": "strong",
            "evidence": ["台积电/中芯国际认证周期>18个月", "已进入5nm产线"],
            "reasoning": "半导体设备赛道客户粘性天然高"
          }
        ],
        "industry_context": "刻蚀设备是晶圆制造核心环节",
        "profit_capture_thesis": "中微公司靠技术锁定+认证壁垒将产业景气转化为利润",
        "thesis_breakers": ["国内晶圆厂资本开支大幅缩减"],
        "roic_note": "ROIC 12-15%, 资本回报健康"
      }
    }
  ],

  "future_strong_candidates": [
    {"code": "688xxx", "name": "...", "category": "future_strong",
     "company_stage": "inflection", "verification": {...}}
  ],

  "watchlist": [
    {"code": "688yyy", "name": "...", "category": "watchlist",
     "company_stage": "unknown", "verification": {}}
  ],

  "eliminated": [
    {"code": "688zzz", "name": "...",
     "_eliminated_by": "comparison_excluded",
     "_eliminated_reason": "同源比较中竞争力不足",
     "company_stage": "unknown", "category": "watchlist"}
  ],

  "comparisons": [{
    "source": "高纯钛酸钡粉体",
    "exclusion_suggestions": [
      {"code": "688aaa", "reason": "产能规模仅为头部1/5"}
    ],
    "observations": [...]
  }],

  "source_detail": {
    "a_stock_mapping": 12,
    "bottleneck_inversion": 8,
    "asset_search_query": 18,
    "human_capital": 7
  },

  "filter_log": [
    {"code": "688yyy", "reason": "已 ST", "filter": "st_delisted"}
  ]
}
```

### 输出关键字段说明

| 字段 | 含义 |
|------|------|
| `ranked_stocks` | 全局排名结果，含完整 verification |
| `future_strong_candidates` | 排名靠前但尚未验证的候选 |
| `watchlist` | 溢出候选 + 比较淘汰者 (留根，不丢失) |
| `eliminated` | 比较环节明确的输家 |
| `candidates_map` | code→全量数据映射, 方便消费者按 code 查找 |
| `company_stage` | 由 LLM 在 _verify_single 中自主判定，非预分类 |

---

## 四阶段处理流程

```
CoreScreeningAgent.analyze():

┌─────────────────────────────────────────────────────────┐
│ Phase 1: 线索收集 (_collect_all_clues)                   │
│   ├─ a_stock_mapping (Step3) → direct_candidates         │
│   ├─ bottleneck_inversions (Step3) → direct_candidates    │
│   ├─ asset_search_queries (Step3+4) → search_clues        │
│   └─ human_capital (Step3) → search_clues                 │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ Phase 2: 搜索 (_execute_search_clues)                    │
│   ├─ 去重 (_dedup_search_clues: Jaccard>0.6)              │
│   ├─ a_share_equivalent: 4路深度搜索                       │
│   │   (供应商/竞争对手/国产替代/人才背景)                    │
│   ├─ 标准搜索: 并发执行 (信号量4)                          │
│   └─ LLM 从搜索结果提取股票代码 → search_candidates        │
└──────────────────────┬──────────────────────────────────┘
                       ↓
           直通 + 搜索候选合并 → 去重 → 硬过滤器
                  (hard_filter: ST/流动性)
                       ↓
┌─────────────────────────────────────────────────────────┐
│ Phase 3a: 同源比较                                       │
│   ├─ _group_by_source() → 按瓶颈节点分组                  │
│   ├─ _llm_screen_group() → ≥4家时快速筛 (零搜索)          │
│   └─ CandidateComparator.compare_within_source()         │
│       → 不排名, 只输出 exclusion_suggestions               │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ Phase 3b: 逐只验证 (_verify_single)                      │
│   ├─ LLM 自主定义分析维度 (无预设框架)                    │
│   ├─ call_with_tools(max_rounds=8)                        │
│   │   ├─ query_financial_data(code, indicators, fields)   │
│   │   └─ web_search(query, num=5)                        │
│   ├─ 注入 FinancialCatalog (财务指标字典)                 │
│   ├─ 输出 lifecycle_stage + category_suggestion           │
│   └─ 溢出候选跳过验证直接进 watchlist                     │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ Phase 4: 全局排名 (CandidateComparator.global_ranking)   │
│   ├─ LLM 跨节点排序                                     │
│   └─ 降级: 按利润池排序                                  │
└─────────────────────────────────────────────────────────┘
```

---

## Phase 1: 线索收集 (纯本地)

`_collect_all_clues()` 从 Step 3/4/5 的输出中提取 4 类线索:

1. **a_stock_mapping** — Step3 子流程已映射好的 A 股标的，直接进直通池
2. **bottleneck_inversions** — 瓶颈拆解中 opportunity=high/medium 的分量，含 A 股候选
3. **asset_search_queries** — Step3+4 生成的搜索线索，含 spillover
4. **human_capital** — 对低国产化率节点，搜索前员工创业方向

**去重**: 从直通候选建立 `seen_codes` 集合，搜索后合并时避免重复。

---

## Phase 2: 搜索 (LLM 提取)

`_execute_search_clues()` 并发处理所有搜索线索:

### 去重策略
`_dedup_search_clues()` 取代旧的 `[:12]` 硬上限:
- **asset_search_query**: 提取中英文关键词，Jaccard 相似度 > 0.6 时保留 priority 更高的
- **human_capital**: 按 leader 名去重（同一 leader 在不同节点被扫描多次）

### a_share_equivalent 深度搜索
对需要"海外公司→A股标的"映射的线索，执行 4 路搜索:
1. `A股 {foreign_company} 供应商 合作伙伴 供货 上市公司 2026`
2. `A股 {foreign_company} 竞争对手 国产替代 对标 上市公司 2026`
3. `{foreign_company} 中国 供应链 合作 A股 供应商 2026`
4. `曾在{foreign_company}工作 前员工 创始人 核心团队 A股 公司 2026` ★ V5.16 新增

LLM 从搜索结果中提取股票代码数组 `[{code, name, relevance}]`。

### 标准搜索
普通搜索线索: web search → LLM 提取 → 去重合并。

---

## Phase 3a: 同源比较

### 分组
`_group_by_source()` 按 `source_node` 字段分组，建立 `node_context` 映射（瓶颈描述/利润池/供给刚性等）。

### 快速筛选 (Phase A)
`_llm_screen_group()`: 只在候选 ≥ 4 时触发，纯 LLM 判断哪些"明显不具备参与该环节的资格"：
- 零搜索，仅基于节点描述 + 候选列表
- 宁可多留不要误杀（边界情况全保留）
- LLM 失败时全保留（不阻断流程）

### 比较排除
`CandidateComparator.compare_within_source()`:
- V1.1 设计: 不输出排名，只输出 `exclusion_suggestions`
- LLM 失败时降级: 全部保留（safe fallback）
- ≥2 候选触发高级比较（4+ 时进入 `_pairwise_tournament` 多轮淘汰赛）

#### 多轮淘汰赛
`_pairwise_tournament()`: 当同组候选 ≥4 时，避免一次 LLM 比较丢失所有信息:
1. **配对初赛**: 两两比较，每轮只比 2 家
2. **胜者组决赛**: 初赛胜者排序
3. 轮空自动晋级，LLM 失败默认保留

---

## Phase 3b: 逐只验证 (LLM 自主分析)

`_verify_single()` 是 Step 6 的核心创新 — V5.15 重构的核心：

### 设计原则
- **LLM 自主定义分析维度** — 不预设六维权力/财务框架
- **先查数据再判断** — LLM 必须先调工具获取数据才能下结论
- **无预设排除规则** — 所有候选都获得完整分析机会

### 执行流程
1. 构建 `_build_competitive_analysis_prompt()`: 注入产业背景 + 可用工具说明
2. 注入 `FinancialCatalog`: `FinancialQueryService.format_catalog_for_prompt()` 提供 30+ 财务指标字典
3. `call_with_tools(prompt, tool_defs=..., max_rounds=8)`:
   - LLM 自主定义分析维度（根据行业特征选择）
   - 自主调用 `query_financial_data` 获取财务指标
   - 自主调用 `web_search` 搜索市场信息
4. 解析输出:
   - `lifecycle_stage` (LLM 判定，非预分类) — `startup | inflection | growth | mature | cyclical_bottom | cyclical_decline`
   - `category_suggestion` — `current_strong | future_strong | watchlist`
   - `analysis_dimensions[]` — 每个维度含 `dimension/rating/evidence/reasoning`

### 溢出候选
标记 `_audit_pass_no_compare` 的候选跳过全套验证，直接进 watchlist（`company_stage: "unknown"`, `category: "watchlist"`）。

### 补跑机制
`patch_verify_single()`: 支持对已完成的 checkpoint 增量补跑单只验证，不触发全量分析。

---

## Phase 4: 全局排名

`CandidateComparator.global_ranking()`:
- 跨节点对所有 verified 候选排序
- LLM 成功: 返回 `ranked_stocks[]`（含 rank/why）
- LLM 失败: 降级按利润池大小排序
- 输出 `enriched_ranked`: 从 verified_map 补齐 verification/category 等字段

---

## 关键设计决策

### 1. 生命周期阶段由 LLM 判定 (V5.16)
- **旧**: StageClassifier 预分类 → stage_map 锁定 → verifier 仅读取
- **新**: LLM 在验证过程中基于自主查询的财务数据判定 `lifecycle_stage`
- 原因: pre-classification 限制了 LLM 的推理空间

### 2. FinancialAuditor 不是固定步骤
- **Path A** (step2_only, DEPRECATED): 保留 FinancialAuditor 调用
- **Path C** (V5.15+): 不固定调用。由 _verify_single 中的 LLM 自主决定是否需要审计类分析
- 原因: 不是所有公司都需要深度财务审计，LLM 自主判断效率更高

### 3. 比较器不排名
- 只输出 `exclusion_suggestions`，不做完整排序
- 排名归 Phase 4 全局排名
- 降低每轮 LLM 调用的复杂度

### 4. 淘汰者留根
- 被比较器排除的候选进 `eliminated[]`（仍含 `company_stage: "unknown"`）
- 保留在输出中供下游参考，不静默丢弃
- 溢出候选进 watchlist，不丢失

### 5. 硬过滤器 (hud_filter) 仅保留必要排除
- 只排除: ST / 已退市 / 日均成交额 < 1,000 万
- 不设财务阈值排除（营收增速/ROIIC/ROIC 等已在 V5.16 移除）

---

## Path A 弃用 (DEPRECATED V5.16)

`step2_only` 分支标记已废弃:
- 入口打印 `logger.warning` 弃用日志
- 三个方法标注 `DEPRECATED V5.16, will be removed in V6`:
  - `_legacy_step2_flow()` — 简化版无比较排名
  - `_aggregate_candidates_from_step2()` — 从 Step2 transmission_order 挖标的
  - `_llm_tag_to_stock_mapping()` — tags→股票代码分批映射
- 代码保留向后兼容，V6 移除

---

## 当前实现

| 属性 | 值 |
|------|------|
| 文件 | `domain/research/agents/core_screening_agent.py` |
| 版本 | V5.16 |
| API | `POST /api/research/pipeline/{run_id}/analyze` (作为 pipeline Step 6 调用) |
| 输入 | Step 3 + Step 4 + Step 5 checkpoint |
| LLM | `deepseek-v4-flash`（搜索提取/LLM screen/competitive analysis）+ `deepseek-v4-pro`（_verify_single 工具调用） |
| 工具调用 | `call_with_tools(max_rounds=8)` — web_search + query_financial_data |
| 财务数据 | FinancialQueryService（30+ 财务指标，20+ 原始字段） |
| 比较器 | CandidateComparator V1.1（排除建议） |
| 搜索 | 4 路并发（Semaphore 4），a_share_equivalent 4 路 deep search |

## 验证

```bash
# 触发全流程
curl -X POST http://127.0.0.1:8000/api/research/pipeline/{run_id}/analyze

# 检查:
# - ranked_stocks 全局排名输出
# - 每只股票有 verification.analysis_dimensions (LLM 自主定义维度)
# - company_stage 来自 LLM 判定 (非预分类)
# - elimination 有 excluded 记录
# - watchlist 有 overflow 候选
# - 无综合数字分数 (不是打分排名, 是分类+定性)
```
