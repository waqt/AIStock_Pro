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
import app.quant.tasks # 显式导入以触发装饰器

# 导入领域路由器
from app.api import tasks, data, positions

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

# 2. 挂载前端静态资源
frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")
    logger.info(f"[✅] Frontend mounted at: {frontend_path}")

# 3. 注册业务路由
app.include_router(tasks.router)
app.include_router(data.router)
app.include_router(positions.router)

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

    # 3. 启动自愈 (按照用户要求标记为 FAILED)
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

from fastapi.responses import RedirectResponse

@app.get("/")
async def root():
    """便捷重定向到前端主页"""
    return RedirectResponse(url="/static/index.html")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "architecture": "DDD / Clean V5.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
