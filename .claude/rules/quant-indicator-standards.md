# 量化指标设计标准

## 一、指标注册

### 单一注册表
- **唯一注册表**: `app/domain/quant/indicators/__init__.py` → `INDICATOR_REGISTRY`
- **API**: `GET /quant/indicators/registry` — 返回全部已注册指标及其元信息
- 新增指标必须在此注册表中可见

### 新增指标模板
```python
# indicators/<category>/<name>.py
from ..base import BaseIndicator, register

@register
class XxxIndicator(BaseIndicator):
    name = "xxx"           # 唯一标识, 全小写+下划线
    category = "trend"     # trend|momentum|volatility|volume|crowding|chip
    params = {"window": 20}
    output = ["field_a", "field_b"]  # 输出字段名 = data_json 的 key
    requires = ["close"]   # 依赖的 df 列 + 上游指标 output 字段

    @classmethod
    def compute(cls, df):
        # 纯函数: 输入 DataFrame(含 OHLCV + 上游指标列), 输出 dict
        return {"field_a": ..., "field_b": ...}
```

### 检查清单
- [ ] 继承 `BaseIndicator`，加 `@register`
- [ ] `name` 全局唯一，`output` 中各字段名不与其他指标冲突
- [ ] `requires` 准确声明依赖（缺依赖的指标在两轮计算中会被跳过）
- [ ] `compute()` 纯函数，无 I/O、无状态
- [ ] 更新本文件的 §四 data_json schema
- [ ] 新增后运行全量重算：`POST /quant/indicators/compute?mode=historical`

---

## 二、股票范围

### 定义
```
需要指标计算的股票 = Position.stock_code ∪ WatchlistItem.stock_code
```

### 使用位置
| 位置 | 代码 |
|------|------|
| `calc_indicators` 任务 | `target_codes=None` 时自动取并集 |
| `POST /quant/indicators/compute` | `codes` 参数为空时取并集 |
| 覆盖检测 API | `scope=all` 时取并集 |

### 新增股票
- `POST /watchlist/add` 自动触发 `sync_market(AUTO)` → 行情同步 + 估值 + 行业 + **指标历史回补**
- 指标回补通过 `batch_sync_and_analyze` 末尾的 INDICATORS 节点执行
- 可在 `GET /quant/indicators/coverage` 验证新股票指标已就绪

---

## 三、指标计算

### 统一入口
- **异步任务**: `calc_indicators` (通过 `POST /system/tasks/executions` 或 `IndicatorCompute` 前端组件)
- **参数**: `target_codes`(默认全部) / `mode`(snapshot|incremental|historical) / `indicator_names`(默认全部)
- **计算引擎**: `IndicatorRunner` — 统一使用 `_run_indicators` / `_run_indicators_full`（两轮处理，ctx 上下文传递）

### 模式说明
| 模式 | 方法 | 用途 |
|------|------|------|
| `snapshot` | `compute_snapshot` | 仅今天，快速验证 |
| `incremental` | `compute_incremental` | 增量补算，自动检测旧数据是否缺筹码/拥挤度 |
| `historical` | `compute_historical` | 全量历史，新增股票或新增指标后使用 |

### 覆盖检测
- `GET /api/quant/indicators/coverage` — 返回每只股票的指标天数 + 缺失指标列表
- 系统健康概览 `GET /data/health/overview` 提供 `indicators_coverage` 汇总

---

## 四、data_json 存储 schema

每行 `stock_indicators.data_json` 包含以下字段（按分类）：

```
# 趋势 (trend)
ma5 ma10 ma20 ma60 ma120 ma250
macd macd_signal macd_hist
k d j

# 动量 (momentum)
rsi atr cci

# 波动率 (volatility)
bb_upper bb_mid bb_lower bb_width

# 量能 (volume)
obv v_ma5 v_ma10 v_ma20 vwap

# 拥挤度 (crowding)
turnover_20d turnover_120d crowding_ratio sharpe_60d

# 筹码 (chip)
chip_concentration chip_peak_price chip_avg_cost
chip_peaks chip_valleys chip_is_single_peak
chip_pattern chip_signal chip_pattern_detail

# 元信息
price     # 当日收盘价
_prev_*   # 前一交易日的对应字段值
```

### 约束
- 唯一约束: `UNIQUE(stock_code, analysis_date)` — 每天每只股票仅一行
- 指标计算写入时使用覆盖策略（delete today's row + insert）
- 前端查询统一读 `data_json` 字典

---

## 五、前端消费

### 指标计算触发
- 统一使用 `IndicatorCompute` 组件 (位于 `js/framework/indicator_compute.js`)
- `IndicatorCompute.render('id')` — 完整控制面板
- `IndicatorCompute.openModal({...})` — Modal 弹窗
- `IndicatorCompute.submit(params, feedback)` — 直接提交

### 数据查询
- 单股最新指标: `GET /quant/indicators/{stock_code}`
- 历史时间序列: `GET /quant/indicators/history/{stock_code}?fields=...`
- 自选股拥挤度: `GET /data/alt/crowding/watchlist`
- 行业拥挤度: `GET /data/alt/crowding/industry`
- 筹码+拥挤度总览: `GET /data/alt/overview`
- 覆盖检测: `GET /quant/indicators/coverage`
