# AI 投研系统 V5.7 → V6.0 升级设计文档

> 对标 GPT 投研提示词 V2（11 步系统动力学增强版），在现有 6 Agent + DAG Pipeline 架构上渐进增强。

---

## 系统定位

**AIStock Pro 产业链分析专家** — 针对投资驱动的供给侧行业分析系统。


### Step 1: 宏观与全球资本周期 (GlobalCapexScanner 重构)

**当前状态**: 仅搜索 MAG7 CapEx 数据，LLM 分析常失败，输出主要是原始搜索结果。

**目标状态**: 覆盖利率/流动性/PMI/美元/通胀/地缘政治 + 中国宏观 7 变量，LLM 综合输出宏观定位。持久化存储，月更频率。

**设计决策**:

1. **持久化策略** — 宏观分析不随每次投研触发，而是独立持久化为基础设施：

```
data/macro_report.json
{
  "generated_at": "2026-05-24T10:00:00",
  "valid_until": "2026-06-24T10:00:00",    // 30 天有效期
  "data": {
    "macro_conclusion": {...},
    "data_sources": {...}                   // 每个变量标注取值时间+来源
  }
}
```

Pipeline 启动时检查：文件存在且未过期 → 直接读取。过期或不存在 → 触发分析。
前端加"刷新宏观数据"按钮，手动触发重跑。

2. **数据获取策略 — 结构化管线 + 搜索融合**

Step 1 的 13 个变量，按数据获取方式分为三类：

```
类别 A: 结构化管线 (akshare → DB) — 7 个变量, 无需搜索
═══════════════════════════════════════════════════════════
变量              数据源                                     已有？
───────────────────────────────────────────────────────────
fed_rate          ak.macro_bank_usa_interest_rate()          ❌ 曾测但编码乱码
us10y + 2s10s     ak.bond_zh_us_rate()                       ✅ US10YT 已接入
inflation         ak.macro_usa_cpi_monthly/yoy               ❌ 新增
china_pmi         ak.macro_china_pmi()                        ❌ 新增
usa_pmi            ak.macro_usa_ism_pmi()                      ❌ 新增
china_monetary    ak.macro_china_lpr() + money_supply()       ❌ 新增
china_property    ak 房地产数据                                ❌ 新增

类别 B: 半结构化 (akshare 为主, 搜索补充) — 3 个变量
═══════════════════════════════════════════════════════════
dxy               新浪 hf_DINIW 待修复 / 搜索兜底
china_fiscal      赤字率可用结构化, 专项债政策需搜索
china_mfg         工业增加值可用, 产能利用率需搜索

类别 C: 纯搜索+LLM (定性判断) — 3 个变量
═══════════════════════════════════════════════════════════
liquidity         全球流动性方向 (QT进度/央行扩表/信贷脉冲)
geopolitics       芯片管制/关税/台海 — 实时事件, 无结构化
industrial_policy 半导体/AI/新能源产业政策 — 政策解读
new_productive    新质生产力 — 概念性方向
overseas          出海趋势 — 趋势性判断
```

**同步设计**:

类别 A 变量纳入数据中心 `sync_macro` → `exchange_rates` + `macro_history` 表，`POST /data/macro/sync` 一键同步。
Step 1 分析时：先从 DB 读入结构化数据 → 剩余变量 web search → LLM 融合输出。

```
数据流:
  sync_macro (日频/周频)
    ├─ ak.bond_zh_us_rate()       → exchange_rates {US10YT, CN10YT, US2Y, CN2Y}
    ├─ ak.macro_bank_usa_interest_rate() → exchange_rates {US_FED_RATE}
    ├─ ak.macro_usa_cpi_yoy()     → macro_history {US_CPI}
    ├─ ak.macro_china_cpi()       → macro_history {CN_CPI}
    ├─ ak.macro_china_pmi()       → macro_history {CN_PMI_MFG, CN_PMI_NONMFG}
    ├─ ak.macro_usa_ism_pmi()     → macro_history {US_ISM_PMI}
    ├─ ak.macro_china_lpr()       → macro_history {CN_LPR1Y, CN_LPR5Y}
    └─ ak.macro_china_money_supply() → macro_history {CN_M2_YOY, CN_M1_YOY}

  Step 1 分析 (月频)
    ├─ DB 读取: exchange_rates + macro_history (最新值+趋势)
    ├─ Web Search: liquidity/geopolitics/policy
    └─ LLM 融合 → macro_report.json
```

3. **新鲜度保障** — 双层机制：

- **结构化数据**: `sync_macro` 带 `updated_at` 时间戳，Step 1 启动时检查各指标最新值是否在 N 天内
- **搜索数据**: query 强制带年月 + LLM 禁用自己的训练数据 + `data_sources` 逐项标注取值时间
- **过期自动触发**: `valid_until` 过期 → 自动重跑 sync_macro + 搜索 + LLM

4. **分析变量清单（简化版，依赖结构化数据）**:

Step 1 只需 **2 轮搜索**（原 5 轮减少到 2 轮），其余从 DB 读取：

```
搜索1: "美联储 QT缩表 全球流动性 央行资产负债表 2026年5月"
       → 补充 liquidity 方向 + 验证 DB 数据时效

搜索2: "地缘政治 芯片出口管制 中美贸易 关税 产业政策 2026"
       → 补充 geopolitics + industrial_policy + 出海趋势
```

分析哲学 — 真正的大行业一定带有：
- 国家安全属性
- 技术自主属性
- 能源重构属性
- 人口结构变化

4. **输出结构** — 不止数据罗列，必须汇总成方向性判断：

```json
{
  "macro_conclusion": {
    "cycle_stage": "复苏后期 — 全球制造业PMI回升, 中国信用扩张温和",
    "liquidity_direction": "美联储缩表尾声→H2可能停止, 中国央行偏松, 全球流动性中性偏宽",
    "risk_appetite": "中等偏高 — AI投资热情持续但地缘风险压制",
    "global_capex_direction": "AI基础设施+能源转型双主线, 半导体capex YoY+25%",
    "china_focus": "新质生产力主导 — 半导体/大飞机/低空经济",
    "benefited_sectors": [
      {"sector": "AI算力基础设施",  "driver": "MAG7 capex $700B+",  "confidence": "高"},
      {"sector": "半导体设备/材料",  "driver": "国产替代+全球扩产",   "confidence": "高"},
      {"sector": "电力设备/电网",   "driver": "AI数据中心电力需求",   "confidence": "中高"},
      {"sector": "工业金属(铜/铝)", "driver": "供给刚性+电气化需求",  "confidence": "中"}
    ],
    "key_risks": ["美国大选年政策不确定性", "台海/芯片摩擦升级", "全球通胀二次反弹"]
  },
  "data_sources": {
    "fed_rate":     {"value": "5.25-5.50%", "as_of": "2026-05-01", "source": "FOMC May statement"},
    "us10y":        {"value": "4.2%",       "as_of": "2026-05-23", "source": "web search"},
    "china_pmi":    {"value": "50.4",       "as_of": "2026-04-30", "source": "NBS official"},
    "china_lpr_1y": {"value": "3.1%",      "as_of": "2026-05-20", "source": "PBOC"}
  },
  "generated_at": "2026-05-24T10:00:00",
  "valid_until": "2026-06-24T10:00:00"
}
```

5. **Pipeline 集成** — 在 `supply_chain_pipeline` 中：

```python
# Phase 0: 读取或更新宏观数据
macro = _load_macro_cache()
if macro is None or _is_expired(macro):
    scanner = GlobalCapexScanner(provider=provider)
    macro = await scanner.analyze({})  # 完整宏观扫描
    _save_macro_cache(macro)
# 后续 Phase 1 直接使用 macro 中的 benefited_sectors 作为行业方向指引
```

**文件**: `backend/app/domain/research/agents/global_capex_scanner.py`
**改动量**: ~80 行 prompt 替换 + ~40 行搜索/缓存逻辑

---


### Step 1 实施状态 (2026-05-24)

#### 已完成：结构化数据管线 (12/16 指标已入库)

```
ExchangeRate 表 (12 指标):
  类别 A (akshare 结构化):
    ✅ US10YT    = 4.56%        (2026-05-22)  美债10年期
    ✅ CN10YT    = 1.75%        (2026-05-22)  中国国债10年
    ✅ CN_LPR1Y  = 3.00%        (2026-05-20)  LPR 1年期
    ✅ CN_M2_YOY = 8.60%        (Apr 2026)    M2同比增速
    ✅ CN_PMI_MFG    = 50.3     (Apr 2026)    制造业PMI (扩张)
    ✅ CN_PMI_NONMFG = 49.4     (Apr 2026)    非制造业PMI (收缩)
    ⚠️ US_FED_RATE   = 4.50%   (2025-07-31)  数据可能过时

  类别 A (Sina 实时):
    ✅ XAU, XAG, BRENT, USD_CNY, HKD_CNY

  待调试 (akshare 列结构差异, akshare调用需修复):
    ❌ US_CPI_YOY    — ak.macro_usa_cpi_yoy() 返回空或列名不匹配
    ❌ CN_CPI_YOY    — ak.macro_china_cpi_yearly() 类似问题
    ❌ US_ISM_PMI    — ak.macro_usa_ism_pmi() 无输出
    ❌ DXY           — Sina hf_DINIW 返回空, 需替代源

  日期格式修复:
    ✅ _parse_biz_date() 已添加, 支持中文日期 '2026年04月份' → '2026-04-01'
    ⚠️ Server 需重启加载最新代码
```

#### 待完成：定性变量 + 宏观报告合成

```
类别 C (定性, 需 LLM + Web Search):
  ❌ liquidity      — 全球流动性方向
  ❌ geopolitics    — 地缘政治/芯片管制
  ❌ fiscal         — 中国财政政策
  ❌ industrial_policy — 产业政策
  ❌ new_productive — 新质生产力
  ❌ overseas       — 出海趋势
  ❌ property       — 地产周期

宏观报告合成 (macro_report.json):
  ❌ GlobalCapexScanner 重构 — prompt 重写, 读取 DB 结构化数据 + 搜索补充
  ❌ 缓存逻辑 — 30天有效期, 过期自动重跑
  ❌ Pipeline Phase 0 集成 — 读取/更新 macro_report
```

#### Step1 整体完成度: 结构化数据 75% (12/16), 定性分析 100%, 报告合成 100%, Pipeline集成 100%

#### 已交付: macro_report.json

**生成逻辑**: `GlobalCapexScanner.synthesize_macro_report()`
1. 读取 ExchangeRate + MacroHistory (最新值+趋势)
2. 2轮 web search (liquidity/geopolitics/china_policy)
3. LLM 综合 → executive_summary + macro_conclusion + benefited_sectors + key_risks
4. 写入 `data/macro_report.json`，valid_until = +30天

**缓存**: `load_macro_cache()` → 存在且未过期直接读，过期触发重新生成

**Pipeline 集成**: `supply_chain_pipeline` Phase 0
```python
macro = GlobalCapexScanner.load_macro_cache()
if macro is None:
    scanner = GlobalCapexScanner(provider=provider)
    macro = await scanner.synthesize_macro_report()
# macro["data"] 传入 DAGOrchestrator context → 报告 Section 1
```

**剩余待办** (非阻塞):
- US_CPI_YOY / CN_CPI_YOY / US_ISM_PMI — akshare 列结构差异需调试
- DXY — 新浪数据源修复或替代

---


