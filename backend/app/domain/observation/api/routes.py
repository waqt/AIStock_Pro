"""观察框架 API — 查询/管理/提取观察事件"""
import os, json
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from app.framework.pipeline.observation_store import ObservationStore
from app.framework.pipeline.checkpoint import CHECKPOINT_DIR
from app.domain.observation.services.extractor import STEP_EXTRACTORS
from app.framework.logger import logger

router = APIRouter(prefix="/api", tags=["observations"])


# ═══ Schemas ═══════════════════════════════════

class StatusUpdateRequest(BaseModel):
    status: str
    notes: Optional[str] = None
    check_count: Optional[int] = None


class ObservationResponse(BaseModel):
    id: str
    source_step: str
    level: str
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    direction: Optional[str] = None
    confidence: Optional[str] = None
    expected_date: Optional[str] = None
    window_description: Optional[str] = None
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    monitor_metric: Optional[str] = None
    trigger_threshold: Optional[str] = None
    data_source_hint: Optional[str] = None
    search_query: Optional[str] = None
    related_stock_code: Optional[str] = None
    parent_id: Optional[str] = None
    industry: Optional[str] = None
    status: str
    check_count: int
    notes: Optional[str] = None
    created_at: str
    updated_at: str


class ObservationListResponse(BaseModel):
    total: int
    observations: List[ObservationResponse]


class CountResponse(BaseModel):
    total: int
    active: int
    monitoring: int
    triggered: int
    expired: int


# ═══ 工具函数 ═══════════════════════════════════

def _parse_step_from_filename(fname: str) -> str:
    """从 checkpoint 文件名中提取 step 名称，如 step2_gatekeeper_xxx.json → step2"""
    name = fname.replace(".json", "").replace(".trace.txt", "")
    parts = name.split("_")
    # 处理形如 "step2_gatekeeper_a3b4c5" 的文件名
    step_candidates = [p for p in parts if p.startswith("step")]
    return step_candidates[0] if step_candidates else ""


# ═══ Endpoints ═══════════════════════════════════

@router.get("/observations", response_model=ObservationListResponse)
async def list_observations(
    run_id: Optional[str] = Query(None, description="来源 run_id (模糊匹配 source_info)"),
    status: Optional[str] = Query(None, description="筛选: draft/active/monitoring/triggered/confirmed/invalidated/expired"),
    level: Optional[str] = Query(None, description="筛选: industry/supply_chain_node/stock/cross_industry"),
    source_step: Optional[str] = Query(None, description="筛选来源 Step: step2~step6"),
    category: Optional[str] = Query(None, description="分类筛选 (支持前缀, 如 供需类)"),
    stock_code: Optional[str] = Query(None, alias="stock_code", description="关联股票"),
    industry: Optional[str] = Query(None, description="所属行业"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """查询观察事件列表 (多条件 AND)"""
    logger.info(f"[ObservationAPI] list: status={status}, level={level}, step={source_step}, industry={industry}")
    store = ObservationStore()
    results = store.list(
        run_id=run_id, status=status, level=level,
        source_step=source_step, category=category,
        stock_code=stock_code, industry=industry,
        limit=limit, offset=offset,
    )
    return ObservationListResponse(total=len(results), observations=[ObservationResponse(**r) for r in results])


@router.get("/observations/{obs_id}", response_model=ObservationResponse)
async def get_observation(obs_id: str):
    """获取单条观察详情"""
    logger.info(f"[ObservationAPI] get: {obs_id}")
    store = ObservationStore()
    obs = store.get(obs_id)
    if not obs:
        raise HTTPException(status_code=404, detail=f"Observation {obs_id} not found")
    return ObservationResponse(**obs)


@router.patch("/observations/{obs_id}/status")
async def update_observation_status(obs_id: str, body: StatusUpdateRequest):
    """更新观察状态 (自动设置对应时间戳)"""
    logger.info(f"[ObservationAPI] update_status: {obs_id} → {body.status}")
    store = ObservationStore()
    existing = store.get(obs_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Observation {obs_id} not found")
    extra = {}
    if body.notes is not None:
        extra['notes'] = body.notes
    if body.check_count is not None:
        extra['check_count'] = body.check_count
    store.update_status(obs_id, body.status, **extra)
    return {"success": True, "id": obs_id, "new_status": body.status}


@router.get("/observations/stocks/{stock_code}", response_model=ObservationListResponse)
async def get_stock_observations(stock_code: str, status: Optional[str] = Query(None)):
    """特定股票的所有观察"""
    logger.info(f"[ObservationAPI] by_stock: {stock_code}, status={status}")
    store = ObservationStore()
    results = store.get_by_stock(stock_code, status=status)
    return ObservationListResponse(total=len(results), observations=[ObservationResponse(**r) for r in results])


@router.get("/observations/industries/{industry_name}", response_model=ObservationListResponse)
async def get_industry_observations(industry_name: str, status: Optional[str] = Query(None)):
    """特定行业的所有观察"""
    logger.info(f"[ObservationAPI] by_industry: {industry_name}, status={status}")
    store = ObservationStore()
    results = store.get_by_industry(industry_name, status=status)
    return ObservationListResponse(total=len(results), observations=[ObservationResponse(**r) for r in results])


@router.get("/observations/stats/counts", response_model=CountResponse)
async def get_observation_counts():
    """观察事件统计"""
    store = ObservationStore()
    return CountResponse(
        total=store.count(),
        active=store.count(status='active'),
        monitoring=store.count(status='monitoring'),
        triggered=store.count(status='triggered'),
        expired=store.count(status='expired'),
    )


# ═══ 提取/入库 端点 ═════════════════════════════

@router.get("/observations/extract-preview/{run_id}")
async def extract_preview(run_id: str):
    """预览从 Pipeline run 提取的观察事件 (不写入 DB)"""
    logger.info(f"[ObservationAPI] extract-preview: {run_id}")

    run_dir = os.path.join(CHECKPOINT_DIR, run_id)
    if not os.path.isdir(run_dir):
        raise HTTPException(status_code=404, detail=f"Run directory not found: {run_id}")

    # 扫描 checkpoint 文件
    checkpoint_files = []
    for fname in sorted(os.listdir(run_dir)):
        if not fname.endswith(".json") or ".trace" in fname:
            continue
        step = _parse_step_from_filename(fname)
        if not step or step not in STEP_EXTRACTORS:
            continue
        checkpoint_files.append({"step": step, "fname": fname, "path": os.path.join(run_dir, fname)})

    if not checkpoint_files:
        return {"run_id": run_id, "total": 0, "groups": [], "observations": []}

    # 执行提取
    store = ObservationStore()
    existing_set = store.find_ids_by_run(run_id)  # (title, step, industry) 三元组

    all_observations = []
    groups = []
    for cf in checkpoint_files:
        try:
            with open(cf["path"], "r", encoding="utf-8") as f:
                checkpoint = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"[ObservationAPI] Skipping {cf['fname']}: {e}")
            continue

        output = checkpoint.get("output", {})
        if not output:
            continue

        saved_at = checkpoint.get("saved_at", datetime.now().isoformat())
        extractor = STEP_EXTRACTORS[cf["step"]]

        try:
            extracted = extractor(output, run_id, saved_at)
        except Exception as e:
            logger.warning(f"[ObservationAPI] Extract failed {run_id}/{cf['step']}: {e}")
            continue

        # 标记已存在
        new_count = 0
        existing_count = 0
        for obs in extracted:
            key = (obs.get("title", ""), obs.get("source_step", ""), obs.get("industry", "") or "")
            obs["already_saved"] = key in existing_set
            if obs["already_saved"]:
                existing_count += 1
            else:
                new_count += 1

        all_observations.extend(extracted)
        groups.append({
            "step": cf["step"],
            "total": len(extracted),
            "new": new_count,
            "existing": existing_count,
            "fname": cf["fname"],
        })

    return {
        "run_id": run_id,
        "total": len(all_observations),
        "groups": groups,
        "observations": all_observations,
    }


class BatchSaveRequest(BaseModel):
    observations: List[dict] = Body(..., description="待入库的观察事件列表")


@router.post("/observations/batch-save")
async def batch_save_observations(body: BatchSaveRequest):
    """批量入库用户筛选后的观察事件"""
    logger.info(f"[ObservationAPI] batch-save: {len(body.observations)} observations")

    if not body.observations:
        return {"success": True, "saved": 0, "ids": []}

    # 规范化: 确保每个 observation 有必要的字段
    store = ObservationStore()
    now = datetime.now().isoformat(timespec="seconds")
    to_save = []
    for obs in body.observations:
        row = dict(obs)
        # 移除 UI 临时字段
        row.pop("already_saved", None)
        row.pop("selected", None)
        if not row.get("created_at"):
            row["created_at"] = now
        row["updated_at"] = now
        to_save.append(row)

    ids = store.save_batch(to_save)
    logger.info(f"[ObservationAPI] batch-save done: {len(ids)} saved")
    return {"success": True, "saved": len(ids), "ids": ids}
