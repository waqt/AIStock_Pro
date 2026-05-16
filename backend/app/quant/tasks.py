import asyncio
from app.core.database import async_session
from app.quant.engine import QuantEngine
from app.core.logger import logger
from app.core.task_manager import task_manager

@task_manager.register(code="sync_market", name="行情数据同步", description="同步持仓股票的最新行情并重算技术指标")
async def sync_market_data_task(mode: str = "AUTO", exec_id: str = None):
    """
    领域逻辑实现：行情同步任务 (V5.0 注册版)
    """
    async with async_session() as db:
        # 实例化引擎
        engine = QuantEngine(db)
        
        # 实际执行领域层的分析逻辑
        if mode == "PRICE_ONLY":
            await engine.sync_prices_only(task_id=exec_id)
        else:
            await engine.batch_analyze_positions(task_id=exec_id, mode=mode)

@task_manager.register(code="calc_indicators", name="指标重算", description="仅针对现有数据重新计算量化指标")
async def calculate_indicators_task(exec_id: str = None):
    """
    领域逻辑实现：指标重算任务
    """
    async with async_session() as db:
        engine = QuantEngine(db)
        await engine.batch_analyze_positions(task_id=exec_id, mode="INDICATORS_ONLY")
