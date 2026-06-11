from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, insert
from sqlalchemy.dialects.mysql import insert as mysql_insert
from datetime import date, datetime, timedelta

# 行情同步起始日期 (AUTO 模式无历史数据时从此日期起拉取)
_SYNC_START_DATE = date(2019, 1, 1)
import asyncio

from app.framework.database.session import async_session
from app.domain.market_data.sources.router import data_router
from app.models.models import Position, MarketData, TaskExecution
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

        mode:
          AUTO  — 智能增量: 查最新日期→算gap→补缺失
          FORCE — 强制拉取最近10天, 不检查gap
          FULL  — 全量覆盖: 删除该标的历史数据, 从2019年起重插
        """
        # 1. 判断同步模式
        days_to_fetch = 500
        is_full = False
        if mode == "FORCE":
            days_to_fetch = 10  # 强制拉取最近10天, 不检查gap
        elif mode == "FULL":
            is_full = True
            days_to_fetch = 2500  # 2500交易日 ≈ 10年
        elif mode == "AUTO":
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
                if gap <= 1:
                    return 0
                if weekday == 0 and gap <= 2:
                    return 0
                days_to_fetch = max(gap + 5, 10)
            else:
                # 无历史数据 → 从 _SYNC_START_DATE 起全量拉取
                cal_days = (date.today() - _SYNC_START_DATE).days
                days_to_fetch = min(int(cal_days * 1.4), 2500)

        # 2. 全量覆盖模式: 先删除历史数据
        if is_full:
            await self.db.execute(
                delete(MarketData).where(MarketData.stock_code == stock_code)
            )

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
        批量同步 (数据同步与指标计算已分离)
        节点: FX → FETCHING → SAVING → UPDATING_POSITIONS → VALUATION
        指标计算独立: POST /api/quant/indicators/compute
        target_codes: 可选; None则同步全部持仓+全部自选股
        """
        from app.models.models import WatchlistItem
        result = await self.db.execute(select(Position))
        positions = result.scalars().all()
        if not target_codes:
            # 全量同步: 持仓 + 自选股 (去重)
            wl_res = await self.db.execute(select(WatchlistItem.stock_code))
            wl_codes = [r[0] for r in wl_res.all()]
            pos_codes = {p.stock_code for p in positions}
            extra = [type('_', (), {'stock_code': c})() for c in wl_codes if c not in pos_codes]
            positions = positions + extra
        elif target_codes:
            # 允许同步非持仓股: 不在持仓中的 code 构造虚拟条目
            pos_codes = {p.stock_code for p in positions}
            extra = [type('_', (), {'stock_code': c})() for c in target_codes if c not in pos_codes]
            positions = [p for p in positions if p.stock_code in set(target_codes)] + extra
        total = len(positions)

        try:
            # ── 节点 0: 宏观数据同步 (仅全量同步时, 单股跳过) ──
            if not target_codes:
                from app.domain.market_data.services.macro_sync import sync_macro_data
                await sync_macro_data()
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

            # ── 节点 2: SAVING ──
            await self.db.commit()
            if exec_id:
                await task_manager.update_progress(exec_id, 50, "SAVING: 落库完成")

            # ── 节点 3: UPDATING_POSITIONS ──
            for idx, pos in enumerate(positions):
                await asyncio.sleep(0)
                if exec_id:
                    await task_manager.update_progress(
                        exec_id, 50 + int(((idx + 1) / total) * 25),
                        f"UPDATING_POSITIONS: {idx+1}/{total} | {pos.stock_code}"
                    )
                await self.update_position_pnl(pos.stock_code)
            await self.db.commit()

            # ── 节点 4: VALUATION ──
            if exec_id:
                await task_manager.update_progress(exec_id, 95, "VALUATION: syncing PE/PB/mcap...")
            from app.domain.market_data.services.valuation import sync_valuation
            val_count = await sync_valuation(target_codes)
            if exec_id:
                await task_manager.update_progress(exec_id, 98, f"估值同步完成: {val_count}只")

            # ── 节点 5: STOCK_INFO ──
            from app.domain.market_data.services.valuation import sync_stock_info
            all_codes = list(set(p.stock_code for p in positions))
            for idx, code in enumerate(all_codes):
                await asyncio.sleep(0.05)
                await sync_stock_info(code)
            if exec_id:
                await task_manager.update_progress(exec_id, 99, f"行业同步完成: {len(all_codes)}只")

            # ── 节点 6: INDICATORS (可选, target_codes 指定时触发历史回补) ──
            if target_codes:
                from app.domain.quant.engine.indicator_runner import IndicatorRunner
                for code in target_codes:
                    await asyncio.sleep(0)
                    try:
                        r = await IndicatorRunner.compute_historical(code)
                        logger.info(f"[SyncEngine] {code}: {r.get('days_computed',0)} days indicators")
                    except Exception as e:
                        logger.warning(f"[SyncEngine] {code} indicators failed: {e}")
            if exec_id:
                await task_manager.update_progress(exec_id, 100, f"同步完成: {len(all_codes)}只")

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
