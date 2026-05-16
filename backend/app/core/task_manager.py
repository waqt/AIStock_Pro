import asyncio
import uuid
import os
import inspect
from datetime import datetime
from typing import Dict, Any, Callable, Optional
from sqlalchemy import update, select, delete
from app.core.database import async_session
from app.models.models import TaskDefinition, TaskExecution
from app.core.logger import logger

class TaskEngine:
    """
    AIStock Pro 任务调度引擎 V5.0 (工业级内核)
    支持：注册装饰器、并发管控(Semaphore)、强杀信号、结果持久化
    """
    
    # 核心组件
    _registry: Dict[str, Callable] = {}
    _running_handles: Dict[str, asyncio.Task] = {}
    _semaphore = asyncio.Semaphore(3) # 全局并发上限，防止资源耗尽

    @classmethod
    def register(cls, code: str, name: str, description: str = ""):
        """任务注册装饰器"""
        def decorator(func: Callable):
            cls._registry[code] = func
            # 注意：这里我们只记录到内存，数据库同步将由专门的 sync_definitions 方法处理
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
        """将内存中的注册信息同步到数据库定义表"""
        async with async_session() as db:
            for code, func in cls._registry.items():
                meta = getattr(func, "_task_meta", {})
                # 覆盖或新增定义
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
        """外部调用入口：异步调起一个任务执行"""
        if task_code not in cls._registry:
            raise ValueError(f"Task code '{task_code}' not found in registry.")

        exec_id = str(uuid.uuid4())
        
        # 1. 预登记执行记录 (PENDING)
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

        # 2. 派发协程并追踪
        coro = cls._execution_wrapper(exec_id, task_code, params or {})
        task = asyncio.create_task(coro)
        cls._running_handles[exec_id] = task
        
        return exec_id

    @classmethod
    async def _execution_wrapper(cls, exec_id: str, task_code: str, params: Dict[str, Any]):
        """执行生命周期包装器 (带信号量和异常处理)"""
        async with cls._semaphore: # 并发管控点
            start_time = datetime.now()
            func = cls._registry[task_code]
            
            try:
                # 更新状态为 RUNNING
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

                # 执行实际业务代码
                # 如果业务函数支持传入 exec_id，则传入以供进度更新
                sig = inspect.signature(func)
                if "exec_id" in sig.parameters:
                    await func(exec_id=exec_id, **params)
                else:
                    await func(**params)

                # 成功收尾
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
                raise # 重新抛出以符合 asyncio 标准

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
        """尝试终止任务"""
        if exec_id in cls._running_handles:
            # 更新状态为 STOPPING (中间态)
            async with async_session() as db:
                await db.execute(
                    update(TaskExecution).where(TaskExecution.id == exec_id).values(status="STOPPING")
                )
                await db.commit()
            
            # 发送取消信号
            cls._running_handles[exec_id].cancel()
            return True
        return False

    @classmethod
    async def update_progress(cls, exec_id: str, progress: int, msg: str = None):
        """提供给业务模块调用的进度更新接口"""
        async with async_session() as db:
            values = {"progress": progress}
            if msg: values["result_msg"] = msg
            await db.execute(
                update(TaskExecution).where(TaskExecution.id == exec_id).values(**values)
            )
            await db.commit()

# 全局单例供外部引用
task_manager = TaskEngine
