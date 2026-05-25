# 五、前端设计

> 本文档定义 research.html 升级方案、2 个新页面 (pipeline/validation) 和组件设计。

---

## 5.1 现有前端概况

### 5.1.1 页面清单 (15 页)

| # | 页面 | 用途 | 状态 |
|---|------|------|------|
| 1 | `index.html` | 首页/导航 | ✅ |
| 2 | `positions.html` | 持仓管理 | ✅ |
| 3 | `import.html` | 智能导入 (OCR/Excel) | ✅ |
| 4 | `research.html` | AI 投研指挥中心 | ✅ → 升级 |
| 5 | `quant.html` | 量化决策 | ✅ |
| 6 | `data.html` | 数据中心 (6 Tab) | ✅ → 小升级 |
| 7 | `indicators.html` | 指标数据 | ✅ |
| 8 | `definitions.html` | 任务注册表 | ✅ |
| 9 | `history.html` | 任务执行历史 | ✅ |
| 10 | `settings.html` | 系统设置 | ✅ |
| 11 | `morning_report.html` | 晨报 (占位) | 🏗️ |
| 12 | `closing_report.html` | 收盘报 (占位) | 🏗️ |
| 13 | `suggestions.html` | 策略建议 (占位) | 🏗️ |
| 14-15 | `tasks_*.html` | 重定向桩 | ✅ |

### 5.1.2 技术规范

| 方面 | 规范 |
|------|------|
| 框架 | 原生 HTML + Vanilla JS (无框架) |
| 样式 | `css/` 目录, 暗色主题 |
| 组件 | `js/framework/` 下的公共组件 (indicator_compute.js 等) |
| 图表 | ECharts 5.x |
| 数据缓存 | localStorage (刷新恢复) |
| 任务监控 | `js/framework/task_monitor.js` (8s 轮询) |
| 弹窗 | Modal.alert / Modal.confirm / Modal.danger |
| 页面模板 | `<body data-page-id>` + sidebar + topbar + workspace |

---

## 5.2 research.html 升级方案

### 5.2.1 新增功能清单

| # | 功能 | 说明 | 优先级 |
|---|------|------|--------|
| F1 | Pipeline 运行面板 | 替代原有进度条, DAG 步骤状态卡片 | P0 |
| F2 | Step 进度实时更新 | 8s 轮询 Pipeline 状态, 自动更新面板 | P0 |
| F3 | 产业推演渲染块 | 报告新增 `system_dynamics` 章节渲染 | P0 |
| F4 | 预期差渲染块 | 报告新增 `expectation_gap` 章节渲染 | P0 |
| F5 | 论点验证渲染块 | 报告新增 `thesis_validation` 章节渲染 | P1 |
| F6 | 追溯标签页 | 报告详情页新增「追溯」Tab | P1 |
| F7 | Pipeline 历史列表 | 左侧面板增加 Pipeline run 列表 | P1 |
| F8 | 失败恢复按钮 | Pipeline 失败时显示「从失败点继续」 | P1 |

### 5.2.2 Pipeline 运行面板

**位置**: 替代原有 `#analysisProgress` 区域

```
┌────────────────────────────────────────────────────────┐
│  Pipeline: 20260525_SOFC_v1                   ⏱ 3:45   │
│  行业: SOFC燃料电池  模式: full                         │
│                                                        │
│  ┌─────────────┬──────┬──────────┐                    │
│  │ 步骤        │ 状态 │ 耗时      │                    │
│  ├─────────────┼──────┼──────────┤                    │
│  │ Step1 宏观   │ ✅   │ 缓存命中  │                    │
│  │ Step2 看门人 │ ✅   │ 20s      │                    │
│  │ Step3 产业链 │ ✅   │ 2m00s    │                    │
│  │ Step4 推演   │ 🔄   │ 45s...   │                    │
│  │ Step5 审计   │ ⏳   │ —        │                    │
│  │ Step9 预期差 │ ⏳   │ —        │                    │
│  │ Step11 报告  │ ⏳   │ —        │                    │
│  └─────────────┴──────┴──────────┘                    │
│                                                        │
│  [████████████░░░░░░░░░░░ 43%]                        │
│                                                        │
│  当前: 系统动力学推演 — 分析资源迁移与瓶颈链...          │
└────────────────────────────────────────────────────────┘
```

**实现要点**:

```javascript
// 轮询 Pipeline 状态 (复用 task_monitor.js 的 8s 间隔)
async function pollPipelineStatus(runId) {
    const resp = await fetch(`/api/research/pipeline/${runId}`);
    const data = await resp.json();
    
    // 更新步骤卡片
    const stepsContainer = document.getElementById('pipelineSteps');
    stepsContainer.innerHTML = '';
    
    for (const [stepName, stepInfo] of Object.entries(data.steps)) {
        const card = createStepCard(stepName, stepInfo);
        stepsContainer.appendChild(card);
    }
    
    // 更新进度条
    const progressBar = document.getElementById('pipelineProgress');
    const pct = Math.round((data.completed_steps / data.total_steps) * 100);
    progressBar.style.width = `${pct}%`;
    progressBar.textContent = `${pct}%`;
    
    // 完成或失败时停止轮询
    if (data.status === 'COMPLETED') {
        clearInterval(pollInterval);
        loadReport(data.report_id);
    } else if (data.status === 'FAILED') {
        clearInterval(pollInterval);
        showFailureRecovery(runId, data.failed_step);
    }
}

function createStepCard(name, info) {
    const statusIcons = {
        COMPLETED: '✅', RUNNING: '🔄', PENDING: '⏳', 
        FAILED: '❌', SKIPPED: '⏭️'
    };
    // ... DOM 构建
}

function showFailureRecovery(runId, failedStep) {
    // 显示 "从失败点继续" 按钮
    const btn = document.getElementById('resumeBtn');
    btn.style.display = 'block';
    btn.onclick = () => resumePipeline(runId, failedStep);
}
```

### 5.2.3 报告新增渲染块

#### ⑥ 产业推演 (system_dynamics)

```
┌─ 产业推演 ——————————————————————————————————————————————┐
│                                                          │
│ 📌 瓶颈链:                                               │
│   GPU → HBM → 先进封装 → 电力 → 铜 → 变压器 → 液冷       │
│                                                          │
│ 📌 资源迁移:                                              │
│   ┌─────────┬──────────┬────────────────────────────┐    │
│   │ 从      │ 到       │ 影响                       │    │
│   ├─────────┼──────────┼────────────────────────────┤    │
│   │ 低端DDR │ HBM产线  │ 二线DRAM厂涨价受益 (688XXX) │    │
│   │ 传统封装│ CoWoS    │ 封装设备商订单暴增           │    │
│   └─────────┴──────────┴────────────────────────────┘    │
│                                                          │
│ 📌 隐性受益者:                                            │
│   • 成熟制程测试厂 — 先进制程受限→成熟制程爆满→测试激增    │
│                                                          │
│ 📌 受损方:                                               │
│   • 服务器OEM — HBM涨价侵蚀BOM (-8pct)                  │
│                                                          │
│ 📌 相变预测:                                             │
│   当前: 供给短缺 → 预计 2027Q3 缓解 → 2028H1 过剩风险     │
│                                                          │
│ 📌 瓶颈迁移时间线:                                       │
│   现在: CoWoS → 12个月后: HBM3E → 24个月后: 数据中心电力  │
└──────────────────────────────────────────────────────────┘
```

**渲染逻辑**:

```javascript
function renderSystemDynamics(dynamics) {
    if (!dynamics) return '';
    
    let html = '<div class="report-section system-dynamics">';
    html += '<h3>📊 产业推演</h3>';
    
    // 瓶颈链 (横向箭头)
    if (dynamics.bottleneck_chain) {
        html += '<div class="bottleneck-chain">';
        html += '<h4>📌 瓶颈链</h4>';
        html += '<div class="chain-flow">';
        const chain = dynamics.bottleneck_chain[0].split('→');
        chain.forEach((node, i) => {
            html += `<span class="chain-node">${node.trim()}</span>`;
            if (i < chain.length - 1) html += '<span class="chain-arrow">→</span>';
        });
        html += '</div></div>';
    }
    
    // 资源迁移表
    if (dynamics.resource_migration?.length) {
        html += renderMigrationTable(dynamics.resource_migration);
    }
    
    // 隐性受益者
    if (dynamics.hidden_beneficiaries?.length) {
        html += '<h4>📌 隐性受益者</h4><ul>';
        dynamics.hidden_beneficiaries.forEach(b => {
            html += `<li><strong>${b.sector}</strong> — ${b.reason}</li>`;
        });
        html += '</ul>';
    }
    
    // 受损方
    if (dynamics.victims?.length) {
        html += '<h4>📌 受损方</h4><ul>';
        dynamics.victims.forEach(v => {
            html += `<li>${v.segment} — ${v.why} (利润影响: ${v.margin_impact})</li>`;
        });
        html += '</ul>';
    }
    
    // 相变预测
    if (dynamics.equilibrium_forecast) {
        html += renderEquilibriumForecast(dynamics.equilibrium_forecast);
    }
    
    html += '</div>';
    return html;
}
```

#### ⑦ 市场预期差 (expectation_gap)

```
┌─ 市场预期差 ————————————————————————————————————————————┐
│                                                          │
│ ┌─────────┬──────────────┬──────────────┬────────────┐  │
│ │ 维度    │ 市场共识      │ 我们的判断    │ 差异       │  │
│ ├─────────┼──────────────┼──────────────┼────────────┤  │
│ │ 估值    │ 目标市值2400亿│ 2850亿       │ +19% ↑     │  │
│ │ 盈利    │ 增速20%      │ 35%          │ 超预期 ↑↑  │  │
│ │ 风险    │ 技术差距大    │ 政策支撑底线  │ 高估风险 ↓ │  │
│ │ 护城河  │ 壁垒较弱     │ 客户认证+政策 │ 低估壁垒 ↑ │  │
│ └─────────┴──────────────┴──────────────┴────────────┘  │
│                                                          │
│ 📌 拥挤度评估: 🔴 拥挤                                   │
│   证据: 券商覆盖30+家 | 公募重仓TOP10 | 北向持续增持       │
│   含义: 高拥挤→即使景气兑现, 股价上行空间被压缩            │
│                                                          │
│ 📌 催化剂时间线:                                         │
│   🗓 2026-08: Q2财报超预期 (盈利预期差兑现)               │
│   🗓 2026-Q4: 新品流片成功 (技术壁垒重估)                │
└──────────────────────────────────────────────────────────┘
```

#### ⑧ 论点验证 (thesis_validation)

```
┌─ 核心论点验证 ——————————————————————————————————————————┐
│                                                          │
│ 📋 论点 1: HBM 持续紧缺至 2027                          │
│   置信度: ████████████████████░░░░░ 75%                  │
│   领先指标: HBM现货价 | GPU交期 | CoWoS交期 | SK稼动率    │
│   证伪信号: ❌ HBM价连续3月下跌 (未触发)                  │
│            ❌ 三星HBM3E良率>80% (未触发)                 │
│   时间窗: 6-18个月                                       │
│                                                          │
│ 📋 论点 2: AI电力需求推动电网超级周期                     │
│   置信度: ████████████████░░░░░░░░ 60%                   │
│   领先指标: MAG7 capex | 数据中心在建 | 变压器交期         │
│   证伪信号: ❌ MAG7 capex增速放缓至个位数 (未触发)        │
│   时间窗: 12-24个月                                      │
└──────────────────────────────────────────────────────────┘
```

### 5.2.4 追溯标签页

在报告详情区域新增「追溯」Tab:

```
[报告内容] [追溯]    ← Tab 切换

追溯标签页内容:
┌──────────────────────────────────────────────────────┐
│ 步骤列表:                                            │
│                                                      │
│ ▶ Step2 看门人 — AI电力基础设施 (20s)                 │
│   └─ 搜索: 4轮 | LLM: deepseek-v4-flash | 1500 chars│
│                                                      │
│ ▼ Step3 产业链拆解 — 展开详情                         │
│   ┌────────────────────────────────────────────┐     │
│   │ 搜索查询 [1/3]:                            │     │
│   │   "AI电力基础设施 产业链 供应链 技术壁垒"   │     │
│   │   → 4 results from Brave Search            │     │
│   │   [1] "AI电力需求2026年爆发..." (500 chars) │     │
│   │                                            │     │
│   │ LLM 调用:                                  │     │
│   │   Model: deepseek-v4-flash                 │     │
│   │   Prompt: 3800 chars                       │     │
│   │   Response: 1500 chars                     │     │
│   │                                            │     │
│   │ 关键判断依据:                               │     │
│   │   bottleneck=CoWoS:                        │     │
│   │     → 搜索[2/3] "台积电独家, 扩产需18个月" │     │
│   └────────────────────────────────────────────┘     │
│                                                      │
│ ▶ Step4 系统动力学 (60s)                              │
│ ▶ Step5 并行审计 (180s)                               │
│ ▶ Step9 预期差 (30s)                                  │
└──────────────────────────────────────────────────────┘
```

**实现**: 调用 `GET /api/research/pipeline/{run_id}/trace/{step}` 获取 trace 内容, 用 `<pre>` 渲染。

---

## 5.3 新页面: pipeline.html (Pipeline 控制台)

### 5.3.1 定位

独立的 Pipeline 运维页面, 面向需要深度调试 Pipeline 的场景。与 research.html 的区别:
- **research.html**: 面向分析, 聚焦报告内容
- **pipeline.html**: 面向运维, 聚焦运行状态/溯源/重跑

### 5.3.2 页面布局

```
┌──────────────────────────────────────────────────────────────┐
│ ← 侧边栏     Pipeline 控制台                        ⚙ 设置  │
├──────────┬───────────────────────────────────────────────────┤
│          │                                                   │
│  运行历史  │  ┌─ 运行详情 ───────────────────────────────────┐ │
│          │  │                                              │ │
│ ● CPU v2 │  │  Run: 20260525_CPU_v2                        │ │
│   ✅ 5/5  │  │  状态: ✅ 完成  耗时: 5m20s                  │ │
│   5m20s  │  │  行业: CPU    模式: full                     │ │
│          │  │  代码版本: 592fa59                            │ │
│ ● CPU v1 │  │  模型: deepseek-v4-flash                     │ │
│   ❌ 3/5  │  │                                              │ │
│   3m10s  │  │  ┌─ 步骤甘特图 ────────────────────────────┐  │ │
│          │  │  │ Step1 宏观   ██ 0s (缓存)               │  │ │
│ ● SOFC v1│  │  │ Step2 看门人  ████████ 20s              │  │ │
│   ✅ 5/5  │  │  │ Step3 产业链 ████████████████████ 120s  │  │ │
│   4m45s  │  │  │ Step4 推演   ██████████████ 60s          │  │ │
│          │  │  │ Step5 审计   ████████████████████████ 180s│  │ │
│ [新建Run] │  │  │ Step9 预期差 ████████ 30s               │  │ │
│          │  │  │ Step11 报告  ████ 10s                    │  │ │
│ ───────  │  │  └──────────────────────────────────────────┘  │ │
│ 筛选:    │  │                                              │ │
│ [全部 ▼]  │  │  Token 使用: prompt 12,500 | completion 8,200│ │
│          │  │  搜索次数: 14 轮                              │ │
│          │  │                                              │ │
│          │  │  [查看报告] [查看追溯] [重跑] [删除]           │ │
│          │  └──────────────────────────────────────────────┘ │
│          │                                                   │
│          │  ┌─ 追溯面板 ────────────────────────────────────┐ │
│          │  │                                              │ │
│          │  │  ▼ Step3 产业链拆解                           │ │
│          │  │  ─────────────────────────                    │ │
│          │  │  搜索 [1/3]: "CPU 产业链 供应链..."           │ │
│          │  │    → 4 results from Brave                    │ │
│          │  │    [1] "CPU 产业链深度分析..." (480 chars)    │ │
│          │  │                                              │ │
│          │  │  LLM 调用: deepseek-v4-flash                 │ │
│          │  │  Prompt: 3800 chars | Response: 1500 chars   │ │
│          │  │                                              │ │
│          │  │  关键证据:                                    │ │
│          │  │    bottleneck=光刻机:                         │ │
│          │  │      → 搜索[1/3] "ASML独家供应, 交期>12个月" │ │
│          │  │                                              │ │
│          │  └──────────────────────────────────────────────┘ │
└──────────┴───────────────────────────────────────────────────┘
```

### 5.3.3 功能清单

| # | 功能 | 说明 |
|---|------|------|
| P1 | 运行历史列表 | 左侧面板, 显示所有 Pipeline run |
| P2 | 运行详情 | run_id / 状态 / 行业 / 耗时 / 代码版本 / 模型 |
| P3 | 步骤甘特图 | 可视化每步耗时, 状态颜色区分 |
| P4 | Token 统计 | 汇总本次 run 的 LLM token 使用量 |
| P5 | 追溯面板 | 每步 trace log 展开/折叠查看 |
| P6 | 查看报告 | 跳转到 research.html 查看关联报告 |
| P7 | 重跑按钮 | 从指定步骤重跑 (选择步骤下拉) |
| P8 | 新建 Run | 输入行业名 + 模式, 启动新 Pipeline |
| P9 | 筛选/搜索 | 按行业/状态/日期筛选历史 |
| P10 | 删除 Run | 删除 run 记录 + 检查点文件 |

---

## 5.4 新页面: validation.html (论点验证面板, V7.0 预留)

### 5.4.1 定位

投资论点生命周期管理。V7.0 核心页面, V6.0 阶段仅做基本的 CRUD + 手动录入。

### 5.4.2 页面布局

```
┌──────────────────────────────────────────────────────────────┐
│ ← 侧边栏     论点验证面板                   [筛选: 全部 ▼]   │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ ┌─ HBM 持续紧缺至 2027 ──────────────── 置信度: 75% ───────┐│
│ │ 行业: AI半导体  来源: 20260520_HBM_v1  状态: 🟢 活跃      ││
│ │                                                           ││
│ │ 领先指标:                           证伪信号:              ││
│ │   HBM 现货价  $12.5/GB ↑            ❌ HBM价连续3月下跌   ││
│ │   GPU 交期    16周 →                 ❌ 三星良率>80%       ││
│ │   CoWoS 交期  6个月 →                                     ││
│ │                                                           ││
│ │ 时间窗: 6-18个月  上次验证: 2026-05-20                    ││
│ │ [更新置信度] [手动录入指标] [查看历史] [标记证伪]           ││
│ └───────────────────────────────────────────────────────────┘│
│                                                              │
│ ┌─ AI电力需求推动电网超级周期 ──────── 置信度: 60% ─────────┐│
│ │ 行业: 电力设备  来源: 20260522_POWER_v1  状态: 🟢 活跃    ││
│ │ ...                                                       ││
│ └───────────────────────────────────────────────────────────┘│
│                                                              │
│ [+ 新增论点]                                                 │
│                                                              │
│ ─── 已证伪 ──────────────────────────────────────────────── │
│ ┌─ xxx论点 ────────────────────────── 🔴 已证伪 ──────────┐│
│ │ ...                                                       ││
│ └───────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

### 5.4.3 V6.0 最小可用功能

| # | 功能 | V6.0 实现 | V7.0 增强 |
|---|------|----------|----------|
| V1 | 论点列表 | ✅ 从 thesis_records 读取 | 按行业/状态/置信度筛选 |
| V2 | 新增论点 | ✅ 手动输入表单 | Pipeline 自动创建 |
| V3 | 更新置信度 | ✅ 手动输入新值+原因 | 贝叶斯自动更新 |
| V4 | 手动录入指标 | ✅ 写入 industry_leading_indicators | 自动数据采集 |
| V5 | 查看历史 | ✅ 读取 thesis_confidence_log | 趋势图可视化 |
| V6 | 标记证伪/验证 | ✅ 状态变更 | 自动预警推送 |

---

## 5.5 data.html 升级

### 5.5.1 宏观 Tab 增强

新增宏观报告摘要卡片:

```
┌─ 宏观分析报告 ─────────────────────────────────────────────┐
│                                                             │
│ 生成时间: 2026-05-24 10:00  有效至: 2026-06-24             │
│                                                             │
│ 📌 周期阶段: 复苏后期                                      │
│ 📌 流动性: 中性偏宽 (美联储缩表尾声)                       │
│ 📌 风险偏好: 中等偏高                                      │
│                                                             │
│ 📌 受益行业:                                               │
│   🟢 AI算力基础设施 (高确定性)                              │
│   🟢 半导体设备/材料 (高确定性)                             │
│   🟡 电力设备/电网 (中高确定性)                             │
│   🟡 工业金属 (中确定性)                                    │
│                                                             │
│ [🔄 刷新宏观报告]  [📊 查看详细报告]                        │
└─────────────────────────────────────────────────────────────┘
```

### 5.5.2 领先指标录入 (V7.0 预留)

在宏观 Tab 或新建子 Tab 中增加手动录入入口:

```
┌─ 行业领先指标录入 ─────────────────────────────────────────┐
│                                                             │
│ 指标代码: [HBM_SPOT_PRICE ▼]  观测日期: [2026-05-25]      │
│ 指标值:   [12.5          ]    单位:     [美元/GB    ]      │
│ 备注:     [SK Hynix 报价                           ]      │
│                                                             │
│ [保存]                                                      │
│                                                             │
│ 最近录入:                                                   │
│ ┌──────────────┬────────┬──────┬──────────┐               │
│ │ 指标         │ 值     │ 日期 │ 趋势     │               │
│ ├──────────────┼────────┼──────┼──────────┤               │
│ │ HBM 现货价   │ $12.5  │ 5/25 │ ↑ (+6%) │               │
│ │ GPU 交期     │ 16周   │ 5/20 │ → (不变) │               │
│ │ CoWoS 交期   │ 6个月  │ 5/15 │ → (不变) │               │
│ └──────────────┴────────┴──────┴──────────┘               │
└─────────────────────────────────────────────────────────────┘
```

---

## 5.6 侧边栏更新

```html
<!-- 在现有业务模块区增加入口 -->
<nav class="sidebar">
  <div class="nav-section">业务模块</div>
  <a href="/index.html">📊 指挥中心</a>
  <a href="/positions.html">💰 持仓管理</a>
  <a href="/research.html">🤖 AI投研</a>
  <a href="/pipeline.html">🔬 Pipeline控制台</a>  <!-- ★ 新增 -->
  <a href="/quant.html">📈 量化决策</a>
  <a href="/data.html">🗄️ 数据中心</a>
  <a href="/indicators.html">📉 指标数据</a>
  
  <div class="nav-section">系统管理</div>
  <a href="/definitions.html">⚙️ 任务定义</a>
  <a href="/history.html">📋 执行历史</a>
  <a href="/validation.html">🎯 论点验证</a>  <!-- ★ 新增 (V7.0) -->
  <a href="/settings.html">🔧 设置</a>
</nav>
```

---

## 5.7 前端文件变更总览

| 文件 | 操作 | 改动量 | 说明 |
|------|------|--------|------|
| `research.html` | 修改 | ~300行 | Pipeline面板 + 3个渲染块 + 追溯Tab |
| `pipeline.html` | ★ 新建 | ~400行 | Pipeline 控制台 |
| `validation.html` | ★ 新建 | ~300行 | 论点验证面板 (V7.0 预留) |
| `data.html` | 修改 | ~80行 | 宏观报告卡片 + 指标录入 |
| `index.html` | 修改 | ~5行 | 侧边栏增加 2 个入口 |
| `css/pipeline.css` | ★ 新建 | ~100行 | Pipeline 页面样式 |
| `js/pipeline.js` | ★ 新建 | ~200行 | Pipeline 交互逻辑 |
| **合计** | | **~1385行** | |
