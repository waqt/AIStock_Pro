"""投研分析 API"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.domain.research.agents.base import ResearchAgent
from app.domain.research.agents.coordinator import ResearchCoordinator
from app.domain.research.agents.industry_analyst import IndustryAnalyst
from app.domain.research.agents.supply_chain_analyst import SupplyChainAnalyst
from app.domain.research.agents.supply_chain_hacker import SupplyChainHacker
from app.domain.research.services.stock_auditor import StockAuditor
from app.domain.research.agents.global_capex_scanner import GlobalCapexScanner
from app.domain.research.agents.dag_orchestrator import DAGOrchestrator
from app.domain.research.agents.market_scanner import MarketScanner
from app.domain.research.agents.system_dynamics_agent import SystemDynamicsAgent
from app.domain.research.agents.core_screening_agent import CoreScreeningAgent
from app.domain.research.agents.expectation_gap_agent import ExpectationGapAgent
from app.domain.research.agents.risk_analysis_agent import RiskAnalysisAgent
from app.domain.research.agents.report_synthesis_agent import ReportSynthesisAgent
from app.domain.research.pipelines import PIPELINES
from app.domain.research.services.data_loader import data_loader
from app.domain.graph.bridge import graph_bridge
import app.domain.graph.builder  # noqa: register Step 3 parser
from app.domain.research.services.report_store import save_report, list_reports, get_report, delete_report
from app.framework.logger import logger
from app.domain.observation.services.extractor import save_step_observations

router = APIRouter(prefix="/api/research", tags=["投研分析"])

# Step 名称映射
STEP_LABELS = {
    "step1_macro": "宏观分析",
    "step1b_capital_flow": "资本流向扫描",
    "step2_gatekeeper": "行业看门人",
    "step3_sc_hacker": "产业链拆解",
    "step4_system_dynamics": "系统动力学推演",
    "step5_cross_industry": "跨产业关联分析",
    "step6_core_screening": "核心资产筛选",
    "step7_financial_audit": "财务质量审计",
    "step8_human_capital": "人力资本审计",
    "step8_valuation": "估值定价",
    "step9_expectation_gap": "市场预期差",
    "step10_risk_analysis": "风险分析",
    "step11_report": "综合报告",
}

# 统一完整 Pipeline（所有产业分析模式共享）
FULL_PIPELINE = [
    "step1_macro",
    "step1b_capital_flow",
    "step2_gatekeeper",
    "step3_sc_hacker",
    "step4_system_dynamics",
    "step6_core_screening",
    "step7_financial_audit",
    "step8_human_capital",
    "step8_valuation",
    "step9_expectation_gap",
    "step10_risk_analysis",
    "step11_report",
]

# 已实现的步骤
IMPLEMENTED_STEPS = {
    "step1_macro", "step1b_capital_flow", "step2_gatekeeper", "step3_sc_hacker", "step4_system_dynamics",
    "step5_cross_industry", "step6_core_screening",
    "step9_expectation_gap", "step10_risk_analysis", "step11_report",
}

# 可选步骤（不阻塞 pipeline）
OPTIONAL_STEPS = {"step8_human_capital"}

# Step 1b → Step 2 桥接: 系统压力节点映射到候选产业
PRESSURE_INDUSTRY_MAP = {
    "power_infrastructure": [
        "变压器", "电网设备", "铜", "取向硅钢", "高压开关", "电力电缆"
    ],
    "thermal_management": [
        "液冷散热", "服务器电源", "空调制冷", "散热材料"
    ],
    "memory_bandwidth": [
        "HBM高带宽内存", "先进封装", "ABF基板", "存储芯片"
    ],
    "compute_chip": [
        "AI芯片", "GPU", "ASIC定制芯片", "芯片代工"
    ],
    "optical_communication": [
        "光模块", "光芯片", "光纤光缆", "光器件"
    ],
    "energy_storage": [
        "储能", "锂电池", "钠电池", "逆变器"
    ],
}
FALLBACK_HYPOTHESIS = [
    {"sector": "AI算力基础设施", "name": "AI算力"},
    {"sector": "半导体设备国产化", "name": "半导体设备"},
    {"sector": "电力设备与电网升级", "name": "电网设备"},
]


async def _map_pressure_to_industries(vectors: list, provider=None) -> list:
    """Step 1b → Step 2 桥接: 用 LLM 将系统压力节点映射为候选产业。
    PRESSURE_INDUSTRY_MAP 保留为种子/提示注入 LLM prompt, 不限制映射范围。

    Args:
        vectors: pressure_vectors 列表, 每项含 system_node + pressure_signals
        provider: AI provider, None 时使用 DeepSeekProvider fallback

    Returns:
        hypothesis: [{"sector":..., "name":..., "pressure_node":..., "pressure_signals":[...], "source":"capital_flow_pressure"}, ...]
    """
    import json as _j, re as _re
    if not vectors:
        return []

    if not provider:
        from app.framework.ai.providers.deepseek import DeepSeekProvider
        provider = DeepSeekProvider()

    # 构建系统节点清单
    node_lines = []
    for i, v in enumerate(vectors):
        node = v.get("system_node", v.get("target", ""))
        signals = v.get("pressure_signals", [])
        sig_str = "; ".join(signals[:3]) if signals else "(无信号)"
        node_lines.append(f'{i+1}. system_node: "{node}"\n   pressure_signals: {sig_str}')

    # 已知映射表作为种子提示
    seed_lines = []
    for node, industries in PRESSURE_INDUSTRY_MAP.items():
        seed_lines.append(f'  "{node}" → {industries}')

    node_list_str = "\n".join(node_lines)
    seed_list_str = "\n".join(seed_lines)

    prompt = f"""你是A股产业映射专家。给定全球资本与能源流向分析识别的系统压力节点，映射到最相关的A股实体细分产业。

## 系统压力节点列表
{node_list_str}

## 已知映射参考（仅作种子提示，不限于此）
{seed_list_str}

## 要求
- 对每个节点，输出最相关的1-3个A股实体细分产业（如"变压器"、"液冷散热"、"HBM"、"光模块"）
- 可以沿用已知映射，也可以根据你的知识补充更合适的产业
- 如果某个节点明显指向多个不相关方向，可以输出多个产业
- 如果某个节点在你的知识中无对应A股产业，输出空数组
- 产业名必须是A股真实存在的细分行业

## 输出纯JSON
{{"mappings": [
  {{"system_node": "power_infrastructure", "industries": ["变压器", "电网设备", "取向硅钢"]}},
  ...
]}}
## 规则
- 只输出JSON, 不要任何其他文字
- mappings 数组长度 = 输入节点数"""

    try:
        text = await provider.chat_flash(prompt, max_tokens=2048, timeout=90)
        if isinstance(text, str):
            m = _re.search(r'\{.*\}', text, _re.DOTALL)
            text = m.group(0) if m else text
            result = _j.loads(text)
        elif isinstance(text, dict):
            result = text
        else:
            result = None

        mappings = result.get("mappings", []) if isinstance(result, dict) else []
        hypothesis = []
        for m in mappings:
            node = m.get("system_node", "")
            industries = m.get("industries", [])
            orig = next((v for v in vectors if v.get("system_node", v.get("target", "")) == node), {})
            signals = orig.get("pressure_signals", [])[:2]
            for ind in industries[:3]:
                hypothesis.append({
                    "sector": ind, "name": ind,
                    "pressure_node": node, "pressure_signals": signals,
                    "source": "capital_flow_pressure"
                })
        if hypothesis:
            logger.info(f"[PressureMapping] LLM mapped {len(vectors)} nodes → {len(hypothesis)} candidates")
            return hypothesis
    except Exception as e:
        logger.warning(f"[PressureMapping] LLM failed: {e}, falling back to static map")

    return _fallback_map(vectors)


def _fallback_map(vectors: list) -> list:
    """静态回退: 使用 PRESSURE_INDUSTRY_MAP 做映射 (与 LLM 失败时)"""
    hypothesis = []
    for v in vectors:
        node = v.get("system_node", v.get("target", ""))
        industries = PRESSURE_INDUSTRY_MAP.get(node, [])
        signals = v.get("pressure_signals", [])[:2]
        for ind in industries[:3]:
            hypothesis.append({
                "sector": ind, "name": ind,
                "pressure_node": node, "pressure_signals": signals,
                "source": "capital_flow_pressure"
            })
    return hypothesis


# ═══ 分析智能体注册表 ═══════════════════════
# 新增智能体只需在此加一条, 前端自动加载

AGENT_REGISTRY = [
    {
        "id": "supply_chain",
        "name": "产业链分析智能体",
        "desc": "产业链穿透 + 系统动力学 + CIO报告",
        "icon": "sitemap",
        "modes": [
            {"id": "auto_scan",          "name": "全局扫描",
             "desc": "全自动从宏观到报告，一站式产业链深度分析",
             "input_type": "none", "placeholder": "",
             "pipeline": FULL_PIPELINE},
            {"id": "manual_industry",    "name": "定性产业分析",
             "desc": "手动输入产业名称，展开全产业链穿透分析",
             "input_type": "industry", "placeholder": "输入行业关键词, 如: SOFC固体氧化物燃料电池",
             "pipeline": FULL_PIPELINE},
            {"id": "stock_deep",         "name": "公司深度分析",
             "desc": "输入股票代码或公司名，进行行业+公司双轨深度分析",
             "input_type": "stock_code", "placeholder": "输入6位代码或公司名, 如: 688012中微公司",
             "pipeline": FULL_PIPELINE},
            {"id": "stock_audit",        "name": "公司财务审计",
             "desc": "输入股票代码，仅运行财务质量审计(Step7)",
             "input_type": "stock_code", "placeholder": "输入6位代码, 如: 688012",
             "pipeline": ["step1_macro", "step7_financial_audit"]},
            {"id": "macro_only",        "name": "宏观周期分析",
             "desc": "独立运行宏观分析，生成宏观周期报告和路由决策",
             "input_type": "none", "placeholder": "",
             "pipeline": ["step1_macro"]},
            {"id": "capital_flow",       "name": "资本流向扫描",
             "desc": "从全球资本流向出发，识别产业机会并完成全链路分析",
             "input_type": "none", "placeholder": "",
             "pipeline": FULL_PIPELINE},  # 跳过 Step 1a, 从 Step 1b 跑全链
        ],
    },
    # 未来扩展:
    # {"id": "financial_analysis", "name": "财务分析智能体", ...},
    # {"id": "quant_trading", "name": "量化交易智能体", ...},
]


class ResearchRequest(BaseModel):
    question: str = ""
    stock_codes: List[str] = []
    industry: Optional[str] = None
    include_portfolio: bool = True
    analysis_type: Optional[str] = None  # supply_chain | macro_cycle | founder_audit | valuation_scan


class ScanRequest(BaseModel):
    """投研分析请求 — 支持多智能体 + 多模式"""
    agent_id: str = "supply_chain"   # 智能体ID
    mode_id: str = "manual_industry" # 模式ID
    target: str = ""                 # 行业名/股票代码 (根据 mode.input_type)
    mode: str = "auto"               # [废弃] 兼容旧参数
    target_industry: str = ""        # [废弃] 兼容旧参数
    question: str = ""               # [废弃] 兼容旧参数


# ── 初始化协调器 ───────────────────

def _get_coordinator():
    """创建协调器并注册分析师"""
    from app.framework.ai.providers.deepseek import DeepSeekProvider
    provider = DeepSeekProvider()
    coordinator = ResearchCoordinator(provider=provider)
    coordinator.register(IndustryAnalyst(provider=provider))
    return coordinator


# ── 端点 ────────────────────────────

@router.get("/analysts")
async def list_analysts():
    """列出所有可用的投研分析师类型"""
    result = []
    for name, info in PIPELINES.items():
        result.append({"type": name, "label": info["label"], "description": info["description"]})
    return {"success": True, "data": result}


@router.post("/analyze")
async def research_analyze(req: ResearchRequest):
    """统一投研入口 — 根据 analysis_type 选择 Pipeline"""
    from app.framework.ai.providers.deepseek import DeepSeekProvider
    provider = DeepSeekProvider()
    pipe_type = req.analysis_type or "supply_chain"
    pipeline = PIPELINES.get(pipe_type)
    if not pipeline:
        raise HTTPException(status_code=400, detail=f"Unknown analysis type: {pipe_type}")
    logger.info(f"[Analyze] Pipeline: {pipe_type} ({pipeline['label']}), industry={req.industry or req.question}")
    result = await pipeline["func"](industry=req.industry or req.question, provider=provider,
        params={"stock_codes": req.stock_codes, "include_portfolio": req.include_portfolio})
    save_report(pipeline["label"], req.industry or req.question, result)
    return {"success": True, "data": result, "freshness": ResearchAgent.freshness_stamp()}


@router.post("/analyze-v4")
async def research_analyze_v4(req: ResearchRequest, skip_phase1: bool = Query(False)):
    """V4.0 DAG 编排 — 分阶段执行, 支持断点续跑。
    skip_phase1=true → 读已有 Phase1 文件, 只重跑 Phase2 (审计+定价+报告)。适合修复审计/定价 bug 后快速验证。"""
    import os, json as _json, time as _time
    from app.framework.ai.providers.deepseek import DeepSeekProvider
    industry = req.industry or req.question
    slug = industry.replace(" ", "_")[:20]
    out_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "temp_lab")
    os.makedirs(out_dir, exist_ok=True)

    provider = DeepSeekProvider()
    t0 = _time.time()

    # ═══ Phase 1: 供应链扫描 → 落盘 ═══
    sc_path = os.path.join(out_dir, f"{slug}_phase1_sc.json")
    if skip_phase1 and os.path.exists(sc_path):
        hacker_result = _json.load(open(sc_path, "r", encoding="utf-8"))
        logger.info(f"[analyze-v4] Phase1 SKIPPED (loaded from cache): {len(hacker_result.get('core_stocks',[]))} stocks")
    else:
        hacker = SupplyChainHacker(provider=provider)
        hacker_result = await hacker.analyze({
            "industry": industry, "stock_codes": req.stock_codes,
            "include_portfolio": False})
        with open(sc_path, "w", encoding="utf-8") as f:
            _json.dump(hacker_result, f, ensure_ascii=False, indent=2)
        logger.info(f"[analyze-v4] Phase1 SC saved ({_time.time()-t0:.0f}s): {len(hacker_result.get('core_stocks',[]))} stocks")

    # ═══ Phase 2: 审计+定价 → 落盘 ═══
    core_stocks = hacker_result.get("core_stocks", [])
    codes = [s["code"] for s in core_stocks if s.get("code")]
    orchestrator = DAGOrchestrator(provider=provider)
    context = {
        "question": req.question, "stock_codes": codes, "industry": industry,
        "include_portfolio": req.include_portfolio,
        "_supply_chain_prefetched": hacker_result,
    }
    dag_result = await orchestrator.analyze(context)
    dag_path = os.path.join(out_dir, f"{slug}_phase2_dag.json")
    with open(dag_path, "w", encoding="utf-8") as f:
        _json.dump(dag_result, f, ensure_ascii=False, indent=2)
    logger.info(f"[analyze-v4] Phase2 DAG saved ({_time.time()-t0:.0f}s total)")

    # ═══ Phase 3: 组装报告 → 落盘 ═══
    dag_result["supply_chain"] = hacker_result
    save_report("DAGOrchestrator", industry, dag_result)
    return {"success": True, "data": dag_result, "freshness": ResearchAgent.freshness_stamp()}


@router.post("/report/{slug}")
async def regenerate_report(slug: str):
    """从已保存的 Phase1+Phase2 数据重新生成报告 (不改搜索和审计, 秒级迭代)"""
    import os, json as _json
    out_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "temp_lab")
    sc_path = os.path.join(out_dir, f"{slug}_phase1_sc.json")
    dag_path = os.path.join(out_dir, f"{slug}_phase2_dag.json")

    if not os.path.exists(sc_path):
        raise HTTPException(status_code=404, detail=f"Phase1 not found: {sc_path}")
    if not os.path.exists(dag_path):
        raise HTTPException(status_code=404, detail=f"Phase2 not found: {dag_path}")

    hacker = _json.load(open(sc_path, "r", encoding="utf-8"))
    dag = _json.load(open(dag_path, "r", encoding="utf-8"))
    dag["supply_chain"] = hacker

    return {"success": True, "data": dag,
            "note": f"Report from cached data. Edit _synthesize_basic in dag_orchestrator.py and retry this endpoint to iterate on report format."}


@router.post("/analyze-v3")
async def research_analyze_v3(req: ResearchRequest):
    """V3.0 多智能体联合投研分析 (同步, 向后兼容) — 路径 /analyze-v3"""
    try:
        coordinator = _get_coordinator()
        context = {"question": req.question, "stock_codes": req.stock_codes,
                   "industry": req.industry, "include_portfolio": req.include_portfolio}
        result = await coordinator.analyze(context)
        return {"success": True, "data": result, "freshness": ResearchAgent.freshness_stamp()}
    except Exception as e:
        logger.error(f"[❌] Research analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/search")
async def search_stocks(q: str = "", limit: int = 20):
    """搜索股票 (供投研 Agent 调用)"""
    return await data_loader.search_stocks(q, limit)


@router.get("/data/positions")
async def get_positions_data():
    """获取持仓数据"""
    return await data_loader.load_positions()


@router.get("/data/macro")
async def get_macro_data():
    """获取宏观数据"""
    return await data_loader.load_macro()


@router.post("/supply-chain")
async def supply_chain_analysis(req: ResearchRequest):
    """供应链深度分析 — 5步推理: 景气信号→供应链图谱→瓶颈→标的→估值"""
    try:
        from app.framework.ai.providers.deepseek import DeepSeekProvider
        provider = DeepSeekProvider()
        analyst = SupplyChainAnalyst(provider=provider)
        context = {"question": req.question, "stock_codes": req.stock_codes,
                   "industry": req.industry or req.question, "include_portfolio": req.include_portfolio}
        result = await analyst.analyze(context)
        save_report("SupplyChainAnalyst", req.industry or req.question, result)
        return {"success": True, "data": result, "freshness": ResearchAgent.freshness_stamp()}
    except Exception as e:
        logger.error(f"[❌] Supply chain analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class LevelAnalysisRequest(BaseModel):
    industry: str = ""
    level_name: str = ""
    level_info: Optional[Dict[str, Any]] = None


@router.post("/supply-chain-hacker/level")
async def supply_chain_level_analysis(req: LevelAnalysisRequest):
    """V4.0 供应链单层级深度穿透 — 找出该层所有高价值资产"""
    try:
        from app.framework.ai.providers.deepseek import DeepSeekProvider
        hacker = SupplyChainHacker(provider=DeepSeekProvider())
        result = await hacker.analyze_level(req.industry, req.level_name, req.level_info)
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"[❌] Level analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# (旧的 /supply-chain-hacker 已迁移至 V5.8 版本 — 见下方 @router.post("/supply-chain-hacker"))


# (旧的 /audit/human-capital + /audit/financial 已移除 — 改用 /stock-audit/*)


@router.post("/capex-scan")
async def global_capex_scan(req: ResearchRequest):
    """V4.0 全球 CapEx 扫描 — MAG7 资本开支计划 → 景气方向"""
    try:
        from app.framework.ai.providers.deepseek import DeepSeekProvider
        scanner = GlobalCapexScanner(provider=DeepSeekProvider())
        context = {"industry": req.industry or "", "question": req.question}
        result = await scanner.analyze(context)
        save_report("GlobalCapexScanner", req.industry or "全局", result)
        return {"success": True, "data": result, "freshness": ResearchAgent.freshness_stamp()}
    except Exception as e:
        logger.error(f"[❌] Global capex scan failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents")
async def list_agents():
    """返回已注册的分析智能体及其支持的模式"""
    return {"success": True, "data": AGENT_REGISTRY}


async def _do_scan(req: ScanRequest, pre_run_id: str = None):
    """投研分析核心逻辑 (同步/异步模式复用)"""
    from app.framework.ai.providers.deepseek import DeepSeekProvider
    from app.framework.pipeline.checkpoint import (
        generate_run_id, hash_input, load_checkpoint,
        save_checkpoint, save_manifest,
    )
    from app.framework.pipeline.trace import TraceContext

    target = req.target or req.target_industry or req.question
    agent_id = req.agent_id
    mode_id = req.mode_id

    agent_def = next((a for a in AGENT_REGISTRY if a["id"] == agent_id), None)
    if not agent_def:
        raise HTTPException(status_code=400, detail=f"Unknown agent: {agent_id}")
    mode_def = next((m for m in agent_def["modes"] if m["id"] == mode_id), None)
    if not mode_def:
        raise HTTPException(status_code=400, detail=f"Unknown mode '{mode_id}' for agent '{agent_id}'")
    if mode_def["input_type"] != "none" and not target:
        raise HTTPException(status_code=400, detail=f"Mode '{mode_id}' requires input: {mode_def['input_type']}")

    scanner = MarketScanner(provider=DeepSeekProvider())
    cf_loaded = False  # 初始化, manual_industry 模式也会用到

    if mode_id == "macro_only":
        target = "宏观周期分析-" + datetime.now().strftime("%Y%m%d-%H%M")
        from app.domain.research.agents.global_capex_scanner import GlobalCapexScanner
        gcs = GlobalCapexScanner(provider=DeepSeekProvider())
        macro_result = await gcs.synthesize_macro_report()
        return {"success": True, "data": macro_result, "run_id": generate_run_id(target),
                "freshness": ResearchAgent.freshness_stamp()}

    if mode_id in ("auto_scan", "capital_flow"):
        import os as _os, json as _json, glob as _glob
        hypothesis = []
        target = (mode_id == "auto_scan" and "全局扫描-" or "资本流向-") + datetime.now().strftime("%Y%m%d-%H%M")
        today = datetime.now().strftime("%Y%m%d")

        # Step 1b: 资本流向缓存或自动运行
        base_data = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "..", "..", "..", "data"))
        cf_pattern = _os.path.join(base_data, "pipeline_checkpoints", "*资本流向*", "step1b_capital_flow*.json")
        cf_runs = sorted(_glob.glob(cf_pattern), reverse=True)
        cf_loaded = False
        if cf_runs:
            try:
                with open(cf_runs[0], "r", encoding="utf-8") as f:
                    cf = _json.load(f)
                cf_date = (cf.get("saved_at", "") or "")[:10].replace("-", "")
                if cf_date == today:  # 当天有效
                    output = cf.get("output", {})
                    vectors = output.get("pressure_vectors", [])
                    # 降级: 旧格式 capex_vectors (无 pressure_vectors 时回退)
                    if not vectors:
                        vectors = output.get("capex_vectors", [])
                        logger.info(f"[MarketScanner] Using legacy capex_vectors format")
                    # 系统节点 → 候选产业映射 (Step 1b → Step 2 桥接, 使用 LLM)
                    hypothesis = await _map_pressure_to_industries(vectors, provider=DeepSeekProvider())
                    if hypothesis:
                        cf_loaded = True
                        cf_cached_output = output  # 稍后复制到 run_id
                        logger.info(f"[MarketScanner] Using capital_flow cache: {len(hypothesis)} candidates")
                else:
                    logger.info(f"[MarketScanner] Capital flow cache expired ({cf_date} < {today})")
            except Exception as e:
                logger.warning(f"[MarketScanner] Capital flow cache read failed: {e}")

        # 无当天缓存 → 自动跑 Step 1b
        if not cf_loaded:
            logger.info(f"[MarketScanner] Auto-running capital flow scan...")
            try:
                from app.domain.research.agents.capital_flow_scanner import CapitalFlowScanner
                from app.framework.pipeline.trace import TraceContext
                cf_scanner = CapitalFlowScanner(provider=DeepSeekProvider())
                cf_run_id = generate_run_id("资本流向")
                cf_trace = TraceContext(cf_run_id)
                cf_result = await cf_scanner.analyze(ctx={}, trace=cf_trace)
                output = cf_result
                vectors = output.get("pressure_vectors", [])
                if not vectors:
                    vectors = output.get("capex_vectors", [])
                hypothesis = await _map_pressure_to_industries(vectors, provider=DeepSeekProvider())
                # 保存到独立缓存目录 (供后续项目复用)
                ih = hash_input({"step": "capital_flow", "date": today})
                save_checkpoint("step1b_capital_flow", cf_run_id, ih, cf_result, {"elapsed": 0})
                save_manifest(cf_run_id, {"run_id": cf_run_id, "industry": "资本流向", "status": "completed",
                    "started_at": cf_trace.to_dict()["started_at"], "completed_at": datetime.now().isoformat(),
                    "step": "step1b_capital_flow"})
                cf_trace.write("step1b_capital_flow")
                cf_loaded = True
                cf_cached_output = cf_result
                logger.info(f"[MarketScanner] Capital flow done: {len(hypothesis)} candidates, cached to {cf_run_id}")
            except Exception as e:
                logger.warning(f"[MarketScanner] Capital flow auto-run failed: {e}")
                try:
                    ih = hash_input({"step": "capital_flow", "date": today})
                    save_checkpoint("step1b_capital_flow", cf_run_id, ih, {"agent": "CapitalFlowScanner", "error": str(e)[:200], "pressure_vectors": []}, {"elapsed": 0})
                except Exception: pass

        if not hypothesis:
            logger.warning(f"[MarketScanner] Capital flow returned no vectors, using fallback")
            hypothesis = FALLBACK_HYPOTHESIS
        ctx = {"mode": "auto", "hypothesis_sectors": hypothesis}
    else:
        ctx = {"mode": "manual" if mode_def["input_type"] != "none" else "auto"}
        if target: ctx["target_industry"] = target

    report_label = target if target else "每日扫描"
    step = "step2_gatekeeper"
    run_id = pre_run_id or generate_run_id(report_label)
    # 如果从缓存加载了 Step 1b, 复制到当前 run_id
    if cf_loaded:
        try:
            ih = hash_input({"step": "capital_flow", "date": today})
            save_checkpoint("step1b_capital_flow", run_id, ih, cf_cached_output, {"elapsed": 0})
        except Exception: pass
    t0 = __import__("time").time()

    input_hash = hash_input({
        "mode": req.mode, "target": target,
        "date": __import__("datetime").datetime.now().strftime("%Y%m%d"),
        "agent_version": "market_scanner_v5.11",
    })
    cached = load_checkpoint(step, run_id, input_hash)
    if cached:
        logger.info(f"[MarketScanner] CACHE HIT: {run_id}/{step}")
        return {"success": True, "data": cached, "from_cache": True, "run_id": run_id,
                "freshness": ResearchAgent.freshness_stamp()}

    trace = TraceContext(run_id)
    result = await scanner.analyze(ctx, trace=trace)

    elapsed = round(__import__("time").time() - t0, 1)
    try:
        save_checkpoint(step, run_id, input_hash, result, {"elapsed": elapsed, "input_summary": f"mode={req.mode}, target={target}"})
        await graph_bridge.notify(run_id, step, result)
        _now = datetime.now().isoformat()
        # DISABLED: await save_step_observations(run_id, step, result, _now)
        trace.write(step)
        save_manifest(run_id, {"run_id": run_id, "industry": report_label,
            "mode": "auto" if mode_id == "auto_scan" else "manual",
            "mode_id": mode_id, "agent_id": agent_id,
            "status": "completed", "started_at": trace.to_dict()["started_at"],
            "completed_at": __import__("datetime").datetime.now().isoformat(),
            "elapsed_seconds": elapsed, "step": step, "input_hash": input_hash})
    except Exception as e:
        logger.warning(f"[MarketScanner] Checkpoint save failed (non-fatal): {e}")

    save_report("MarketScanner", report_label, result)

    # ── 仅 1 个候选产业时自动链 Step 3, 多产业等用户手动选择 ──
    s3_result = None
    industries = (result or {}).get("industries", [])
    if len(industries) == 1:
        pick = industries[0]
        s3_industry = pick.get("industry", "")
        if s3_industry:
            try:
                logger.info(f"[MarketScanner] Auto-chain Step3: {s3_industry} (single industry)")
                from app.framework.ai.providers.deepseek import DeepSeekProvider
                hacker = SupplyChainHacker(provider=DeepSeekProvider())
                s3_guidance = pick.get("_step3_guidance", {})
                s3_ctx = {"industry": s3_industry, "step2_guidance": s3_guidance}
                s3_trace = TraceContext(run_id)
                s3_result = await hacker.analyze(s3_ctx, trace=s3_trace)
                s3_result["industry"] = s3_industry
                save_checkpoint("step3_sc_hacker", run_id, "drilldown", s3_result, {"elapsed": 0})
                await graph_bridge.notify(run_id, "step3_sc_hacker", s3_result)
                s3_trace.write("step3_sc_hacker")
                # DISABLED: await save_step_observations(run_id, "step3_sc_hacker", s3_result, datetime.now().isoformat())
                logger.info(f"[MarketScanner] Step3 done: {s3_industry} → {len(s3_result.get('supply_chain_map',[]))} layers")
            except Exception as e:
                logger.warning(f"[MarketScanner] Step3 auto-chain failed: {e}")
    elif len(industries) > 1:
        logger.info(f"[MarketScanner] {len(industries)} candidates, user to pick: {[i.get('industry','') for i in industries]}")

    return {"success": True, "data": result, "run_id": run_id,
            "freshness": ResearchAgent.freshness_stamp(),
            "next_step": "step3_sc_hacker" if s3_result else None}


@router.post("/scan")
async def market_scan(req: ScanRequest = ScanRequest(), async_mode: bool = Query(default=False)):
    """投研分析入口 — ?async=true 后台执行, 立即返回 exec_id"""
    if async_mode:
        from app.framework.tasks.engine import TaskEngine
        from app.framework.pipeline.checkpoint import generate_run_id, save_manifest
        target = req.target or req.target_industry or req.question or ("全局扫描" if req.mode_id == "auto_scan" else "资本流向" if req.mode_id == "capital_flow" else "宏观分析" if req.mode_id == "macro_only" else "分析")
        run_id = generate_run_id(target)
        save_manifest(run_id, {"run_id": run_id, "industry": target, "mode": "auto" if req.mode_id in ("auto_scan","capital_flow") else "manual",
            "mode_id": req.mode_id, "agent_id": req.agent_id, "status": "pending",
            "started_at": datetime.now().isoformat()})
        exec_id = await TaskEngine.run_task("research_analyze", {
            "agent_id": req.agent_id, "mode_id": req.mode_id, "target": target, "pre_run_id": run_id,
        })
        return {"success": True, "data": {"exec_id": exec_id, "status": "PENDING", "run_id": run_id},
                "message": "任务已提交, 轮询 GET /system/tasks/executions/" + exec_id}
    try:
        return await _do_scan(req)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[MarketScanner] Scan failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class SupplyChainRequest(BaseModel):
    industry: str = ""
    step2_output: dict = None  # Step 2 的完整输出 (含 _step3_guidance)


@router.post("/supply-chain-hacker")
async def supply_chain_hacker(req: SupplyChainRequest = SupplyChainRequest(),
                                async_mode: bool = Query(default=False)):
    """Step 3: 产业链系统拆解 — ?async_mode=true 后台执行"""
    if async_mode:
        from app.framework.tasks.engine import TaskEngine
        exec_id = await TaskEngine.run_task("research_analyze", {
            "agent_id": "supply_chain", "mode_id": "step3_standalone",
            "target": req.industry, "step2_output": req.step2_output,
        })
        return {"success": True, "data": {"exec_id": exec_id, "status": "PENDING"},
                "message": "Step3任务已提交, 轮询 GET /system/tasks/executions/" + exec_id}
    try:
        from app.framework.ai.providers.deepseek import DeepSeekProvider
        from app.framework.pipeline.checkpoint import (
            generate_run_id, hash_input, load_checkpoint,
            save_checkpoint, save_manifest,
        )
        from app.framework.pipeline.trace import TraceContext

        industry = req.industry.strip()
        if not industry:
            raise HTTPException(status_code=400, detail="industry is required")

        hacker_instance = SupplyChainHacker(provider=DeepSeekProvider())
        step = "step3_sc_hacker"
        # 复用已有 run_id (如果来自同一个 industry), 否则新建
        run_id = generate_run_id(industry)
        t0 = __import__("time").time()

        # 提取 Step 2 指引
        step2 = (req.step2_output or {}).get("_step3_guidance", {}) if req.step2_output else {}
        ctx = {"industry": industry, "step2_guidance": step2}

        # 缓存
        input_hash = hash_input({
            "industry": industry,
            "step2_phase": step2.get("cycle_phase", ""),
            "date": __import__("datetime").datetime.now().strftime("%Y%m%d"),
            "agent_version": "supply_chain_hacker_v5.8",
        })
        cached = load_checkpoint(step, run_id, input_hash)
        if cached:
            logger.info(f"[SupplyChainHacker] CACHE HIT: {run_id}/{step}")
            return {"success": True, "data": cached, "from_cache": True, "run_id": run_id}

        trace = TraceContext(run_id)
        result = await hacker_instance.analyze(ctx, trace=trace)

        result["industry"] = industry
        elapsed = round(__import__("time").time() - t0, 1)
        try:
            save_checkpoint(step, run_id, input_hash, result, {"elapsed": elapsed})
            trace.write(step)
            # DISABLED: await save_step_observations(run_id, step, result, datetime.now().isoformat())
            # 更新已有 manifest (追加 step3 信息)
            from app.framework.pipeline.checkpoint import load_manifest
            manifest = load_manifest(run_id) or {}
            manifest["step"] = step
            manifest["elapsed_seconds"] = (manifest.get("elapsed_seconds", 0) or 0) + elapsed
            save_manifest(run_id, manifest)
            logger.info(f"[SupplyChainHacker] Checkpoint saved: {run_id}/{step} ({elapsed}s)")
        except Exception as e:
            logger.warning(f"[SupplyChainHacker] Checkpoint save failed (non-fatal): {e}")

        save_report("SupplyChainHacker", industry, result)
        return {"success": True, "data": result, "run_id": run_id,
                "freshness": ResearchAgent.freshness_stamp()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[SupplyChainHacker] Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _synthesize_step11(run_id: str, industry: str, provider=None, trace_label="auto"):
    """Step 11 综合报告合成 — 收集所有 step outputs → ReportSynthesisAgent

    这是一个可复用函数, 在多个 auto-chain 场景中调用。
    """
    import json as _json
    from app.framework.pipeline.checkpoint import find_checkpoint_file, save_checkpoint
    from app.framework.pipeline.trace import TraceContext
    if not provider:
        from app.framework.ai.providers.deepseek import DeepSeekProvider
        provider = DeepSeekProvider()

    # 收集所有可用的 step outputs
    step_checkpoints = {
        "step1b_capital_flow": "step1b_capital_flow",
        "step2_gatekeeper": "step2_gatekeeper",
        "step3_sc_hacker": "step3_sc_hacker",
        "step4_system_dynamics": "step4_system_dynamics",
        "step6_core_screening": "step6_core_screening",
        "step9_expectation_gap": "step9_expectation_gap",
        "step10_risk_analysis": "step10_risk_analysis",
    }
    steps = {}
    present = 0
    for step_name, cp_step in step_checkpoints.items():
        cp_file = find_checkpoint_file(run_id, cp_step)
        if cp_file:
            try:
                with open(cp_file, "r", encoding="utf-8") as f:
                    record = _json.load(f)
                output = record.get("output", {})
                if output:
                    steps[step_name] = output
                    present += 1
                else:
                    steps[step_name] = {"note": "empty output"}
            except Exception as e:
                steps[step_name] = {"note": f"read failed: {e}"}
        else:
            steps[step_name] = {"note": "not found"}

    logger.info(f"[SynthesizeStep11] {industry}: {present} steps found")

    if present < 3:
        logger.warning(f"[SynthesizeStep11] {industry}: only {present} steps, report may be thin")

    rs_agent = ReportSynthesisAgent(provider=provider)
    rs_ctx = {"industry": industry, "steps": steps}
    rs_trace = TraceContext(run_id)
    step11_result = await rs_agent.analyze(rs_ctx, trace=rs_trace)

    save_checkpoint("step11_report", run_id, trace_label, step11_result, {"elapsed": 0})
    await graph_bridge.notify(run_id, "step11_report", step11_result)
    rs_trace.write("step11_report")

    n_sections = len(step11_result.get("report", {}).get("sections", []))
    logger.info(f"[SynthesizeStep11] Done: {industry} → {n_sections} sections")
    return step11_result


class IndustryDrilldownRequest(BaseModel):
    parent_run_id: str = ""
    industry_name: str = ""


@router.post("/scan/industry-drilldown")
async def industry_drilldown(req: IndustryDrilldownRequest):
    """全局扫描结果 → 选定行业 → 触发 Step 3"""
    try:
        from app.framework.pipeline.checkpoint import find_checkpoint_file, save_checkpoint
        from app.framework.pipeline.trace import TraceContext
        from app.framework.ai.providers.deepseek import DeepSeekProvider
        import json as _json

        # 从父 run 的 step2 检查点找该行业的输出
        cp_file = find_checkpoint_file(req.parent_run_id, "step2_gatekeeper")
        if not cp_file:
            raise HTTPException(status_code=404, detail=f"Parent run not found: {req.parent_run_id}")
        with open(cp_file, "r", encoding="utf-8") as f:
            step2 = _json.load(f)
        industries = step2.get("output", {}).get("industries", [])
        target = next((i for i in industries if i.get("industry") == req.industry_name), None)
        if not target:
            raise HTTPException(status_code=404, detail=f"Industry '{req.industry_name}' not found in run {req.parent_run_id}")

        # 调 Step 3
        hacker = SupplyChainHacker(provider=DeepSeekProvider())
        step2_guidance = target.get("_step3_guidance", {})
        ctx = {"industry": req.industry_name, "step2_guidance": step2_guidance}
        run_id = req.parent_run_id  # 保存到同一目录
        trace = TraceContext(run_id)
        result = await hacker.analyze(ctx, trace=trace)

        result["industry"] = req.industry_name
        save_checkpoint("step3_sc_hacker", run_id, "drilldown", result, {"elapsed": 0})
        await graph_bridge.notify(run_id, "step3_sc_hacker", result)
        trace.write("step3_sc_hacker")
        # DISABLED: await save_step_observations(run_id, "step3_sc_hacker", result, datetime.now().isoformat())
        logger.info(f"[Drilldown] Step3 done: {req.industry_name} → {len(result.get('supply_chain_map',[]))} layers")

        # Step 4: 系统动力学推演 (supply_chain_map >= 2 层时触发)
        if len(result.get("supply_chain_map", [])) >= 2:
            try:
                from app.domain.research.agents.system_dynamics_agent import SystemDynamicsAgent
                sd = SystemDynamicsAgent(provider=DeepSeekProvider())
                # V5.12: Step 2 可选增强
                s2_analysis = {} if not target else {
                    "cycle_phase": target.get("cycle_position", {}).get("phase", ""),
                    "sub_phase": target.get("cycle_position", {}).get("sub_phase", ""),
                    "profit_redirection": target.get("mismatch_analysis", {}).get("profit_redistribution", {}).get("direction", ""),
                    "repricing_stage": target.get("time_horizon", {}).get("market_repricing_stage", ""),
                    "payoff_asymmetry": target.get("payoff", {}).get("asymmetry", ""),
                    "substitution_risk": target.get("thesis_killers", {}).get("substitution_risk", ""),
                    "propagation_depth": target.get("propagation", {}).get("depth", ""),
                }
                sd_ctx = {"industry": req.industry_name,
                          "supply_chain_map": result.get("supply_chain_map", []),
                          "scarcity_ranking": result.get("scarcity_ranking", []),
                          "core_stocks": result.get("core_stocks", []),
                          "step2_analysis": s2_analysis}
                sd_trace = TraceContext(run_id)
                step4_result = await sd.analyze(sd_ctx, trace=sd_trace)
                save_checkpoint("step4_system_dynamics", run_id, "drilldown", step4_result, {"elapsed": 0})
                await graph_bridge.notify(run_id, "step4_system_dynamics", step4_result)
                sd_trace.write("step4_system_dynamics")
                # DISABLED: await save_step_observations(run_id, "step4_system_dynamics", step4_result, datetime.now().isoformat())
                logger.info(f"[Drilldown] Step4 done: {req.industry_name}")

                # Step 5: 跨产业关联 (V5.14 已合并入 Step 4)
                sd_out = step4_result.get("system_dynamics", {})
                cross_chain = sd_out.get("cross_chain_spillover", [])
                logger.info(f"[Drilldown] Step5 (merged): {len(cross_chain)} cross-chain spillovers")

                # Step 6: 核心资产筛选
                if cross_chain:
                    try:
                        step5_constructed = {"cross_chain_spillover": cross_chain, "cross_industry_linkages": cross_chain}
                        screener = CoreScreeningAgent(provider=DeepSeekProvider())
                        screen_ctx = {
                            "industry": req.industry_name,
                            "step3_output": result,
                            "step4_output": {"system_dynamics": sd_out},
                            "step5_output": step5_constructed,
                        }
                        screen_trace = TraceContext(run_id)
                        step6_result = await screener.analyze(screen_ctx, trace=screen_trace)
                        save_checkpoint("step6_core_screening", run_id, "drilldown", step6_result, {"elapsed": 0})
                        await graph_bridge.notify(run_id, "step6_core_screening", step6_result)
                        screen_trace.write("step6_core_screening")
                        # DISABLED: await save_step_observations(run_id, "step6_core_screening", step6_result, datetime.now().isoformat())
                        logger.info(f"[Drilldown] Step6 done: {len(step6_result.get('ranked_stocks',[]))} strong + {len(step6_result.get('future_strong_candidates',[]))} future")

                        # Step 9: 市场预期差
                        try:
                            eg_agent = ExpectationGapAgent(provider=DeepSeekProvider())
                            eg_ctx = {"industry": req.industry_name, "step6_output": step6_result}
                            eg_trace = TraceContext(run_id)
                            step9_result = await eg_agent.analyze(eg_ctx, trace=eg_trace)
                            save_checkpoint("step9_expectation_gap", run_id, "drilldown", step9_result, {"elapsed": 0})
                            await graph_bridge.notify(run_id, "step9_expectation_gap", step9_result)
                            eg_trace.write("step9_expectation_gap")
                            logger.info(f"[Drilldown] Step9 done: {len(step9_result.get('expectation_gaps',[]))} gaps")

                            # Step 10: 风险分析
                            try:
                                ra_agent = RiskAnalysisAgent(provider=DeepSeekProvider())
                                ra_ctx = {
                                    "industry": req.industry_name,
                                    "step6_output": step6_result,
                                    "step9_output": step9_result,
                                    "step4_output": {"system_dynamics": sd_out} if sd_out else {},
                                }
                                ra_trace = TraceContext(run_id)
                                step10_result = await ra_agent.analyze(ra_ctx, trace=ra_trace)
                                save_checkpoint("step10_risk_analysis", run_id, "drilldown", step10_result, {"elapsed": 0})
                                await graph_bridge.notify(run_id, "step10_risk_analysis", step10_result)
                                ra_trace.write("step10_risk_analysis")
                                logger.info(f"[Drilldown] Step10 done: {len(step10_result.get('risks',[]))} risks")

                                # ── 自动链 Step 11: 综合报告 ──
                                try:
                                    await _synthesize_step11(run_id, req.industry_name, provider=DeepSeekProvider(), trace_label="drilldown")
                                except Exception as e:
                                    logger.warning(f"[Drilldown] Step11 failed (non-fatal): {e}")

                            except Exception as e:
                                logger.warning(f"[Drilldown] Step10 failed (non-fatal): {e}")
                        except Exception as e:
                            logger.warning(f"[Drilldown] Step9 failed (non-fatal): {e}")

                    except Exception as e:
                        logger.warning(f"[Drilldown] Step6 failed (non-fatal): {e}")
            except Exception as e:
                logger.warning(f"[Drilldown] Step4 failed (non-fatal): {e}")

        return {"success": True, "data": result, "run_id": run_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Drilldown] Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class SystemDynamicsRequest(BaseModel):
    industry: str = ""
    step3_output: dict = None


@router.post("/system-dynamics")
async def system_dynamics_analysis(req: SystemDynamicsRequest = SystemDynamicsRequest(),
                                     async_mode: bool = Query(default=False)):
    """Step 4: 系统动力学推演 — ?async_mode=true 后台执行"""
    if async_mode:
        from app.framework.tasks.engine import TaskEngine
        exec_id = await TaskEngine.run_task("research_analyze", {
            "agent_id": "supply_chain", "mode_id": "step4_standalone",
            "target": req.industry, "step3_output": req.step3_output,
        })
        return {"success": True, "data": {"exec_id": exec_id, "status": "PENDING"}}
    try:
        from app.framework.ai.providers.deepseek import DeepSeekProvider
        from app.domain.research.agents.system_dynamics_agent import SystemDynamicsAgent
        from app.framework.pipeline.checkpoint import generate_run_id, hash_input, load_checkpoint, save_checkpoint
        from app.framework.pipeline.trace import TraceContext

        industry = req.industry.strip()
        if not industry:
            raise HTTPException(status_code=400, detail="industry is required")

        agent = SystemDynamicsAgent(provider=DeepSeekProvider())
        run_id = generate_run_id(industry)
        step3 = req.step3_output or {}
        ctx = {"industry": industry,
               "supply_chain_map": step3.get("supply_chain_map", []),
               "scarcity_ranking": step3.get("scarcity_ranking", []),
               "core_stocks": step3.get("core_stocks", [])}
        trace = TraceContext(run_id)
        result = await agent.analyze(ctx, trace=trace)

        input_hash = hash_input({"industry": industry, "date": __import__("datetime").datetime.now().strftime("%Y%m%d")})
        save_checkpoint("step4_system_dynamics", run_id, input_hash, result, {"elapsed": 0})
        await graph_bridge.notify(run_id, "step4_system_dynamics", result)
        trace.write("step4_system_dynamics")
        # DISABLED: await save_step_observations(run_id, "step4_system_dynamics", result, datetime.now().isoformat())

        # ── 自动链 Step 5+6: 跨产业关联 (V5.14 已合并入 Step 4) + 核心资产筛选 ──
        sd_out = result.get("system_dynamics", {})
        cross_chain = sd_out.get("cross_chain_spillover", [])
        if cross_chain:
            try:
                step5_constructed = {"cross_chain_spillover": cross_chain, "cross_industry_linkages": cross_chain}
                screener = CoreScreeningAgent(provider=DeepSeekProvider())
                screen_ctx = {
                    "industry": industry,
                    "step3_output": step3,
                    "step4_output": {"system_dynamics": sd_out},
                    "step5_output": step5_constructed,
                }
                screen_trace = TraceContext(run_id)
                step6_result = await screener.analyze(screen_ctx, trace=screen_trace)
                save_checkpoint("step6_core_screening", run_id, "auto", step6_result, {"elapsed": 0})
                await graph_bridge.notify(run_id, "step6_core_screening", step6_result)
                screen_trace.write("step6_core_screening")
                # DISABLED: await save_step_observations(run_id, "step6_core_screening", step6_result, datetime.now().isoformat())
                logger.info(f"[SystemDynamics] Step6 auto-chain done: {len(step6_result.get('ranked_stocks',[]))} strong, {len(step6_result.get('future_strong_candidates',[]))} future")

                # ── Step 9: 市场预期差 ──
                try:
                    eg_agent = ExpectationGapAgent(provider=DeepSeekProvider())
                    eg_ctx = {"industry": industry, "step6_output": step6_result}
                    eg_trace = TraceContext(run_id)
                    step9_result = await eg_agent.analyze(eg_ctx, trace=eg_trace)
                    save_checkpoint("step9_expectation_gap", run_id, "auto", step9_result, {"elapsed": 0})
                    await graph_bridge.notify(run_id, "step9_expectation_gap", step9_result)
                    eg_trace.write("step9_expectation_gap")
                    logger.info(f"[SystemDynamics] Step9 auto-chain done: {len(step9_result.get('expectation_gaps',[]))} gaps")

                    # ── Step 10: 风险分析 ──
                    try:
                        ra_agent = RiskAnalysisAgent(provider=DeepSeekProvider())
                        ra_ctx = {
                            "industry": industry,
                            "step6_output": step6_result,
                            "step9_output": step9_result,
                            "step4_output": {"system_dynamics": sd_out},
                        }
                        ra_trace = TraceContext(run_id)
                        step10_result = await ra_agent.analyze(ra_ctx, trace=ra_trace)
                        save_checkpoint("step10_risk_analysis", run_id, "auto", step10_result, {"elapsed": 0})
                        await graph_bridge.notify(run_id, "step10_risk_analysis", step10_result)
                        ra_trace.write("step10_risk_analysis")
                        logger.info(f"[SystemDynamics] Step10 auto-chain done: {len(step10_result.get('risks',[]))} risks")

                        # ── 自动链 Step 11: 综合报告 ──
                        if industry:
                            try:
                                await _synthesize_step11(run_id, industry, provider=DeepSeekProvider(), trace_label="auto")
                            except Exception as e:
                                logger.warning(f"[SystemDynamics] Step11 auto-chain failed: {e}")

                    except Exception as e:
                        logger.warning(f"[SystemDynamics] Step10 auto-chain failed: {e}")
                except Exception as e:
                    logger.warning(f"[SystemDynamics] Step9 auto-chain failed: {e}")

            except Exception as e:
                logger.warning(f"[SystemDynamics] Step6 auto-chain failed: {e}")

        return {"success": True, "data": result, "run_id": run_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[SystemDynamics] Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pipeline/{run_id}/continue/{step}")
async def continue_pipeline_step(run_id: str, step: str):
    """断点续跑: 从 run_id 的最新 checkpoint 启动指定 step"""
    try:
        from app.framework.pipeline.checkpoint import find_checkpoint_file, load_checkpoint, save_checkpoint, list_checkpoints
        from app.framework.pipeline.trace import TraceContext
        from app.framework.ai.providers.deepseek import DeepSeekProvider

        if step == "step3_sc_hacker":
            s2_file = find_checkpoint_file(run_id, "step2_gatekeeper")
            if not s2_file:
                raise HTTPException(status_code=404, detail="Step 2 checkpoint not found")
            import json as _json
            with open(s2_file, "r", encoding="utf-8") as f:
                s2 = _json.load(f)
            s2_out = s2.get("output", {})
            # manual_industry 模式: 读完整的 step2 输出
            step2_guidance = s2_out.get("_step3_guidance", {})
            industry = s2_out.get("industry", "") or (s2_out.get("industries", [{}])[0].get("industry", ""))

            hacker_instance = SupplyChainHacker(provider=DeepSeekProvider())
            ctx = {"industry": industry, "step2_guidance": step2_guidance}
            trace = TraceContext(run_id)
            result = await hacker_instance.analyze(ctx, trace=trace)

            result["industry"] = industry
            save_checkpoint("step3_sc_hacker", run_id, "continue", result, {"elapsed": 0})
            await graph_bridge.notify(run_id, "step3_sc_hacker", result)
            trace.write("step3_sc_hacker")
            _now_s3 = datetime.now().isoformat()
            # DISABLED: await save_step_observations(run_id, "step3_sc_hacker", result, _now_s3)
            # 链 Step 4
            scm = result.get("supply_chain_map", [])
            if len(scm) >= 2:
                try:
                    from app.domain.research.agents.system_dynamics_agent import SystemDynamicsAgent
                    sd = SystemDynamicsAgent(provider=DeepSeekProvider())
                    # V5.12: 从 s2_out 提取 Step 2 分析数据
                    _s2_entry = next((i for i in s2_out.get("industries", []) if i.get("industry") == industry), s2_out)
                    step2_analysis = {
                        "cycle_phase": _s2_entry.get("cycle_position", {}).get("phase", ""),
                        "sub_phase": _s2_entry.get("cycle_position", {}).get("sub_phase", ""),
                        "profit_redirection": _s2_entry.get("mismatch_analysis", {}).get("profit_redistribution", {}).get("direction", ""),
                        "repricing_stage": _s2_entry.get("time_horizon", {}).get("market_repricing_stage", ""),
                        "payoff_asymmetry": _s2_entry.get("payoff", {}).get("asymmetry", ""),
                        "substitution_risk": _s2_entry.get("thesis_killers", {}).get("substitution_risk", ""),
                        "propagation_depth": _s2_entry.get("propagation", {}).get("depth", ""),
                    }
                    sd_ctx = {"industry": industry,
                              "supply_chain_map": scm,
                              "scarcity_ranking": result.get("scarcity_ranking", []),
                              "core_stocks": result.get("core_stocks", []),
                              "step2_analysis": step2_analysis}
                    sd_trace = TraceContext(run_id)
                    step4_result = await sd.analyze(sd_ctx, trace=sd_trace)
                    save_checkpoint("step4_system_dynamics", run_id, "continue", step4_result, {"elapsed": 0})
                    await graph_bridge.notify(run_id, "step4_system_dynamics", step4_result)
                    sd_trace.write("step4_system_dynamics")
                    # DISABLED: await save_step_observations(run_id, "step4_system_dynamics", step4_result, datetime.now().isoformat())
                    # Step 5 (V5.14 已合并入 Step 4) → Step 6
                    sd_out = step4_result.get("system_dynamics", {})
                    cross_chain = sd_out.get("cross_chain_spillover", [])
                    if cross_chain:
                        try:
                            step5_constructed = {"cross_chain_spillover": cross_chain, "cross_industry_linkages": cross_chain}
                            screener = CoreScreeningAgent(provider=DeepSeekProvider())
                            screen_ctx = {
                                "industry": industry,
                                "step3_output": result,
                                "step4_output": {"system_dynamics": sd_out},
                                "step5_output": step5_constructed,
                            }
                            screen_trace = TraceContext(run_id)
                            step6_result = await screener.analyze(screen_ctx, trace=screen_trace)
                            save_checkpoint("step6_core_screening", run_id, "continue", step6_result, {"elapsed": 0})
                            await graph_bridge.notify(run_id, "step6_core_screening", step6_result)
                            screen_trace.write("step6_core_screening")
                            # DISABLED: await save_step_observations(run_id, "step6_core_screening", step6_result, datetime.now().isoformat())
                        except Exception as e:
                            logger.warning(f"[ContinueStep] Step6 chain failed: {e}")
                except Exception as e:
                    logger.warning(f"[ContinueStep] Step4 chain failed: {e}")
            return {"success": True, "data": result, "run_id": run_id,
                    "auto_chained": ["step3_sc_hacker", "step4_system_dynamics"]}

        elif step == "step4_system_dynamics":
            # 找 Step 3 checkpoint
            s3_file = find_checkpoint_file(run_id, "step3_sc_hacker")
            if not s3_file:
                raise HTTPException(status_code=404, detail="Step 3 checkpoint not found. Run Step 3 first.")
            import json as _json
            with open(s3_file, "r", encoding="utf-8") as f:
                s3 = _json.load(f)
            s3_out = s3.get("output", {})
            scm = s3_out.get("supply_chain_map", [])
            if len(scm) < 2:
                return {"success": True, "data": {"message": "Step 3 has <2 layers, Step 4 skipped", "layers": len(scm)}}

            from app.domain.research.agents.system_dynamics_agent import SystemDynamicsAgent
            sd = SystemDynamicsAgent(provider=DeepSeekProvider())
            # V5.12: 尝试加载 Step 2 数据 (可选)
            s2_file = find_checkpoint_file(run_id, "step2_gatekeeper")
            if s2_file:
                with open(s2_file, "r", encoding="utf-8") as f:
                    s2_out = _json.load(f).get("output", {})
                _industry = s3_out.get("industry", "")
                _s2_entry = next((i for i in s2_out.get("industries", []) if i.get("industry") == _industry), s2_out)
                step2_analysis = {
                    "cycle_phase": _s2_entry.get("cycle_position", {}).get("phase", ""),
                    "sub_phase": _s2_entry.get("cycle_position", {}).get("sub_phase", ""),
                    "profit_redirection": _s2_entry.get("mismatch_analysis", {}).get("profit_redistribution", {}).get("direction", ""),
                    "repricing_stage": _s2_entry.get("time_horizon", {}).get("market_repricing_stage", ""),
                    "payoff_asymmetry": _s2_entry.get("payoff", {}).get("asymmetry", ""),
                    "substitution_risk": _s2_entry.get("thesis_killers", {}).get("substitution_risk", ""),
                    "propagation_depth": _s2_entry.get("propagation", {}).get("depth", ""),
                }
            else:
                step2_analysis = {}
            sd_ctx = {"industry": s3_out.get("industry", ""),
                      "supply_chain_map": scm,
                      "scarcity_ranking": s3_out.get("scarcity_ranking", []),
                      "core_stocks": s3_out.get("core_stocks", []),
                      "step2_analysis": step2_analysis}
            trace = TraceContext(run_id)
            result = await sd.analyze(sd_ctx, trace=trace)
            save_checkpoint("step4_system_dynamics", run_id, "continue", result, {"elapsed": 0})
            await graph_bridge.notify(run_id, "step4_system_dynamics", result)
            trace.write("step4_system_dynamics")
            # DISABLED: await save_step_observations(run_id, "step4_system_dynamics", result, datetime.now().isoformat())
            # Step 5 (V5.14 已合并入 Step 4) → Step 6
            sd_out = result.get("system_dynamics", {})
            cross_chain = sd_out.get("cross_chain_spillover", [])
            if cross_chain:
                try:
                    step5_constructed = {"cross_chain_spillover": cross_chain, "cross_industry_linkages": cross_chain}
                    screener = CoreScreeningAgent(provider=DeepSeekProvider())
                    screen_ctx = {
                        "industry": s3_out.get("industry", ""),
                        "step3_output": s3_out,
                        "step4_output": {"system_dynamics": sd_out},
                        "step5_output": step5_constructed,
                    }
                    screen_trace = TraceContext(run_id)
                    step6_result = await screener.analyze(screen_ctx, trace=screen_trace)
                    save_checkpoint("step6_core_screening", run_id, "continue", step6_result, {"elapsed": 0})
                    await graph_bridge.notify(run_id, "step6_core_screening", step6_result)
                    screen_trace.write("step6_core_screening")
                    # DISABLED: await save_step_observations(run_id, "step6_core_screening", step6_result, datetime.now().isoformat())
                except Exception as e:
                    logger.warning(f"[ContinueStep] Step6 chain failed: {e}")
            return {"success": True, "data": result, "run_id": run_id}

        elif step == "step5_cross_industry":
            # V5.14: Step 5 已合并入 Step 4, 从 Step 4 checkpoint 提取 cross_chain_spillover
            s3_file = find_checkpoint_file(run_id, "step3_sc_hacker")
            s4_file = find_checkpoint_file(run_id, "step4_system_dynamics")
            if not s3_file:
                raise HTTPException(status_code=404, detail="Step 3 checkpoint not found. Run Step 3 first.")
            if not s4_file:
                raise HTTPException(status_code=404, detail="Step 4 checkpoint not found. Run Step 4 first.")
            import json as _json
            with open(s3_file, "r", encoding="utf-8") as f:
                s3 = _json.load(f)
            with open(s4_file, "r", encoding="utf-8") as f:
                s4 = _json.load(f)
            s3_out = s3.get("output", {})
            s4_out = s4.get("output", {}).get("system_dynamics", {})
            cross_chain = s4_out.get("cross_chain_spillover", [])

            result = {"cross_chain_spillover": cross_chain, "cross_industry_linkages": cross_chain, "discovery_summary": s4_out.get("thesis_breakers", [{}])[0].get("thesis", "") if s4_out.get("thesis_breakers") else ""}
            logger.info(f"[ContinueStep] Step5 (merged, from Step4): {len(cross_chain)} spillovers")

            # 自动链 Step 6
            if cross_chain:
                try:
                    s3_industry = s3_out.get("industry", "(not set)")
                    logger.info(f"[ContinueStep] Chaining Step6: industry={s3_industry}, spillovers={len(cross_chain)}")
                    screener = CoreScreeningAgent(provider=DeepSeekProvider())
                    screen_ctx = {
                        "industry": s3_industry,
                        "step3_output": s3_out,
                        "step4_output": {"system_dynamics": s4_out},
                        "step5_output": result,
                    }
                    screen_trace = TraceContext(run_id)
                    step6_result = await screener.analyze(screen_ctx, trace=screen_trace)
                    save_checkpoint("step6_core_screening", run_id, "continue", step6_result, {"elapsed": 0})
                    await graph_bridge.notify(run_id, "step6_core_screening", step6_result)
                    screen_trace.write("step6_core_screening")
                    # DISABLED: await save_step_observations(run_id, "step6_core_screening", step6_result, datetime.now().isoformat())
                    logger.info(f"[ContinueStep] Step6 done: {len(step6_result.get('ranked_stocks',[]))} strong, {len(step6_result.get('future_strong_candidates',[]))} future")
                except Exception as e:
                    logger.error(f"[ContinueStep] Step6 chain FAILED: {type(e).__name__}: {e}")
            return {"success": True, "data": result, "run_id": run_id}

        elif step == "step6_core_screening":
            s3_file = find_checkpoint_file(run_id, "step3_sc_hacker")
            s4_file = find_checkpoint_file(run_id, "step4_system_dynamics")
            s5_file = find_checkpoint_file(run_id, "step5_cross_industry")
            if not s3_file:
                raise HTTPException(status_code=404, detail="Step 3 checkpoint not found")
            import json as _json
            with open(s3_file, "r", encoding="utf-8") as f:
                s3 = _json.load(f)
            s3_out = s3.get("output", {})
            s4_out, s5_out = {}, {}
            if s4_file:
                with open(s4_file, "r", encoding="utf-8") as f:
                    s4_out = _json.load(f).get("output", {})
            if s5_file:
                with open(s5_file, "r", encoding="utf-8") as f:
                    s5_out = _json.load(f).get("output", {})

            screener = CoreScreeningAgent(provider=DeepSeekProvider())
            ctx = {
                "industry": s3_out.get("industry", ""),
                "step3_output": s3_out,
                "step4_output": s4_out,
                "step5_output": s5_out,
            }
            trace = TraceContext(run_id)
            result = await screener.analyze(ctx, trace=trace)
            save_checkpoint("step6_core_screening", run_id, "continue", result, {"elapsed": 0})
            await graph_bridge.notify(run_id, "step6_core_screening", result)
            trace.write("step6_core_screening")
            # DISABLED: await save_step_observations(run_id, "step6_core_screening", result, datetime.now().isoformat())

            # ── 自动链 Step 9: 市场预期差 ──
            try:
                s6_industry = s3_out.get("industry", "")
                logger.info(f"[ContinueStep] Chaining Step9: {s6_industry}")
                eg_agent = ExpectationGapAgent(provider=DeepSeekProvider())
                eg_ctx = {"industry": s6_industry, "step6_output": result}
                eg_trace = TraceContext(run_id)
                step9_result = await eg_agent.analyze(eg_ctx, trace=eg_trace)
                save_checkpoint("step9_expectation_gap", run_id, "continue", step9_result, {"elapsed": 0})
                await graph_bridge.notify(run_id, "step9_expectation_gap", step9_result)
                eg_trace.write("step9_expectation_gap")
                logger.info(f"[ContinueStep] Step9 done: {len(step9_result.get('expectation_gaps',[]))} gaps")

                # ── 自动链 Step 10: 风险分析 ──
                try:
                    step4_sd = {}
                    if s4_file:
                        with open(s4_file, "r", encoding="utf-8") as f:
                            step4_sd = _json.load(f).get("output", {})
                    ra_agent = RiskAnalysisAgent(provider=DeepSeekProvider())
                    ra_ctx = {
                        "industry": s6_industry,
                        "step6_output": result,
                        "step9_output": step9_result,
                        "step4_output": step4_sd,
                    }
                    ra_trace = TraceContext(run_id)
                    step10_result = await ra_agent.analyze(ra_ctx, trace=ra_trace)
                    save_checkpoint("step10_risk_analysis", run_id, "continue", step10_result, {"elapsed": 0})
                    await graph_bridge.notify(run_id, "step10_risk_analysis", step10_result)
                    ra_trace.write("step10_risk_analysis")
                    logger.info(f"[ContinueStep] Step10 done: {len(step10_result.get('risks',[]))} risks")

                    # ── 自动链 Step 11: 综合报告 ──
                    if s6_industry:
                        try:
                            await _synthesize_step11(run_id, s6_industry, provider=DeepSeekProvider(), trace_label="continue")
                        except Exception as e:
                            logger.warning(f"[ContinueStep] Step11 chain failed (non-fatal): {e}")

                except Exception as e:
                    logger.warning(f"[ContinueStep] Step10 chain failed (non-fatal): {e}")
            except Exception as e:
                logger.warning(f"[ContinueStep] Step9 chain failed (non-fatal): {e}")

            return {"success": True, "data": result, "run_id": run_id}

        elif step == "step9_expectation_gap":
            s6_file = find_checkpoint_file(run_id, "step6_core_screening")
            if not s6_file:
                raise HTTPException(status_code=404, detail="Step 6 checkpoint not found. Run Step 6 first.")
            import json as _json
            with open(s6_file, "r", encoding="utf-8") as f:
                s6 = _json.load(f)
            s6_out = s6.get("output", {})

            eg_agent = ExpectationGapAgent(provider=DeepSeekProvider())
            ctx = {
                "industry": s6_out.get("industry", ""),
                "step6_output": s6_out,
            }
            trace = TraceContext(run_id)
            result = await eg_agent.analyze(ctx, trace=trace)
            save_checkpoint("step9_expectation_gap", run_id, "continue", result, {"elapsed": 0})
            await graph_bridge.notify(run_id, "step9_expectation_gap", result)
            trace.write("step9_expectation_gap")

            # 自动链 Step 10
            try:
                ra_agent = RiskAnalysisAgent(provider=DeepSeekProvider())
                ra_ctx = {
                    "industry": s6_out.get("industry", ""),
                    "step6_output": s6_out,
                    "step9_output": result,
                }
                ra_trace = TraceContext(run_id)
                step10_result = await ra_agent.analyze(ra_ctx, trace=ra_trace)
                save_checkpoint("step10_risk_analysis", run_id, "continue", step10_result, {"elapsed": 0})
                await graph_bridge.notify(run_id, "step10_risk_analysis", step10_result)
                ra_trace.write("step10_risk_analysis")
                logger.info(f"[ContinueStep] Step10 auto-chain done: {len(step10_result.get('risks',[]))} risks")
            except Exception as e:
                logger.warning(f"[ContinueStep] Step10 auto-chain failed (non-fatal): {e}")

            return {"success": True, "data": result, "run_id": run_id}

        elif step == "step10_risk_analysis":
            s6_file = find_checkpoint_file(run_id, "step6_core_screening")
            s9_file = find_checkpoint_file(run_id, "step9_expectation_gap")
            if not s6_file:
                raise HTTPException(status_code=404, detail="Step 6 checkpoint not found. Run Step 6 first.")
            import json as _json
            with open(s6_file, "r", encoding="utf-8") as f:
                s6 = _json.load(f)
            s6_out = s6.get("output", {})
            s9_out = {}
            if s9_file:
                with open(s9_file, "r", encoding="utf-8") as f:
                    s9_out = _json.load(f).get("output", {})

            ra_agent = RiskAnalysisAgent(provider=DeepSeekProvider())
            ctx = {
                "industry": s6_out.get("industry", ""),
                "step6_output": s6_out,
                "step9_output": s9_out,
            }
            trace = TraceContext(run_id)
            result = await ra_agent.analyze(ctx, trace=trace)
            save_checkpoint("step10_risk_analysis", run_id, "continue", result, {"elapsed": 0})
            await graph_bridge.notify(run_id, "step10_risk_analysis", result)
            trace.write("step10_risk_analysis")

            # ── 自动链 Step 11: 综合报告 ──
            try:
                s6_industry = s6_out.get("industry", "")
                if s6_industry:
                    await _synthesize_step11(run_id, s6_industry, provider=DeepSeekProvider(), trace_label="continue")
            except Exception as e:
                logger.warning(f"[ContinueStep] Step11 chain failed (non-fatal): {e}")

            return {"success": True, "data": result, "run_id": run_id}

        elif step == "step11_report":
            # Step 11: 综合报告 — 收集所有可用 step 输出, 调用 ReportSynthesisAgent
            from app.framework.pipeline.checkpoint import find_checkpoint_file, load_checkpoint
            import json as _json

            # 收集所有步骤
            step_checkpoints_map = {
                "step1b_capital_flow": "step1b_capital_flow",
                "step2_gatekeeper": "step2_gatekeeper",
                "step3_sc_hacker": "step3_sc_hacker",
                "step4_system_dynamics": "step4_system_dynamics",
                "step6_core_screening": "step6_core_screening",
                "step9_expectation_gap": "step9_expectation_gap",
                "step10_risk_analysis": "step10_risk_analysis",
            }
            steps = {}
            # 先用 industry 变量
            industry_hint = ""

            for step_name, cp_step in step_checkpoints_map.items():
                cp_file = find_checkpoint_file(run_id, cp_step)
                if cp_file:
                    with open(cp_file, "r", encoding="utf-8") as f:
                        record = _json.load(f)
                    output = record.get("output", {})
                    if output:
                        steps[step_name] = output
                        if not industry_hint and isinstance(output, dict):
                            for key in ("industry",):
                                industry_hint = output.get(key, "") or industry_hint

            if not industry_hint:
                # 从 manifest 获取
                from app.framework.pipeline.checkpoint import load_manifest
                manifest = load_manifest(run_id)
                industry_hint = (manifest or {}).get("industry", "未指定")

            result = await _synthesize_step11(run_id, industry_hint, provider=DeepSeekProvider(), trace_label="continue")
            return {"success": True, "data": result, "run_id": run_id}

        else:
            raise HTTPException(status_code=400, detail=f"Unknown or unsupported step: {step}")
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"[ContinueStep] {run_id}/{step} failed: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/direct-asset-mine")
async def direct_asset_mine(body: dict):
    """Path A: 直接资产挖掘 — 用 Step 2 的 transmission_order 节点直接挖掘标的"""
    try:
        from app.framework.ai.providers.deepseek import DeepSeekProvider
        from app.framework.pipeline.checkpoint import generate_run_id, save_checkpoint
        from app.framework.pipeline.trace import TraceContext

        industry = body.get("industry", "")
        step2_output = body.get("step2_output", {})
        if not industry:
            raise HTTPException(status_code=400, detail="industry is required")
        if not step2_output:
            raise HTTPException(status_code=400, detail="step2_output is required")

        provider = DeepSeekProvider()
        miner = CoreScreeningAgent(provider=provider)
        run_id = generate_run_id(industry)
        t0 = __import__("time").time()

        trace = TraceContext(run_id)
        result = await miner.analyze({
            "industry": industry,
            "step2_only": True,
            "step2_output": step2_output,
        }, trace=trace)

        elapsed = round(__import__("time").time() - t0, 1)
        save_checkpoint("step2a_direct_asset", run_id, "direct_asset_mine", result, {"elapsed": elapsed})
        await graph_bridge.notify(run_id, "step2a_direct_asset", result)
        trace.write("step2a_direct_asset")
        # DISABLED: await save_step_observations(run_id, "step2a_direct_asset", result, datetime.now().isoformat())

        n_strong = len(result.get("ranked_stocks", []))
        n_future = len(result.get("future_strong_candidates", []))
        logger.info(f"[DirectAssetMine] {industry}: {n_strong} strong, {n_future} future ({elapsed:.1f}s)")
        return {"success": True, "data": result, "run_id": run_id, "elapsed": elapsed}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DirectAssetMine] Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/second-order-extrapolate")
async def second_order_extrapolate(body: dict):
    """Path B: 从 Step 2 输出外推相邻产业预期差"""
    try:
        from app.framework.ai.providers.deepseek import DeepSeekProvider
        from app.framework.pipeline.checkpoint import generate_run_id, save_checkpoint
        from app.framework.pipeline.trace import TraceContext
        from app.domain.research.agents.second_order_extrapolator import SecondOrderExtrapolator

        industry = body.get("industry", "")
        step2_output = body.get("step2_output", {})
        if not industry:
            raise HTTPException(status_code=400, detail="industry is required")
        if not step2_output:
            raise HTTPException(status_code=400, detail="step2_output is required")

        provider = DeepSeekProvider()
        extrapolator = SecondOrderExtrapolator(provider=provider)
        run_id = generate_run_id(industry)
        t0 = __import__("time").time()

        trace = TraceContext(run_id)
        result = await extrapolator.analyze({
            "industry": industry,
            "step2_output": step2_output,
        }, trace=trace)

        elapsed = round(__import__("time").time() - t0, 1)
        save_checkpoint("step2b_second_order", run_id, "second_order_extrapolate", result, {"elapsed": elapsed})
        await graph_bridge.notify(run_id, "step2b_second_order", result)
        trace.write("step2b_second_order")
        # DISABLED: await save_step_observations(run_id, "step2b_second_order", result, datetime.now().isoformat())

        n_adj = len(result.get("adjacent_industries", []))
        logger.info(f"[SecondOrderExtrapolate] {industry}: {n_adj} adjacent industries ({elapsed:.1f}s)")
        return {"success": True, "data": result, "run_id": run_id, "elapsed": elapsed}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[SecondOrderExtrapolate] Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cross-industry")
async def cross_industry_analysis():
    """Step 5: 跨产业关联分析 (DEPRECATED in V5.14 — 已合并入 Step 4 SystemDynamicsAgent)"""
    logger.warning(f"[CrossIndustry] DEPRECATED: Step 5 merged into Step 4 (V5.14). Use /system-dynamics instead.")
    return {"success": True, "data": {
        "deprecated": True,
        "message": "Step 5 已合并入 Step 4 (V5.14), cross_chain_spillover 现在作为 system_dynamics 的一部分输出。请使用 POST /api/research/system-dynamics 替代。",
        "migration": "Step 4 输出中的 system_dynamics.cross_chain_spillover[] 替代了原 Step 5 的 cross_industry_linkages[]"
    }}


@router.post("/capital-flow")
async def capital_flow_scan(async_mode: bool = Query(default=False)):
    """Step 1b: 全球资本流向扫描 — ?async_mode=true 后台执行"""
    if async_mode:
        from app.framework.tasks.engine import TaskEngine
        exec_id = await TaskEngine.run_task("research_analyze", {
            "agent_id": "supply_chain", "mode_id": "capital_flow",
            "target": "capital_flow",
        })
        return {"success": True, "data": {"exec_id": exec_id, "status": "PENDING"}}
    try:
        from app.framework.ai.providers.deepseek import DeepSeekProvider
        from app.domain.research.agents.capital_flow_scanner import CapitalFlowScanner
        from app.framework.pipeline.checkpoint import generate_run_id, hash_input, load_checkpoint, save_checkpoint, save_manifest
        from app.framework.pipeline.trace import TraceContext

        scanner = CapitalFlowScanner(provider=DeepSeekProvider())
        run_id = generate_run_id("资本流向")
        step = "step1b_capital_flow"
        t0 = __import__("time").time()

        input_hash = hash_input({
            "step": "capital_flow",
            "date": __import__("datetime").datetime.now().strftime("%Y%m%d"),
        })
        cached = load_checkpoint(step, run_id, input_hash)
        if cached:
            return {"success": True, "data": cached, "from_cache": True, "run_id": run_id}

        trace = TraceContext(run_id)
        result = await scanner.analyze(ctx={}, trace=trace)

        elapsed = round(__import__("time").time() - t0, 1)
        try:
            save_checkpoint(step, run_id, input_hash, result, {"elapsed": elapsed})
            trace.write(step)
            save_manifest(run_id, {"run_id": run_id, "industry": "资本流向", "status": "completed",
                "started_at": trace.to_dict()["started_at"],
                "completed_at": __import__("datetime").datetime.now().isoformat(),
                "elapsed_seconds": elapsed, "step": step})
        except Exception as e:
            logger.warning(f"[CapitalFlow] Checkpoint save failed (non-fatal): {e}")

        save_report("CapitalFlowScanner", "资本流向", result)
        return {"success": True, "data": result, "run_id": run_id}
    except Exception as e:
        logger.error(f"[CapitalFlow] Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stocks/batch-info")
async def batch_stock_info(codes: List[str]):
    """批量获取股票基本信息 (供投研标的提取面板使用) — 从 StockMaster + StockValuation"""
    if not codes:
        return {"success": True, "data": []}
    from app.framework.database.session import async_session
    from app.models.models import StockMaster, StockValuation
    from sqlalchemy import select, outerjoin, collate
    async with async_session() as db:
        j = outerjoin(StockMaster, StockValuation,
                      StockMaster.stock_code == collate(StockValuation.stock_code, 'utf8mb4_unicode_ci'))
        res = await db.execute(
            select(StockMaster, StockValuation)
            .select_from(j)
            .where(StockMaster.stock_code.in_(codes[:30])))
        info_map = {}
        for r in res.all():
            m, v = r
            info_map[m.stock_code] = {
                "name": m.stock_name,
                "industry": m.industry,
                "pe_ttm": v.pe_ttm if v else None,
                "mcap_yi": v.mcap_yi if v else None,
            }
        result = []
        for code in codes:
            s = info_map.get(code, {})
            result.append({
                "code": code,
                "name": s.get("name", code),
                "industry": s.get("industry"),
                "pe_ttm": s.get("pe_ttm"),
                "mcap_yi": s.get("mcap_yi"),
            })
        return {"success": True, "data": result}


# ═══════════════════════════════════════════
# Pipeline 运维 API
# ═══════════════════════════════════════════

class ResumeRequest(BaseModel):
    from_step: str = "step3_sc_hacker"
    force: bool = False


@router.get("/pipeline/runs")
async def list_pipeline_runs(limit: int = Query(default=20, ge=1, le=100)):
    """列出所有 Pipeline run 历史"""
    try:
        from app.framework.pipeline.checkpoint import list_runs, make_display_name
        runs = list_runs()
        for r in runs:
            r["display_name"] = make_display_name(r["run_id"], r.get("industry", ""))
        return {"success": True, "data": runs[:limit], "total": len(runs)}
    except Exception as e:
        logger.error(f"[PipelineAPI] List runs failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipeline/{run_id}")
async def get_pipeline_run(run_id: str):
    """单 run 详情: manifest + 各 step 检查点列表 (含虚拟 Step1 宏观)"""
    try:
        from app.framework.pipeline.checkpoint import (
            load_manifest, list_checkpoints, CHECKPOINT_DIR, make_display_name
        )
        import os
        manifest = load_manifest(run_id)
        checkpoints = list_checkpoints(run_id)
        steps = {}
        for cp in checkpoints:
            s = cp.get("step", "unknown")
            steps[s] = {
                "step": s, "saved_at": cp.get("saved_at"),
                "elapsed_seconds": cp.get("elapsed"), "file": cp.get("file"),
            }
        run_dir = os.path.join(CHECKPOINT_DIR, run_id)
        for s in list(steps.keys()):
            tf = os.path.join(run_dir, f"{s}.trace.txt")
            if os.path.exists(tf):
                steps[s]["has_trace"] = True

        # 虚拟 Step 1: 宏观报告 (全局共享, 不在 run 目录下)
        macro_path = os.path.join(CHECKPOINT_DIR, "..", "macro_report.json")
        macro_path = os.path.abspath(macro_path)
        if os.path.exists(macro_path):
            macro_stat = os.stat(macro_path)
            steps["step1_macro"] = {
                "step": "step1_macro",
                "saved_at": __import__("datetime").datetime.fromtimestamp(macro_stat.st_mtime).isoformat(),
                "elapsed_seconds": 0,
                "file": macro_path,
                "has_trace": False,
                "is_shared": True,
            }
            steps = dict(sorted(steps.items()))

        # 根据 manifest 中的 mode_id 查找预期 pipeline
        mode_id = (manifest or {}).get("mode_id", "")
        mode = (manifest or {}).get("mode", "manual")
        pipeline_def = []
        # 从 AGENT_REGISTRY 精确匹配
        for agent in AGENT_REGISTRY:
            for m in agent.get("modes", []):
                if m["id"] == mode_id:
                    pipeline_def = m.get("pipeline", [])
                    break
            if pipeline_def: break
        # 降级: 根据 mode 推断
        if not pipeline_def:
            if mode == "auto":
                pipeline_def = ["step1_macro", "step1b_capital_flow", "step2_gatekeeper"]
            else:
                pipeline_def = ["step1_macro", "step2_gatekeeper", "step3_sc_hacker"]

        # 合并 pipeline 定义 + 实际完成状态 (三态: completed / pending / planned)
        full_steps = {}
        run_status = (manifest or {}).get("status", "pending")
        for s in pipeline_def:
            label = STEP_LABELS.get(s, s)
            implemented = s in IMPLEMENTED_STEPS
            optional = s in OPTIONAL_STEPS
            if s in steps:
                full_steps[s] = {**steps[s], "label": label, "status": "completed",
                                 "implemented": True, "optional": optional}
            elif not implemented:
                full_steps[s] = {"step": s, "label": label, "status": "planned",
                                 "elapsed_seconds": 0, "implemented": False, "optional": optional}
            else:
                full_steps[s] = {"step": s, "label": label, "status": "pending",
                                 "elapsed_seconds": 0, "implemented": True, "optional": optional}
        for s, info in steps.items():
            if s not in full_steps:
                full_steps[s] = {**info, "label": STEP_LABELS.get(s, s), "status": "completed",
                                 "implemented": True, "optional": s in OPTIONAL_STEPS}
        full_steps = dict(sorted(full_steps.items()))

        return {"success": True, "data": {
            "run_id": run_id,
            "display_name": make_display_name(run_id, manifest.get("industry", "") if manifest else ""),
            "manifest": manifest,
            "steps": full_steps,
            "pipeline": pipeline_def,
        }}
    except Exception as e:
        logger.error(f"[PipelineAPI] Get run failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipeline/{run_id}/trace/{step}")
async def get_pipeline_trace(run_id: str, step: str):
    """读取某 step 的溯源日志"""
    import os, json as _json
    from app.framework.pipeline.checkpoint import CHECKPOINT_DIR
    tp = os.path.join(CHECKPOINT_DIR, run_id, f"{step}.trace.txt")
    if not os.path.exists(tp):
        raise HTTPException(status_code=404, detail=f"Trace not found: {run_id}/{step}")
    events = []
    with open(tp, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(_json.loads(line))
                except Exception:
                    events.append({"raw": line[:500]})
    return {"success": True, "data": {"run_id": run_id, "step": step, "event_count": len(events), "events": events}}


@router.post("/pipeline/{run_id}/resume")
async def resume_pipeline_run(run_id: str, req: ResumeRequest = ResumeRequest()):
    """从指定 step 断点续跑"""
    try:
        from app.framework.pipeline.checkpoint import load_manifest
        manifest = load_manifest(run_id)
        if not manifest:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
        return {"success": True, "data": {
            "run_id": run_id, "from_step": req.from_step,
            "status": "not_implemented",
            "message": "PipelineRunner 尚未实现。手动操作: (1) 编辑 checkpoint JSON → (2) curl Agent 端点重跑下游",
            "manifest_industry": manifest.get("industry", ""),
        }}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PipelineAPI] Resume failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/pipeline/{run_id}/star")
async def toggle_star(run_id: str):
    """切换星标收藏"""
    try:
        from app.framework.pipeline.checkpoint import load_manifest, update_manifest
        manifest = load_manifest(run_id)
        if not manifest:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
        starred = not manifest.get("starred", False)
        update_manifest(run_id, {"starred": starred})
        return {"success": True, "data": {"run_id": run_id, "starred": starred}}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PipelineAPI] Star toggle failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══ Patch 补跑 API ═════════════════════════════════

class PatchRequest(BaseModel):
    stock_codes: List[str]  # 待补跑股票代码
    steps: List[str] = ["valuation"]  # 补跑环节: valuation | moat | audit

@router.get("/pipeline/{run_id}/patches")
async def list_patches(run_id: str):
    """列出指定 run 的所有补跑状态"""
    from app.framework.pipeline.checkpoint import load_patches
    patches = load_patches(run_id)
    return {"success": True, "data": patches, "total": len(patches)}


@router.post("/pipeline/{run_id}/patch")
async def trigger_patch(run_id: str, req: PatchRequest):
    """触发补跑: 对指定股票的指定环节重跑 Verification

    Body: {"stock_codes": ["688072","002916"], "steps": ["valuation","moat"]}

    流程:
    1. 读取已有 step6 checkpoint
    2. 对每只股票执行 patch_verify_single (只重跑 verification)
    3. 合并回 checkpoint
    4. 重新执行 global_ranking
    5. 更新 patch_status
    """
    import json as _json
    from app.framework.pipeline.checkpoint import (
        find_checkpoint_file, save_checkpoint, add_patch, update_patch, load_manifest
    )
    from app.framework.ai.providers.deepseek import DeepSeekProvider
    from app.framework.pipeline.trace import TraceContext

    # 1. 找 step6 checkpoint
    cp_file = find_checkpoint_file(run_id, "step6_core_screening")
    if not cp_file:
        raise HTTPException(status_code=404, detail=f"Step 6 checkpoint not found for {run_id}")

    with open(cp_file, "r", encoding="utf-8") as f:
        record = _json.load(f)
    step6_output = record.get("output", {})

    manifest = load_manifest(run_id) or {}
    industry = manifest.get("industry", "") or step6_output.get("industry", "")

    # 2. 逐只补跑
    provider = DeepSeekProvider()
    screener = CoreScreeningAgent(provider=provider)
    trace = TraceContext(run_id)

    updated = []
    for code in req.stock_codes:
        patch_id = ""
        try:
            patch = add_patch(run_id, code, "step6_core_screening", "")
            patch_id = patch.get("id", "")
            update_patch(run_id, patch_id, {"status": "running"})

            result = await screener.patch_verify_single(code, step6_output, industry, trace)
            if result.get("error"):
                logger.warning(f"[Patch] {code}: {result['error']}")
                update_patch(run_id, patch_id, {"status": "failed", "error": result["error"]})
                continue

            updated.append(result)
            update_patch(run_id, patch_id, {"status": "completed"})
            logger.info(f"[Patch] {code}: verification patched")

        except Exception as e:
            logger.warning(f"[Patch] {code} failed: {e}")
            if patch_id:
                update_patch(run_id, patch_id, {"status": "failed", "error": str(e)[:200]})

    if not updated:
        return {"success": True, "data": {"run_id": run_id, "patched": 0, "updated": []}}

    # 3. 合并回 checkpoint — 更新所有候选列表
    def _replace_in_list(lst, cand):
        for i, c in enumerate(lst):
            if c.get("code") == cand.get("code"):
                lst[i] = cand
                return True
        return False

    for cand in updated:
        code = cand["code"]
        for key in ("future_strong_candidates", "watchlist", "eliminated"):
            if _replace_in_list(step6_output.get(key, []), cand):
                break

    # 4. 重新全局排名
    try:
        from app.domain.research.agents.candidate_comparator import CandidateComparator
        comparator = CandidateComparator(provider=provider)
        verified = (
            step6_output.get("future_strong_candidates", []) +
            step6_output.get("watchlist", []) +
            step6_output.get("eliminated", [])
        )
        ranking = await comparator.global_ranking(verified)
        step6_output["ranked_stocks"] = ranking.get("ranked_stocks", [])
        step6_output["runner_ups"] = ranking.get("runner_ups", [])
    except Exception as e:
        logger.warning(f"[Patch] Global ranking re-run failed: {e}")

    # 5. 保存更新后的 checkpoint (hash="patch" 区分于原版)
    save_checkpoint("step6_core_screening", run_id, "patch", step6_output, {"elapsed": 0})
    await graph_bridge.notify(run_id, "step6_core_screening", step6_output)
    trace.write("step6_core_screening_patch")

    logger.info(f"[Patch] Done: {len(updated)}/{len(req.stock_codes)} patched")
    return {"success": True, "data": {
        "run_id": run_id,
        "patched": len(updated),
        "requested": len(req.stock_codes),
        "stock_codes": [c["code"] for c in updated],
    }}


@router.delete("/pipeline/{run_id}")
async def delete_pipeline_run(run_id: str):
    """删除项目及其所有检查点文件"""
    try:
        import shutil, os
        from app.framework.pipeline.checkpoint import CHECKPOINT_DIR
        run_dir = os.path.join(CHECKPOINT_DIR, run_id)
        if not os.path.isdir(run_dir):
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
        # 同时清理关联的 research_reports
        try:
            manifest = __import__("app.framework.pipeline.checkpoint", fromlist=["load_manifest"]).load_manifest(run_id)
            industry = (manifest or {}).get("industry", "")
        except Exception:
            industry = ""
        shutil.rmtree(run_dir)
        logger.info(f"[PipelineAPI] Deleted run: {run_id}")
        return {"success": True, "data": {"run_id": run_id, "deleted": True, "industry": industry}}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PipelineAPI] Delete run failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipeline/{run_id}/checkpoint/{step}")
async def get_checkpoint_output(run_id: str, step: str):
    """读取指定 step 的检查点 output 内容"""
    try:
        import json as _json, os
        from app.framework.pipeline.checkpoint import find_checkpoint_file

        # 虚拟 Step 1: 直接读 macro_report.json
        if step == "step1_macro":
            macro_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "data", "macro_report.json")
            macro_path = os.path.abspath(macro_path)
            if not os.path.exists(macro_path):
                raise HTTPException(status_code=404, detail="Macro report not found")
            with open(macro_path, "r", encoding="utf-8") as f:
                macro = _json.load(f)
            return {"success": True, "data": {
                "run_id": run_id, "step": "step1_macro",
                "output": {
                    "generated_at": macro.get("generated_at", ""),
                    "valid_until": macro.get("valid_until", ""),
                    "generated_by": macro.get("generated_by", ""),
                    "executive_summary": macro.get("data", {}).get("executive_summary", {}),
                    "top_3_themes": macro.get("data", {}).get("top_3_themes", []),
                },
                "saved_at": macro.get("generated_at", ""),
            }}

        cp_file = find_checkpoint_file(run_id, step)
        if not cp_file:
            raise HTTPException(status_code=404, detail=f"Checkpoint not found: {run_id}/{step}")
        with open(cp_file, "r", encoding="utf-8") as f:
            record = _json.load(f)
        return {"success": True, "data": {
            "run_id": run_id, "step": step,
            "output": record.get("output", {}),
            "saved_at": record.get("saved_at"),
        }}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PipelineAPI] Get checkpoint failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class CheckpointEditRequest(BaseModel):
    output: dict  # 新的 checkpoint output 内容


@router.put("/pipeline/{run_id}/checkpoint/{step}")
async def save_checkpoint_edit(run_id: str, step: str, body: CheckpointEditRequest):
    """保存手动编辑后的 checkpoint output"""
    try:
        from app.framework.pipeline.checkpoint import update_checkpoint_output
        result = update_checkpoint_output(run_id, step, body.output)
        if not result:
            raise HTTPException(status_code=404, detail=f"Checkpoint not found: {run_id}/{step}")
        logger.info(f"[PipelineAPI] Checkpoint edited: {run_id}/{step} → {result}")
        return {"success": True, "data": {"run_id": run_id, "step": step, "saved": result}}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PipelineAPI] Checkpoint edit failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data/stock/{code}")
async def get_stock_data(code: str):
    """获取单只股票的完整投研数据"""
    market = await data_loader.load_market_data([code], days=30)
    fund = await data_loader.load_fundamentals([code])
    ind = await data_loader.load_indicators([code])
    return {
        "code": code,
        "market_data": market.get(code, []),
        "fundamentals": fund.get(code, {}),
        "indicators": ind.get(code, {}),
    }


# ═══════════════════════════════════════════
# 研报持久化
# ═══════════════════════════════════════════

@router.get("/reports")
async def list_research_reports(limit: int = 20):
    """列出历史研报 (摘要列表)"""
    return {"success": True, "data": list_reports(limit)}


@router.get("/reports/{report_id}")
async def get_research_report(report_id: str):
    """获取单篇研报完整内容"""
    report = get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return {"success": True, "data": report}


@router.post("/scrape")
async def scrape_url(url: str = None, urls: str = None):
    """抓取网页并抽取正文。传 url= 或 urls=(逗号分隔)"""
    if urls:
        url_list = [u.strip() for u in urls.split(",") if u.strip()]
        result = await data_loader.scrape_urls(url_list)
    elif url:
        result = await data_loader.scrape_url(url)
    else:
        raise HTTPException(status_code=400, detail="需要 url 或 urls 参数")
    return {"success": True, "data": result}


@router.post("/reports/{report_id}/regenerate")
async def regenerate_report_markdown(report_id: str):
    """用已存储的结构化数据重新生成完整中文 Markdown 报告。
    不改供应链扫描和审计数据, 只重跑 _synthesize_basic。
    适用于历史报告格式迁移或报告模板迭代。
    """
    report = get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

    data = report.get("data", {})
    detail = data.get("detail", {})
    hacker = detail.get("supply_chain") or data.get("supply_chain", {})
    capex = detail.get("capex", {})
    audits = detail.get("audits", [])
    prices = detail.get("prices", [])
    industry = report.get("industry", "")

    if not hacker:
        raise HTTPException(status_code=400, detail="Report has no supply_chain data, cannot regenerate")

    from app.domain.research.agents.dag_orchestrator import DAGOrchestrator
    orchestrator = DAGOrchestrator(provider=None)  # _synthesize_basic 不需要 provider
    basic = await orchestrator._synthesize_basic(industry, capex, hacker, audits, prices)

    # 更新报告
    data["cio_report"] = basic["cio_report"]
    data["top_picks"] = basic.get("top_picks", data.get("top_picks", []))
    data["final_summary"] = basic.get("final_summary", "")
    data["key_risks"] = basic.get("key_risks", [])
    data["catalysts_to_watch"] = basic.get("catalysts_to_watch", [])

    import os, json as _json
    from app.domain.research.services.report_store import REPORTS_DIR
    # 直接覆盖原文件
    filepath = os.path.join(REPORTS_DIR, f"{report_id}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        report["data"] = data
        _json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    return {"success": True, "message": f"Report {report_id} regenerated", "data": report}


@router.delete("/reports/{report_id}")
async def delete_research_report(report_id: str):
    """删除单篇研报"""
    ok = delete_report(report_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return {"success": True, "message": f"Deleted {report_id}"}


# ═══════════════════════════════════════════════════════
# StockHealthChecker — 个股全方位健康体检
# ═══════════════════════════════════════════════════════


class HealthCheckRequest(BaseModel):
    stock_code: str
    stock_name: Optional[str] = None
    industry: Optional[str] = None
    dimensions: Optional[List[str]] = None  # ["financial","technical","talent","valuation"]


@router.post("/health-check")
async def stock_health_check(req: HealthCheckRequest):
    """个股全方位健康体检 — LLM 自主工具编排

    系统提供财务指标、技术指标、网络搜索、基本面快照等工具,
    LLM 自行规划分析路径: 先查什么 → 再查什么 → 综合判断

    Args:
        stock_code: 6位股票代码
        stock_name: 股票名称（可选，自动补全）
        industry: 所属行业（可选）
        dimensions: 限定分析维度（可选，默认全维度）

    Returns:
        结构化体检报告 (四维度: 财务/技术/人才/估值), 自动保存快照
    """
    code = req.stock_code
    logger.info(f"[HealthCheck] Requested: {code} dims={req.dimensions}")

    from app.framework.ai.providers.deepseek import DeepSeekProvider
    from app.domain.research.agents.stock_health_checker import StockHealthChecker
    from app.framework.pipeline.health_check_store import save_snapshot

    try:
        provider = DeepSeekProvider()
        checker = StockHealthChecker(provider=provider)

        ctx = {
            "stock_code": code,
            "stock_name": req.stock_name or "",
            "industry": req.industry or "",
        }
        if req.dimensions and len(req.dimensions) > 0:
            ctx["dimensions"] = req.dimensions

        result = await checker.analyze(ctx=ctx)

        # 自动保存快照
        try:
            name = req.stock_name or result.get("stock_name", "")
            record_id = save_snapshot(code, name, result)
        except Exception as e:
            logger.warning(f"[HealthCheck] Snapshot save failed (non-fatal): {e}")
            record_id = None

        return {
            "success": True,
            "data": result,
            "record_id": record_id,
            "message": "Health check complete",
        }
    except Exception as e:
        logger.error(f"[HealthCheck] Failed: {code} | {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health-check/history")
async def health_check_history(stock_code: Optional[str] = None, limit: int = 50, offset: int = 0):
    """查询体检历史，可按股票代码筛选"""
    from app.framework.pipeline.health_check_store import get_history
    records, total = get_history(stock_code=stock_code, limit=limit, offset=offset)
    return {"success": True, "total": total, "records": records}


@router.get("/health-check/history/{record_id}")
async def health_check_detail(record_id: str):
    """获取单条体检结果详情"""
    from app.framework.pipeline.health_check_store import get_snapshot
    record = get_snapshot(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"success": True, "data": record}


@router.delete("/health-check/history/{record_id}")
async def health_check_delete(record_id: str):
    """删除体检记录"""
    from app.framework.pipeline.health_check_store import delete_snapshot
    ok = delete_snapshot(record_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"success": True, "message": "Record deleted"}


# ═══════════════════════════════════════════════════════
# StockAuditor — 个股审计工具 (替代旧 Step7+Step8)
# ═══════════════════════════════════════════════════════


class AuditRequest(BaseModel):
    stock_code: str
    stock_name: Optional[str] = None


@router.post("/stock-audit/{code}")
async def stock_audit_full(code: str, name: Optional[str] = Query(None)):
    """全量审计: financial + human_capital + valuation"""
    auditor = StockAuditor()
    result = await auditor.audit_full(code, name or "")
    return {"success": True, "data": result}


@router.post("/stock-audit/{code}/financial")
async def stock_audit_financial(code: str):
    """仅财务审计"""
    auditor = StockAuditor()
    result = await auditor.audit_financial(code)
    return {"success": True, "data": result}


@router.post("/stock-audit/{code}/human-capital")
async def stock_audit_human_capital(code: str, name: Optional[str] = Query(None)):
    """仅人力资本审计 (Web搜索+LLM, 较贵)"""
    auditor = StockAuditor()
    result = await auditor.audit_human_capital(code, name or "")
    return {"success": True, "data": result}


@router.post("/stock-audit/{code}/valuation")
async def stock_audit_valuation(code: str, name: Optional[str] = Query(None)):
    """仅估值定价 (LLM规划方法 + 框架计算)"""
    auditor = StockAuditor()
    result = await auditor.audit_valuation(code, name or "")
    return {"success": True, "data": result}


@router.post("/stock-audit/{code}/summary")
async def stock_audit_summary(code: str):
    """轻量审计摘要 (不跑 human capital, 供 Step 6 enrichment)"""
    auditor = StockAuditor()
    result = await auditor.audit_summary(code)
    return {"success": True, "data": result}


@router.post("/stock-audit")
async def stock_audit_json(req: AuditRequest):
    """全量审计 (JSON body)"""
    auditor = StockAuditor()
    result = await auditor.audit_full(req.stock_code, req.stock_name or "")
    return {"success": True, "data": result}
