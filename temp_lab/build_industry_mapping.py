"""建立行业分类映射库 — 尝试多个数据源, 输出 stock_code→industry 的 JSON 映射

运行: conda activate aiteacher && cd backend && python ../temp_lab/build_industry_mapping.py

输出: data/industry_mapping.json (stock_code → industry 字典)
"""
import os, sys, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import asyncio
import httpx
import warnings
warnings.filterwarnings("ignore")

PROXY = "http://127.0.0.1:7890"
OUTPUT = os.path.join(os.path.dirname(__file__), "..", "backend", "data", "industry_mapping.json")

# ── 源 1: 巨潮行业分类 (CNINFO) ──
async def source_cninfo() -> dict:
    """尝试通过 akshare 获取巨潮行业分类"""
    import akshare as ak
    mapping = {}
    try:
        df = ak.stock_industry_category_cninfo()
        print(f"[CNINFO] Got {len(df)} rows, cols={df.columns.tolist()}")
        # 尝试识别行业列
        for col in df.columns:
            if '行业' in str(col) or 'industry' in str(col).lower():
                industry_col = col
                break
        else:
            print("[CNINFO] No industry column found, trying first 3 cols...")
            # 猜测: 股票代码, 股票名称, 行业
            for _, row in df.iterrows():
                code = str(row.iloc[0]).strip().zfill(6) if len(str(row.iloc[0]).strip()) <= 6 else str(row.iloc[0]).strip()
                industry = str(row.iloc[2]) if len(row) > 2 else ""
                if code and industry and industry not in ("-", "", "nan"):
                    mapping[code] = industry
            return mapping
    except Exception as e:
        print(f"[CNINFO] Failed: {e}")
    return mapping


# ── 源 2: THS 行业分类 ──
async def source_ths() -> dict:
    """尝试通过 akshare 获取同花顺行业成分"""
    import akshare as ak
    mapping = {}
    try:
        # 获取行业列表
        boards = ak.stock_board_industry_name_ths()
        print(f"[THS] Got {len(boards)} industry boards")
        for idx, (_, row) in enumerate(boards.iterrows()):
            board_name = row.get("行业名称", row.get("name", str(row.iloc[0])))
            try:
                cons = ak.stock_board_industry_cons_ths(symbol=board_name)
                for _, c in cons.iterrows():
                    code = str(c.get("代码", c.get("symbol", ""))).strip().zfill(6)
                    if code and len(code) == 6:
                        mapping[code] = board_name
            except Exception as e:
                print(f"  [{idx}] {board_name}: skip ({e})")
            if idx % 10 == 0:
                print(f"  progress: {idx}/{len(boards)}, mapped {len(mapping)} stocks")
            await asyncio.sleep(0.1)
    except Exception as e:
        print(f"[THS] Failed: {e}")
    return mapping


# ── 源 3: Sina 行业分类 ──
async def source_sina() -> dict:
    """尝试通过 Sina 接口获取行业成分"""
    mapping = {}
    try:
        async with httpx.AsyncClient(proxy=None, timeout=10,
                                      headers={"User-Agent": "Mozilla/5.0"}) as client:
            # Sina concept/industry board list
            resp = await client.get(
                "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_BK.industry.getlist"
            )
            if resp.status_code == 200 and resp.text:
                data = resp.json()
                print(f"[Sina] Got {len(data)} industry boards")
                for board in data[:5]:  # 只试前5个
                    board_code = board.get("code", "")
                    board_name = board.get("name", "")
                    print(f"  board: {board_code} {board_name}")
    except Exception as e:
        print(f"[Sina] Failed: {e}")
    return mapping


# ── 源 4: 本地 akshare stock_info_a_code_name (仅名称) ──
async def source_names() -> dict:
    """获取全量A股代码→名称映射 (确认可用的数据源)"""
    import akshare as ak
    names = {}
    try:
        df = ak.stock_info_a_code_name()
        for _, row in df.iterrows():
            code = str(row["code"]).strip().zfill(6)
            name = str(row["name"]).strip()
            names[code] = name
        print(f"[Names] Got {len(names)} stocks")
    except Exception as e:
        print(f"[Names] Failed: {e}")
    return names


async def main():
    print("=" * 60)
    print("行业分类映射构建工具")
    print("=" * 60)

    # 1. 先拿全量名称
    names = await source_names()

    # 2. 尝试 CNINFO
    print("\n--- Source 1: CNINFO ---")
    cninfo = await source_cninfo()
    print(f"  => {len(cninfo)} stocks mapped")

    # 3. 尝试 THS (较慢, 仅当 CNINFO 结果不足时)
    ths = {}
    if len(cninfo) < 1000:
        print("\n--- Source 2: THS ---")
        ths = await source_ths()
        print(f"  => {len(ths)} stocks mapped")

    # 合并 (CNINFO 优先)
    mapping = {**ths, **cninfo}  # CNINFO 覆盖 THS
    print(f"\nTotal mapped: {len(mapping)} stocks")

    # 输出
    output = {
        "mapping": mapping,
        "stats": {
            "total_mapped": len(mapping),
            "source_cninfo": len(cninfo),
            "source_ths": len(ths),
            "total_names": len(names),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    }
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {OUTPUT}")

    # 验证覆盖
    covered = sum(1 for c in names if c in mapping)
    print(f"Coverage: {covered}/{len(names)} ({covered/len(names)*100:.1f}%)")


if __name__ == "__main__":
    asyncio.run(main())
