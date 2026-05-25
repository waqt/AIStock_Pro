# 三、后端程序设计

> 本文档定义后端 DDD 分层架构、新增模块、Pipeline 基础设施和 API 设计。

---

## 3.1 DDD 分层架构

### 3.1.1 目录结构

```
backend/app/
├── api/                                 # ① 路由接入层 (禁止业务逻辑)
│   ├── __init__.py
│   ├── data.py                          # 数据中心 API (46KB, 含宏观/行情/自选/财务)
│   ├── research.py                      # ★ 投研 API (Pipeline + 各 Agent 端点)
│   ├── tasks.py                         # 任务管理 API
│   ├── import_api.py                    # 导入 API (OCR/Excel/文本)
│   └── positions.py                     # 持仓 API
│
├── domain/                              # ② 领域逻辑层 (核心业务)
│   ├── research/                        # 投研领域 ★ 主要变更区域
│   │   ├── agents/                      # 智能体实现
│   │   │   ├── base.py                  # ResearchAgent 基类 (5.6KB)
│   │   │   ├── global_capex_scanner.py  # Step 1 (16.7KB)
│   │   │   ├── market_scanner.py        # Step 2 (12.7KB) ✅
│   │   │   ├── supply_chain_hacker.py   # Step 3 (21KB) → 重构 (拆出 Step4+5)
│   │   │   ├── system_dynamics_agent.py # Step 4+5 ★ 独立新建 (~200行)
│   │   │   ├── financial_auditor.py     # Step 7 (15KB) → 小增强
│   │   │   ├── human_capital_detective.py # 人力审计 (6.5KB)
│   │   │   ├── valuation_pricer.py      # Step 8 (10.4KB) → 小增强
│   │   │   ├── expectation_gap.py       # Step 9 ★ 新建 (~150行)
│   │   │   ├── dag_orchestrator.py      # Step 6+10+11 (34KB) → 增强
│   │   │   └── coordinator.py           # 旧版编排 (3.4KB, 保留兼容)
│   │   ├── pipelines.py                 # Pipeline 注册表 (9.1KB)
│   │   ├── services/                    # ★ 投研应用服务
│   │   │   └── pipeline_runner.py       # ★ Pipeline Runner 新建 (~200行)
│   │   └── api/                         # 投研路由 (委托到 api/research.py)
│   │
│   ├── market_data/                     # 行情数据领域 (不变)
│   ├── portfolio/                       # 持仓领域 (不变)
│   ├── quant/                           # 量化策略领域 (不变)
│   └── strategy/                        # 策略领域 (不变)
│
├── framework/                           # ③ 基础设施层
│   ├── pipeline/                        # ★ Pipeline 基础设施 新建
│   │   ├── __init__.py
│   │   ├── checkpoint.py                # ★ 检查点管理 (~150行)
│   │   ├── trace_logger.py              # ★ 溯源日志 (~100行)
│   │   └── manifest.py                  # ★ Run Manifest (~80行)
│   ├── agents/base.py                   # BaseAgent 抽象基类 (不变)
│   ├── database/                        # 数据库连接 (不变)
│   └── providers/                       # AI Provider (不变)
│
├── models/                              # ④ 数据模型层
│   ├── models.py                        # SQLAlchemy 模型 (10.2KB) → 新增 3 model
│   └── schemas.py                       # Pydantic 校验 (2.4KB) → 新增 schema
│
└── data/                                # ⑤ 数据存储
    ├── indicators.db                    # 量化指标 SQLite (不变)
    ├── macro_report.json                # 宏观报告 30天缓存 (不变)
    ├── research_reports/                # 最终投研报告 (不变)
    └── pipeline_checkpoints/            # ★ Pipeline 检查点 新建
        └── {YYYYMMDD}_{slug}_v{n}/      # 每次 run 一个目录
```

### 3.1.2 层级依赖规则

```
                api/ (路由层)
                  ↓ 调用
              domain/ (领域层)
                  ↓ 使用
            framework/ (基础设施层)
                  ↓ 读写
              models/ + data/ (数据层)

规则:
  ✅ api → domain → framework → models
  ❌ domain → api (禁止反向引用)
  ❌ domain 内部跨领域引用 (如 research → quant)
  ✅ framework 可被任何层使用
```

---

## 3.2 新增模块详细设计

### 3.2.1 PipelineRunner — Pipeline 运行器

**文件**: `domain/research/services/pipeline_runner.py`

**职责**: 编排完整的 Step1-11 Pipeline, 支持检查点、失败恢复和溯源。

```python
"""
Pipeline Runner — 投研 Pipeline 的生命周期管理器

职责:
1. 编排 Step1-11 按 DAG 顺序执行
2. 逐 Step 保存检查点 (JSON + trace.txt)
3. 支持失败恢复 (--resume / --force-from)
4. 管理 Run Manifest (所有 Step 状态 + 时间 + 错误)
5. 集成到 task_engine (可通过任务系统触发)

使用方式:
  runner = PipelineRunner(provider=deepseek, db=session)
  result = await runner.run(industry="CPU", run_id="20260525_CPU_v1")
  
  # 失败后恢复
  result = await runner.run(industry="CPU", run_id="20260525_CPU_v1", resume=True)
  
  # 从指定步骤重跑
  result = await runner.run(industry="CPU", run_id="20260525_CPU_v1", 
                            force_from="step3_sc_hacker")
"""

class PipelineRunner:
    
    def __init__(self, provider, db_session, checkpoint_mgr=None, trace_logger=None):
        self.provider = provider
        self.db = db_session
        self.checkpoint = checkpoint_mgr or CheckpointManager()
        self.trace = trace_logger or TraceLogger()
        
        # Agent 实例 (延迟初始化)
        self._agents = {}
    
    async def run(self, 
                  industry: str, 
                  run_id: str = None,
                  mode: str = "full",
                  stock_codes: list = None,
                  force_from: str = None,
                  resume: bool = False) -> dict:
        """
        执行完整 Pipeline
        
        Args:
            industry: 行业名称 (如 "CPU", "SOFC", "AI电力基础设施")
            run_id: 运行标识, 默认自动生成 {YYYYMMDD}_{slug}_v{n}
            mode: "full" (完整11步) / "quick" (跳过Step4+5)
            stock_codes: 指定分析的股票代码 (可选, 默认从Step3发现)
            force_from: 从指定步骤强制重跑
            resume: 从上次失败点继续
            
        Returns:
            {run_id, status, elapsed, report_id, manifest}
        """
        # 1. 初始化 run
        run_id = run_id or self._generate_run_id(industry)
        manifest = self._load_or_create_manifest(run_id, industry, mode)
        
        # 2. 定义步骤 DAG
        steps = self._build_step_dag(mode)
        
        # 3. 记录 DB
        await self._create_pipeline_run_record(run_id, industry, mode)
        
        # 4. 逐步执行
        context = {}  # 跨步骤共享的上下文
        
        for step_name, step_func, step_deps in steps:
            # 判断是否跳过
            if self._should_skip(step_name, manifest, force_from, resume):
                # 从缓存加载已完成步骤的输出到 context
                cached = self.checkpoint.load(run_id, step_name)
                if cached:
                    context[step_name] = cached["output"]
                continue
            
            try:
                manifest.mark_running(step_name)
                await self._update_pipeline_step_record(run_id, step_name, "RUNNING")
                
                # 执行步骤
                result, trace_data = await step_func(industry, context, stock_codes)
                
                # 保存检查点 + 溯源日志
                self.checkpoint.save(run_id, step_name, result, trace=trace_data)
                context[step_name] = result
                
                manifest.mark_completed(step_name)
                await self._update_pipeline_step_record(run_id, step_name, "COMPLETED")
                
            except Exception as e:
                manifest.mark_failed(step_name, str(e))
                await self._update_pipeline_step_record(run_id, step_name, "FAILED", str(e))
                self._save_manifest(manifest)
                raise
        
        # 5. 完成
        manifest.mark_run_completed()
        self._save_manifest(manifest)
        await self._complete_pipeline_run_record(run_id)
        
        return manifest.to_dict()
    
    def _build_step_dag(self, mode: str) -> list:
        """构建步骤 DAG"""
        steps = [
            ("step1_macro",           self._run_step1_macro,           []),
            ("step2_gatekeeper",      self._run_step2_gatekeeper,      ["step1_macro"]),
            ("step3_sc_hacker",       self._run_step3_supply_chain,    ["step2_gatekeeper"]),
        ]
        
        if mode != "quick":
            steps.append(
                ("step4_system_dynamics", self._run_step4_dynamics,     ["step3_sc_hacker"])
            )
        
        steps.extend([
            ("step5_dag_audits",      self._run_step5_audits,          ["step3_sc_hacker"]),
            ("step9_expectation_gap", self._run_step9_expectation,     ["step5_dag_audits"]),
            ("step11_report",         self._run_step11_report,         ["step9_expectation_gap"]),
        ])
        
        return steps
    
    async def _run_step1_macro(self, industry, context, codes):
        """Phase 0: 宏观分析 (30天缓存)"""
        from .agents.global_capex_scanner import GlobalCapexScanner
        
        macro = GlobalCapexScanner.load_macro_cache()
        if macro is None:
            scanner = GlobalCapexScanner(provider=self.provider)
            macro = await scanner.synthesize_macro_report()
        
        trace = {"step": "step1_macro", "cache_hit": macro is not None}
        return macro, trace
    
    async def _run_step2_gatekeeper(self, industry, context, codes):
        """Phase 0.5: 看门人"""
        from .agents.market_scanner import MarketScanner
        
        scanner = MarketScanner(provider=self.provider)
        result = await scanner.analyze({
            "mode": "manual",
            "target_industry": industry,
            "macro_report": context.get("step1_macro", {})
        })
        
        # 检查是否值得继续
        if not result.get("verdict", {}).get("enter_step3", True):
            raise PipelineSkipError(f"Step2 verdict: 行业 {industry} 不值得深研")
        
        trace = {"step": "step2_gatekeeper", "industry": industry}
        return result, trace
    
    # ... 其他 step 方法类似
    
    def _generate_run_id(self, industry: str) -> str:
        """生成 run_id: 20260525_CPU_v1"""
        import re
        from datetime import datetime
        
        date_str = datetime.now().strftime("%Y%m%d")
        slug = re.sub(r'[^a-zA-Z0-9]', '_', industry)[:20]
        
        # 查找同日同行业的版本号
        existing = self.checkpoint.list_runs(f"{date_str}_{slug}_*")
        version = len(existing) + 1
        
        return f"{date_str}_{slug}_v{version}"
```

### 3.2.2 CheckpointManager — 检查点管理器

**文件**: `framework/pipeline/checkpoint.py`

```python
"""
Pipeline 检查点管理器

文件布局:
  data/pipeline_checkpoints/
  └── 20260525_CPU_v1/
      ├── _run_manifest.json
      ├── step2_gatekeeper_a1b2c3.json
      ├── step2_gatekeeper_a1b2c3.trace.txt
      └── ...
"""

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path

class CheckpointManager:
    
    BASE_DIR = Path("data/pipeline_checkpoints")
    
    def save(self, run_id: str, step: str, data: dict, trace: dict = None):
        """保存检查点 (JSON) + 可选追溯日志 (trace.txt)"""
        run_dir = self.BASE_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        
        # 计算输出 hash (用于缓存命中判断)
        data_hash = hashlib.md5(
            json.dumps(data, sort_keys=True, default=str).encode()
        ).hexdigest()[:6]
        
        # 保存 checkpoint JSON
        filepath = run_dir / f"{step}_{data_hash}.json"
        checkpoint = {
            "step": step,
            "run_id": run_id,
            "output_hash": data_hash,
            "saved_at": datetime.now().isoformat(),
            "code_version": self._get_git_version(),
            "output": data
        }
        filepath.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2))
        
        # 保存 trace log
        if trace:
            trace_path = filepath.with_suffix('.trace.txt')
            trace_path.write_text(self._format_trace(step, run_id, trace))
        
        return str(filepath)
    
    def load(self, run_id: str, step: str) -> dict | None:
        """加载检查点 (如果存在且有效)"""
        run_dir = self.BASE_DIR / run_id
        if not run_dir.exists():
            return None
        
        # 查找最新的检查点文件
        matches = list(run_dir.glob(f"{step}_*.json"))
        if not matches:
            return None
        
        latest = max(matches, key=lambda p: p.stat().st_mtime)
        return json.loads(latest.read_text(encoding='utf-8'))
    
    def list_runs(self, pattern: str = "*") -> list:
        """列出匹配的 run 目录"""
        return sorted([
            d.name for d in self.BASE_DIR.glob(pattern) if d.is_dir()
        ])
    
    def _get_git_version(self) -> str:
        try:
            return subprocess.check_output(
                ['git', 'rev-parse', '--short', 'HEAD'], 
                stderr=subprocess.DEVNULL
            ).decode().strip()
        except Exception:
            return "unknown"
    
    def _format_trace(self, step: str, run_id: str, trace: dict) -> str:
        """格式化追溯日志为人类可读文本"""
        lines = [
            "═" * 50,
            f"Step: {step}",
            f"Run: {run_id}",
            f"Time: {datetime.now().isoformat()}",
            "═" * 50,
            ""
        ]
        
        # 搜索查询
        if "search_queries" in trace:
            lines.append("── 搜索查询 " + "─" * 38)
            for i, sq in enumerate(trace["search_queries"], 1):
                lines.append(f"[{i}/{len(trace['search_queries'])}] {sq['query']}")
                lines.append(f"  → {len(sq.get('results', []))} results")
                for j, r in enumerate(sq.get("results", [])[:3], 1):
                    lines.append(f"  [{j}] {r.get('title', '')[:60]}")
                lines.append("")
        
        # LLM 调用
        if "llm_prompt" in trace:
            lines.append("── LLM 调用 " + "─" * 38)
            lines.append(f"Model: {trace.get('provider', 'unknown')}")
            lines.append(f"Prompt ({len(trace['llm_prompt'])} chars):")
            lines.append(trace["llm_prompt"][:500] + "...")
            lines.append(f"\nResponse ({len(trace.get('llm_response', ''))} chars):")
            lines.append(trace.get("llm_response", "")[:500] + "...")
            lines.append("")
        
        # 关键判断依据
        if "key_evidence" in trace:
            lines.append("── 关键判断依据 " + "─" * 34)
            for evidence in trace["key_evidence"]:
                lines.append(f"  {evidence}")
            lines.append("")
        
        return "\n".join(lines)
```

### 3.2.3 TraceLogger — 溯源日志器

**文件**: `framework/pipeline/trace_logger.py`

```python
"""
追溯日志器 — 为每个 Agent 的每次分析记录完整的推理过程

生成规则:
  每条判断必须追溯到一个具体来源:
  
  | 判断类型         | 引用格式                                        |
  |------------------|-------------------------------------------------|
  | 搜索结果中的数字   | 搜索结果[2/4] "标题" — snippet中的数字             |
  | DB 中的数据       | exchange_rates.US10YT = 4.56 (2026-05-22)        |
  | LLM 的逻辑推理    | 如果A→B→C, 则D                                    |
  | 程序化计算         | financial_auditor.py: score = PASS if m_score < ..|
"""

class TraceLogger:
    
    def create_trace(self, step: str, industry: str) -> TraceContext:
        """创建一个追溯上下文"""
        return TraceContext(step=step, industry=industry)
    

class TraceContext:
    """追溯上下文 — Agent 执行过程中持续追加信息"""
    
    def __init__(self, step: str, industry: str):
        self.step = step
        self.industry = industry
        self.search_queries = []
        self.llm_prompt = None
        self.llm_response = None
        self.provider = None
        self.key_evidence = []
        self.db_lookups = []
        self.started_at = datetime.now()
    
    def log_search(self, query: str, results: list):
        self.search_queries.append({"query": query, "results": results})
    
    def log_llm(self, prompt: str, response: str, provider: str = None):
        self.llm_prompt = prompt
        self.llm_response = response
        self.provider = provider
    
    def log_evidence(self, judgment: str, source: str, evidence: str):
        self.key_evidence.append(f"{judgment}:\n  → {source}: {evidence}")
    
    def log_db_lookup(self, table: str, field: str, value, as_of: str = None):
        self.db_lookups.append(f"{table}.{field} = {value} ({as_of or 'latest'})")
    
    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "industry": self.industry,
            "started_at": self.started_at.isoformat(),
            "search_queries": self.search_queries,
            "llm_prompt": self.llm_prompt or "",
            "llm_response": self.llm_response or "",
            "provider": self.provider or "",
            "key_evidence": self.key_evidence,
            "db_lookups": self.db_lookups,
        }
```

### 3.2.4 RunManifest — Run 元信息

**文件**: `framework/pipeline/manifest.py`

```python
"""
Run Manifest — 一次 Pipeline 运行的完整元信息

文件: data/pipeline_checkpoints/{run_id}/_run_manifest.json
"""

class RunManifest:
    
    def __init__(self, run_id: str, industry: str, mode: str):
        self.run_id = run_id
        self.industry = industry
        self.mode = mode
        self.status = "PENDING"
        self.started_at = datetime.now().isoformat()
        self.completed_at = None
        self.steps = {}  # step_name → {status, started_at, completed_at, elapsed, error}
        self.context = {}  # 跨步骤共享数据
    
    def mark_running(self, step: str):
        self.status = "RUNNING"
        self.steps[step] = {
            "status": "RUNNING",
            "started_at": datetime.now().isoformat(),
        }
    
    def mark_completed(self, step: str):
        step_info = self.steps[step]
        step_info["status"] = "COMPLETED"
        step_info["completed_at"] = datetime.now().isoformat()
        step_info["elapsed"] = (
            datetime.fromisoformat(step_info["completed_at"]) - 
            datetime.fromisoformat(step_info["started_at"])
        ).total_seconds()
    
    def mark_failed(self, step: str, error: str):
        self.status = "FAILED"
        self.steps[step]["status"] = "FAILED"
        self.steps[step]["error"] = error
    
    def mark_run_completed(self):
        self.status = "COMPLETED"
        self.completed_at = datetime.now().isoformat()
```

---

## 3.3 API 设计

### 3.3.1 新增端点

| 路径 | 方法 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| `/api/research/pipeline/run` | POST | 启动 Pipeline | `{industry, mode?, stock_codes?}` | `{run_id, status}` |
| `/api/research/pipeline/{run_id}` | GET | 查询状态 | - | `{manifest}` |
| `/api/research/pipeline/{run_id}/resume` | POST | 恢复失败的 Run | `{force_from?}` | `{status}` |
| `/api/research/pipeline/history` | GET | 运行历史 | `?limit=20` | `[{run_id, status}]` |
| `/api/research/pipeline/{run_id}/trace/{step}` | GET | 溯源日志 | - | `{trace_text}` |
| `/api/research/expectation-gap` | POST | 单独调用预期差 | `{stock_code, industry}` | `{gap_analysis}` |
| `/api/data/macro/report` | GET | 获取宏观报告 | - | `{macro_report}` |
| `/api/data/macro/report/refresh` | POST | 刷新宏观报告 | - | `{status}` |

### 3.3.2 Pipeline API 详细定义

#### POST `/api/research/pipeline/run`

```python
@router.post("/pipeline/run")
async def start_pipeline(request: PipelineRunRequest, db=Depends(get_db)):
    """
    启动完整投研 Pipeline
    
    Body:
      {
        "industry": "CPU",               // 必填: 行业名称
        "mode": "full",                   // 可选: full/quick (默认 full)
        "stock_codes": ["688041"]         // 可选: 指定分析的股票代码
      }
    
    Response (202 Accepted):
      {
        "run_id": "20260525_CPU_v1",
        "status": "RUNNING",
        "message": "Pipeline started"
      }
    
    行为:
      1. 生成 run_id
      2. 创建 pipeline_runs + pipeline_steps DB 记录
      3. 通过 task_engine 异步启动 PipelineRunner
      4. 立即返回 run_id (前端轮询进度)
    """
    runner = PipelineRunner(provider=get_provider(), db_session=db)
    run_id = runner._generate_run_id(request.industry)
    
    # 异步执行
    task_engine.start_task(
        name=f"pipeline_{run_id}",
        coro_func=runner.run,
        industry=request.industry,
        run_id=run_id,
        mode=request.mode or "full",
        stock_codes=request.stock_codes,
    )
    
    return {"run_id": run_id, "status": "RUNNING"}
```

#### GET `/api/research/pipeline/{run_id}`

```python
@router.get("/pipeline/{run_id}")
async def get_pipeline_status(run_id: str, db=Depends(get_db)):
    """
    查询 Pipeline 运行状态
    
    Response:
      {
        "run_id": "20260525_CPU_v1",
        "industry": "CPU",
        "status": "RUNNING",
        "started_at": "2026-05-25T10:00:00",
        "elapsed_seconds": 125,
        "steps": {
          "step1_macro": {"status": "COMPLETED", "elapsed": 0, "note": "缓存命中"},
          "step2_gatekeeper": {"status": "COMPLETED", "elapsed": 20},
          "step3_sc_hacker": {"status": "RUNNING", "elapsed": 45},
          "step4_system_dynamics": {"status": "PENDING"},
          "step5_dag_audits": {"status": "PENDING"},
          "step9_expectation_gap": {"status": "PENDING"},
          "step11_report": {"status": "PENDING"}
        },
        "completed_steps": 2,
        "total_steps": 7,
        "progress_pct": 28
      }
    """
```

### 3.3.3 现有端点 (保持不变)

以下端点确保向后兼容:

```
POST /api/research/scan              — MarketScanner (Legacy)
POST /api/research/supply-chain      — SupplyChainAnalyst (Legacy)
POST /api/research/analyze           — ResearchCoordinator (Legacy)
GET  /api/research/reports           — 报告列表
GET  /api/research/reports/{id}      — 报告详情
DELETE /api/research/reports/{id}    — 删除报告

GET  /api/data/*                     — 全部数据中心 API
POST /api/tasks/*                    — 全部任务 API
GET  /api/quant/*                    — 全部量化 API
```

---

## 3.4 文件变更总览

### 3.4.1 新建文件

| 文件 | 行数 | 说明 |
|------|------|------|
| `domain/research/agents/expectation_gap.py` | ~150 | ExpectationGapAgent (Step 9) |
| `domain/research/agents/system_dynamics_agent.py` | ~200 | SystemDynamicsAgent (Step 4+5) ★ 独立拆分 |
| `domain/research/services/pipeline_runner.py` | ~200 | PipelineRunner |
| `framework/pipeline/__init__.py` | ~5 | 包初始化 |
| `framework/pipeline/checkpoint.py` | ~150 | 检查点管理 |
| `framework/pipeline/trace_logger.py` | ~100 | 溯源日志 |
| `framework/pipeline/manifest.py` | ~80 | Run Manifest |
| **合计** | **~885** | |

### 3.4.2 修改文件

| 文件 | 改动行 | 说明 |
|------|--------|------|
| `agents/supply_chain_hacker.py` | ~80 | Step3 Prompt重写 (拆出 Step4+5 后减少) |
| `agents/dag_orchestrator.py` | ~60 | Step6质量加权 + Step10风险 + Step11模板 + DAG编排 |
| `agents/financial_auditor.py` | ~20 | 盈利释放判断 |
| `agents/valuation_pricer.py` | ~10 | payoff_asymmetry |
| `models/models.py` | ~80 | 3 个新 Model |
| `api/research.py` (或新建) | ~80 | Pipeline API 端点 |
| **合计** | **~440** | |

### 3.4.3 不变文件

- `pipelines.py` — Pipeline 注册表
- `api/data.py` — 数据中心 API
- `api/tasks.py` — 任务 API
- `framework/agents/base.py` — BaseAgent
- `framework/database/` — 数据库连接
- `framework/providers/` — AI Provider
- 全部前端文件 (在后端 Phase 完成后再改)
