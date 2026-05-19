from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, insert
from sqlalchemy.dialects.mysql import insert as mysql_insert
from datetime import date, datetime, timedelta
import asyncio

from app.framework.database.session import async_session
from app.domain.market_data.sources.router import data_router
from app.domain.quant.engine.indicators import Indicators
from app.domain.quant.engine.patterns import Patterns
from app.models.models import StockIndicator, Position, MarketData, TaskExecution
from app.framework.logger import logger
from app.framework.tasks.engine import task_manager


class QuantEngine:
    """V5.1 量化决策引擎 — 增量同步 + 批量 upsert + 节点追踪"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ═══════════════════════════════════════════
    # 行情数据同步
    # ═══════════════════════════════════════════

    async def sync_market_data(self, stock_code: str, mode: str = "AUTO") -> int:
        """
        同步单股日线数据 (支持增量/全量感知)
        返回: 新增记录数
        """
        # 1. 判断同步模式
        days_to_fetch = 500
        if mode == "AUTO":
            res = await self.db.execute(
                select(MarketData.trade_date)
                .where(MarketData.stock_code == stock_code)
                .order_by(MarketData.trade_date.desc())
                .limit(1)
            )
            latest_date = res.scalars().first()
            if latest_date:
                gap = (date.today() - latest_date).days
                weekday = date.today().weekday()
                # 跳过逻辑 (考虑周末):
                # gap<=1: 今天/昨天数据, 总是最新
                # 周一 gap<=2: 周六/日数据(实际不存在), 周五数据gap=3需同步
                if gap <= 1:
                    return 0
                if weekday == 0 and gap <= 2:
                    return 0
                days_to_fetch = max(gap + 5, 10)
            # else: 无历史数据 → 全量抓取 (days=500)

        # 2. 抓取行情
        df = await data_router.get_daily_data(stock_code, days=days_to_fetch)
        if df.empty:
            return 0

        # 3. 过滤出数据库中缺失的日期
        existing_dates = set()
        res = await self.db.execute(
            select(MarketData.trade_date).where(MarketData.stock_code == stock_code)
        )
        for row in res.scalars().all():
            existing_dates.add(row)

        new_rows = []
        for _, row in df.iterrows():
            td = row['trade_date']
            if hasattr(td, 'date'):
                td = td.date()
            if td not in existing_dates:
                new_rows.append({
                    "stock_code": stock_code,
                    "trade_date": td,
                    "open": float(row['open']),
                    "high": float(row['high']),
                    "low": float(row['low']),
                    "close": float(row['close']),
                    "volume": float(row['volume']),
                    "amount": float(row.get('amount', 0)),
                    "change_pct": float(row.get('change_pct', 0)) if row.get('change_pct') and str(row.get('change_pct')) != 'nan' else None
                })

        # 4. 批量 upsert
        if new_rows:
            await self.db.execute(
                mysql_insert(MarketData).values(new_rows).prefix_with("IGNORE")
            )
            logger.info(f"[+] {stock_code}: synced {len(new_rows)} new daily records")
        return len(new_rows)

    # ═══════════════════════════════════════════
    # 指标计算
    # ═══════════════════════════════════════════

    async def calculate_indicators(self, stock_code: str) -> dict:
        """计算单股全部技术指标并存储"""
        res = await self.db.execute(
            select(MarketData)
            .where(MarketData.stock_code == stock_code)
            .order_by(MarketData.trade_date.asc())
        )
        rows = res.scalars().all()
        if not rows:
            return {}

        import pandas as pd
        df = pd.DataFrame([{
            'trade_date': r.trade_date,
            'open': r.open, 'high': r.high, 'low': r.low, 'close': r.close,
            'volume': r.volume, 'amount': r.amount
        } for r in rows])

        df = Indicators.calculate_all(df)
        findings = Patterns.scan(df)
        latest = df.iloc[-1]

        indicator_snapshot = {
            "price": float(latest['close']),
            "ma5": float(latest['ma5']) if pd.notna(latest.get('ma5')) else None,
            "ma10": float(latest['ma10']) if pd.notna(latest.get('ma10')) else None,
            "ma20": float(latest['ma20']) if pd.notna(latest.get('ma20')) else None,
            "ma60": float(latest['ma60']) if pd.notna(latest.get('ma60')) else None,
            "ma120": float(latest['ma120']) if pd.notna(latest.get('ma120')) else None,
            "ma250": float(latest['ma250']) if pd.notna(latest.get('ma250')) else None,
            "rsi": float(latest['rsi']) if pd.notna(latest.get('rsi')) else None,
            "macd": float(latest['macd']) if pd.notna(latest.get('macd')) else None,
            "macd_signal": float(latest['macd_signal']) if pd.notna(latest.get('macd_signal')) else None,
            "macd_hist": float(latest['macd_hist']) if pd.notna(latest.get('macd_hist')) else None,
            "bb_upper": float(latest['bb_upper']) if pd.notna(latest.get('bb_upper')) else None,
            "bb_mid": float(latest['bb_mid']) if pd.notna(latest.get('bb_mid')) else None,
            "bb_lower": float(latest['bb_lower']) if pd.notna(latest.get('bb_lower')) else None,
            "v_ma5": float(latest['v_ma5']) if pd.notna(latest.get('v_ma5')) else None,
            "v_ma10": float(latest['v_ma10']) if pd.notna(latest.get('v_ma10')) else None,
            "v_ma20": float(latest['v_ma20']) if pd.notna(latest.get('v_ma20')) else None,
        }

        # 覆盖式写入今日指标
        await self.db.execute(
            delete(StockIndicator).where(
                StockIndicator.stock_code == stock_code,
                StockIndicator.analysis_date == date.today()
            )
        )
        self.db.add(StockIndicator(
            stock_code=stock_code,
            indicator_type="FULL_SCAN",
            data_json=indicator_snapshot,
            logic_chain={"findings": findings} if findings else None,
            analysis_date=date.today()
        ))

        return {"snapshot": indicator_snapshot, "findings": findings}

    # ═══════════════════════════════════════════
    # 更新持仓损益
    # ═══════════════════════════════════════════

    async def update_position_pnl(self, stock_code: str) -> bool:
        """根据最新行情更新单股持仓的现价和盈亏"""
        res = await self.db.execute(
            select(MarketData)
            .where(MarketData.stock_code == stock_code)
            .order_by(MarketData.trade_date.desc())
            .limit(1)
        )
        latest = res.scalars().first()
        if not latest:
            return False

        price = latest.close
        pos_res = await self.db.execute(select(Position).where(Position.stock_code == stock_code))
        position = pos_res.scalars().first()
        if position:
            position.current_price = price
            position.market_value = float(position.volume) * price
            cost_basis = float(position.volume) * float(position.avg_cost)
            position.profit_loss = position.market_value - cost_basis
            # 负成本(已收回本金): 损益金额正确, 比率无意义
            if float(position.avg_cost) > 0:
                position.profit_loss_ratio = (position.profit_loss / cost_basis) * 100
            else:
                position.profit_loss_ratio = None
            position.updated_at = datetime.now()
        return True

    # ═══════════════════════════════════════════
    # 批量任务入口
    # ═══════════════════════════════════════════

    async def batch_sync_and_analyze(self, exec_id: str = None, mode: str = "AUTO", target_codes: list = None):
        """
        批量同步 + 分析 (V5.2 节点追踪版)
        节点: FX → FETCHING → CALCULATING → SAVING → UPDATING_POSITIONS
        target_codes: 可选, 指定要同步的股票代码列表; 为None则同步全部持仓
        """
        result = await self.db.execute(select(Position))
        positions = result.scalars().all()
        if target_codes:
            # 允许同步非持仓股: 不在持仓中的 code 构造虚拟条目
            pos_codes = {p.stock_code for p in positions}
            extra = [type('_', (), {'stock_code': c})() for c in target_codes if c not in pos_codes]
            positions = [p for p in positions if p.stock_code in set(target_codes)] + extra
        total = len(positions)

        try:
            # ── 节点 0: 宏观数据同步 (仅全量同步时, 单股跳过) ──
            if not target_codes:
                await data_router.sync_macro_data()
                if exec_id:
                    await task_manager.update_progress(exec_id, 2, "宏观数据同步完成")

            # ── 节点 1: FETCHING ──
            for idx, pos in enumerate(positions):
                await asyncio.sleep(0)
                if exec_id:
                    await task_manager.update_progress(
                        exec_id, int(((idx + 1) / total) * 25),
                        f"FETCHING: {idx+1}/{total} | {pos.stock_code}"
                    )
                await self.sync_market_data(pos.stock_code, mode=mode)

            # ── 节点 2: CALCULATING ──
            for idx, pos in enumerate(positions):
                await asyncio.sleep(0)
                if exec_id:
                    await task_manager.update_progress(
                        exec_id, 25 + int(((idx + 1) / total) * 25),
                        f"CALCULATING: {idx+1}/{total} | {pos.stock_code}"
                    )
                await self.calculate_indicators(pos.stock_code)

            # ── 节点 3: SAVING ──
            await self.db.commit()
            if exec_id:
                await task_manager.update_progress(exec_id, 75, "SAVING: 落库完成")

            # ── 节点 4: UPDATING_POSITIONS ──
            for idx, pos in enumerate(positions):
                await asyncio.sleep(0)
                if exec_id:
                    await task_manager.update_progress(
                        exec_id, 75 + int(((idx + 1) / total) * 25),
                        f"UPDATING_POSITIONS: {idx+1}/{total} | {pos.stock_code}"
                    )
                await self.update_position_pnl(pos.stock_code)
            await self.db.commit()

            # ── 节点 5: VALUATION ──
            if exec_id:
                await task_manager.update_progress(exec_id, 95, "VALUATION: syncing PE/PB/mcap...")
            from app.domain.market_data.services.valuation import sync_valuation
            val_count = await sync_valuation(target_codes)
            if exec_id:
                await task_manager.update_progress(exec_id, 100, f"估值同步完成: {val_count}只")

            logger.info("[✅] Batch sync+analyze complete.")
        except asyncio.CancelledError:
            logger.warning(f"[🛑] Task {exec_id} cancelled, rolling back.")
            await self.db.rollback()
            raise
        except Exception as e:
            logger.error(f"[❌] Task {exec_id} failed: {e}")
            await self.db.rollback()
            raise
        return total

    async def sync_prices_only(self, exec_id: str = None):
        """仅刷新持仓价格 (轻量模式)"""
        result = await self.db.execute(select(Position))
        positions = result.scalars().all()
        total = len(positions)

        for idx, pos in enumerate(positions):
            await asyncio.sleep(0)
            try:
                df = await data_router.get_daily_data(pos.stock_code, days=1)
                if not df.empty:
                    price = float(df.iloc[-1]['close'])
                    pos.current_price = price
                    pos.market_value = float(pos.volume) * price
                    pos.profit_loss = pos.market_value - (float(pos.volume) * float(pos.avg_cost))
                    if float(pos.avg_cost) > 0:
                        pos.profit_loss_ratio = (pos.profit_loss / (float(pos.volume) * float(pos.avg_cost))) * 100
            except Exception as e:
                logger.error(f"Failed to sync price for {pos.stock_code}: {e}")

            if exec_id:
                await task_manager.update_progress(
                    exec_id, int(((idx + 1) / total) * 100),
                    f"PRICE_ONLY: {idx+1}/{total} | {pos.stock_code}"
                )
            await self.db.commit()

        if exec_id:
            await task_manager.update_progress(exec_id, 100, "行情刷新完成")
        return total
