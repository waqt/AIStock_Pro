# 数据中心模块 V2.0 — 完整设计

> 2026-05-19 | 六大子中心: 宏观 | 自选股 | 行情 | 基本面 | 财务报告 | 另类数据

---

## 一、宏观数据中心

### 1.1 数据持久化

表: `exchange_rates` (已有) — code(PK) / name / rate / change_pct / updated_at
> [!NOTE]
> 该表虽命名为 `exchange_rates`，但在实际运行中作为“全球大宗/汇率/核心宏观指标数据缓存表”，承载所有宏观监控指标的最新值与变化幅度。

| 数据项 | code | 说明 | 状态 |
|--------|------|------|------|
| 黄金 | XAU | 现货黄金（盎司/美元） | ✅ 已实现 (Sina hq.sinajs.cn) |
| 白银 | XAG | 现货白银（盎司/美元） | ✅ 已实现 (Sina) |
| 布伦特原油 | BRENT | 国际油价基准 | ✅ 已实现 (Sina) |
| 美元/人民币 | USD_CNY | 离岸/在岸汇率 | ✅ 已实现 (Sina) |
| 港币/人民币 | HKD_CNY | 港币汇率 | ✅ 已实现 (Sina) |
| 美国10年期国债收益率 | US10YT | 全球资产定价之锚 | ✅ 已实现 (akshare bond_zh_us_rate) |
| 美元指数 | DXY | 实时全球美元强度指标 | ❌ Sina hf_DINIW返回空; akshare需要第三方API Key |
| 美国联邦基金有效利率 | US_FED_RATE | 美联储基准利率 | ❌ akshare返回乱码+NaN, 数据不可用 |
| 中国信用脉冲 | CREDIT_IMPULSE | 社融增量占GDP比重变动率 | ⏳ 需要PBOC社融+GDP计算逻辑 |
| 中国PPI | CN_PPI | 工业品出厂价格变动 | ⏳ akshare最新值为NaN |
| 美国PPI | US_PPI | 美国工业通胀指标 | ⏳ 需要FRED API Key |

### 1.2 数据源

| 数据项 | 来源 | 端点/接口 | 频率 | 状态 |
|--------|------|------|------|------|
| XAU/XAG/BRENT | 新浪 | hq.sinajs.cn | 实时 | ✅ |
| USD_CNY/HKD_CNY | 新浪 | hq.sinajs.cn | 实时 | ✅ |
| 美国10年期国债收益率 | AkShare | `ak.bond_zh_us_rate` | 日度 | ✅ |
| 美元指数 | — | 待定 (Sina失效, akshare需Key) | 实时 | ❌ |
| 联邦基金利率 | — | akshare数据不可用 | 日度 | ❌ |
| 信用脉冲 | — | 待定 (需PBOC社融+NBS GDP) | 月度 | ⏳ |
| 中国PPI | — | akshare最新值为NaN | 月度 | ⏳ |
| 美国PPI | — | 需要FRED API Key | 月度 | ⏳ |

### 1.3 同步策略

- **触发方式**: 手动 POST `/data/macro/sync` (原 `/data/forex/sync` 兼容路由)
- **调度频率**: 建议每日开盘前 (08:30) 自动触发一次，且可在交易日收盘后 (15:45) 追加触发。
- **同步模式**:
  1. **增量同步**: 对高频日度数据（外汇、大宗商品、美债收益率、美联储利率等），优先采用增量拉取模式，合并最新数据至数据库中，并保留历史轨迹。
  2. **全量补充**: 对低频月度数据（信用脉冲、中/美 PPI），以近两年（24个月）为口径定期扫描，检测到数据缺失或发布更新时，进行回溯与补充同步，保证时间序列的完整性。

### 1.4 数据清洗

- **价格与指标值合理性校验**:
  - 外汇、大宗商品、美债收益率等金融行情：`rate <= 0` → 跳过写入/记录日志；
  - 信用脉冲、PPI 年率、利差等宏观指标：允许为负值，当且仅当 `rate == NULL` 或空值时跳过写入。
- **变化率异常监控**: `change_pct > 50%` → 标记数据异常，暂存审核表并发出预警（防范新浪等三方源因除权、拆分或故障导致的假数据）。
- **容错策略**: 获取数据失败时进行 3 次指数退避重试，若仍失败则记录 `Warning` 级别的系统日志。

### 1.5 数据完整性

- **存活检查 (Liveness Check)**:
  - **日度/实时数据**: 检查 `updated_at > 24h` → 标记为 `STALE`；
  - **月度宏观数据**: 检查最新观测值 `updated_at > 35天` → 标记为 `STALE`，提示需更新。
- **交叉校验 (Cross Validation)**:
  - 美元指数与美元/人民币汇率的反向相关性校验；
  - 美债收益率 10Y vs 2Y 倒挂及利差合理性检查；
  - 信用脉冲与社融/信贷规模方向一致性检查。

### 1.6 数据查看

- **API 接口**: GET `/data/macro/latest`
- **前端呈现**: 宏观数据大盘卡片 (展示指标当前值 + 环比/同比涨跌幅 + 趋势线迷你图 mini-chart)。

### 1.7 手动维护

- **全局/单项同步**: 支持前端一键拉取全局最新宏观数据，或针对单项指标（如美债收益率）进行重拉。
- **数值手动修正**: 对因口径调整导致的信用脉冲、PPI 历史数据缺失，支持管理员通过管理后台进行单条手动修正或补充（待实现）。

---

## 二、自选股中心

### 2.1 数据持久化

表: `watchlist` (已创建)

| 字段 | 类型 | 说明 |
|------|------|------|
| stock_code | VARCHAR(20) PK | 股票代码 |
| stock_name | VARCHAR(50) | 股票名称 |
| group_tag | VARCHAR(30) | 分组标签 |
| is_held | BOOLEAN | 是否已持仓 |
| sort_order | INT | 排序 |
| added_at | DATETIME | 添加时间 |

### 2.2 数据源

- 用户手动输入
- 从持仓一键导入
- 从投研报告核心标的导入

### 2.3 同步策略

- 行情: 复用 market_data sync, target_codes=自选股
- 估值: 复用 valuation sync, target_codes=自选股
- 指标: 可对自选股单独触发
- 自动补全名称: 从 StockInfo 查询

### 2.4 数据清洗

- 代码格式校验 (6位A股 / 5位港股)
- 名称自动补全
- 已存在代码 → 更新分组, 不重复插入

### 2.5 数据完整性

- is_held 标记: 与 positions 表交叉比对
- 退市检查: StockInfo 是否存在

### 2.6 数据查看

- API: GET /data/watchlist
- 前端: 按分组折叠, 标记[持仓]

### 2.7 手动维护

- 添加/删除/修改分组 (已实现)
- 批量导入 (待实现)
- 清理无效代码 (待实现)

---

## 三、股票行情中心

### 3.1 数据持久化

表: `market_data` (已有) — stock_code / trade_date (UNIQUE) / open / high / low / close / volume / amount / change_pct

### 3.2 数据源

| 优先级 | 来源 | 覆盖 | 延迟 |
|--------|------|------|------|
| 1 | AkShare (EastMoney) | A股全量 | 低 |
| 2 | Sina | A股全量 | 低 |
| 3 | AkShare (EastMoney) | 港股 | 中 |

### 3.3 同步策略

- AUTO 模式: 查 DB 最新日期 → gap > 1天 → 拉缺失天数
- 周末感知: 周五到周一 gap=3 仍为 HEALTHY
- target_codes: 单股/自选股/持仓 三种范围
- 增量条数: max(gap+5, 10), 上限500
- 写入: INSERT IGNORE 防重复
- 定时: 可选 APScheduler 交易日 15:30

### 3.4 数据清洗

- OHLC <= 0 → 跳过
- volume < 0 → 跳过
- 复权检测: 日涨跌幅 > 20% (非新股) → 标记
- high < low → 交换或跳过

### 3.5 数据完整性

- 每只股票: 日期范围 + 记录数
- 跳空检测: gap > 5天 → 标记 GAP
- 交叉验证: 随机抽样与新浪对比收盘价
- 覆盖率: indicators_coverage + valuation_coverage

### 3.6 数据查看

- Health table: 标的/区间/价格/gap/状态 (已实现)
- Detail popup: OHLC+涨跌幅+形态信号 (已实现)
- K线图: ECharts (已实现)
- 自选股价格查看：自选股显示最新价格，可查看K线详情（待实现）

### 3.7 手动维护

- 单股同步 (已实现)
- 手动输入同步 (已实现)
- 全量同步 (已实现)
- 指定日期范围补拉 (待实现)

---

## 四、股票基本数据中心

### 4.1 数据持久化

表: `stock_info` (已有) — stock_code(PK) / stock_name / exchange / industry / pe_ttm / pb / mcap_yi / float_mcap_yi / turnover_pct / updated_at

### 4.2 数据源

| 数据 | 来源 | 端点 |
|------|------|------|
| PE/PB/市值/换手率 | 腾讯 | qt.gtimg.cn |
| 股票列表(代码+名称) | 东财push2 | 全量5529只 |
| 行业分类 | 东财/申万 | 待接入 |

### 4.3 同步策略

- 估值: 腾讯批量API, 一次拉全部持仓
- 列表: 东财全量 (full=true) 或增量补充
- target_codes: 单股同步时仅拉该股
- 频率: 跟随行情同步自动触发

### 4.4 数据清洗

- PE为负 (亏损) → 保留
- 市值/PE日变 > 50% → 保留但标记
- 名称空格/特殊字符 → 规范化

### 4.5 数据完整性

- 持仓股缺估值检查
- industry 空值率统计
- PE/PB 为0 检查

### 4.6 数据查看

- 持仓表总市值列 (已实现)
- 基本面趋势迷你图 (待实现)

### 4.7 手动维护

- 估值同步按钮 (已有)
- 全量列表同步 (已有)
- CSV 导入 (已有)

---

## 五、财务报告中心

### 5.1 数据持久化 (新建表)

```sql
CREATE TABLE financial_statements (
    id INT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(20) NOT NULL,
    report_date DATE NOT NULL,
    revenue DOUBLE DEFAULT 0,
    parent_profit DOUBLE DEFAULT 0,
    operate_cost DOUBLE DEFAULT 0,
    sale_expense DOUBLE DEFAULT 0,
    manage_expense DOUBLE DEFAULT 0,
    op_cashflow DOUBLE DEFAULT 0,
    inventory DOUBLE DEFAULT 0,
    contract_liability DOUBLE DEFAULT 0,
    accounts_receivable DOUBLE DEFAULT 0,
    total_assets DOUBLE DEFAULT 0,
    current_assets DOUBLE DEFAULT 0,
    fixed_assets DOUBLE DEFAULT 0,
    total_liabilities DOUBLE DEFAULT 0,
    created_at DATETIME DEFAULT NOW(),
    UNIQUE KEY uq_stock_date (stock_code, report_date)
);
```

### 5.2 数据源

| API | 数据 |
|-----|------|
| akshare.stock_profit_sheet_by_quarterly_em | 营收/利润/成本/费用 |
| akshare.stock_cash_flow_sheet_by_quarterly_em | 经营现金流 |
| akshare.stock_balance_sheet_by_report_em | 存货/负债/应收/资产 |

### 5.3 同步策略

- 触发: 手动 (单股/批量)
- 范围: 每只拉全部历史 (8-20季度)
- 写入: UPSERT by (stock_code, report_date)
- 增量: 仅拉 MAX(report_date) + 3个月

### 5.4 数据清洗

- 营收/利润 QoQ > 500% → 保留但标记
- 现金流与利润符号相反且差异大 → 标记
- 缺失字段填 0

### 5.5 数据完整性

- 季度连续性检查
- 营收 vs 价格×股本 粗略校验

### 5.6 数据查看

- 8Q 趋势图: ECharts (待实现)
- 季度明细表 (待实现)
- 异常高亮

### 5.7 手动维护

- 单股拉取 (待实现)
- 批量拉取 (待实现)
- 删除重拉 (待实现)

---

## 六、另类数据中心

### 6.1 数据持久化 (新建表)

```sql
-- Web搜索缓存
CREATE TABLE search_cache (
    id INT AUTO_INCREMENT PRIMARY KEY,
    query_hash VARCHAR(64) UNIQUE,
    query_text VARCHAR(500),
    results JSON,
    source VARCHAR(20),
    cached_at DATETIME DEFAULT NOW(),
    expires_at DATETIME
);

-- 网页抓取缓存
CREATE TABLE scrape_cache (
    id INT AUTO_INCREMENT PRIMARY KEY,
    url_hash VARCHAR(64) UNIQUE,
    url VARCHAR(1000),
    title VARCHAR(500),
    content TEXT,
    scraped_at DATETIME DEFAULT NOW(),
    expires_at DATETIME
);
```

筹码/拥挤度数据复用 `stock_indicators` 表 (已有)。

### 6.2 数据源

| 数据 | 来源 | 说明 |
|------|------|------|
| Web搜索 | Brave/DDG | 加缓存层 |
| 网页正文 | WebScraper | 已有 |
| 筹码分布 | COST算法 | 已有 |
| 拥挤度 | 自研 | 已有 |
| 策略信号 | StrategySignal表 | 已有 |

### 6.3 同步策略

- 搜索缓存: TTL 24h, 未命中实时搜索+写缓存
- 爬虫缓存: TTL 7天
- 筹码/拥挤度: 跟随指标计算
- 清理: 定时清理过期缓存

### 6.4 数据清洗

- 搜索: 去重 (同URL), 过滤短摘要 (<20字符)
- 爬虫: 去HTML标签, 过滤导航/广告
- 筹码: 负价格跳过, 集中度>100%→100%

### 6.5 数据完整性

- 搜索缓存命中率
- 爬虫成功率
- 筹码数据覆盖率

### 6.6 数据查看

- 搜索历史 (待实现)
- 爬虫结果 (待实现)
- 筹码分布 ECharts (待实现)
- 拥挤度排名 (待实现)

### 6.7 手动维护

- 清除搜索/爬虫缓存 (待实现)
- 手动触发搜索/爬虫 (待实现)
