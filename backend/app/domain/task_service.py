import uuid
from datetime import datetime
from sqlalchemy import update, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import AnalysisTask
from app.core.logger import logger

class TaskService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_task(self, task_type: str) -> str:
        """创建一个新的后台任务记录"""
        task_id = str(uuid.uuid4())
        new_task = AnalysisTask(
            id=task_id,
            task_type=task_type,
            status="PENDING",
            progress=0,
            current_step="Initializing task..."
        )
        self.db.add(new_task)
        await self.db.commit()
        logger.info(f"Task created: {task_id} [{task_type}]")
        return task_id

    async def update_progress(self, task_id: str, progress: int, step_desc: str):
        """更新任务进度与步骤描述"""
        query = (
            update(AnalysisTask)
            .where(AnalysisTask.id == task_id)
            .values(
                progress=progress, 
                current_step=step_desc,
                status="RUNNING" if progress < 100 else "SUCCESS"
            )
        )
        await self.db.execute(query)
        await self.db.commit()
        logger.debug(f"Task {task_id} progress: {progress}% - {step_desc}")

    async def mark_failed(self, task_id: str, error_msg: str):
        """将任务标记为失败"""
        query = (
            update(AnalysisTask)
            .where(AnalysisTask.id == task_id)
            .values(status="FAILED", error_msg=error_msg)
        )
        await self.db.execute(query)
        await self.db.commit()
        logger.error(f"Task {task_id} failed: {error_msg}")

    async def get_task_status(self, task_id: str) -> Optional[AnalysisTask]:
        """获取任务当前状态"""
        result = await self.db.execute(select(AnalysisTask).where(AnalysisTask.id == task_id))
        return result.scalars().first()
