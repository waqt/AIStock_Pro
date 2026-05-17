"""
东方财富 push2his — 资金流向 + 个股基本面 + 行业板块
直连 HTTP, 无第三方依赖
"""
import httpx
from typing import List, Dict, Optional
from app.framework.logger import logger


async def get_stock_fundamentals(codes: List[str]) -> Dict[str, dict]:
    """批量获取个股基本面 (总股本/流通股本/总市值/流通市值/行业/上市日)"""
    if not codes:
        return {}
    secids = []
    for c in codes:
        mkt = "1" if str(c).startswith(("6", "9")) else "0"
        secids.append(f"{mkt}.{c}")
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {
        "secid": ",".join(secids),
        "fields": "f57,f58,f84,f85,f116,f117,f127,f189,f43,f169,f170",
    }
    try:
        async with httpx.AsyncClient(proxy=None, timeout=10.0,
                                      headers={"User-Agent": "Mozilla/5.0"}) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return {}
            data = resp.json()
            items = data.get("data", {}) if isinstance(data.get("data"), list) else [data.get("data")]
    except Exception as e:
        logger.warning(f"[Push2 fundamental fetch failed: {e}]")
        return {}

    result = {}
    for item in items:
        if not item:
            continue
        code = item.get("f57", "")
        if not code:
            continue
        result[code] = {
            "name": item.get("f58", ""),
            "total_shares": item.get("f84"),  # 总股本
            "float_shares": item.get("f85"),  # 流通股本
            "total_mcap": item.get("f116"),   # 总市值
            "float_mcap": item.get("f117"),   # 流通市值
            "industry": item.get("f127", ""), # 行业
            "list_date": item.get("f189"),    # 上市日期
            "price": item.get("f43"),         # 最新价
        }
    return result


async def get_capital_flow(code: str, days: int = 60) -> List[Dict]:
    """个股资金流向 (主力/散户/超大单 日级)"""
    mkt = "1" if str(code).startswith("6") else "0"
    url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
    params = {
        "secid": f"{mkt}.{code}",
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        "lmt": str(days),
    }
    try:
        async with httpx.AsyncClient(proxy=None, timeout=10.0,
                                      headers={"User-Agent": "Mozilla/5.0"}) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return []
            data = resp.json()
            klines = data.get("data", {}).get("klines", [])
    except Exception as e:
        logger.warning(f"[Capital flow fetch failed {code}: {e}]")
        return []

    rows = []
    for line in klines:
        parts = line.split(",")
        if len(parts) < 7:
            continue
        rows.append({
            "date": parts[0],
            "main_net": float(parts[1]) if parts[1] != "-" else 0.0,
            "small_net": float(parts[2]) if parts[2] != "-" else 0.0,
            "mid_net": float(parts[3]) if parts[3] != "-" else 0.0,
            "large_net": float(parts[4]) if parts[4] != "-" else 0.0,
            "super_net": float(parts[5]) if parts[5] != "-" else 0.0,
        })
    return rows


async def get_industry_rankings() -> List[Dict]:
    """行业板块涨跌排名"""
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "50", "po": "1", "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2", "invt": "2",
        "fid": "f3", "fs": "m:90+t:2",
        "fields": "f12,f14,f2,f3,f104,f105,f140",
    }
    try:
        async with httpx.AsyncClient(proxy=None, timeout=10.0,
                                      headers={"User-Agent": "Mozilla/5.0"}) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return []
            data = resp.json()
            items = data.get("data", {}).get("diff", [])
    except Exception as e:
        logger.warning(f"[Industry ranking failed: {e}]")
        return []

    return [{
        "code": i.get("f12"), "name": i.get("f14"),
        "price": i.get("f2"), "change_pct": i.get("f3"),
        "up_count": i.get("f104"), "down_count": i.get("f105"),
        "leader": i.get("f140"),
    } for i in items]
