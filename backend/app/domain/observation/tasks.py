"""观察框架 — 定时任务"""
from app.framework.tasks.engine import task_manager
from app.framework.logger import logger


@task_manager.register("monitor_check", "监控检查", "遍历所有活跃监控计划, 检查是否触发")
async def monitor_check_task():
    """定时检查所有活跃监控计划"""
    from app.domain.observation.monitor.engine import MonitorEngine
    engine = MonitorEngine()
    stats = await engine.run_once()
    logger.info(f"[MonitorTask] Check complete: {stats}")
    return stats
