from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from datetime import datetime

from app.core.config import settings
from app.core.database import engine, async_session, Base
from app.core.logger import logger
from app.models.models import TaskExecution
from sqlalchemy import update, select
from app.core.task_manager import task_manager
from app.core.scheduler import scheduler
import app.quant.tasks # 显式导入以触发装饰器

# 导入领域路由器
from app.api import tasks, data, positions, import_api

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AIStock Pro - Clean Architecture (DDD)"
)

# 1. 中间件与跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. 注册业务路由 (优先级最高)
app.include_router(tasks.router)
app.include_router(data.router)
app.include_router(positions.router)
app.include_router(import_api.router)

# 3. 挂载前端静态资源 (作为兜底)
frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="static")
    logger.info(f"[✅] Frontend mounted at root from: {frontend_path}")

@app.on_event("startup")
async def startup_event():
    logger.info("[🚀] AIStock_Pro V5.0 Engine Initializing...")
    
    # 1. 数据库表验证
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("[✅] Database schema verified.")
    except Exception as e:
        logger.error(f"[❌] Schema verification failed: {e}")

    # 2. 任务注册同步 (V5.0 核心)
    try:
        await task_manager.sync_definitions_to_db()
    except Exception as e:
        logger.error(f"[❌] Task Registration failed: {e}")

    # 3. 启动定时调度器 (V5.0 APScheduler)
    try:
        await scheduler.start()
    except Exception as e:
        logger.error(f"[❌] Scheduler start failed: {e}")

    # 4. 启动自愈 (按照用户要求标记为 FAILED)
    try:
        async with async_session() as db:
            res = await db.execute(
                select(TaskExecution).where(TaskExecution.status.in_(["RUNNING", "PENDING", "STOPPING"]))
            )
            zombies = res.scalars().all()
            
            if zombies:
                logger.warning(f"[🧹] Found {len(zombies)} zombie tasks. Marking as FAILED...")
                await db.execute(
                    update(TaskExecution).where(TaskExecution.status.in_(["RUNNING", "PENDING", "STOPPING"])).values(
                        status="FAILED", 
                        result_msg="[系统自愈] 服务器意外重启，任务强制中断",
                        end_time=datetime.now(),
                        updated_at=datetime.now()
                    )
                )
                await db.commit()
                logger.info("[✅] Zombie tasks reset to FAILED.")
    except Exception as e:
        logger.error(f"[❌] Startup self-healing failed: {e}")

    logger.info("[✅] System startup sequence complete.")

@app.get("/")
async def root():
    """欢迎页面 (现在由 StaticFiles 兜底，此接口仅作为元数据展示)"""
    return {"message": "AIStock Pro Engine V5.1 Running"}

@app.on_event("shutdown")
async def shutdown_event():
    await scheduler.shutdown()

@app.get("/health")
async def health_check():
    return {"status": "healthy", "architecture": "DDD / Clean V5.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
