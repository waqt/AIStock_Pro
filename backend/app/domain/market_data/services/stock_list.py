"""股票名称补充 — 从 MarketData 已有代码 + Sina 实时查询"""
import asyncio
import httpx
from app.framework.database.session import async_session
from app.models.models import StockInfo, MarketData, Position
from sqlalchemy import select, func, distinct
from app.framework.logger import logger


async def sync_stock_list():
    """从 MarketData/Position 已有代码 + Sina API 补充名称到 stock_info 表"""
    total = 0

    async with async_session() as db:
        # 1. 收集所有已知股票代码
        codes = set()
        for model in [MarketData, Position]:
            res = await db.execute(select(distinct(model.stock_code)))
            codes.update(r[0] for r in res.all() if r[0])

        # 2. 过滤已存在的
        exist_res = await db.execute(select(StockInfo.stock_code))
        existing = {r[0] for r in exist_res.all()}
        new_codes = [c for c in codes if c not in existing]
        logger.info(f"[*] {len(new_codes)} new stock codes to fetch names")

        # 3. 通过 Sina API 批量查询名称 (每次最多 50 个)
        for i in range(0, len(new_codes), 50):
            batch = new_codes[i:i+50]
            symbols = []
            for code in batch:
                if len(code) == 5:
                    symbols.append(f"hk{code}")
                else:
                    prefix = 'sh' if code.startswith(('6','9')) else 'sz'
                    symbols.append(f"{prefix}{code}")

            try:
                url = f"http://hq.sinajs.cn/list={','.join(symbols)}"
                headers = {"Referer": "https://finance.sina.com.cn"}
                async with httpx.AsyncClient(proxy=None, timeout=10.0, headers=headers) as client:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        for j, code in enumerate(batch):
                            symbol = symbols[j]
                            # 解析: var hq_str_XXX="名称,..."
                            text = resp.text
                            idx = text.find(f'var hq_str_{symbol}=')
                            if idx < 0:
                                continue
                            start = text.find('"', idx) + 1
                            end = text.find('"', start)
                            if end < 0:
                                continue
                            fields = text[start:end].split(',')
                            name = fields[0] if fields and fields[0] else code
                            exchange = "HK" if len(code) == 5 else ("SH" if code.startswith(('6','9')) else "SZ")
                            db.add(StockInfo(stock_code=code, stock_name=name, exchange=exchange))
                            total += 1
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.warning(f"[Batch {i} failed: {e}]")

        await db.commit()

    # 4. 也补充 Position 中没有但 StockInfo 中也没有的名称
    async with async_session() as db:
        pos_res = await db.execute(select(Position.stock_code, Position.stock_name).where(Position.stock_name.isnot(None)))
        for code, name in pos_res.all():
            if code and name and code not in existing:
                exist2 = await db.get(StockInfo, code)
                if not exist2:
                    ex = "HK" if len(code) == 5 else ("SH" if code.startswith(('6','9')) else "SZ")
                    db.add(StockInfo(stock_code=code, stock_name=name, exchange=ex))
                    total += 1
        await db.commit()

    logger.info(f"[✅] Stock names synced: {total}")
    return total
