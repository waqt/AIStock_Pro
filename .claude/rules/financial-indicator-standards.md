# 财务量化指标设计标准

> 与价量技术指标平行的独立体系。基于季度财报 (FinancialStatement)，面向 AI 投研 Pipeline (Step 6/7) 和 Agent on-demand 查询。

---

## 一、架构总览

```
数据源: akshare → FinancialStatement (MySQL, 11张表)
   ↓
计算引擎: financial_compute.py (滑动窗口, newest-first)
   ↓ 遍历 FINANCIAL_REGISTRY 全部 27+ 指标
存储: financial_indicators (SQLite, 35 数值列 + 15 文本列, 自动推导)
   ↓
查询层: FinancialQueryService (catalog + on-demand query + SQLite 缓存)
   ↓
消费方: /api/quant/financial-indicators/* (REST API)
         pipeline glossary.py (LLM prompt 注入)
         Agent 按需组装 (query_financial_data)
```

**与技术指标的关键区别：**

| 维度 | 技术指标 (indicators) | 财务指标 (financial_indicators) |
|------|----------------------|-------------------------------|
| 数据源 | MarketData (日线) | FinancialStatement (季报) |
| 频率 | 日频 | 季度 (QoQ) |
| 计算引擎 | IndicatorRunner (三轮处理+ctx) | financial_compute.py (滑动窗口) |
| 注册表 | INDICATOR_REGISTRY | FINANCIAL_REGISTRY |
| 基类 | BaseIndicator | FinancialIndicator |
| 存储 | indicators 表 (同一宽表) | financial_indicators 表 (独立表) |
| 触发 | sync_market 任务自动触发 | calc_financial_indicators 任务触发的计算 |

---

## 二、指标注册体系

### 单一注册表
- **唯一注册表**: `app/domain/quant/indicators/fundamental/__init__.py` → `FINANCIAL_REGISTRY`
- **API**: `GET /api/quant/financial-indicators/registry` — 返回全部已注册财务指标及其 meta()
- `FINANCIAL_REGISTRY` 同时是 SQLite 列自动推导的真相源（`indicator_store._get_dynamic_financial_cols()`）

### 基类属性

```python
# base.py — FinancialIndicator
class FinancialIndicator:
    name: str = ""           # 唯一标识, 全小写+下划线
    label: str = ""          # 中文显示名 (如 "ROIC(%)")
    description: str = ""    # 指标含义说明 (60-100字)
    judgment: str = ""       # 数据判断方法 (阈值/指南)
    category: str = "fundamental"  # profitability | growth | health | quality | profile
    indicator_type: str = "both"   # "moat"(护城河) / "prosperity"(高景气) / "both"
    applicable_stages: list = []   # ["startup","inflection","growth","mature","decline"]
    params: dict = {}        # 可调参数
    output: list = []        # 输出字段名列表 (全系统唯一)
    requires: list = []      # 依赖的 FinancialStatement 字段
    text_output: list = []   # 🌟 output 中属于文本/枚举类型的字段名
    #         存储时作为 TEXT 列, 查询时不参与数值计算
    #         未列在此属性中的 output 字段自动视为 NUMERIC (REAL 列)
```

### `@register` 装饰器
```python
from ..base import FinancialIndicator, register

@register  # 自动加入 FINANCIAL_REGISTRY
class ROICIndicator(FinancialIndicator):
    name = "roic"
    output = ["roic", "roic_pct", "roic_quality", "roic_interpretation"]
    text_output = ["roic_quality", "roic_interpretation"]  # 枚举/文本
    requires = ["revenue", "operate_cost", ...]
```

**关键规则：**
- ✅ 每个 `output` 字段要么是 NUMERIC (默认, REAL列)，要么声明在 `text_output` 中 (TEXT列)
- ✅ 新增指标只需一个文件 + `@register`，列自动推导、catalog 自动出现
- ❌ 不要手写 `indicator_store.FINANCIAL_NUMERIC_COLS` — 已自动推导

### `text_output` 何时使用

| 字段类型 | 示例 | text_output |
|----------|------|-------------|
| 纯数值 (%) | `roe`, `rd_intensity`, `revenue_yoy` | 不声明 |
| 纯数值 (倍) | `working_capital_efficiency`, `operating_leverage` | 不声明 |
| 纯数值 (分) | `m_score` | 不声明 |
| 枚举字符串 | `roic_quality`, `ocf_health`, `revenue_scale` | 声明 |
| 文本描述 | `roic_interpretation`, `m_score_components` | 声明 |
| 布尔/标志 | `scissor_is_expanding` | 声明 |

---

## 三、算子和范式

### 统一定向
所有指标数据方向为 **newest-first**：quarters[0] = 最新报告期，与 DB 的 `ORDER BY report_date DESC` 一致。

### compute() 签名
```python
@classmethod
def compute(cls, financials: list) -> dict:
    """
    financials: List[Dict] — FinancialStatement 行, newest-first
    返回: Dict[str, Any] — 字段名→值, 值与 output+text_output 一致
    """
```

### 滑动窗口约定
- 4Q 窗口：`financials[:4]` — 最新 TTM
- YoY 对比：`financials[0]` vs `financials[4]` — 同比
- 8Q 窗口：`financials[:8]` — 两年前瞻
- 不足数据：返回 `{"field": None, ...}` 而不是抛异常

### 纯函数约束
- ✅ 纯函数：输入 financials list，输出 dict
- ✅ 向量化计算：sum/mean/min/max + list comprehension
- ❌ 禁止 I/O（DB/网络/文件），禁止状态
- ❌ 禁止访问全局注册表或缓存（降低耦合，方便单测）

### 工具函数 (base.py)
```python
from ..base import _pct, _safe_div

_pct(current, base)     → 计算百分比变化, base=0 返回 None
_safe_div(a, b)         → 安全除法, b=0 返回 0
```

---

## 四、存储与自动列推导

### 表结构
```sql
financial_indicators (
    stock_code   TEXT NOT NULL,       -- 股票代码
    report_date  TEXT NOT NULL,       -- 报告期 (如 "2026-03-31")
    -- 所有 output 字段自动创建:
    --   NUMERIC 字段 → REAL DEFAULT NULL
    --   TEXT 字段    → TEXT DEFAULT NULL
    PRIMARY KEY (stock_code, report_date)
)
```

### 自动推导机制
```python
# indicator_store.py — 无需手动维护
def _get_dynamic_financial_cols() -> tuple:
    """从 FINANCIAL_REGISTRY 自动推导数值列和文本列"""
```

- 初始建表只有 `(stock_code, report_date)` PRIMARY KEY
- `_init_financial_table()` 通过 `ALTER TABLE ADD COLUMN` 自动补齐缺失列
- 新增指标后首次 compute 自动添加新列，不 DROP 表、不丢失数据
- 如果列已存在则自动跳过（幂等）

### 缓存
```python
# 模块级缓存, 避免每次写操作重复推导
_fin_cols_cache = None
# 以下情况需清缓存:
#   1. 测试/热加载后
#   2. 新增指标后如需立即生效 (通常重启即自动重建)
_reset_financial_cols_cache()
```

---

## 五、数据流与计算

### FinancialStatement 加载
```python
from app.domain.research.services.data_loader import data_loader
fin = await data_loader.load_financial_statements("688012", periods=8)
# quarters → newest-first list of dicts
```

### 批量计算
```python
# API: POST /api/quant/financial-indicators/compute
# Task: calc_financial_indicators (代码 = calc_financial_indicators)
from app.domain.quant.engine.financial_compute import compute_financial_for_codes
result = await compute_financial_for_codes(codes, mode="local")
```

计算流程：
1. `load_financials(code, periods=20)` → 加载 newest-first 财务数据
2. `for i in range(len(quarters)-3)` → 每窗口 = `quarters[i:]` (从 i 到末尾)
3. 每个窗口遍历全部 `FINANCIAL_REGISTRY` 指标 → `cls.compute(window)`
4. `store_financial_indicator(code, rpt_date, record)` → upsert 到 SQLite

### ETF 过滤
```python
# financial_compute.py
ETF_CODE_PREFIXES = ('159', '510', '512', '513', '560', '588')
# TODO V6: 使用 stock_info.asset_type 替代硬编码前缀
```

---

## 六、查询层

### FinancialQueryService
```python
from app.domain.quant.engine.financial_query_service import FinancialQueryService

svc = FinancialQueryService()
catalog = svc.get_catalog()                     # 数据字典 (已缓存)
data = await svc.query(                          # 按需组装 (SQLite 缓存优先)
    code="688012",
    indicators=["roic_pct", "revenue_yoy"],
    raw_fields=["revenue", "rd_expense"]
)
prompt_text = svc.format_catalog_for_prompt()    # Agent prompt 注入
```

### 字段元数据
每个字段在 `cls.meta()["output_fields"][field_name]` 中包含：
```python
{
    "unit": "%",           # 自动推断 (通过 _infer_unit())
    "meaning": "...",       # 取自 cls.description
    "is_text": False,       # 是否 text_output 字段
}
```

### API 端点
```
GET    /api/quant/financial-indicators/registry          — 指标注册表 (meta())
GET    /api/quant/financial-indicators/catalog           — 数据字典 (含 unit/meaning)
POST   /api/quant/financial-indicators/query             — Agent 按需组装
GET    /api/quant/financial-indicators/{stock_code}      — 单股最新 (支持 fields 筛选)
GET    /api/quant/financial-indicators/history/{code}    — 历史序列
GET    /api/quant/financial-indicators/field/{name}      — 全股票排名
POST   /api/quant/financial-indicators/compute           — 批量计算
```

### SQLite 缓存机制
`FinancialQueryService.query(latest_only=True)` 的缓存策略：
1. 先调 `indicator_store.get_financial_latest(code)` 检查 SQLite
2. 如果所有请求的字段都在缓存中 → 直接返回
3. 否则回退到 `load_financials()` + 滑动窗口计算

---

## 七、新增财务指标检查清单

### 开发阶段
- [ ] 文件放在 `fundamental/<category>/<name>.py`
- [ ] 继承 `FinancialIndicator`，加 `@register`
- [ ] `name` 全局唯一，`output` 字段名不与现有指标冲突（查 `FINANCIAL_REGISTRY` 或 `indicator_store._get_dynamic_financial_cols()`）
- [ ] 声明 `text_output`：枚举/文本字段必须列出
- [ ] `requires` 准确声明依赖的 FinancialStatement 字段
- [ ] `compute()` 纯函数，输入 newest-first list，返回 dict
- [ ] 不足数据时返回 `None` 而非抛异常

### 验证阶段
- [ ] `python -m py_compile` 通过
- [ ] `GET /api/quant/financial-indicators/registry` 出现新指标
- [ ] `GET /api/quant/financial-indicators/catalog` 出现新字段 unit/meaning
- [ ] `POST /api/quant/financial-indicators/compute` 对新字段可正常写入
- [ ] `GET /api/quant/financial-indicators/{stock_code}?fields=<new_field>` 返回正确值
- [ ] SQLite 表自动扩展新列（无需手动 DDL）

---

## 八、架构约束

- `indicator_store.FINANCIAL_NUMERIC_COLS()` / `FINANCIAL_TEXT_COLS()` 是**函数**（动态调用），不是模块级列表
- 不要直接 import `FINANCIAL_NUMERIC_COLS` 做列表操作 — 调用函数
- 清缓存：`indicator_store._reset_financial_cols_cache()`（测试/热加载时使用）
- 消费方通过 `FinancialQueryService` 访问，不直接读 SQLite（除非需要原始行数据）
- 数据方向全线 newest-first：quarters[0] = 最新季度
