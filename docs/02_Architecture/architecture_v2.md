# AIStock_Pro 核心架构设计方案 (V2.1 - 混合动力版)

本架构旨在实现 **量化计算 (Code) + 本地技能 (Skill) + 远程智能 (AI)** 的深度融合，由 Python 3.10+ 异步引擎驱动。

---

## 🏗️ 1. 系统核心拓扑 (The Hybrid Pipeline)

系统不再是简单的请求/响应模式，而是采用 **Orchestrator (编排器)** 模式来驱动混合任务流：

```mermaid
graph TD
    %% 输入层
    Start[触发任务] --> Pipeline[Orchestrator 编排器]

    %% 混合执行流
    subgraph 混合流水线 (Analysis Chain)
        Pipeline --> Step1[量化计算层: Pandas/Numpy 计算小时线/日线指标]
        Step1 --> Step2[本地 Skill 层: 调用下载的专业 Skill/策略插件]
        Step2 --> Step3[AI 决策层: 远程 LLM 进行逻辑总结与事实核查]
    end

    %% 支撑体系
    subgraph 支撑中心
        Plugins[插件中心: /plugins/ 动态加载策略与技能]
        LogCenter[日志中心: 全链路 Trace 记录]
        Visual[可视化中心: ECharts 展现量化指标与策略逻辑树]
    end

    Step3 --> End[输出: 策略报告/调仓建议]
    
    %% 数据层
    MySQL[(MySQL: aistock_pro)]
    Redis[(Redis: 策略缓存)]
    Step1 <--> MySQL
    Step2 <--> Plugins
```

---

## 🔧 2. 详细设计规范

### 2.1 策略逻辑链 (Strategy Chain)
- **取消加权评分**：引入基于逻辑规则的“链式触发”。
- **原子条件**：例如 `MA_Long_Trend`, `RSI_Oversold`, `Alpha_High_Growth`。
- **DSL 实现**：使用简单的 Python Dict 或 YAML 定义逻辑组合（如：`ConditionA AND ConditionB THEN SuggestionC`）。

### 2.2 插件化 Skill 体系 (Plugin Architecture)
- **目录隔离**：
    - `backend/app/plugins/quant/`：存放量化算子插件。
    - `backend/app/plugins/research/`：存放投研分析 Skill（支持接入外部向量库）。
- **动态加载**：利用 Python 的 `importlib` 实现热加载，无需重启服务即可更新策略。

### 2.3 可观测性 (Non-functional Requirements)
- **结构化日志**：记录每一次 AI 调用的 `Input Token`, `Output Token`, `Strategy Signal`。
- **临时实验室 (Temp Lab)**：设立根目录 `temp_lab/`，专门存放 AI 生成的测试脚本、临时数据清理脚本。

### 2.4 可视化 (Visualization)
- **策略调试器**：前端增加专门页面，允许查看策略执行过程中的中间变量值。
- **指标大盘**：支持将量化指标（如：筹码分布、MACD背离点）叠加在 ECharts K线图上。

---

## 📂 3. 全新目录结构预览

```text
AIStock_Pro/
├── backend/
│   ├── app/
│   │   ├── api/            # 路由层
│   │   ├── core/           # 异步引擎、配置、日志定义
│   │   ├── domain/         # 核心业务逻辑 (持仓、资产)
│   │   ├── quant/          # 【混合层】基础量化算子
│   │   ├── agents/         # 【混合层】AI Orchestrator 与 Prompt 编排
│   │   ├── plugins/        # 【扩展层】可下载的 Skill 与策略插件
│   │   └── models/         # SQLAlchemy 2.0 异步模型
│   ├── scripts/            # 数据库迁移与生产工具
│   ├── temp_lab/           # AI 实验性脚本存放区
│   └── logs/               # 系统运行日志
├── frontend/               # 增强版可视化 UI
└── docs/                   # 架构与需求文档库
```

---
*Document Updated by AI Assistant*
*Date: 2026-05-15*
