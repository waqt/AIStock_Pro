from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import select, update, delete, desc
from app.core.database import async_session
from app.models.models import TaskDefinition, TaskExecution
from app.core.task_manager import task_manager
from app.core.logger import logger
from pydantic import BaseModel

router = APIRouter(prefix="/api/system/tasks", tags=["任务管理"])

# --- Request Models ---
class TaskRunRequest(BaseModel):
    task_code: str
    params: Optional[Dict[str, Any]] = {}

class TaskUpdateRequest(BaseModel):
    cron_expr: Optional[str] = None
    is_enabled: Optional[bool] = None

# --- Endpoints ---

@router.get("/definitions")
async def get_task_definitions():
    """获取所有已注册的任务定义"""
    async with async_session() as db:
        res = await db.execute(select(TaskDefinition))
        return res.scalars().all()

@router.put("/definitions/{code}")
async def update_task_definition(code: str, req: TaskUpdateRequest):
    """修改任务计划 (如 CRON 表达式)"""
    async with async_session() as db:
        res = await db.execute(select(TaskDefinition).where(TaskDefinition.code == code))
        defn = res.scalars().first()
        if not defn:
            raise HTTPException(status_code=404, detail="Task definition not found")
        
        if req.cron_expr is not None: defn.cron_expr = req.cron_expr
        if req.is_enabled is not None: defn.is_enabled = req.is_enabled
        
        await db.commit()
        return {"status": "success"}

@router.get("/executions/active")
async def get_active_executions():
    """获取当前活跃任务 (RUNNING, PENDING, STOPPING)"""
    async with async_session() as db:
        res = await db.execute(
            select(TaskExecution)
            .where(TaskExecution.status.in_(["RUNNING", "PENDING", "STOPPING"]))
            .order_by(desc(TaskExecution.start_time))
        )
        return res.scalars().all()

@router.get("/executions/history")
async def get_execution_history(
    page: int = 1, 
    limit: int = 20, 
    task_code: Optional[str] = None
):
    """分页获取历史记录"""
    async with async_session() as db:
        stmt = select(TaskExecution).where(TaskExecution.status.notin_(["RUNNING", "PENDING", "STOPPING"]))
        if task_code:
            stmt = stmt.where(TaskExecution.task_code == task_code)
        
        stmt = stmt.order_by(desc(TaskExecution.start_time)).offset((page-1)*limit).limit(limit)
        res = await db.execute(stmt)
        return res.scalars().all()

@router.post("/executions")
async def trigger_task(req: TaskRunRequest):
    """手动触发一个任务"""
    try:
        exec_id = await task_manager.run_task(req.task_code, req.params)
        return {"id": exec_id, "status": "PENDING"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Trigger failed: {str(e)}")

@router.delete("/executions/{exec_id}")
async def stop_task_execution(exec_id: str):
    """终止正在运行的任务"""
    success = await task_manager.stop_task(exec_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not running or already finished")
    return {"status": "stopping"}

@router.delete("/history")
async def clear_history(
    days_ago: Optional[int] = Query(None), 
    ids: Optional[List[str]] = Query(None)
):
    """批量清理历史记录"""
    async with async_session() as db:
        stmt = delete(TaskExecution).where(TaskExecution.status.notin_(["RUNNING", "PENDING", "STOPPING"]))
        
        if ids:
            stmt = stmt.where(TaskExecution.id.in_(ids))
        elif days_ago is not None:
            cutoff = datetime.now() - timedelta(days=days_ago)
            stmt = stmt.where(TaskExecution.start_time < cutoff)
        else:
            raise HTTPException(status_code=400, detail="Must provide ids or days_ago")
            
        await db.execute(stmt)
        await db.commit()
        return {"status": "cleared"}
