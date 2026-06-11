"""StockInfoAdapter — 股票基本信息数据适配层

DB 标准字段口径:
  total_shares  : float   总股本(股)    — 个股市数量级 1e7~1e11
  float_shares  : float   流通股本(股)  — 个股市数量级 1e7~1e11

数据源链路 (按优先级):
  ① push2 f84/f85    → 最权威, 但部分网络环境不可达
  ② Tencent fields 74/73 → 可靠备用, 单位 股
  ③ akshare 总股本/流通股 → 同 push2 同源, 最后兜底

  push2 f116 → 总市值(元)  push2 f189 → 上市日期
"""
import asyncio
import re
from typing import Optional

from app.framework.logger import logger

_EM_UT = "fa5fd1943c7b386f172d6893dbfba10b"

# 腾讯行情已知字段索引 (sz/sh 格式一致):
#   field 73 = 流通股本(股), field 74 = 总股本(股)
_TENCENT_FIELD_TOTAL = 73
_TENCENT_FIELD_FLOAT = 72


async def _fetch_push2_stock(code: str, fields: str) -> Optional[dict]:
    """调东方财富 push2 个股详情 API (带 ut 参数) — 短超时, 不重试"""
    import requests
    market_code = 1 if code.startswith("6") else 0
    try:
        resp = await asyncio.to_thread(
            requests.get,
            "https://push2.eastmoney.com/api/qt/stock/get",
            params={"ut": _EM_UT, "fltt": "2", "invt": "2",
                    "fields": fields, "secid": f"{market_code}.{code}"},
            timeout=1.5, verify=False,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        if resp.status_code == 200:
            data = resp.json().get("data")
            if data:
                return data
    except Exception:
        pass
    return None


async def _fetch_tencent_shares(code: str) -> Optional[dict]:
    """从腾讯行情提取总股本/流通股本 (单位:股)

    A 股 fields: total=73 (0-indexed), float=72
    HK 股 fields: total=69, float=70
    """
    import requests
    # 确定交易所前缀
    # 确定交易所前缀 (A股6位代码, 港股5位)
    if len(code) == 6:
        prefix = "sh" if code[0] in ("5", "6") else "sz"
    else:
        prefix = "hk"
    is_hk = prefix == "hk"
    total_field = 69 if is_hk else 73
    float_field = 70 if is_hk else 72
    try:
        resp = await asyncio.to_thread(
            requests.get,
            f"https://qt.gtimg.cn/q={prefix}{code}",
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        if resp.status_code != 200:
            return None
        text = resp.text
        m = re.search(r'"(.*)"', text)
        if not m:
            return None
        parts = m.group(1).split("~")
        total = float(parts[total_field]) if len(parts) > total_field and parts[total_field].strip() else None
        floats = float(parts[float_field]) if len(parts) > float_field and parts[float_field].strip() else None
        if total or floats:
            return {"total_shares": total, "float_shares": floats}
    except Exception:
        pass
    return None


async def get_total_shares(code: str) -> Optional[float]:
    """获取总股本(股) — 链路: push2 → Tencent → akshare"""
    # 源①: push2 f84
    d = await _fetch_push2_stock(code, "f57,f84,f85,f116")
    if d and d.get("f84"):
        return float(d["f84"])

    # 源②: Tencent field 74
    tc = await _fetch_tencent_shares(code)
    if tc and tc.get("total_shares"):
        return tc["total_shares"]

    # 源③: akshare 兜底
    if len(code) == 6:
        try:
            import akshare as ak
            df = await asyncio.to_thread(ak.stock_individual_info_em, symbol=code)
            if df is not None and not df.empty:
                items = dict(zip(df['item'], df['value']))
                if items.get('总股本'):
                    return float(items['总股本'])
        except Exception:
            pass
    return None


async def get_float_shares(code: str) -> Optional[float]:
    """获取流通股本(股) — 链路: push2 → Tencent → akshare"""
    # 源①: push2 f85
    d = await _fetch_push2_stock(code, "f57,f85")
    if d and d.get("f85"):
        return float(d["f85"])

    # 源②: Tencent field 73
    tc = await _fetch_tencent_shares(code)
    if tc and tc.get("float_shares"):
        return tc["float_shares"]

    # 源③: akshare 兜底
    if len(code) == 6:
        try:
            import akshare as ak
            df = await asyncio.to_thread(ak.stock_individual_info_em, symbol=code)
            if df is not None and not df.empty:
                items = dict(zip(df['item'], df['value']))
                if items.get('流通股'):
                    return float(items['流通股'])
        except Exception:
            pass
    return None
