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
        c = str(c).strip().upper()
        if c.startswith("US") or c.startswith("us"):
            prefixed.append(c.lower())  # 美股: usNVDA, usTSM
        elif len(c) == 5:
            prefixed.append(f"hk{c}")   # 港股
        elif c.startswith(("5", "6", "9")):
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
            if len(vals) < 10:
                continue
                continue
            code = raw_code[2:]  # 去 sh/sz/bj/hk 前缀
            def sf(v):  # safe float
                try: return float(v) if v else 0.0
                except ValueError: return 0.0

            result[code] = {
                "name": vals[1],
                "price": sf(vals[3]),
                "last_close": sf(vals[4]),
                "change_pct": sf(vals[32]),
                "high": sf(vals[33]),
                "low": sf(vals[34]),
                "amount_wan": sf(vals[37]),
                "turnover_pct": sf(vals[38]),
                "pe_ttm": sf(vals[39]),
                "amplitude_pct": sf(vals[43]),
                "mcap_yi": sf(vals[45]),
                "float_mcap_yi": sf(vals[44]),
                "pb": sf(vals[46]),
                "limit_up": sf(vals[47]),
                "limit_down": sf(vals[48]),
                "vol_ratio": sf(vals[49]),
                "pe_static": sf(vals[52]),
            }
        except (ValueError, IndexError):
            continue

    return result
