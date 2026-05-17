import asyncio
import uuid
import os
import inspect
from datetime import datetime
from typing import Dict, Any, Callable, Optional
from sqlalchemy import update, select, delete
from app.framework.database.session import async_session
from app.models.models import TaskDefinition, TaskExecution
from app.framework.logger import logger

class TaskEngine:
    """
    AIStock Pro 任务调度引擎 V5.0 (工业级内核)
    支持：注册装饰器、并发管控(Semaphore)、强杀信号、结果持久化
    """

    _registry: Dict[str, Callable] = {}
    _running_handles: Dict[str, asyncio.Task] = {}
    _semaphore = asyncio.Semaphore(3)

    @classmethod
    def register(cls, code: str, name: str, description: str = ""):
        def decorator(func: Callable):
            cls._registry[code] = func
            func._task_meta = {
                "code": code,
                "name": name,
                "description": description,
                "module_path": f"{func.__module__}.{func.__name__}"
            }
            return func
        return decorator

    @classmethod
    async def sync_definitions_to_db(cls):
        async with async_session() as db:
            for code, func in cls._registry.items():
                meta = getattr(func, "_task_meta", {})
                res = await db.execute(select(TaskDefinition).where(TaskDefinition.code == code))
                defn = res.scalars().first()
                if not defn:
                    db.add(TaskDefinition(
                        code=code,
                        name=meta.get("name", code),
                        description=meta.get("description", ""),
                        module_path=meta.get("module_path", "")
                    ))
                else:
                    defn.name = meta.get("name", defn.name)
                    defn.description = meta.get("description", defn.description)
            await db.commit()
            logger.info(f"[🏁] Task Engine: {len(cls._registry)} tasks registered and synced.")

    @classmethod
    async def run_task(cls, task_code: str, params: Dict[str, Any] = None) -> str:
        if task_code not in cls._registry:
            raise ValueError(f"Task code '{task_code}' not found in registry.")

        exec_id = str(uuid.uuid4())

        async with async_session() as db:
            new_exec = TaskExecution(
                id=exec_id,
                task_code=task_code,
                params=params or {},
                status="PENDING",
                result_msg="在队列中等待资源..."
            )
            db.add(new_exec)
            await db.commit()

        coro = cls._execution_wrapper(exec_id, task_code, params or {})
        task = asyncio.create_task(coro)
        cls._running_handles[exec_id] = task

        return exec_id

    @classmethod
    async def _execution_wrapper(cls, exec_id: str, task_code: str, params: Dict[str, Any]):
        async with cls._semaphore:
            start_time = datetime.now()
            func = cls._registry[task_code]

            try:
                async with async_session() as db:
                    await db.execute(
                        update(TaskExecution).where(TaskExecution.id == exec_id).values(
                            status="RUNNING",
                            pid=os.getpid(),
                            start_time=start_time,
                            result_msg="执行中..."
                        )
                    )
                    await db.commit()

                sig = inspect.signature(func)
                if "exec_id" in sig.parameters:
                    await func(exec_id=exec_id, **params)
                else:
                    await func(**params)

                async with async_session() as db:
                    await db.execute(
                        update(TaskExecution).where(TaskExecution.id == exec_id).values(
                            status="SUCCESS",
                            progress=100,
                            end_time=datetime.now(),
                            result_msg="执行成功"
                        )
                    )
                    await db.commit()

            except asyncio.CancelledError:
                logger.warning(f"[🛑] Task Execution {exec_id} was physically cancelled.")
                async with async_session() as db:
                    await db.execute(
                        update(TaskExecution).where(TaskExecution.id == exec_id).values(
                            status="CANCELLED",
                            end_time=datetime.now(),
                            result_msg="任务已被手动强杀"
                        )
                    )
                    await db.commit()
                raise

            except Exception as e:
                logger.error(f"[❌] Task Execution {exec_id} failed: {str(e)}")
                async with async_session() as db:
                    await db.execute(
                        update(TaskExecution).where(TaskExecution.id == exec_id).values(
                            status="FAILED",
                            end_time=datetime.now(),
                            result_msg=f"运行异常: {str(e)}"
                        )
                    )
                    await db.commit()
            finally:
                if exec_id in cls._running_handles:
                    del cls._running_handles[exec_id]

    @classmethod
    async def stop_task(cls, exec_id: str):
        if exec_id in cls._running_handles:
            async with async_session() as db:
                await db.execute(
                    update(TaskExecution).where(TaskExecution.id == exec_id).values(status="STOPPING")
                )
                await db.commit()
            cls._running_handles[exec_id].cancel()
            return True
        return False

    @classmethod
    async def update_progress(cls, exec_id: str, progress: int, msg: str = None):
        async with async_session() as db:
            values = {"progress": progress}
            if msg: values["result_msg"] = msg
            await db.execute(
                update(TaskExecution).where(TaskExecution.id == exec_id).values(**values)
            )
            await db.commit()

# 全局单例
task_manager = TaskEngine
