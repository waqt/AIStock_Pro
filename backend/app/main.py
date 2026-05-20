from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import os, time
from datetime import datetime

from app.framework.config import settings
from app.framework.database.session import engine, async_session, Base
from app.framework.logger import logger
from app.models.models import TaskExecution
from sqlalchemy import update, select
from app.framework.tasks.engine import task_manager
from app.framework.tasks.scheduler import scheduler
import app.quant.tasks # 显式导入以触发装饰器

# 导入领域路由器
from app.api import tasks, data, positions, import_api
from app.domain.research.api.routes import router as research_router
from app.domain.quant.api.indicators import router as quant_indicator_router
from app.domain.quant.api.strategies import router as quant_strategy_router
from app.domain.quant.api.decision import router as quant_decision_router

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI 量化分析与投研系统 — A股+港股, OCR导入, 多源行情, 技术指标, 任务引擎, 智能体架构",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "任务管理", "description": "TaskEngine V5.0 — 注册/调度/并发/强杀/定时"},
        {"name": "数据管理", "description": "多源行情同步, 健康检查, 指标, 汇率, 估值"},
        {"name": "Positions", "description": "持仓CRUD, 账户资产摘要"},
        {"name": "AI 导入", "description": "截图OCR (豆包→DeepSeek→Gemini), Excel, 文本解析"},
    ]
)

# ═══ 中间件 ═══════════════════════════════════

# 1. 请求日志中间件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    dt = (time.time() - t0) * 1000
    # 跳过静态文件和健康检查的日志
    if not request.url.path.startswith("/health") and not request.url.path.endswith((".js", ".css", ".html", ".ico", ".png")):
        logger.info(f"[HTTP] {request.method} {request.url.path} → {response.status_code} ({dt:.0f}ms)")
    return response

# 2. 全局异常处理器
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"[HTTP] Unhandled error on {request.method} {request.url.path}: {type(exc).__name__}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {type(exc).__name__}"},
    )

# 3. CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══ 路由注册 ═════════════════════════════════

app.include_router(tasks.router)
app.include_router(data.router)
app.include_router(positions.router)
app.include_router(import_api.router)
app.include_router(research_router)
app.include_router(quant_indicator_router)
app.include_router(quant_strategy_router)
app.include_router(quant_decision_router)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "architecture": "DDD / Clean V5.0"}


@app.get("/")
async def root():
    return {"message": "AIStock Pro Engine V5.1 Running"}


# ═══ 生命周期 ═════════════════════════════════

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

    # 2. DB连接验证
    try:
        async with async_session() as db:
            await db.execute(select(1))
        logger.info("[✅] Database connection verified.")
    except Exception as e:
        logger.error(f"[❌] Database connection failed: {e}")

    # 3. AI API Key 验证
    if settings.DEEPSEEK_API_KEY:
        logger.info(f"[✅] DeepSeek API configured (flash={settings.DEEPSEEK_FLASH_MODEL}, pro={settings.DEEPSEEK_PRO_MODEL}, thinking={settings.DEEPSEEK_THINKING})")
    else:
        logger.warning("[⚠️] No DeepSeek API key configured — AI features disabled")
    if settings.DOUBAO_API_KEY:
        logger.info(f"[✅] Doubao API configured ({settings.DOUBAO_MODEL})")
    if settings.BRAVE_API_KEY:
        logger.info("[✅] Brave Search API configured")

    # 4. 任务注册同步
    try:
        await task_manager.sync_definitions_to_db()
    except Exception as e:
        logger.error(f"[❌] Task Registration failed: {e}")

    # 5. 启动定时调度器
    try:
        await scheduler.start()
    except Exception as e:
        logger.error(f"[❌] Scheduler start failed: {e}")

    # 6. 启动自愈 (Zombie任务标记)
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


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("[🛑] System shutting down...")
    await scheduler.shutdown()
    await engine.dispose()
    logger.info("[✅] Shutdown complete.")


# ═══ 静态文件挂载 ═════════════════════════════

frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="static")
    logger.info(f"[✅] Frontend mounted at root from: {frontend_path}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
