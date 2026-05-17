import asyncio
from app.core.database import async_session
from app.quant.engine import QuantEngine
from app.core.ai_service import AIImportService
from app.core.logger import logger
from app.core.task_manager import task_manager

@task_manager.register(code="sync_market", name="行情数据同步", description="同步持仓股票的最新行情并重算技术指标")
async def sync_market_data_task(mode: str = "AUTO", exec_id: str = None):
    """V5.1 行情同步任务 — 增量感知 + 节点追踪"""
    async with async_session() as db:
        engine = QuantEngine(db)
        if mode == "PRICE_ONLY":
            await engine.sync_prices_only(exec_id=exec_id)
        else:
            await engine.batch_sync_and_analyze(exec_id=exec_id, mode=mode)

@task_manager.register(code="calc_indicators", name="指标重算", description="仅针对现有数据重新计算量化指标")
async def calculate_indicators_task(exec_id: str = None):
    """V5.1 指标重算任务"""
    async with async_session() as db:
        engine = QuantEngine(db)
        from sqlalchemy import select, func
        from app.models.models import Position, MarketData

        result = await engine.db.execute(select(Position))
        positions = result.scalars().all()
        total = len(positions)
        success = 0
        skipped = 0

        for idx, pos in enumerate(positions):
            await asyncio.sleep(0)

            # 检查是否有行情数据
            has_data = await engine.db.execute(
                select(func.count(MarketData.id)).where(MarketData.stock_code == pos.stock_code)
            )
            if has_data.scalar() == 0:
                skipped += 1
                logger.warning(f"[⚠️] {pos.stock_code}: no market data, skipping")
                continue

            result_data = await engine.calculate_indicators(pos.stock_code)
            if result_data:
                success += 1

            if exec_id:
                await task_manager.update_progress(
                    exec_id, int(((idx + 1) / total) * 100),
                    f"指标重算: {idx+1}/{total} | {pos.stock_code} (成功:{success} 跳过:{skipped})"
                )
        await engine.db.commit()

        if skipped == total:
            raise RuntimeError(f"所有 {total} 只股票均无行情数据，请先同步行情")
        if exec_id:
            await task_manager.update_progress(exec_id, 100, f"完成: 成功{success}只, 跳过{skipped}只")


@task_manager.register(code="ai_recognize", name="AI 截图识别", description="调用 AI 模型识别持仓/交易截图")
async def ai_recognize_image_task(exec_id: str = None, image_base64: str = "",
                                   recognize_type: str = "position"):
    """V5.2 AI 识别异步任务 — 豆包 → DeepSeek → Gemini 链式调用"""
    if exec_id:
        await task_manager.update_progress(exec_id, 5, "正在压缩图片...")

    if recognize_type == "trade":
        result = await AIImportService.recognize_trade_image(image_base64)
    else:
        result = await AIImportService.recognize_stock_image(image_base64)

    if exec_id:
        if result:
            await task_manager.update_progress(exec_id, 100, f"识别完成: {len(result)} 条记录")
        else:
            raise RuntimeError("所有 AI 引擎均未识别到有效数据，请检查 API Key 配置或截图清晰度")
