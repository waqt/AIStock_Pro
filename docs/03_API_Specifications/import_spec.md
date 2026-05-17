# AIStock Pro 持仓/交易导入模块规格书 V1.0

## 1. 模块概述

导入模块负责将外部持仓和交易数据导入系统。支持三种输入方式：截图 OCR（豆包 AI）、Excel 表格上传、文本粘贴解析。导入时支持全量覆盖和增量追加两种模式。

## 2. 数据流

```
截图/Excel/文本
    ↓
前端采集 (import.html)
    ↓
API 路由 (api/import_api.py) ── 7 个端点 /api/ai/*
    ↓
AI 识别服务 (core/ai_service.py) ── 豆包 → DeepSeek → Gemini 链式
    ↓
批量写库 ── Position / TradeHistory
```

## 3. 输入方式

### 3.1 截图 OCR

- 前端采集截图 → base64 → 提交异步任务
- AI 模型链：**豆包 Seed** (primary, 国内直连) → **DeepSeek Vision** (Anthropic 兼容) → **Gemini Vision** (需 VPN, 兜底)
- 图片预处理：Pillow 压缩至 1024x1024 JPEG q=70
- 超时：豆包 90s，DeepSeek 60s，Gemini 60s
- 结果缓存至 `import_cache.json`，前端轮询获取

### 3.2 Excel 上传

- 支持 .xlsx / .xls
- 使用 pandas + openpyxl 解析
- 列名灵活匹配（中英文，如 "股票代码"/"code"/"stock_code"）
- 输出格式与截图识别一致

### 3.3 文本粘贴

- 规则解析，非 AI
- 分隔符：tab / 逗号(中英) / 空格
- 格式：`代码 名称 数量 [成本价]`

## 4. API 端点清单

| 方法 | 路径 | 说明 | 异步 |
|------|------|------|------|
| GET | `/api/ai/get-cache` | 获取上次识别缓存 | - |
| POST | `/api/ai/recognize-image` | 持仓截图识别 | 是 (TaskEngine) |
| POST | `/api/ai/recognize-trades` | 交易截图识别 | 是 (TaskEngine) |
| POST | `/api/ai/parse-text` | 文本解析 | 否 |
| POST | `/api/ai/batch-import` | 批量导入持仓 | 否 |
| POST | `/api/ai/batch-import-trades` | 批量导入交易 | 否 |
| POST | `/api/ai/upload-excel` | Excel 解析 | 否 |

### 异步识别流程

```
POST /api/ai/recognize-image → 立即返回 {task_id}
前端每 1.5s 轮询 /api/ai/get-cache
识别完成 → 缓存命中 → 渲染预览
```

## 5. 数据模型映射

AI 识别输出字段 → DB 字段：

| AI 字段 | DB 字段 (Position) | 说明 |
|---------|-------------------|------|
| stock_code | stock_code | 直接映射 |
| stock_name | stock_name | 直接映射 |
| shares | volume | 股数 |
| cost_price | avg_cost | 成本价 |
| current_price | current_price | 现价 |

| AI 字段 | DB 字段 (TradeHistory) | 说明 |
|---------|----------------------|------|
| stock_code | stock_code | 直接映射 |
| stock_name | 不存储 | 仅用于展示 |
| trade_type | action | BUY/SELL |
| shares | volume | 股数 |
| price | price | 成交价 |
| trade_date | trade_date | 日期，支持多格式 |

导入时自动计算：market_value, profit_loss, profit_loss_ratio, amount, commission, stamp_tax。

## 6. 导入模式

- **覆盖模式** (`clear_old=true`)：DELETE 全部旧持仓 → INSERT 新数据
- **追加模式** (`clear_old=false`)：按 stock_code 查找 → 存在则更新，不存在则插入

## 7. 配置依赖

| 环境变量 | 用途 |
|----------|------|
| DOUBAO_API_KEY | 豆包 OCR (主引擎) |
| DOUBAO_BASE_URL | 默认 ark.cn-beijing.volces.com |
| DOUBAO_MODEL | 默认 doubao-seed-2-0-mini-260428 |
| DEEPSEEK_API_KEY | DeepSeek 备选 |
| DEEPSEEK_BASE_URL | 支持 anthropic 兼容端点 |
| GEMINI_API_KEY | Gemini 兜底 (需 VPN) |

## 8. 关键设计决策

- **豆包优先**：豆包国内直连，无需 VPN，作为主 OCR 引擎
- **异步识别**：截图识别耗时 5-15s，通过 TaskEngine 异步执行，避免 HTTP 超时
- **缓存中间结果**：识别结果先写 `import_cache.json`，前端预览后用户选择导入
- **灵活列名**：Excel 解析支持中英文多种列名变体，兼容不同券商导出格式
- **手续费自动计算**：交易导入时自动计算佣金 (0.03%, 最低 5 元) 和印花税 (卖出 0.1%)

---

*Document: V1.0, 2026-05-17*
