from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.task_manager import task_manager
from app.core.logger import logger

router = APIRouter(prefix="/api/data", tags=["数据同步"])

class SyncRequest(BaseModel):
    type: str = "AUTO"

@router.post("/sync/daily/auto")
async def trigger_auto_sync(request: SyncRequest):
    """
    通过 V5.0 任务引擎调起同步逻辑
    """
    try:
        # 将请求类型透传给注册好的 sync_market 任务
        exec_id = await task_manager.run_task("sync_market", {"mode": request.type})
        logger.info(f"[🚀] Manual sync triggered via API. ExecID: {exec_id}")
        return {"message": "任务已加入执行队列", "task_id": exec_id}
    except Exception as e:
        logger.error(f"Failed to trigger sync: {e}")
        raise HTTPException(status_code=500, detail=str(e))
