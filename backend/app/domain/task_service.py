from datetime import datetime
from sqlalchemy import update, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import TaskExecution
from app.core.logger import logger

class TaskService:
    """领域层任务服务 (V5.0 适配版) — 当前未被引用，保留作为 domain facade"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def update_progress(self, exec_id: str, progress: int, msg: str):
        await self.db.execute(
            update(TaskExecution)
            .where(TaskExecution.id == exec_id)
            .values(progress=progress, result_msg=msg, updated_at=datetime.now())
        )
        await self.db.commit()

    async def mark_failed(self, exec_id: str, error_msg: str):
        await self.db.execute(
            update(TaskExecution)
            .where(TaskExecution.id == exec_id)
            .values(status="FAILED", result_msg=error_msg, end_time=datetime.now())
        )
        await self.db.commit()
        logger.error(f"[❌] Execution {exec_id} failed: {error_msg}")

    async def get_execution(self, exec_id: str):
        result = await self.db.execute(select(TaskExecution).where(TaskExecution.id == exec_id))
        return result.scalars().first()
