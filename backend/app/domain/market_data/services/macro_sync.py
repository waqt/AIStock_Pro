import asyncio
import httpx
import pandas as pd
import math
from datetime import datetime as dt, date as d
from sqlalchemy import select, func
from sqlalchemy.dialects.mysql import insert as mysql_insert
from app.framework.database.session import async_session
from app.models.models import MacroHistory, ExchangeRate
from app.framework.logger import logger

def _clean_date(x):
    """清洗带有中文年/月/日的日期"""
    s = str(x)
    return s.replace("年", "-").replace("月份", "").replace("月", "-").replace("日", "").strip("- ")

def _parse_biz_date(s: str):
    """解析业务日期, 兼容多种格式"""
    if not s: return None
    s = str(s).strip()
    try: return d.fromisoformat(s)
    except: pass
    import re
    m = re.match(r'(\d{4})\s*年\s*(\d{1,2})\s*月', s)
    if m:
        return d(int(m.group(1)), int(m.group(2)), 1)
    try: return d.fromisoformat(s[:10])
    except: pass
    return None

def _calc_latest_and_change(df: pd.DataFrame, date_col: str, val_col: str):
    """提取最新值、计算环比上一个周期的涨跌幅、提取业务日期"""
    try:
        df_clean = df.copy()
        df_clean[date_col] = df_clean[date_col].apply(_clean_date)
        df_clean[date_col] = pd.to_datetime(df_clean[date_col])
        df_clean = df_clean.dropna(subset=[val_col]).sort_values(date_col)
        
        if df_clean.empty:
            return None, None, None
            
        latest = df_clean.iloc[-1]
        val = float(latest[val_col])
        biz_d = str(latest[date_col])[:10]
        
        change_pct = None
        if len(df_clean) >= 2:
            prev_val = float(df_clean.iloc[-2][val_col])
            if prev_val != 0:
                change_pct = round((val - prev_val) / prev_val * 100, 4)
                
        return val, change_pct, biz_d
    except Exception as e:
        logger.warning(f"[_calc_latest_and_change] Error: {e}")
        return None, None, None

async def _sync_sina_history_task(code: str, symbol: str, is_forex: bool):
    try:
        import json
        if is_forex:
            url = f"https://vip.stock.finance.sina.com.cn/forex/api/jsonp.php/var/NewForexService.getDayKLine?symbol={symbol}"
        else:
            url = f"https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var/GlobalFuturesService.getGlobalFuturesDailyKLine?symbol={symbol}"
        
        async with httpx.AsyncClient(proxy=None, timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                text = resp.text
                if is_forex:
                    start = text.find('("') + 2
                    end = text.rfind('")')
                    if start > 1 and end > start:
                        data_str = text[start:end]
                        lines = [line.split(',') for line in data_str.split('|') if line]
                        records = []
                        for line in lines:
                            if len(line) >= 5:
                                records.append({'date': line[0], 'close': float(line[4])})
                        if records:
                            df = pd.DataFrame(records)
                            await _delta_sync_history(code, df, 'date', 'close')
                else:
                    start = text.find('([') + 1
                    end = text.rfind('])') + 1
                    if start > 0 and end > start:
                        json_str = text[start:end]
                        data = json.loads(json_str)
                        if data:
                            df = pd.DataFrame(data)
                            await _delta_sync_history(code, df, 'date', 'close')
    except Exception as e:
        logger.warning(f"[_sync_sina_history_task] Failed for {code}: {e}")

async def _delta_sync_history(code: str, df: pd.DataFrame, date_col: str, value_col: str):
    """通用差量同步函数：查询最大日期，切片后批量 INSERT IGNORE"""
    if df is None or df.empty: 
        return
    
    # 1. 查询数据库中该指标的最大日期
    async with async_session() as db:
        max_date_res = await db.execute(select(func.max(MacroHistory.obs_date)).where(MacroHistory.code == code))
        max_date = max_date_res.scalar()
    
    # 2. 格式化 DataFrame
    try:
        df = df.copy()
        if date_col not in df.columns:
            date_col = df.columns[0]
        if value_col not in df.columns:
            logger.warning(f"[_delta_sync] Value column {value_col} not found for {code}. Available: {list(df.columns)}")
            return
            
        df[date_col] = pd.to_datetime(df[date_col].apply(_clean_date)).dt.date
    except Exception as e:
        logger.warning(f"[_delta_sync] Date conversion failed for {code}: {e}")
        return
    
    # 3. 差量切片
    if max_date:
        df = df[df[date_col] > max_date]
        
    if df.empty:
        return
        
    # 4. 组装 Records
    records = []
    for _, row in df.iterrows():
        val = row.get(value_col)
        dt_val = row.get(date_col)
        if pd.isna(val) or pd.isna(dt_val): 
            continue
        try:
            val = float(val)
            if math.isnan(val) or math.isinf(val): 
                continue
            records.append({"code": code, "obs_date": dt_val, "value": val})
        except (ValueError, TypeError): 
            continue
        
    # 5. 批量落盘 (MySQL INSERT IGNORE)
    if records:
        try:
            async with async_session() as db:
                stmt = mysql_insert(MacroHistory).values(records).prefix_with("IGNORE")
                await db.execute(stmt)
                await db.commit()
            logger.info(f"[✅] {code} 增量同步完成: +{len(records)} 条新数据")
        except Exception as e:
            logger.error(f"[❌] {code} 增量写入失败: {e}")

async def sync_macro_data() -> dict:
    """宏观数据同步: 新浪实时(汇率/大宗) + akshare(美债/利率/PPI) (分离后的服务)"""
    result = {}

    # ── Phase 1: 新浪实时行情 ──
    symbols = {
        'DXY': 'hf_DINIW', 'XAU': 'hf_XAU', 'XAG': 'hf_XAG',
        'BRENT': 'hf_OIL', 'USD_CNY': 'fx_susdcny', 'HKD_CNY': 'fx_shkdcny',
    }
    try:
        codes = ','.join(symbols.values())
        url = f"http://hq.sinajs.cn/list={codes}"
        headers = {"Referer": "https://finance.sina.com.cn"}
        async with httpx.AsyncClient(proxy=None, timeout=10.0, headers=headers) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                text = resp.text
                for code, sina_code in symbols.items():
                    pattern = f'var hq_str_{sina_code}='
                    idx = text.find(pattern)
                    if idx < 0: continue
                    start = text.find('"', idx) + 1
                    end = text.find('"', start)
                    if end < 0: continue
                    fields = text[start:end].split(',')
                    if len(fields) < 2: continue
                    price, change_pct = None, None
                    try:
                        if sina_code.startswith('fx_'):
                            price = float(fields[1]) if fields[1] and fields[1] != '0.0000000000' else None
                            prev = float(fields[2]) if len(fields) > 2 and fields[2] else None
                            if price and prev and prev > 0:
                                change_pct = round((price - prev) / prev * 100, 4)
                        elif sina_code.startswith('hf_'):
                            price = float(fields[0]) if fields[0] and fields[0] != '0.0000' else None
                            prev = float(fields[1]) if len(fields) > 1 and fields[1] and fields[1] != '0.0000' else None
                            if price and prev and prev > 0:
                                change_pct = round((price - prev) / prev * 100, 4)
                    except (ValueError, IndexError): pass
                    if price:
                        # 对于实时数据，用当前时间作为 biz_date（如果前端需要统一的话，目前新浪不返回biz_date）
                        biz_d = dt.now().strftime('%Y-%m-%d')
                        result[code] = {'name': code, 'price': price, 'change_pct': change_pct, 'biz_date': biz_d}
                        
        # 同步历史序列
        history_tasks = []
        for code, sina_code in symbols.items():
            if code == 'DXY':
                history_tasks.append(_sync_sina_history_task(code, 'fx_sdiniw', True))
            elif sina_code.startswith('fx_'):
                history_tasks.append(_sync_sina_history_task(code, sina_code, True))
            elif sina_code.startswith('hf_'):
                history_tasks.append(_sync_sina_history_task(code, sina_code.replace('hf_', ''), False))
        if history_tasks:
            await asyncio.gather(*history_tasks)
            
    except Exception as e:
        logger.warning(f"[⚠️] Sina macro fetch failed: {e}")

    # ── Phase 2: akshare 宏观指标 ──
    try:
        import akshare as ak
        loop = asyncio.get_event_loop()

        # ── 中美债券收益率 ──
        try:
            df = await asyncio.wait_for(loop.run_in_executor(None, ak.bond_zh_us_rate), timeout=20.0)
            if df is not None and not df.empty:
                cols = list(df.columns)
                date_col = cols[0]
                col_map = {
                    'US10YT': '美国国债收益率10年',
                    'CN10YT': '中国国债收益率10年',
                    'US2Y': '美国国债收益率2年',
                    'CN2Y': '中国国债收益率2年',
                }
                for code, col_name in col_map.items():
                    if col_name in cols:
                        val, change_pct, biz_d = _calc_latest_and_change(df, date_col, col_name)
                        if val is not None and not math.isnan(val):
                            result[code] = {'name': code, 'price': val, 'change_pct': change_pct, 'biz_date': biz_d}
                            await _delta_sync_history(code, df, date_col, col_name)
        except Exception as e:
            logger.warning(f"[⚠️] bond_zh_us_rate fetch failed: {e}")

        # ── 美联储利率 ──
        try:
            df = await asyncio.wait_for(loop.run_in_executor(None, ak.macro_bank_usa_interest_rate), timeout=20.0)
            if df is not None and not df.empty:
                val_col = 'value' if 'value' in df.columns else df.columns[-2]
                date_c = df.columns[1] if len(df.columns) > 1 else df.columns[0]
                val, change_pct, biz_d = _calc_latest_and_change(df, date_c, val_col)
                if val is not None and not math.isnan(val):
                    result['US_FED_RATE'] = {'name': '美联储利率', 'price': val, 'change_pct': change_pct, 'biz_date': biz_d}
                    await _delta_sync_history('US_FED_RATE', df, date_c, val_col)
        except Exception as e:
            logger.warning(f"[⚠️] US_FED_RATE fetch failed: {e}")

        # ── 中国 LPR ──
        try:
            df = await asyncio.wait_for(loop.run_in_executor(None, ak.macro_china_lpr), timeout=20.0)
            if df is not None and not df.empty:
                date_c = df.columns[0]
                val, change_pct, biz_d = _calc_latest_and_change(df, date_c, 'LPR1Y')
                if val is not None and not math.isnan(val):
                    result['CN_LPR1Y'] = {'name': 'LPR 1年期', 'price': val, 'change_pct': change_pct, 'biz_date': biz_d}
                    await _delta_sync_history('CN_LPR1Y', df, date_c, 'LPR1Y')
        except Exception as e:
            logger.warning(f"[⚠️] CN_LPR1Y fetch failed: {e}")

        # ── 中国 M2 同比 ──
        try:
            df = await asyncio.wait_for(loop.run_in_executor(None, ak.macro_china_money_supply), timeout=20.0)
            if df is not None and not df.empty:
                m2_col = [c for c in df.columns if 'M2' in str(c) and '同比' in str(c)]
                date_c = df.columns[0]
                if m2_col and date_c:
                    val, change_pct, biz_d = _calc_latest_and_change(df, date_c, m2_col[0])
                    if val is not None and not math.isnan(val):
                        result['CN_M2_YOY'] = {'name': 'M2同比', 'price': val, 'change_pct': change_pct, 'biz_date': biz_d}
                        await _delta_sync_history('CN_M2_YOY', df, date_c, m2_col[0])
        except Exception as e:
            logger.warning(f"[⚠️] CN_M2_YOY fetch failed: {e}")

        # ── 中国 PMI ──
        try:
            df = await asyncio.wait_for(loop.run_in_executor(None, ak.macro_china_pmi), timeout=20.0)
            if df is not None and not df.empty:
                date_c = df.columns[0]
                for col, code in [('制造业', 'CN_PMI_MFG'), ('非制造业', 'CN_PMI_NONMFG')]:
                    mcol = [c for c in df.columns if col in str(c) and '同比' not in str(c)][:1]
                    if mcol:
                        val, change_pct, biz_d = _calc_latest_and_change(df, date_c, mcol[0])
                        if val is not None and not math.isnan(val):
                            result[code] = {'name': f'中国{col}PMI', 'price': val, 'change_pct': change_pct, 'biz_date': biz_d}
                            await _delta_sync_history(code, df, date_c, mcol[0])
        except Exception as e:
            logger.warning(f"[⚠️] CN_PMI fetch failed: {e}")

        # ── 美国 ISM PMI ──
        try:
            df = await asyncio.wait_for(loop.run_in_executor(None, ak.macro_usa_ism_pmi), timeout=20.0)
            if df is not None and not df.empty:
                if 'value' in df.columns:
                    date_c = 'date' if 'date' in df.columns else df.columns[0]
                    val, change_pct, biz_d = _calc_latest_and_change(df, date_c, 'value')
                    if val is not None and not math.isnan(val):
                        result['US_ISM_PMI'] = {'name': '美国ISM PMI', 'price': val, 'change_pct': change_pct, 'biz_date': biz_d}
                        await _delta_sync_history('US_ISM_PMI', df, date_c, 'value')
        except Exception as e:
            logger.warning(f"[⚠️] US_ISM_PMI fetch failed: {e}")

        # ── 美国 CPI 同比 ──
        try:
            df = await asyncio.wait_for(loop.run_in_executor(None, ak.macro_usa_cpi_yoy), timeout=20.0)
            if df is not None and not df.empty:
                if 'value' in df.columns:
                    date_c = 'date' if 'date' in df.columns else df.columns[0]
                    val, change_pct, biz_d = _calc_latest_and_change(df, date_c, 'value')
                    if val is not None and not math.isnan(val):
                        result['US_CPI_YOY'] = {'name': '美国CPI同比', 'price': val, 'change_pct': change_pct, 'biz_date': biz_d}
                        await _delta_sync_history('US_CPI_YOY', df, date_c, 'value')
        except Exception as e:
            logger.warning(f"[⚠️] US_CPI_YOY fetch failed: {e}")

        # ── 中国 CPI 同比 ──
        try:
            df = await asyncio.wait_for(loop.run_in_executor(None, ak.macro_china_cpi_yearly), timeout=20.0)
            if df is not None and not df.empty:
                if 'value' in df.columns:
                    date_c = 'date' if 'date' in df.columns else df.columns[0]
                    val, change_pct, biz_d = _calc_latest_and_change(df, date_c, 'value')
                    if val is not None and not math.isnan(val):
                        result['CN_CPI_YOY'] = {'name': '中国CPI同比', 'price': val, 'change_pct': change_pct, 'biz_date': biz_d}
                        await _delta_sync_history('CN_CPI_YOY', df, date_c, 'value')
        except Exception as e:
            logger.warning(f"[⚠️] CN_CPI_YOY fetch failed: {e}")

    except Exception as e:
        logger.warning(f"[⚠️] akshare macro fetch failed globally: {e}")

    # ── Phase 3: 写入 ExchangeRate 表 ──
    if result:
        try:
            async with async_session() as db:
                for code, info in result.items():
                    price = info['price']
                    if price is None or (isinstance(price, float) and math.isnan(price)):
                        continue
                    biz_d = info.get('biz_date')
                    biz_date = _parse_biz_date(biz_d) if biz_d else None
                    existing = await db.get(ExchangeRate, code)
                    if existing:
                        existing.rate = price
                        existing.change_pct = info.get('change_pct')
                        existing.biz_date = biz_date
                        existing.updated_at = dt.now()
                    else:
                        db.add(ExchangeRate(code=code, name=info.get('name', code),
                            rate=price, change_pct=info.get('change_pct'),
                            biz_date=biz_date))
                await db.commit()
            logger.info(f"[✅] Macro basic rates synced: {list(result.keys())}")
        except Exception as e:
            logger.error(f"[❌] ExchangeRate save failed: {e}")

    return result
