from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.base import JobLookupError
from sqlalchemy import select
from app.core.database import async_session
from app.models.models import TaskDefinition
from app.core.logger import logger
from typing import Dict, List, Optional

class TaskScheduler:
    """V5.0 定时调度引擎 — 基于 APScheduler + TaskDefinition 注册表"""

    _instance: Optional["TaskScheduler"] = None
    _aps: AsyncIOScheduler
    _job_registry: Dict[str, dict] = {}  # code → {cron_expr, job_id}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._aps = AsyncIOScheduler(timezone="Asia/Shanghai")
            self._initialized = True

    # ── 生命周期 ──────────────────────────────

    async def start(self):
        """从 DB 加载所有已启用的定时任务并启动调度器"""
        async with async_session() as db:
            res = await db.execute(
                select(TaskDefinition).where(
                    TaskDefinition.cron_expr.isnot(None),
                    TaskDefinition.cron_expr != "",
                    TaskDefinition.is_enabled == True
                )
            )
            definitions = res.scalars().all()

        for d in definitions:
            self._schedule_one(d.code, d.cron_expr, d.name)

        self._aps.start()
        logger.info(f"[🚀] Scheduler started with {len(definitions)} cron jobs.")

    async def shutdown(self):
        self._aps.shutdown(wait=False)
        logger.info("[✅] Scheduler shut down.")

    # ── 作业管理 ──────────────────────────────

    def _schedule_one(self, code: str, cron_expr: str, name: str = ""):
        """内部：注册一个 cron 作业"""
        try:
            job = self._aps.add_job(
                func=self._fire_task,
                trigger=CronTrigger.from_crontab(cron_expr, timezone="Asia/Shanghai"),
                args=(code,),
                id=f"cron_{code}",
                name=name or code,
                replace_existing=True
            )
            self._job_registry[code] = {"cron_expr": cron_expr, "job_id": job.id}
            logger.info(f"[+] Scheduled: {code} → {cron_expr}")
        except Exception as e:
            logger.error(f"[❌] Failed to schedule {code} ({cron_expr}): {e}")

    def _remove_one(self, code: str):
        """内部：移除一个 cron 作业"""
        job_id = f"cron_{code}"
        try:
            self._aps.remove_job(job_id)
        except JobLookupError:
            pass
        self._job_registry.pop(code, None)
        logger.info(f"[-] Removed schedule: {code}")

    async def _fire_task(self, code: str):
        """定时触发回调 — 调用 TaskEngine 执行业务"""
        from app.core.task_manager import task_manager
        logger.info(f"[⏰] Cron fired: {code}")
        try:
            await task_manager.run_task(code)
        except Exception as e:
            logger.error(f"[❌] Cron task {code} failed: {e}")

    # ── 对外接口 ──────────────────────────────

    def list_jobs(self) -> List[dict]:
        """获取所有已注册的定时作业及其下次运行时间"""
        jobs = []
        for code, meta in self._job_registry.items():
            aps_job = self._aps.get_job(meta["job_id"])
            jobs.append({
                "task_code": code,
                "cron_expr": meta["cron_expr"],
                "next_run_time": aps_job.next_run_time.isoformat() if aps_job and aps_job.next_run_time else None,
                "job_id": meta["job_id"]
            })
        return jobs

    async def refresh_job(self, code: str):
        """根据 DB 定义刷新单个作业 (启用/禁用/改 cron)"""
        async with async_session() as db:
            res = await db.execute(select(TaskDefinition).where(TaskDefinition.code == code))
            d = res.scalars().first()

        if not d:
            self._remove_one(code)
            return

        if d.is_enabled and d.cron_expr:
            self._schedule_one(d.code, d.cron_expr, d.name)
        else:
            self._remove_one(d.code)

    async def refresh_all(self):
        """重新加载所有作业"""
        for code in list(self._job_registry.keys()):
            self._remove_one(code)
        await self.start()


# 全局单例
scheduler = TaskScheduler()
