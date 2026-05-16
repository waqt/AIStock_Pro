from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from datetime import date, datetime
import json
import asyncio

from app.core.data_service import data_service
from app.quant.indicators import Indicators
from app.quant.patterns import Patterns
from app.models.models import StockIndicator, Position, MarketData
from app.core.logger import logger
from app.core.task_manager import task_manager

class QuantEngine:
    """逻辑链量化决策引擎"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def analyze_stock(self, stock_code: str, task_id: str = None, mode: str = "AUTO", db_session=None):
        """执行全栈逻辑分析 (支持原子事务)"""
        db = db_session or self.db
        
        # 0. 自动感知模式
        if mode == "AUTO":
            # ... (保持原有感知逻辑，将 self.db 换成 db)
            res = await db.execute(
                select(StockIndicator.analysis_date)
                .where(StockIndicator.stock_code == stock_code)
                .order_by(StockIndicator.analysis_date.desc())
                .limit(1)
            )
            latest_date = res.scalars().first()
            # ... (中间逻辑略)
            if latest_date:
                gap_days = (date.today() - latest_date).days
                mode = "INCREMENTAL" if gap_days < 15 else "AUTO_FULL"
            else:
                mode = "AUTO_FULL"

        try:
            # 1. 获取行情数据
            df = await data_service.get_daily_data(stock_code, days=500 if mode == "AUTO_FULL" else 60)
            if df.empty: return None

            # 2. 计算技术指标
            df = Indicators.calculate_all(df)
            findings = Patterns.scan(df)
            
            latest = df.iloc[-1]
            indicator_snapshot = {
                "price": float(latest['close']),
                "ma5": float(latest['ma5']),
                "ma20": float(latest['ma20']),
                "rsi": float(latest['rsi']),
                "macd_hist": float(latest['macd_hist'])
            }

            # 3. 持仓表更新 (使用事务 DB)
            price = float(latest['close'])
            pos_result = await db.execute(select(Position).where(Position.stock_code == stock_code))
            position = pos_result.scalars().first()
            if position:
                position.current_price = price
                position.market_value = float(position.volume) * price
                position.updated_at = datetime.now()

            # 4. 覆盖式写入指标库 (在事务内)
            await db.execute(delete(StockIndicator).where(
                StockIndicator.stock_code == stock_code,
                StockIndicator.analysis_date == date.today()
            ))

            db.add(StockIndicator(
                stock_code=stock_code,
                indicator_type="HYBRID_LOGIC",
                data_json=indicator_snapshot,
                logic_chain={"findings": findings},
                analysis_date=date.today()
            ))
            
            # 注意：不再局部 commit，交由外部 batch_analyze 控制
            logger.info(f"[+] {mode} analysis complete for {stock_code}")
            return findings
        except Exception as e:
            logger.error(f"Analysis error for {stock_code}: {str(e)}")
            raise e

    async def batch_analyze_positions(self, task_id: str = None, mode: str = "technical"):
        """批量同步持仓数据 (V3.0 原子回滚版)"""
        logger.info(f"[*] Starting batch analysis (Task: {task_id}, Mode: {mode})")
        
        # 1. 获取所有待处理持仓
        result = await self.db.execute(select(Position))
        positions = result.scalars().all()
        total = len(positions)

        # 2. 开启原子事务
        async with async_session() as db:
            async with db.begin(): # 整个同步过程是一个大事务
                try:
                    for idx, pos in enumerate(positions):
                        # 核心：允许 asyncio 切换任务，从而接收到 cancel 信号
                        await asyncio.sleep(0) 

                        # 执行分析 (传入事务 session)
                        await self.analyze_stock(pos.stock_code, task_id=task_id, mode=mode, db_session=db)
                        
                        # 3. 统一使用引擎接口更新进度
                        if task_id:
                            progress = int(((idx + 1) / total) * 100)
                            await task_manager.update_progress(
                                task_id, 
                                progress, 
                                f"分析中: {idx+1}/{total} | {pos.stock_code}"
                            )
                    
                    logger.info("[✅] All sync operations committed successfully.")
                except asyncio.CancelledError:
                    logger.warning(f"[🛑] Task {task_id} received physical kill signal. Rolling back all changes...")
                    await db.rollback() # 撤销所有 analyze_stock 产生的影响
                    raise # 继续抛出让 TaskManager 标记状态
                except Exception as e:
                    logger.error(f"[❌] Task {task_id} failed: {e}. Rolling back...")
                    await db.rollback()
                    raise
        return total


    async def sync_prices_only(self, task_id: str = None):
        """仅同步行情价格 (V4.0 强杀支持版)"""
        result = await self.db.execute(select(Position))
        positions = result.scalars().all()
        
        if task_id:
            await self.db.execute(
                update(AnalysisTask).where(AnalysisTask.id == task_id).values(status="RUNNING")
            )
            await self.db.commit()

        total = len(positions)
        for idx, pos in enumerate(positions):
            # 允许 asyncio 响应强杀信号
            await asyncio.sleep(0)

            try:
                df = await data_service.get_daily_data(pos.stock_code, days=1)
                if not df.empty:
                    price = float(df.iloc[-1]['close'])
                    pos.current_price = price
                    pos.market_value = float(pos.volume) * price
                    pos.profit_loss = pos.market_value - (float(pos.volume) * float(pos.avg_cost))
                    if float(pos.avg_cost) > 0:
                        pos.profit_loss_ratio = (pos.profit_loss / (float(pos.volume) * float(pos.avg_cost))) * 100
            except Exception as e:
                logger.error(f"Failed to sync price for {pos.stock_code}: {e}")
            
            if task_id:
                await task_manager.update_progress(
                    task_id, 
                    int(((idx+1)/total)*100), 
                    f"行情同步: {idx+1}/{total} | {pos.stock_code}"
                )
        
        if task_id:
            await task_manager.update_progress(task_id, 100, "行情同步完成")
        return total
