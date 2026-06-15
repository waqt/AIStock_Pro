"""
全量同步所有股票的股本数据 (total_shares / float_shares)

直接调腾讯行情 API (跳过 push2, 更快更稳)
"""
import asyncio, sys, time, re, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, r'E:\workspace\AIResearch\AIStock_Pro\backend')

import urllib3
urllib3.disable_warnings()

import requests
from app.framework.database.session import async_session
from app.models.models import StockMaster
from sqlalchemy import select

BATCH_SIZE = 200
CONCURRENCY = 20

# A 股: total=73, float=72  (0-indexed after regex strip)
# HK 股: total=69, float=70
TENCENT_FIELDS = {
    "a": {"total": 73, "float": 72},
    "hk": {"total": 69, "float": 70},
}


def get_tencent_prefix(code: str) -> str:
    if len(code) == 6:
        return "sh" if code[0] in ("5", "6") else "sz"
    return "hk"


async def fetch_tencent(code: str) -> tuple:
    """调腾讯行情, 返回 (total_shares, float_shares)"""
    prefix = get_tencent_prefix(code)
    is_hk = prefix == "hk"
    fmap = TENCENT_FIELDS["hk" if is_hk else "a"]

    try:
        resp = await asyncio.to_thread(
            requests.get, f"https://qt.gtimg.cn/q={prefix}{code}",
            timeout=8, headers={"User-Agent": "Mozilla/5.0"}
        )
        if resp.status_code != 200:
            return None, None
        m = re.search(r'"(.*)"', resp.text)
        if not m:
            return None, None
        parts = m.group(1).split("~")
        total = float(parts[fmap["total"]]) if len(parts) > fmap["total"] and parts[fmap["total"]].strip() else None
        floats = float(parts[fmap["float"]]) if len(parts) > fmap["float"] and parts[fmap["float"]].strip() else None
        return total, floats
    except Exception:
        return None, None


async def main():
    async with async_session() as db:
        res = await db.execute(select(StockMaster.stock_code))
        all_codes = list(res.scalars().all())

    print(f"StockMaster 共 {len(all_codes)} 只股票 (含A股+港股)")
    t0 = time.time()

    updated = 0
    skipped = 0
    sem = asyncio.Semaphore(CONCURRENCY)

    async def fetch_one(code: str):
        async with sem:
            return code, *await fetch_tencent(code)

    for batch_start in range(0, len(all_codes), BATCH_SIZE):
        batch = all_codes[batch_start:batch_start + BATCH_SIZE]
        results = await asyncio.gather(*[fetch_one(c) for c in batch])

        batch_updates = {}
        for code, ts, fs in results:
            if ts or fs:
                batch_updates[code] = {}
                if ts is not None:
                    batch_updates[code]["total_shares"] = ts
                if fs is not None:
                    batch_updates[code]["float_shares"] = fs
            else:
                skipped += 1

        if batch_updates:
            async with async_session() as db:
                for code, kv in batch_updates.items():
                    row = await db.get(StockMaster, code)
                    if row:
                        for k, v in kv.items():
                            setattr(row, k, v)
                await db.commit()
            updated += len(batch_updates)

        done = min(batch_start + BATCH_SIZE, len(all_codes))
        elapsed = time.time() - t0
        rate = done / elapsed if elapsed > 0 else 0
        print(f"  [{done}/{len(all_codes)}] 更新 {updated}, 跳过 {skipped}, "
              f"耗时 {elapsed:.0f}s ({rate:.0f} 只/s)")

    elapsed = time.time() - t0
    print(f"\n{'='*50}")
    print(f"完成! {updated} 更新, {skipped} 跳过(无数据)")
    print(f"总耗时 {elapsed:.0f}s")

    print(f"\n--- 验证抽查 ---")
    async with async_session() as db:
        for code in ["300308", "300502", "300750", "00175", "01277", "01810"]:
            row = await db.get(StockMaster, code)
            if row:
                print(f"  {code} {row.stock_name or '?':<8} total={row.total_shares} float={row.float_shares}")
            else:
                print(f"  {code} NOT FOUND")


if __name__ == "__main__":
    asyncio.run(main())
