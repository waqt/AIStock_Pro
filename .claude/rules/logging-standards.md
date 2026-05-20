# 日志输出规范

## 一、日志级别定义

| 级别 | 使用场景 | 示例 |
|------|---------|------|
| `logger.info` | 关键操作开始/完成、状态变更、数据统计 | 同步完成、Agent分析开始、指标计算数量 |
| `logger.success` | 操作成功完成 (loguru独有) | 系统启动序列完成、任务执行成功 |
| `logger.warning` | 可恢复的异常、降级、数据不足 | API超时重试、数据源降级、指标计算跳过 |
| `logger.error` | 不可恢复的失败、异常 | 任务执行失败、数据库连接丢失、AI调用崩溃 |
| `logger.debug` | 开发调试信息 (生产环境关闭) | 函数入参、中间变量 |

## 二、日志格式规范

### 2.1 模块标识 (必须)
每条日志必须以 `[ModuleName]` 开头, 标识来源模块。

```
# ✅ 正确
logger.info(f"[MarketScanner] Scan complete: {n} industries found")
logger.warning(f"[FinancialAuditor] {code}: insufficient quarters ({n}<4)")

# ❌ 错误 — 无模块标识
logger.info(f"Scan complete: {n} industries")
```

### 2.2 关键变量 (必须)
关键业务变量用 `key=value` 格式内联, 不用自然语言描述。

```
# ✅ 正确
logger.info(f"[QuantEngine] Synced {code}: {new_rows} new rows, {elapsed:.1f}s")

# ❌ 错误 — 变量嵌入自然语言, 难以解析
logger.info(f"[QuantEngine] Successfully synchronized stock {code} with {new_rows} new rows in {elapsed} seconds")
```

### 2.3 股票代码 (涉及股票时必须)
```
logger.info(f"[DecisionCenter] {code} {name}: verdict={verdict}, score={score}")
logger.warning(f"[IndicatorRunner] {code}: missing columns {missing}, skipping {name}")
```

### 2.4 任务ID (任务上下文必须)
```
logger.info(f"[TaskEngine] [task={exec_id}] Started: {task_code}")
logger.error(f"[TaskEngine] [task={exec_id}] Failed: {e}")
```

## 三、各模块日志要求

### 3.1 API 端点

每个 API 端点必须在**入口**和**出口**各打一条日志:

```python
@router.post("/decide/{stock_code}")
async def decide_single(stock_code: str):
    logger.info(f"[QuantAPI] Decision requested: {stock_code}")
    try:
        result = await center.decide([stock_code])
        logger.info(f"[QuantAPI] Decision complete: {stock_code} → {result[0].final_signal}")
        return {"success": True, "data": result[0].model_dump()}
    except Exception as e:
        logger.error(f"[QuantAPI] Decision failed: {stock_code} | {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

**当前缺失日志的端点**: data.py 大部分端点、positions.py、import_api.py、quant API 端点 (indicators/strategies/decision) — 均需补加。

### 3.2 数据同步

```
# 开始
logger.info(f"[DataSync] Starting {mode}: {n} stocks")
# 每只股票
logger.info(f"[DataSync] {code}: +{rows} rows, source={source_name} ({elapsed_ms}ms)")
# 完成
logger.info(f"[DataSync] Complete: {n_stocks} stocks, {total_rows} rows, {total_time:.1f}s")
# 降级
logger.warning(f"[DataSync] {code}: {source1} failed ({reason}), falling back to {source2}")
```

### 3.3 投研 Agent

已基本符合规范。需确保每个 Agent 的 `analyze()` 入口和出口都有日志:

```
logger.info(f"[{self.name}] Starting: {industry}")
logger.info(f"[{self.name}] Phase A complete: {n} signals")
logger.info(f"[{self.name}] Complete: {n_stocks} stocks, {elapsed:.1f}s")
```

**需补加**: IndustryAnalyst (当前完全无日志)

### 3.4 量化策略

**当前全部缺失**。每个策略的 `analyze()` 方法必须加日志:

```python
async def analyze(self, stock_code: str) -> SignalResult:
    logger.info(f"[{self.name}] Analyzing {stock_code}")
    # ... 策略逻辑 ...
    logger.info(f"[{self.name}] {stock_code} → {result.signal} (conf={result.confidence})")
    return result
```

### 3.5 指标计算

```python
logger.info(f"[IndicatorRunner] {mode} started: {stock_code}")
logger.info(f"[IndicatorRunner] {stock_code}: {n} indicators computed, {n_days} days stored")
logger.warning(f"[IndicatorRunner] {stock_code} {name}: missing columns {missing}, skipped")
```

### 3.6 前端

```javascript
// ✅ 正确 — 包含上下文
console.error('[Quant] Decision failed:', stockCode, e.message);

// ❌ 错误 — 无上下文
console.error(e);

// 关键用户操作
console.log('[Research] Scan started');
console.log('[Quant] Portfolio decision triggered:', codes.length, 'stocks');
```

## 四、禁止事项

- ❌ `print()` — 使用 logger
- ❌ 无模块标识的裸日志
- ❌ 敏感信息 (API Key、密码、Token) 出现在日志中
- ❌ 日志中使用中文标点 (英文逗号/冒号便于 grep)
- ❌ 在循环内打 INFO 级别日志 (会刷屏 — 用 DEBUG 或打汇总)

## 五、检查方式

```bash
# 查找缺失日志的模块 (无 logger import 的文件)
grep -L "from app.framework.logger import logger" backend/app/domain/quant/strategies/traditional/*.py

# 查找使用 print() 的违规
grep -rn "\bprint(" backend/app/ --include="*.py"

# 查找无模块标识的日志
grep -rn "logger\.\(info\|warning\|error\)(" backend/app/ --include="*.py" | grep -v "\["
```
