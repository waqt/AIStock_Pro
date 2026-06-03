"""股票名称补充 — 增量 + 全量 A 股东财同步 (目标: StockMaster)"""
import asyncio
import httpx
from app.framework.database.session import async_session
from app.models.models import StockMaster, MarketData, Position
from sqlalchemy import select, func, distinct
from app.framework.logger import logger


async def sync_a_stock_list_full() -> int:
    """从东财 clist 全量获取 A 股代码名称 → StockMaster（含行业）"""
    total = 0
    page_size = 200
    transport = httpx.AsyncHTTPTransport(proxy=None, retries=2)
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}

    for page in range(1, 60):
        url = "http://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": str(page), "pz": str(page_size), "po": "1", "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2", "invt": "2", "fid": "f3",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f12,f14,f10",  # f10=行业
        }
        try:
            async with httpx.AsyncClient(transport=transport, timeout=15.0, headers=headers) as client:
                resp = await client.get(url, params=params)
                if resp.status_code != 200:
                    logger.warning(f"[A-list] Page {page}: HTTP {resp.status_code}")
                    break
                data = resp.json()
                items = data.get("data", {}).get("diff", [])
                if not items:
                    break

                async with async_session() as db:
                    for item in items:
                        code = str(item.get("f12", "")).strip()
                        name = str(item.get("f14", "")).strip()
                        industry = str(item.get("f10", "")).strip() if item.get("f10") else None
                        if not code or not name:
                            continue
                        code = code.zfill(6)
                        exchange = "SH" if code.startswith(("6", "9")) else "SZ"
                        existing = await db.get(StockMaster, code)
                        if not existing:
                            db.add(StockMaster(stock_code=code, stock_name=name, exchange=exchange, industry=industry))
                            total += 1
                        else:
                            if not existing.stock_name or existing.stock_name == code:
                                existing.stock_name = name
                            if industry and not existing.industry:
                                existing.industry = industry
                            total += 1
                    await db.commit()

                logger.info(f"[A-list] Page {page}: {len(items)} stocks (total: {total})")
                await asyncio.sleep(0.3)
        except Exception as e:
            logger.warning(f"[A-list] Page {page} failed: {e}")
            break

    logger.info(f"[✅] Full A-share sync: {total} stocks")
    return total


async def sync_hk_stock_list_full() -> int:
    """从东财 clist 全量获取港股代码名称 → StockMaster"""
    total = 0
    page_size = 200
    transport = httpx.AsyncHTTPTransport(proxy=None, retries=2)
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"}

    for page in range(1, 60):
        url = "http://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": str(page), "pz": str(page_size), "po": "1", "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2", "invt": "2", "fid": "f3",
            "fs": "m:128+t:3,m:128+t:4",  # 主板 + GEM
            "fields": "f12,f14",
        }
        try:
            async with httpx.AsyncClient(transport=transport, timeout=15.0, headers=headers) as client:
                resp = await client.get(url, params=params)
                if resp.status_code != 200:
                    logger.warning(f"[HK-list] Page {page}: HTTP {resp.status_code}")
                    break
                data = resp.json()
                items = data.get("data", {}).get("diff", [])
                if not items:
                    break

                async with async_session() as db:
                    for item in items:
                        code = str(item.get("f12", "")).strip().zfill(5)
                        name = str(item.get("f14", "")).strip()
                        if not code or not name:
                            continue
                        existing = await db.get(StockMaster, code)
                        if not existing:
                            db.add(StockMaster(stock_code=code, stock_name=name, exchange="HK"))
                            total += 1
                        elif not existing.stock_name or existing.stock_name == code:
                            existing.stock_name = name
                            total += 1
                    await db.commit()

                logger.info(f"[HK-list] Page {page}: {len(items)} stocks (total: {total})")
                await asyncio.sleep(0.3)
        except Exception as e:
            logger.warning(f"[HK-list] Page {page} failed: {e}")
            break

    logger.info(f"[✅] Full HK stock sync: {total} stocks")
    return total


async def sync_stock_list():
    """从 MarketData/Position 已有代码 + Sina API 补充名称到 StockMaster 表"""
    total = 0

    async with async_session() as db:
        codes = set()
        for model in [MarketData, Position]:
            res = await db.execute(select(distinct(model.stock_code)))
            codes.update(r[0] for r in res.all() if r[0])

        exist_res = await db.execute(select(StockMaster.stock_code))
        existing = {r[0] for r in exist_res.all()}
        new_codes = [c for c in codes if c not in existing]
        logger.info(f"[*] {len(new_codes)} new stock codes to fetch names")

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
                            db.add(StockMaster(stock_code=code, stock_name=name, exchange=exchange))
                            total += 1
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.warning(f"[Batch {i} failed: {e}]")

        await db.commit()

    # 4. 港股名称修正: 用腾讯 API 换中文名
    try:
        from app.domain.market_data.sources.tencent import get_tencent_quotes
        async with async_session() as db2:
            r2 = await db2.execute(select(StockMaster.stock_code).where(StockMaster.exchange == "HK"))
            hk_codes = [row[0] for row in r2.all()]
        if hk_codes:
            quotes = await get_tencent_quotes(hk_codes)
            async with async_session() as db3:
                for code, q in quotes.items():
                    cname = q.get("name", "")
                    if cname and not all(ord(ch) < 128 for ch in cname):
                        existing = await db3.get(StockMaster, code)
                        if existing:
                            existing.stock_name = cname
                            total += 1
                await db3.commit()
            logger.info(f"[✅] Fixed {len(quotes)} HK names via Tencent")
    except Exception as e:
        logger.warning(f"[HK name fix failed: {e}]")

    logger.info(f"[✅] Stock names synced: {total}")
    return total
