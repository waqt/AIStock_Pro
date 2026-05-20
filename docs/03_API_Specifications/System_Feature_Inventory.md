# AIStock Pro V4.0 — 全系统功能清单

> 审计日期: 2026-05-19 | 版本: V4.0

---

## 模块A: 持仓管理

### A1. 持仓明细页 (positions.html)

| # | 功能 | 说明 | 状态 |
|---|------|------|------|
| A1.1 | 持仓列表 | 全部持仓: 代码/名称/持股数/成本价/现价/市值/盈亏金额/收益率/总市值 | |
| A1.2 | 现价刷新 | 实时从行情数据表读取最新收盘价 | |
| A1.3 | 总市值列 | 以"亿"为单位取整显示 (如 2751亿) | |
| A1.4 | 盈亏金额 | (现价 - 成本价) × 持股数 | |
| A1.5 | 盈亏颜色 | 正数绿色, 负数红色 | |
| A1.6 | 资产分布 | 总资产 / 可用现金 / 持仓市值 / 当日盈亏 | |
| A1.7 | K线走势弹窗 | ECharts 日K蜡烛图 + 成交量柱状图 (500天) | |
| A1.8 | 删除持仓 | 点击删除按钮, Modal.confirm 确认后 DELETE | |
| A1.9 | 刷新行情 | 按钮触发 POST /positions/update-prices | |
| A1.10 | 估值字段 | PE/PB/市值 从 stock_info 表左联查询 | |

### A2. 智能导入页 (import.html)

| # | 功能 | 说明 | 状态 |
|---|------|------|------|
| A2.1 | 截图OCR | 上传持仓截图 → 豆包→DeepSeek→Gemini 链式识别 | |
| A2.2 | 交易截图 | 上传交易截图 → AI识别交易记录 | |
| A2.3 | Excel导入 | 上传 .xlsx/.xls → 解析持仓/交易 | |
| A2.4 | 文本解析 | 粘贴自由文本 → AI提取股票代码+数量+价格 | |
| A2.5 | 预览编辑 | 识别结果表格展示, 可逐行修改 | |
| A2.6 | 全选/单选 | 勾选要导入的记录 | |
| A2.7 | 覆盖/追加 | clear_old=true 清除旧持仓, false 追加 | |
| A2.8 | 批量执行 | 一键写入数据库 | |
| A2.9 | 缓存管理 | 查看/清除 AI 识别缓存 | |
| A2.10 | Tab切换 | 持仓导入 ⇄ 交易记录导入 | |

---

## 模块B: AI 投研

### B1. AI投研页 (research.html)

| # | 功能 | 说明 | 状态 |
|---|------|------|------|
| B1.1 | 每日市场扫描 | 点击"开始扫描" → 4角度Web搜索 → LLM识别3-5个热门赛道 | |
| B1.2 | 赛道卡片 | 赛道名 / 景气评分 1-10 / 核心逻辑 / A股映射代码 | |
| B1.3 | 赛道点击下钻 | 点击卡片 → 自动填入行业名 → 触发 DAG 深度分析 | |
| B1.4 | 供应链下钻 | 输入行业(可选代码) → DAGOrchestrator 5专家并行 | |
| B1.5 | 分析进度 | Phase A(并行扫描) → B(交叉审计) → C(定价) → D(CIO报告) | |
| B1.6 | CIO综合报告 | final_summary 核心结论 2-4句 | |
| B1.7 | Top Picks | 排名/代码/名称/判断(BUY/HOLD)/置信度(HIGH/MEDIUM)/仓位%/角色 | |
| B1.8 | 供应链L1-L4 | 每层: 预期差评分(1-10)/缺口原因/市场规模/国产化率/技术代差 | |
| B1.9 | level_assets | 每层全量公司表: 代码/名称/角色/市占率/技术水平/垄断评分 | |
| B1.10 | 交叉审计 | 财务审计(剪刀差/Beneish/OCF) vs 人力审计(创始人/CTO/专利) 并排 | |
| B1.11 | 关键风险 | 类型(地缘/技术替代/财务/供需) / 严重度(高/中/低) / 描述 | |
| B1.12 | 待观察催化剂 | 即将发生的关键事件列表 | |
| B1.13 | 执行时间线 | CIO建议的建仓时间窗口 | |
| B1.14 | 数据新鲜度 | 报告生成时间 + 各数据源说明 (Web搜索/行情/财报/估值) | |
| B1.15 | 历史研报 | 左侧面板: 最近20篇报告列表 (日期/行业/Agent/标的总数) | |
| B1.16 | 研报回看 | 点击历史报告加载完整分析 (DAG/V3.0格式自动识别) | |
| B1.17 | 删除研报 | 点击删除按钮, Modal.confirm 确认 | |
| B1.18 | 缓存恢复 | localStorage 保存最近一次分析, 刷新页面自动恢复 | |

### B2. V4.0 投研 Agent (后端)

| # | Agent | 职责 | 输入 | 输出 | 状态 |
|---|-------|------|------|------|------|
| B2.1 | MarketScanner | 4角度Web搜索实时市场数据 → LLM识别热门赛道 | 无参数 | hot_industries + briefing | |
| B2.2 | GlobalCapexScanner | 4角度搜索MAG7 CapEx → LLM景气方向 | industry(可选) | capex_signals + hot_sectors | |
| B2.3 | SupplyChainHacker | 3轮迭代搜索+L1-L4瓶颈定位+全量资产发现 | industry | supply_chain_map + level_assets + core_stocks + temporal | |
| B2.4 | SupplyChainHacker.analyze_level | 单层级独立深钻 (如"先进封装CoWoS") | industry + level_name | all_assets(5-8家) + market_structure + investment_thesis | |
| B2.5 | FinancialAuditor | 8Q剪刀差+四连击+Beneish M-Score+存货/合同负债/OCF | stock_code | verdict(PASS/CAUTION/FAIL) + flags + metrics[8Q] | |
| B2.6 | HumanCapitalDetective | 3维搜索(创始人/专利/股权) → LLM审计 | stock_code + name | verdict(STRONG/ADEQUATE/WEAK) + founder_background + patent_quality | |
| B2.7 | ValuationPricer | 全球对标+PEG/PS+护城河时间窗 + DB硬锚PE/PS | stock + audit结果 | target_valuation + moat_window + position_suggest | |
| B2.8 | DAGOrchestrator | Phase A(并行扫描) → B(并行审计) → C(定价) → D(CIO合成) | industry | final_summary + top_picks + portfolio_allocation + risks | |
| B2.9 | 研报持久化 | JSON文件存储到 data/research_reports/ | - | save/list/get/delete | |
| B2.10 | 数据新鲜度戳 | 每个API响应附带 ResearchAgent.freshness_stamp() | - | generated_at + data_sources 说明 | |

---

## 模块C: 量化决策

### C1. 量化决策页 (quant.html)

| # | 功能 | 说明 | 状态 |
|---|------|------|------|
| C1.1 | Tab: 算子清单 | 列出全部16个已注册算子 | |
| C1.2 | 算子分类 | 趋势(蓝)/动量(绿)/波动(金)/量能(红)/拥挤度(紫) 徽章 | |
| C1.3 | 算子详情 | 名称/分类/参数/依赖字段/输出字段 | |
| C1.4 | Tab: 策略清单 | 6个传统策略 + 2个AI链策略 | |
| C1.5 | 策略类型 | 传统量化(绿) / AI链(紫) 徽章 | |
| C1.6 | AI链详情 | logic_chain全文 + persona + temperature + 依赖指标 | |
| C1.7 | Tab: 决策引擎 | 股票代码输入框 + 单股/全部持仓 按钮 | |
| C1.8 | 单股决策 | 8个策略并行 → DecisionReport | |
| C1.9 | 策略明细表 | 每策略: signal(BUY/SELL/HOLD)/confidence/reasoning | |
| C1.10 | 投票汇总 | BUY/SELL/HOLD票数 + score bar(绿/红) + 决策逻辑公式 | |
| C1.11 | 风险标记 | chip_risk/crowding_risk (不否决, 仅提示) | |
| C1.12 | 全部持仓 | 批量决策, 卡片化展示每只股票结果, 点击查看单股详情 | |
| C1.13 | 全量计算 | 对全部持仓跑historical模式(逐日全量) | |

### C2. 量化模块 (后端)

| # | 类别 | 算子/策略 | 说明 | 状态 |
|---|------|----------|------|------|
| C2.1 | 趋势 | MA | 简单移动平均 (5/10/20/60/120/250日) | |
| C2.2 | 趋势 | MACD | 金叉死叉 + 柱状图 (12/26/9) | |
| C2.3 | 趋势 | KDJ | 随机指标 (9/3/3) | |
| C2.4 | 动量 | RSI | 相对强弱 (14日) | |
| C2.5 | 动量 | ATR | 平均真实波幅 (14日) | |
| C2.6 | 动量 | CCI | 商品通道指数 (20日) | |
| C2.7 | 波动 | Bollinger | 布林带 (20日, 2σ) | |
| C2.8 | 波动 | Bollinger Width | 布林宽度 (带宽%) | |
| C2.9 | 量能 | OBV | 能量潮 | |
| C2.10 | 量能 | VolumeMA | 成交量均线 (5/10/20日) | |
| C2.11 | 量能 | VWAP | 成交量加权平均价 | |
| C2.12 | 筹码 | Concentration | 筹码集中度 + 峰值价格 + 平均成本 | |
| C2.13 | 筹码 | Peak Price | 峰值/谷值定位 + 单峰/多峰判定 | |
| C2.14 | 筹码 | Pattern | 六大形态识别 + BUY/SELL信号 | |
| C2.15 | 拥挤度 | Turnover Ratio | 20日/120日换手率比值 | |
| C2.16 | 拥挤度 | Sharpe 60d | 60日年化夏普比率 | |
| | | | | |
| C2.17 | 策略 | macd_cross | MACD金叉买入, 死叉卖出 | |
| C2.18 | 策略 | rsi_oversold | RSI<30超卖买入, >75超买卖出 | |
| C2.19 | 策略 | bollinger_break | 放量突破Bollinger上轨买入, 跌破中轨卖出 | |
| C2.20 | 策略 | ma_alignment | MA5>10>20>60多头排列买入 | |
| C2.21 | 策略 | kdj_golden | KDJ低位金叉买入, 高位死叉卖出 | |
| C2.22 | 策略 | volume_divergence | 价涨量缩→卖出, 价跌量增→买入 | |
| C2.23 | AI链 | aggressive_short | YAML定义, 激进短线: MACD+RSI+KDJ+Vol共振 | |
| C2.24 | AI链 | conservative_long | YAML定义, 稳健长线: 均线+MACD+缩量企稳 | |
| | | | | |
| C2.25 | 决策 | DecisionCenter | 并行调度所有策略 → 加权投票 (传统1.0/AI链1.2, 1.5x阈值) | |
| C2.26 | 决策 | VoteSummary | BUY/SELL/HOLD票数 + 分数 + 决策公式 (透明可追溯) | |
| C2.27 | 决策 | RiskFlags | chip_risk/crowding_risk 不否决, 仅提醒 | |
| C2.28 | 持久化 | StrategySignal表 | stock_code/strategy/signal/confidence/reasoning/decision_date | |
| C2.29 | 历史查询 | GET /quant/signals | 按股票/日期/策略筛选 | |
| C2.30 | 重跑 | POST /quant/signals/rerun | 清理某日数据 + 重跑全部策略 | |
| | | | | |
| C2.31 | 计算 | compute_snapshot | 仅计算最新一天, 覆盖写入 | |
| C2.32 | 计算 | compute_historical | 逐日全量计算(向量化), 批量写入 | |
| C2.33 | 计算 | compute_incremental | 从上一次记录后补算新日期 | |
| C2.34 | 管理 | clear_and_recompute | 清理全量数据 + 重新计算 | |
| C2.35 | 管理 | coverage API | 查询某股的指标覆盖日期范围 (起止日期/天数) | |
| C2.36 | AI链 | 热编辑 | PUT /strategies/ai-chain/{name} → YAML文件更新, 即时生效 | |

---

## 模块D: 数据中心

### D1. 数据中心页 (data.html)

| # | 功能 | 说明 | 状态 |
|---|------|------|------|
| D1.1 | 智能全量同步 | 全持仓: 拉行情 + 更新PnL + 同步估值 | |
| D1.2 | 刷新行情 | 仅拉价格 (PRICE_ONLY模式) | |
| D1.3 | 重算指标 | 触发旧版 calc_indicators 任务 | |
| D1.4 | 同步公共数据 | 独立拉汇率/黄金/原油 (不触发股票同步) | |
| D1.5 | 手动输入 | 输入任意股票代码 (不限于持仓股) | |
| D1.6 | 手动同步 | 对该代码拉行情 + 估值 (单股, 跳宏观) | |
| D1.7 | 手动算指标(快照) | 仅算最新一天指标 | |
| D1.8 | 手动算指标(历史) | 对该代码逐日全量计算 (约30秒/股) | |
| D1.9 | 数据源状态 | 各源在线●/离线● + 延迟ms + 优先级 | |
| D1.10 | 健康总览 | synced_stocks / latest_sync_date / indicators_coverage / valuation_coverage / status | |
| D1.11 | 行情体检表 | 每行: 名称/代码/行情区间(起~止)/最新价格/gap天数/状态 | |
| D1.12 | 状态颜色 | HEALTHY(绿) / STALE(金) / GAP(红) | |
| D1.13 | 周末感知 | 周一gap=3(周五数据) → HEALTHY; 周二gap=4 → HEALTHY | |
| D1.14 | 详细体检 | 弹窗: 数据范围 + 开/高/低/收/涨跌幅 + 形态信号 | |
| D1.15 | 单股同步按钮 | 每行独立同步 (避防爬) | |
| D1.16 | CSV导入 | 上传CSV批量添加股票代码 | |
| D1.17 | 全量同步列表 | 从东财拉取5529只A股代码+名称 | |
| D1.18 | 执行终端 | 操作日志滚动显示, 超过100条清理 | |

### D2. 数据同步 (后端)

| # | 功能 | 说明 | 状态 |
|---|------|------|------|
| D2.1 | 多源降级 | AkShare(优先) → Sina(兜底), 自动切换 | |
| D2.2 | 增量感知 | AUTO模式: 查DB最新日期, 仅拉缺失天数 | |
| D2.3 | 目标筛选 | target_codes参数: 指定股票代码(含非持仓股) | |
| D2.4 | 宏经跳过 | 有target_codes时跳过sync_macro_data | |
| D2.5 | 估值同步 | 腾讯qt.gtimg.cn → PE/PB/市值/换手率 → stock_info | |
| D2.6 | 估值定向 | target_codes参数控制估值同步范围 | |
| D2.7 | 宏观同步 | 新浪hq.sinajs.cn → 美元指数/黄金/白银/原油/美元人民币/港币人民币 | |
| D2.8 | 源探活 | 5分钟间隔probe各数据源, 标记在线/离线 | |

---

## 模块E: 任务系统

| # | 功能 | 所属页面 | 说明 | 状态 |
|---|------|---------|------|------|
| E1 | 任务注册表 | definitions.html | code/名称/描述/模块路径/cron/是否启用 | |
| E2 | 编辑cron | definitions.html | 点击修改, PUT /definitions/{code} | |
| E3 | 定时Job | definitions.html | 已调度的Job及下次运行时间 | |
| E4 | 手动触发 | definitions.html | 选择任务 → POST /executions → 执行 | |
| E5 | 执行历史 | history.html | 分页: 时间/任务名/状态/进度/耗时/摘要 | |
| E6 | 任务筛选 | history.html | 按task_code下拉筛选 | |
| E7 | 详情弹窗 | history.html | 查看单次执行的完整参数和结果 | |
| E8 | 清理旧记录 | history.html | 删除7天前 + 删除全部 | |
| E9 | 并发控制 | 后端 | asyncio.Semaphore(3), 最多3个任务同时运行 | |
| E10 | 状态管理 | 后端 | PENDING→RUNNING→SUCCESS/FAILED/CANCELLED | |
| E11 | 强杀任务 | 后端 | DELETE /executions/{id} → CancelledError | |
| E12 | 调度热更新 | 后端 | PUT /definitions/{code} → 自动refresh_job | |
| E13 | sync_market | 任务 | 行情同步(支持AUTO/PRICE_ONLY/target_codes) | |
| E14 | calc_indicators | 任务 | 旧版指标重算(基于engine/indicators.py) | |
| E15 | ai_recognize | 任务 | AI截图识别(豆包→DeepSeek→Gemini链式) | |

---

## 模块F: 系统基础设施

| # | 类别 | 功能 | 说明 | 状态 |
|---|------|------|------|------|
| F1 | 数据库 | MySQL异步 | aiomysql + SQLAlchemy 2.0 async | |
| F2 | 数据库 | 自动建表 | 启动时 Base.metadata.create_all | |
| F3 | 数据库 | 10张表 | Position/MarketData/StockIndicator/TaskDefinition/TaskExecution/TradeHistory/ExchangeRate/StockInfo/StrategySignal/SystemSetting | |
| F4 | 日志 | loguru | 结构化日志, 按日期滚动到 logs/ | |
| F5 | 配置 | pydantic-settings | 从 .env 读取, settings.XXX 全局访问 | |
| F6 | AI | DeepSeek(主) | api.deepseek.com/anthropic/messages (Anthropic兼容) | |
| F7 | AI | Doubao(次) | ark.cn-beijing.volces.com (豆包Seed) | |
| F8 | AI | Gemini(视觉) | Google Gemini Vision API (OCR辅助) | |
| F9 | 搜索 | DDG→Brave双源 | 通过Clash代理 127.0.0.1:7890 | |
| F10 | CORS | 全开放 | allow_origins=["*"] | |
| F11 | 静态 | 前端挂载 | StaticFiles 挂载 frontend/ 在根路径 | |
| F12 | 健康 | GET /health | {"status":"healthy","architecture":"DDD / Clean V5.0"} | |
| F13 | 前端 | 侧边栏 | 业务模块(指挥/持仓/AI投研/量化/市场分析) + 系统分隔区 | |
| F14 | 前端 | 顶栏 | 账户总资产 + 当日盈亏 + 同步/建议按钮 | |
| F15 | 前端 | 跑马灯 | 市场行情ticker, 30s刷新 | |
| F16 | 前端 | 任务监控 | task_monitor.js, 8s轮询活跃任务 | |
| F17 | 前端 | 暗色弹窗 | Modal.alert / Modal.confirm / Modal.danger | |
| F18 | 前端 | escHtml | common.js 全局HTML转义 | |
| F19 | 规约 | DDD分层 | domain/* → framework/* → models/, domain间禁止互引用 | |
| F20 | 规约 | 禁止项 | print() / requests.get() / 裸asyncio.create_task() | |
| F21 | 规约 | 指标范式 | 继承BaseIndicator + @register, 自动发现 | |
| F22 | 规约 | 策略范式 | 继承TimingStrategy + @register_strategy, AI链用YAML | |
| F23 | 规约 | 前端模板 | <body data-page-id> + sidebar + topbar + workspace | |
| F24 | 规约 | 冒烟测试 | 16 API, 全部PASS方可提交 | |
| F25 | 规约 | Pre-commit | 语法检查(py_compile) + 烟雾测试(smoke_test.py) | |

---

## 模块G: 已知问题与待办

| # | 位置 | 问题 | 建议 | 状态 |
|---|------|------|------|------|
| G1 | suggestions.html | 完全占位 "Strategy Engine Coming Soon" | 待需求确认 | |
| G2 | morning_report.html | 静态占位, 缺 data-page-id | 待需求确认: 是否需要晨报页? | |
| G3 | closing_report.html | 调用不存在API /reports/*, 缺 data-page-id | 修复或删除 | |
| G4 | calc_indicators任务 | 仍用旧版 engine/indicators.py (5个算子) | 迁移到 IndicatorRunner (16个算子) | |
| G5 | domain/quant/tasks/__init__.py | import dead calc module | 清理死代码 | |
| G6 | tasks_registry.html | meta refresh 重定向桩 | 保留或删除 | |
| G7 | tasks_history.html | meta refresh 重定向桩 | 保留或删除 | |
| G8 | data.html D1.3按钮 | "重算指标"调旧calc_indicators | 改为调新 IndicatorRunner.compute_batch | |

---

> **统计**: 模块A-G 共 170 项功能点 | 后端API: 71个 | 数据库表: 10张 | 后台任务: 3个 | AI Agent: 8个(V4.0:6 + V3.0:2) | 量化算子: 16个 | 量化策略: 8个
