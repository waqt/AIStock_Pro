"""腾讯实时行情 — PE/PB/市值/换手率 (GBK编码)"""
import httpx
from typing import List, Dict, Optional
from app.framework.logger import logger


async def get_tencent_quotes(codes: List[str]) -> Dict[str, dict]:
    """批量获取腾讯行情 (PE/PB/市值/涨跌幅/换手率)
    返回: {code: {name, price, pe_ttm, pb, mcap_yi, change_pct, ...}}
    """
    if not codes:
        return {}

    # 构造腾讯前缀
    prefixed = []
    for c in codes:
        c = str(c).strip()
        if len(c) == 5:
            prefixed.append(f"hk{c}")  # 港股 (5位代码)
        elif c.startswith(("6", "9")):
            prefixed.append(f"sh{c}")
        else:
            prefixed.append(f"sz{c}")

    url = f"https://qt.gtimg.cn/q={','.join(prefixed)}"
    try:
        async with httpx.AsyncClient(proxy=None, timeout=10.0,
                                      headers={"User-Agent": "Mozilla/5.0"}) as client:
            resp = await client.get(url)
            # GBK 解码
            text = resp.content.decode("gbk", errors="replace")
    except Exception as e:
        logger.warning(f"[Tencent quote fetch failed: {e}]")
        return {}

    result = {}
    for line in text.strip().split(";"):
        if "=" not in line or '"' not in line:
            continue
        try:
            raw_code = line.split("=")[0].split("_")[-1]
            vals = line.split('"')[1].split("~")
            if len(vals) < 53:
                continue
            code = raw_code[2:]  # 去 sh/sz/bj/hk 前缀
            result[code] = {
                "name": vals[1],
                "price": float(vals[3]) if vals[3] else 0.0,
                "last_close": float(vals[4]) if vals[4] else 0.0,
                "change_pct": float(vals[32]) if vals[32] else 0.0,
                "high": float(vals[33]) if vals[33] else 0.0,
                "low": float(vals[34]) if vals[34] else 0.0,
                "amount_wan": float(vals[37]) if vals[37] else 0.0,
                "turnover_pct": float(vals[38]) if vals[38] else 0.0,
                "pe_ttm": float(vals[39]) if vals[39] else 0.0,
                "amplitude_pct": float(vals[43]) if vals[43] else 0.0,
                "mcap_yi": float(vals[44]) if vals[44] else 0.0,
                "float_mcap_yi": float(vals[45]) if vals[45] else 0.0,
                "pb": float(vals[46]) if vals[46] else 0.0,
                "limit_up": float(vals[47]) if vals[47] else 0.0,
                "limit_down": float(vals[48]) if vals[48] else 0.0,
                "vol_ratio": float(vals[49]) if vals[49] else 0.0,
                "pe_static": float(vals[52]) if vals[52] else 0.0,
            }
        except (ValueError, IndexError):
            continue

    return result
