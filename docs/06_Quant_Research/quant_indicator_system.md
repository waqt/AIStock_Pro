# 量化指标体系 V5.6 — 完整文档

> 适用对象: 后续 AI 开发工具、新加入的开发者

---

## 一、系统概览

### 三层架构

```
定义层 → 计算层 → 存储层 → API 层 → 前端层
```

| 层 | 位置 | 职责 |
|---|------|------|
| 定义 | `indicators/<category>/<name>.py` | 纯函数指标算子, `@register` 自注册 |
| 计算 | `engine/indicator_runner.py` | 3轮处理 + ctx 上下文, 快照/历史/增量 |
| 存储 | `engine/indicator_store.py` | SQLite 宽表, 52列, `upsert_rows` |
| 调度 | `tasks.py` | `calc_indicators` 异步任务 |
| API | `api/indicators.py` | registry / compute / history / coverage / field |
| 前端 | `indicator_compute.js` | 统一计算触发组件 |

---

## 二、16 个指标清单

| 分类 | 指标 | 中文名 | 输出字段 | 依赖 | 加速 |
|------|------|--------|---------|------|------|
| trend | ma | 移动均线 | ma5~ma250 | close | — |
| trend | macd | MACD | macd, macd_signal, macd_hist | close | — |
| trend | kdj | KDJ随机 | k, d, j | high,low,close | — |
| momentum | rsi | RSI相对强弱 | rsi | close | — |
| momentum | atr | ATR真实波幅 | atr | high,low,close | — |
| momentum | cci | CCI商品通道 | cci | high,low,close | — |
| volatility | bollinger | 布林带 | bb_upper, bb_mid, bb_lower | close | — |
| volatility | bollinger_width | 布林带宽 | bb_width | close, bb_upper, bb_lower | — |
| volume | obv | OBV能量潮 | obv | close, volume | — |
| volume | volume_ma | 量能均线 | v_ma5, v_ma10, v_ma20 | volume | — |
| volume | vwap | VWAP均价 | vwap | high,low,close,volume | — |
| crowding | turnover_ratio | 拥挤度(换手) | turnover_20d, turnover_120d, crowding_ratio | volume | — |
| crowding | sharpe_60d | 夏普比率 | sharpe_60d | close | — |
| chip | chip_concentration | 筹码集中度 | chip_concentration, chip_peak_price, chip_avg_cost | high,low,close,volume | **numba** |
| chip | chip_peak_detect | 筹码峰值定位 | chip_peaks, chip_valleys, chip_is_single_peak | high,low,close,volume | **numba** |
| chip | chip_pattern | 筹码形态识别 | chip_pattern, chip_signal | close, chip_concentration, chip_peak_price, chip_peaks, chip_is_single_peak | — |

---

## 三、COST 筹码算法 (V5.6 核心)

### 算法原理

指数衰减 + 三角分布 + COST 分位数。

```
半衰期: decay = 0.5^(1/45)  (45天, 经通达信 600699/300124 验证)

每日:
  chip = chip * decay          # 老筹码指数衰减
  chip += volume * weight      # 新筹码三角分布叠加

每日期末:
  COST(N) = 累计成交量达总成交*N/100 的价格
  WINNER(P) = 价格≤P 的累计筹码占比
  集中度 = (COST90 - COST10) / (COST90 + COST10)   (0~1, 越小越集中)
  形态 = 单峰/双峰/多峰 + 价格位置 + 250日分位
```

### 筹码形态 (5类, 对齐行业标准)

| 形态 | 条件 | 信号 |
|------|------|------|
| 低位单峰密集 | 集中度<0.12 + 单峰 + 峰值在250日低35%分位 | BUY |
| 高位单峰密集 | 集中度<0.12 + 单峰 + 峰值在250日高65%分位 | SELL |
| 双峰密集(近下峰) | 集中度<0.20 + 双峰 + 价格靠近下峰 | BUY |
| 双峰密集(近上峰) | 集中度<0.20 + 双峰 + 价格靠近上峰 | SELL |
| 多峰密集 | 其余情况 (多峰 或 集中度>0.20) | HOLD |

### 验证方法

`temp_lab/chart_chip_distribution.py` → matplotlib 筹码分布图 → 与通达信/手机软件截图比对 (600699/300124 已验证通过)。

### 加速

numba.jit 将 COST 计算从 ~10s/股 降到 ~0.8s/股。

---

## 四、SQLite 宽表存储

### 表结构

```sql
CREATE TABLE indicators (
    stock_code TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    -- 49 个 REAL 数值列 (ma5~obi, rsi~sharpe, chip_concentration~chip_is_single_peak)
    -- 2 个 TEXT 列 (chip_pattern, chip_signal)
    PRIMARY KEY (stock_code, trade_date)
);
```

### 写入策略

| 场景 | 策略 | SQL 调用 |
|------|------|---------|
| 全量重算 | DELETE + executemany INSERT | 2 次 |
| 部分指标 | SELECT 读旧行 → 内存合并 → executemany INSERT | 2 次/股 |
| 快照 (今天) | INSERT OR REPLACE 或 ON CONFLICT UPDATE | 1 次 |

### 数据文件

`backend/data/indicators.db` — 单文件, `cp` 即可备份。

---

## 五、计算模式

| 模式 | 方法 | 持久化 | 用途 |
|------|------|--------|------|
| `snapshot` | `compute_snapshot` | 仅今天一行 | 快速验算 |
| `historical` | `compute_historical` | 全量覆盖 | 新增股票/指标后 |
| `incremental` | `compute_incremental` | 只补新日期 + 自动降级全量 | 每日自动 |

### 参数化

```python
task_manager.run_task("calc_indicators", {
    "target_codes": ["688012"],    # None=全部持仓+自选股
    "mode": "historical",          # snapshot/incremental/historical
    "indicator_names": ["rsi","macd"]  # None=全部16个
})
```

---

## 六、API 端点

| 方法 | 路由 | 用途 |
|------|------|------|
| GET | `/quant/indicators/registry` | 16个指标元信息 (含中文 label) |
| POST | `/quant/indicators/compute?mode=historical` | 批量同步计算 (备用) |
| POST | `/quant/indicators/compute/{code}?mode=snapshot` | 单股计算 |
| GET | `/quant/indicators/{code}` | 单股最新快照 |
| GET | `/quant/indicators/history/{code}?fields=rsi,macd&days=120` | 时间序列 |
| GET | `/quant/indicators/coverage` | 覆盖检测 (哪只股票缺哪些指标) |
| GET | `/quant/indicators/field/{field_name}` | 某指标全部股票排名 |
| GET | `/data/alt/overview` | 筹码 + 拥挤度总览 |
| GET | `/data/alt/crowding/industry` | 行业拥挤度聚合 |
| GET | `/data/alt/crowding/watchlist` | 自选股拥挤度 |

---

## 七、前端消费

### 指标计算触发

统一使用 `IndicatorCompute` 组件 (`js/framework/indicator_compute.js`):

```javascript
IndicatorCompute.render('container-id')         // 完整面板
IndicatorCompute.openModal({mode:'historical'}) // Modal 弹窗
IndicatorCompute.submit({mode:'historical'})    // 直接提交
```

### 数据查看

`indicators.html` — 独立页面, 按股票全景 + 按指标排名 + ECharts 时间序列。

### 数据消费

- 策略 `load_indicators()` → `indicator_store.get_latest()`
- 决策中心 `_load_all_indicators()` → `indicator_store.get_latest()`
- 另类数据 Tab → `GET /alt/overview` → `indicator_store.get_latest_for_codes()`

---

## 八、研发方法论

新增任何指标或策略, 遵循三步:

```
1. 搜索资料学习   — 搞清楚业界标准算法 (论文/书籍/通达信源码)
2. temp_lab/ 验算  — 脚本跑真实数据, 出图表, 跟参考标准比对
3. 确认后写入系统  — 替换 indicators/ 或 strategies/ 下对应文件
```

严禁直接改系统里的文件调试——先在 temp_lab/ 跑通。
