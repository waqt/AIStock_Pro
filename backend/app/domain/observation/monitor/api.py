"""监控模块 API — 监控计划 + 信号事件 CRUD + 生成 + 执行"""
import os, json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel

from app.framework.logger import logger
from app.framework.pipeline.checkpoint import CHECKPOINT_DIR
from app.domain.observation.monitor.store import MonitorStore
from app.domain.observation.monitor.generator import generate_monitor_plans
from app.domain.observation.monitor.engine import MonitorEngine
from app.domain.observation.services.extractor import STEP_EXTRACTORS
from app.framework.pipeline.observation_store import ObservationStore

router = APIRouter(prefix="/api", tags=["monitor"])


# ═══ Schemas ═══════════════════════════════════

class PlanCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    source_report_id: Optional[str] = None
    source_run_id: Optional[str] = None
    source_step: Optional[str] = None
    linked_observation_id: Optional[str] = None
    source_summary: Optional[str] = None
    level: str = "stock"
    target_industry: Optional[str] = None
    target_stock_code: Optional[str] = None
    target_stock_name: Optional[str] = None
    search_config: str = "[]"
    trigger_instruction: Optional[str] = None
    positive_keywords: str = "[]"
    negative_keywords: str = "[]"
    min_match_count: int = 1
    cascade_to_stocks: str = "[]"
    signal_direction: str = "buy"
    signal_strength: str = "medium"
    cooldown_days: int = 30
    check_interval_hours: int = 168
    notes: Optional[str] = None


class PlanUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    search_config: Optional[str] = None
    trigger_instruction: Optional[str] = None
    positive_keywords: Optional[str] = None
    negative_keywords: Optional[str] = None
    min_match_count: Optional[int] = None
    cascade_to_stocks: Optional[str] = None
    signal_direction: Optional[str] = None
    signal_strength: Optional[str] = None
    cooldown_days: Optional[int] = None
    check_interval_hours: Optional[int] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class PlanResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    source_report_id: Optional[str] = None
    source_run_id: Optional[str] = None
    source_step: Optional[str] = None
    linked_observation_id: Optional[str] = None
    level: str
    target_industry: Optional[str] = None
    target_stock_code: Optional[str] = None
    target_stock_name: Optional[str] = None
    search_config: str
    trigger_instruction: Optional[str] = None
    signal_direction: str
    signal_strength: str
    cooldown_days: int
    check_interval_hours: int
    status: str
    total_checks: int
    last_check_at: Optional[str] = None
    last_triggered_at: Optional[str] = None
    created_at: str
    updated_at: str
    notes: Optional[str] = None


class PlanListResponse(BaseModel):
    total: int
    plans: List[PlanResponse]


class SignalResponse(BaseModel):
    id: str
    plan_id: str
    plan_name: Optional[str] = None
    triggered_at: str
    signal_direction: str
    signal_strength: str
    confidence: str
    title: str
    description: Optional[str] = None
    evidence: str
    related_stock_code: Optional[str] = None
    related_stock_name: Optional[str] = None
    target_industry: Optional[str] = None
    status: str
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    acted_at: Optional[str] = None
    notes: Optional[str] = None
    created_at: str


class SignalListResponse(BaseModel):
    total: int
    signals: List[SignalResponse]


class SignalUpdateRequest(BaseModel):
    status: str
    notes: Optional[str] = None
    reviewed_by: Optional[str] = None


class GenerateRequest(BaseModel):
    report_id: str
    run_id: Optional[str] = None


class GenerateResponse(BaseModel):
    success: bool
    plans: List[dict] = []
    message: str = ""


# ═══ 监控计划 API ═══════════════════════════

@router.get("/monitor/plans", response_model=PlanListResponse)
async def list_plans(
    status: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    stock_code: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """列出监控计划"""
    logger.info(f"[MonitorAPI] list_plans: status={status}, level={level}")
    store = MonitorStore()
    plans = store.list_plans(
        status=status, level=level,
        stock_code=stock_code, industry=industry,
        limit=limit, offset=offset,
    )
    return PlanListResponse(
        total=len(plans),
        plans=[PlanResponse(**p) for p in plans],
    )


@router.get("/monitor/plans/{plan_id}", response_model=PlanResponse)
async def get_plan(plan_id: str):
    """获取单个监控计划详情"""
    store = MonitorStore()
    plan = store.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    return PlanResponse(**plan)


@router.post("/monitor/plans")
async def create_plan(body: PlanCreateRequest):
    """创建监控计划"""
    logger.info(f"[MonitorAPI] create_plan: {body.name}")
    store = MonitorStore()
    plan = body.model_dump()
    if not plan.get('created_at'):
        plan['created_at'] = datetime.now().isoformat()
    plan_id = store.save_plan(plan)
    return {"success": True, "id": plan_id}


@router.put("/monitor/plans/{plan_id}")
async def update_plan(plan_id: str, body: PlanUpdateRequest):
    """更新监控计划"""
    logger.info(f"[MonitorAPI] update_plan: {plan_id}")
    store = MonitorStore()
    existing = store.get_plan(plan_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")

    update_data = body.model_dump(exclude_unset=True)
    if update_data.get('status'):
        store.update_plan_status(plan_id, update_data.pop('status'))
    if update_data:
        merged = {**existing, **update_data, 'updated_at': datetime.now().isoformat()}
        store.save_plan(merged)

    return {"success": True, "id": plan_id}


@router.patch("/monitor/plans/{plan_id}/status")
async def update_plan_status(plan_id: str, status: str = Body(..., embed=True)):
    """更新监控计划状态"""
    logger.info(f"[MonitorAPI] update_plan_status: {plan_id} → {status}")
    store = MonitorStore()
    existing = store.get_plan(plan_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    store.update_plan_status(plan_id, status)
    return {"success": True, "id": plan_id, "status": status}


@router.delete("/monitor/plans/{plan_id}")
async def delete_plan(plan_id: str):
    """删除监控计划 (级联删除关联信号)"""
    logger.info(f"[MonitorAPI] delete_plan: {plan_id}")
    store = MonitorStore()
    store.delete_plan(plan_id)
    return {"success": True}


# ═══ 信号事件 API ═══════════════════════════

@router.get("/monitor/signals", response_model=SignalListResponse)
async def list_signals(
    plan_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    stock_code: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """列出信号事件"""
    logger.info(f"[MonitorAPI] list_signals: status={status}, direction={direction}")
    store = MonitorStore()
    signals = store.list_signals(
        plan_id=plan_id, status=status,
        stock_code=stock_code, industry=industry,
        direction=direction, limit=limit, offset=offset,
    )
    return SignalListResponse(
        total=len(signals),
        signals=[SignalResponse(**s) for s in signals],
    )


@router.get("/monitor/signals/{signal_id}", response_model=SignalResponse)
async def get_signal(signal_id: str):
    """获取单个信号事件详情"""
    store = MonitorStore()
    signal = store.get_signal(signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail=f"Signal {signal_id} not found")
    return SignalResponse(**signal)


@router.patch("/monitor/signals/{signal_id}/status")
async def update_signal_status(signal_id: str, body: SignalUpdateRequest):
    """更新信号状态 (pending_review → confirmed/dismissed)"""
    logger.info(f"[MonitorAPI] update_signal_status: {signal_id} → {body.status}")
    store = MonitorStore()
    existing = store.get_signal(signal_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Signal {signal_id} not found")
    extra = {}
    if body.notes:
        extra['notes'] = body.notes
    if body.reviewed_by:
        extra['reviewed_by'] = body.reviewed_by
    store.update_signal_status(signal_id, body.status, **extra)
    return {"success": True, "id": signal_id, "status": body.status}


# ═══ 生成和执行 API ═══════════════════════

@router.post("/monitor/generate", response_model=GenerateResponse)
async def generate_plans(body: GenerateRequest):
    """LLM 辅助从研报生成监控计划建议

    读取研报 JSON + 已有观察事件 → LLM 生成监控计划建议
    """
    report_id = body.report_id
    run_id = body.run_id or ""

    logger.info(f"[MonitorAPI] generate_plans: report_id={report_id}")

    # 1. 找研报文件
    reports_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'data', 'research_reports')
    report_path = os.path.join(reports_dir, report_id)
    if not report_id.endswith('.json'):
        report_path += '.json'

    if not os.path.exists(report_path):
        # 尝试通过 report_store 获取
        from app.domain.research.services.report_store import get_report
        report = get_report(report_id)
        if not report:
            raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    else:
        with open(report_path, 'r', encoding='utf-8') as f:
            report = json.load(f)

    report_data = report.get('data', report)

    # 2. 获取已有观察 (如果 run_id 有值)
    observations = []
    if run_id:
        obs_store = ObservationStore()
        raw = obs_store.list(run_id=run_id)
        observations = [dict(r) for r in raw] if raw else []
    else:
        # 尝试从报告 ID 推导 run_id
        pass

    # 3. LLM 生成
    plans = await generate_monitor_plans(
        report_data=report_data,
        observations=observations,
        report_id=report_id,
        run_id=run_id,
    )

    return GenerateResponse(
        success=True,
        plans=plans,
        message=f"Generated {len(plans)} plan proposals",
    )


@router.post("/monitor/execute")
async def run_monitor_check(plan_id: Optional[str] = Body(None, embed=True)):
    """手动触发一次监控检查

    Args:
        plan_id: 指定计划则只检查单个, 为空则检查全部到期的
    """
    logger.info(f"[MonitorAPI] execute: plan_id={plan_id}")
    engine = MonitorEngine()
    if plan_id:
        result = await engine.check_plan(plan_id)
        return {
            "success": True,
            "checked": 1,
            "triggered": 1 if result else 0,
            "signal": result,
        }
    else:
        stats = await engine.run_once()
        return {
            "success": True,
            **stats,
        }


@router.get("/monitor/stats/counts")
async def get_monitor_stats():
    """监控统计"""
    store = MonitorStore()
    return {
        "plans": {
            "total": store.count_plans(),
            "active": store.count_plans(status='active'),
            "draft": store.count_plans(status='draft'),
        },
        "signals": {
            "total": store.count_signals(),
            "pending_review": store.count_signals(status='pending_review'),
            "confirmed": store.count_signals(status='confirmed'),
            "dismissed": store.count_signals(status='dismissed'),
            "buy": store.count_signals(direction='buy'),
            "sell": store.count_signals(direction='sell'),
        },
    }
