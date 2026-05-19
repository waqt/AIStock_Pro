"""指标计算引擎 — 用新的指标库算子对MarketData做批量计算并持久化"""
import pandas as pd
from datetime import date, datetime
from typing import List, Optional
from sqlalchemy import select, delete
from app.framework.database.session import async_session
from app.models.models import MarketData, StockIndicator
from app.domain.quant.indicators import INDICATOR_REGISTRY
from app.framework.logger import logger


class IndicatorRunner:
    """指标计算运行器 — 加载行情 → 跑全部/指定算子 → 写入StockIndicator"""

    @staticmethod
    async def compute_single(stock_code: str, indicator_names: List[str] = None) -> dict:
        """计算单只股票的全部指标 (或指定指标), 持久化到 StockIndicator"""
        async with async_session() as db:
            # 加载日线数据
            res = await db.execute(
                select(MarketData)
                .where(MarketData.stock_code == stock_code)
                .order_by(MarketData.trade_date.asc())
            )
            rows = res.scalars().all()
            if not rows:
                return {"stock_code": stock_code, "error": "No market data", "computed": 0}

            # 转 DataFrame
            df = pd.DataFrame([{
                "trade_date": r.trade_date,
                "open": float(r.open or 0), "high": float(r.high or 0),
                "low": float(r.low or 0), "close": float(r.close or 0),
                "volume": float(r.volume or 0),
            } for r in rows])

            # 计算每个指标
            results = {}
            computed = 0
            for name, cls in INDICATOR_REGISTRY.items():
                if indicator_names and name not in indicator_names:
                    continue
                try:
                    # 检查依赖字段
                    missing = [f for f in cls.requires if f not in df.columns]
                    if missing:
                        logger.warning(f"[IndicatorRunner] {name}: missing columns {missing}, skipping")
                        continue
                    output = cls.compute(df)
                    # 取最新值 (标量)
                    latest = {}
                    for k, v in output.items():
                        if hasattr(v, 'iloc'):  # pandas Series
                            last_val = v.dropna().iloc[-1] if len(v.dropna()) > 0 else None
                            latest[k] = float(last_val) if last_val is not None else None
                            # 也存前一值 (用于金叉死叉判断)
                            if len(v.dropna()) >= 2:
                                latest[f"_prev_{k}"] = float(v.dropna().iloc[-2])
                        else:
                            latest[k] = float(v) if v is not None else None
                    results.update(latest)
                    computed += 1
                except Exception as e:
                    logger.warning(f"[IndicatorRunner] {name} compute failed: {e}")

            if not results:
                return {"stock_code": stock_code, "computed": 0, "error": "No indicators computed"}

            # 添加价格
            latest_close = float(rows[-1].close or 0)
            results["price"] = latest_close

            # 删除今天的旧指标, 写入新的
            today = date.today()
            await db.execute(
                delete(StockIndicator).where(
                    StockIndicator.stock_code == stock_code,
                    StockIndicator.analysis_date == today,
                    StockIndicator.indicator_type == "FULL_SCAN"
                )
            )
            db.add(StockIndicator(
                stock_code=stock_code,
                indicator_type="FULL_SCAN",
                data_json=results,
                logic_chain={},
                analysis_date=today,
            ))
            await db.commit()

            logger.info(f"[IndicatorRunner] {stock_code}: {computed} indicators computed")
            return {"stock_code": stock_code, "computed": computed, "indicators": list(results.keys())}

    @staticmethod
    async def compute_batch(stock_codes: List[str], indicator_names: List[str] = None) -> dict:
        """批量计算多只股票"""
        total = 0
        errors = []
        for code in stock_codes:
            r = await IndicatorRunner.compute_single(code, indicator_names)
            if "error" in r:
                errors.append(r)
            else:
                total += r.get("computed", 0)
        return {"total_computed": total, "stocks": len(stock_codes), "errors": len(errors)}
