"""投研数据加载器 — 为 Agent 提供统一的数据查询接口"""
from typing import List, Dict, Any, Optional
from app.framework.database.session import async_session
from app.models.models import (
    StockMaster, StockValuation, MarketData, Position, ExchangeRate, MacroHistory
)
from sqlalchemy import select, func, desc
from app.framework.logger import logger


class ResearchDataLoader:
    """投研数据加载器 — 封装所有数据库查询, 供 Agent 调用"""

    async def load_market_data(self, codes: List[str], days: int = 60) -> Dict[str, List[Dict]]:
        """加载行情数据 (近N天日线)"""
        if not codes:
            return {}
        result = {}
        async with async_session() as db:
            for code in codes:
                rows = await db.execute(
                    select(MarketData)
                    .where(MarketData.stock_code == code)
                    .order_by(MarketData.trade_date.desc())
                    .limit(days)
                )
                result[code] = [
                    {"date": str(r.trade_date), "open": r.open, "high": r.high,
                     "low": r.low, "close": r.close, "volume": r.volume,
                     "change_pct": r.change_pct}
                    for r in rows.scalars().all()
                ]
        return result

    async def load_macro_latest(self, codes: Optional[List[str]] = None) -> Dict[str, Dict]:
        """加载最新的宏观经济数据和基本行情 (快照)"""
        result = {}
        async with async_session() as db:
            query = select(ExchangeRate)
            if codes:
                query = query.where(ExchangeRate.code.in_(codes))
            rows = await db.execute(query)
            for r in rows.scalars().all():
                result[r.code] = {
                    "name": r.name,
                    "price": float(r.rate) if r.rate is not None else None,
                    "change_pct": float(r.change_pct) if r.change_pct is not None else None,
                    "biz_date": str(r.biz_date) if r.biz_date else None,
                    "updated_at": str(r.updated_at)
                }
        return result

    async def load_macro_history(self, code: str, days: int = 365) -> List[Dict]:
        """加载特定宏观指标的历史时间序列"""
        result = []
        async with async_session() as db:
            rows = await db.execute(
                select(MacroHistory)
                .where(MacroHistory.code == code)
                .order_by(MacroHistory.obs_date.desc())
                .limit(days)
            )
            for r in rows.scalars().all():
                result.append({
                    "date": str(r.obs_date),
                    "value": float(r.value)
                })
        # 返回按时间正序排列的序列
        return result[::-1]

    async def load_fundamentals(self, codes: List[str]) -> Dict[str, Dict]:
        """加载基本面 (名称/行业/PE/PB/市值/ROE) — 从 StockMaster + StockValuation"""
        if not codes:
            return {}
        async with async_session() as db:
            from sqlalchemy import outerjoin
            j = outerjoin(StockMaster, StockValuation,
                          StockMaster.stock_code == StockValuation.stock_code)
            rows = await db.execute(
                select(StockMaster, StockValuation)
                .select_from(j)
                .where(StockMaster.stock_code.in_(codes))
            )
            result = {}
            for r in rows.all():
                m, v = r  # tuple: (StockMaster row, StockValuation row or None)
                result[m.stock_code] = {
                    "name": m.stock_name, "exchange": m.exchange,
                    "pe_ttm": v.pe_ttm if v else None,
                    "pb": v.pb if v else None,
                    "mcap_yi": v.mcap_yi if v else None,
                    "industry": m.industry,
                    "roe": v.roe if v else None,
                    "dividend_yield": v.dividend_yield if v else None,
                    "eps_growth_3y": v.eps_growth_3y if v else None,
                }
            return result

    async def load_indicators(self, codes: List[str]) -> Dict[str, Dict]:
        """加载最新技术指标 (SQLite)，支持遭遇新股票时 JIT(Just-In-Time) 现场计算"""
        if not codes:
            return {}
        from app.domain.quant.engine import indicator_store
        from app.domain.quant.engine.indicator_runner import IndicatorRunner
        from app.domain.quant.engine.engine import QuantEngine
        
        result = {}
        rows = indicator_store.get_latest_for_codes(list(codes))
        found_codes = set()
        
        for row in rows:
            code = row.get("stock_code")
            if code:
                found_codes.add(code)
                result[code] = {
                    "date": row.get("trade_date"),
                    "snapshot": row,
                }
                
        # JIT: 处理本地未命中的标的 (新探索标的)
        missing_codes = set(codes) - found_codes
        if missing_codes:
            logger.info(f"[JIT] Missing indicators for {missing_codes}, triggering live compute...")
            async with async_session() as db:
                engine = QuantEngine(db)
                for code in missing_codes:
                    # 1. 尝试强行拉取最新几天的基础日线 (兜底)
                    await engine.sync_market_data(code, mode="FORCE")
                    # 2. 触发历史计算
                    await IndicatorRunner.compute_historical(code)
            
            # 3. JIT 补全基本信息: 从 MarketData 新增代码中同步到 StockMaster
            from app.domain.market_data.services.stock_list import sync_stock_list
            await sync_stock_list()
                    
            # 重新查一次
            new_rows = indicator_store.get_latest_for_codes(list(missing_codes))
            for row in new_rows:
                code = row.get("stock_code")
                if code:
                    result[code] = {
                        "date": row.get("trade_date"),
                        "snapshot": row,
                    }
        return result

    async def load_indicators_timeseries(self, codes: List[str], fields: List[str] = None, days: int = 10) -> Dict[str, Dict]:
        """加载过去 N 天的连续量价指标时序序列 (支持趋势和背离分析)"""
        if not codes:
            return {}
        # 预触发 JIT 数据补全
        await self.load_indicators(codes)
        
        from app.domain.quant.engine import indicator_store
        result = {}
        if not fields:
            from app.domain.quant.engine.indicator_store import INDICATOR_ALL_COLS
            fields = INDICATOR_ALL_COLS()
            
        for code in codes:
            history = indicator_store.get_history(code, fields, days=days)
            if history and history.get("dates"):
                # 只保留最后 N 天
                dates = history["dates"][-days:]
                trimmed_fields = {k: v[-days:] for k, v in history["fields"].items()}
                result[code] = {"dates": dates, "fields": trimmed_fields}
        return result

    async def load_positions(self) -> List[Dict]:
        """加载当前持仓 (名称从 StockMaster 获取)"""
        async with async_session() as db:
            rows = await db.execute(
                select(Position, StockMaster.stock_name)
                .outerjoin(StockMaster, Position.stock_code == StockMaster.stock_code)
            )
            return [
                {
                    "stock_code": p.Position.stock_code, "stock_name": p.stock_name or p.Position.stock_code,
                    "volume": p.Position.volume, "avg_cost": p.Position.avg_cost,
                    "current_price": p.Position.current_price, "market_value": p.Position.market_value,
                    "profit_loss": p.Position.profit_loss, "profit_loss_ratio": p.Position.profit_loss_ratio,
                }
                for p in rows.all()
            ]

    async def load_sector_overview(self, industry: str) -> Dict:
        """加载行业概览 (该行业所有股票的估值汇总) — from StockMaster + StockValuation"""
        async with async_session() as db:
            from sqlalchemy import outerjoin
            j = outerjoin(StockMaster, StockValuation,
                          StockMaster.stock_code == StockValuation.stock_code)
            rows = await db.execute(
                select(StockMaster, StockValuation)
                .select_from(j)
                .where(StockMaster.industry.isnot(None))
            )
            all_stocks = []
            for r in rows.all():
                m, v = r
                if industry in (m.industry or ""):
                    all_stocks.append({
                        "code": m.stock_code, "name": m.stock_name,
                        "pe_ttm": v.pe_ttm if v else None,
                        "pb": v.pb if v else None,
                        "mcap_yi": v.mcap_yi if v else None,
                    })

            pe_values = [s["pe_ttm"] for s in all_stocks if s["pe_ttm"] and s["pe_ttm"] > 0]
            pb_values = [s["pb"] for s in all_stocks if s["pb"] and s["pb"] > 0]
            return {
                "count": len(all_stocks),
                "avg_pe": sum(pe_values) / len(pe_values) if pe_values else None,
                "avg_pb": sum(pb_values) / len(pb_values) if pb_values else None,
                "stocks": all_stocks[:20],
            }

    async def search_stocks(self, keyword: str, limit: int = 20) -> List[Dict]:
        """搜索股票 (代码/名称模糊匹配) — from StockMaster"""
        async with async_session() as db:
            rows = await db.execute(
                select(StockMaster.stock_code, StockMaster.stock_name, StockMaster.exchange)
                .where(
                    StockMaster.stock_code.like(f"%{keyword}%") |
                    StockMaster.stock_name.like(f"%{keyword}%")
                )
                .limit(limit)
            )
            return [{"code": r[0], "name": r[1], "exchange": r[2]} for r in rows.all()]

    async def load_macro(self) -> Dict:
        """加载宏观数据 (汇率/金/银/油)"""
        async with async_session() as db:
            rows = await db.execute(select(ExchangeRate))
            return {
                r.code: {"name": r.name, "price": r.rate, "change_pct": r.change_pct}
                for r in rows.scalars().all()
            }

    async def search_industry_stocks(self, keyword: str) -> List[Dict]:
        """搜索行业内所有标的 — from StockMaster + StockValuation"""
        async with async_session() as db:
            from sqlalchemy import outerjoin
            j = outerjoin(StockMaster, StockValuation,
                          StockMaster.stock_code == StockValuation.stock_code)
            rows = await db.execute(
                select(StockMaster, StockValuation)
                .select_from(j)
                .where(StockMaster.industry.isnot(None))
            )
            matched = []
            for r in rows.all():
                m, v = r
                if keyword in (m.industry or ""):
                    matched.append({
                        "code": m.stock_code, "name": m.stock_name,
                        "industry": m.industry,
                        "pe_ttm": v.pe_ttm if v else None,
                        "pb": v.pb if v else None,
                        "mcap_yi": v.mcap_yi if v else None,
                    })
            return matched

    async def load_financials(self, codes: List[str]) -> Dict[str, Dict]:
        """加载财务数据 — PE/PB/市值 (akshare优先, tushare兜底)"""
        result = await self.load_fundamentals(codes)
        # Tushare 兜底: 补充缺失的估值数据
        from app.domain.market_data.sources.tushare_provider import TushareProvider
        if TushareProvider.available():
            for code in codes:
                if code not in result or not result[code].get('pe_ttm'):
                    try:
                        df = await TushareProvider.get_daily_basic(code, days=5)
                        if not df.empty:
                            latest = df.iloc[-1]
                            result[code] = {
                                'pe_ttm': float(latest.get('pe_ttm', 0) or 0),
                                'pb': float(latest.get('pb', 0) or 0),
                                'mcap_yi': float(latest.get('total_mv', 0) or 0) / 1e4,
                            }
                    except Exception:
                        pass
        return result

    async def load_financial_statements(self, code: str, periods: int = 8) -> Dict[str, Any]:
        """获取单只股票连续 N 个季度的三大表核心字段 (V4.0 数据底座)

        Args:
            code: 股票代码 (6位如 600519, 或含前缀如 SH600519)
            periods: 季度数, 默认 8Q

        Returns:
            {"code": "600519", "quarters": [
                {"report_date": "2024-03-31", "revenue": ..., "profit": ...,
                 "op_cashflow": ..., "inventory": ..., "contract_liability": ...},
                ...
            ]}
        """
        # DB 优先: 查 financial_statements 表
        from app.models.models import FinancialStatement
        async with async_session() as db:
            res = await db.execute(
                select(FinancialStatement)
                .where(FinancialStatement.stock_code == code)
                .order_by(FinancialStatement.report_date.desc())
                .limit(periods)
            )
            rows = res.scalars().all()
            if len(rows) >= 4:
                quarters = [{
                    "report_date": str(r.report_date),
                    "revenue": float(r.revenue or 0), "profit": float(r.parent_profit or 0),
                    "operate_cost": float(r.operate_cost or 0), "op_cashflow": float(r.op_cashflow or 0),
                    "inventory": float(r.inventory or 0), "contract_liability": float(r.contract_liability or 0),
                    "accounts_receivable": float(r.accounts_receivable or 0),
                    "total_assets": float(r.total_assets or 0), "current_assets": float(r.current_assets or 0),
                    "fixed_assets": float(r.fixed_assets or 0), "total_liabilities": float(r.total_liabilities or 0),
                    "total_equity": float(r.total_equity or 0),
                    "sale_expense": float(r.sale_expense or 0), "manage_expense": float(r.manage_expense or 0),
                    "rd_expense": float(r.rd_expense or 0),
                    "cash": float(r.cash or 0), "current_liabilities": float(r.current_liabilities or 0),
                    "short_loan": float(r.short_loan or 0), "long_loan": float(r.long_loan or 0),
                    "accounts_payable": float(r.accounts_payable or 0), "noncurrent_liab_1year": float(r.noncurrent_liab_1year or 0),
                } for r in rows]
                return {"code": code, "quarters": quarters, "source": "DB"}

        # JIT: 如果本地没有足够数据，调用复用的同步方法
        from app.domain.market_data.services.financial_sync import sync_financials
        logger.info(f"[Financial] Local data missing for {code}, triggering JIT financial sync...")
        sync_res = await sync_financials(code)
        
        if "error" in sync_res and sync_res["error"]:
            logger.warning(f"[Financial] JIT sync failed for {code}: {sync_res['error']}")
            return {"code": code, "quarters": [], "error": sync_res["error"]}
            
        # 重新查库返回数据
        async with async_session() as db:
            res = await db.execute(
                select(FinancialStatement)
                .where(FinancialStatement.stock_code == code)
                .order_by(FinancialStatement.report_date.desc())
                .limit(periods)
            )
            rows = res.scalars().all()
            quarters = [{
                "report_date": str(r.report_date),
                "revenue": float(r.revenue or 0), "profit": float(r.parent_profit or 0),
                "operate_cost": float(r.operate_cost or 0), "op_cashflow": float(r.op_cashflow or 0),
                "inventory": float(r.inventory or 0), "contract_liability": float(r.contract_liability or 0),
                "accounts_receivable": float(r.accounts_receivable or 0),
                "total_assets": float(r.total_assets or 0), "current_assets": float(r.current_assets or 0),
                "fixed_assets": float(r.fixed_assets or 0), "total_liabilities": float(r.total_liabilities or 0),
                "total_equity": float(r.total_equity or 0),
                "sale_expense": float(r.sale_expense or 0), "manage_expense": float(r.manage_expense or 0),
                "rd_expense": float(r.rd_expense or 0),
                "cash": float(r.cash or 0), "current_liabilities": float(r.current_liabilities or 0),
                "short_loan": float(r.short_loan or 0), "long_loan": float(r.long_loan or 0),
                "accounts_payable": float(r.accounts_payable or 0), "noncurrent_liab_1year": float(r.noncurrent_liab_1year or 0),
            } for r in rows]
            logger.info(f"[Financial] Loaded {len(quarters)} quarters for {code} after JIT sync")
            return {"code": code, "quarters": quarters, "source": "JIT-Akshare"}

    @staticmethod
    def _code_to_akshare_prefix(code: str) -> Optional[str]:
        """转换股票代码为 akshare 前缀格式"""
        c = str(code).strip().upper()
        if c.startswith("SH") or c.startswith("SZ") or c.startswith("BJ"):
            return c
        if len(c) == 6:
            if c.startswith(("5", "6", "9")):
                return f"SH{c}"
            elif c.startswith(("0", "2", "3")):
                return f"SZ{c}"
            elif c.startswith(("4", "8")):
                return f"BJ{c}"
        return None

    @staticmethod
    def _fetch_income_sheet(prefix: str):
        """获取单季度利润表 → 营收/利润/营业成本/销售费用/管理费用"""
        import akshare as ak
        import pandas as pd
        df = ak.stock_profit_sheet_by_quarterly_em(symbol=prefix)
        df = df.rename(columns={
            "OPERATE_INCOME": "revenue",
            "PARENT_NETPROFIT": "profit",
            "OPERATE_COST": "operate_cost",
            "SALE_EXPENSE": "sale_expense",
            "MANAGE_EXPENSE": "manage_expense",
        })
        df["REPORT_DATE"] = pd.to_datetime(df["REPORT_DATE"])
        cols = ["REPORT_DATE", "revenue", "profit", "operate_cost", "sale_expense", "manage_expense"]
        missing = [c for c in cols if c not in df.columns]
        if missing: logger.warning(f"[Financial] Income sheet missing columns: {missing}")
        return df[[c for c in cols if c in df.columns]].dropna(subset=["revenue"])

    @staticmethod
    def _fetch_cashflow_sheet(prefix: str):
        """获取单季度现金流量表 → 经营活动现金流量净额"""
        import akshare as ak
        import pandas as pd
        df = ak.stock_cash_flow_sheet_by_quarterly_em(symbol=prefix)
        df = df.rename(columns={"NETCASH_OPERATE": "op_cashflow"})
        df["REPORT_DATE"] = pd.to_datetime(df["REPORT_DATE"])
        return df[["REPORT_DATE", "op_cashflow"]]

    @staticmethod
    def _fetch_balance_sheet(prefix: str):
        """获取资产负债表(按报告期) → 资产/负债/权益核心字段"""
        import akshare as ak
        import pandas as pd
        df = ak.stock_balance_sheet_by_report_em(symbol=prefix)
        df = df.rename(columns={
            "INVENTORY": "inventory",
            "CONTRACT_LIAB": "contract_liability",
            "ACCOUNTS_RECE": "accounts_receivable",
            "TOTAL_ASSETS": "total_assets",
            # V5.11 fix: TOTAL_CURRENT_ASSETS 而非 CURRENT_ASSET_BALANCE (后者为0/垃圾值)
            "TOTAL_CURRENT_ASSETS": "current_assets",
            "FIXED_ASSET": "fixed_assets",
            "TOTAL_LIABILITIES": "total_liabilities",
            "TOTAL_EQUITY": "total_equity",
            # ★ V5.11 新增: ROIIC/ROIC 精确计算
            "MONETARYFUNDS": "cash",
            "TOTAL_CURRENT_LIAB": "current_liabilities",
            "SHORT_LOAN": "short_loan",
            "LONG_LOAN": "long_loan",
            "ACCOUNTS_PAYABLE": "accounts_payable",
            "NONCURRENT_LIAB_1YEAR": "noncurrent_liab_1year",
        })
        df["REPORT_DATE"] = pd.to_datetime(df["REPORT_DATE"])
        cols = ["REPORT_DATE", "inventory", "contract_liability",
                "accounts_receivable", "total_assets", "current_assets",
                "fixed_assets", "total_liabilities", "total_equity",
                "cash", "current_liabilities", "short_loan",
                "long_loan", "accounts_payable", "noncurrent_liab_1year"]
        return df[[c for c in cols if c in df.columns]]

    @staticmethod
    def _merge_financial_sheets(income_df, cashflow_df, balance_df, periods: int):
        """合并三表, 取最近 N 个季度"""
        import pandas as pd
        merged = income_df.sort_values("REPORT_DATE")
        if cashflow_df is not None and not cashflow_df.empty:
            merged = merged.merge(cashflow_df, on="REPORT_DATE", how="left")
        else:
            merged["op_cashflow"] = 0
        if balance_df is not None and not balance_df.empty:
            merged = merged.merge(balance_df, on="REPORT_DATE", how="left")
        else:
            merged["inventory"] = 0
            merged["contract_liability"] = 0
        for col in ["op_cashflow", "inventory", "contract_liability"]:
            if col not in merged.columns:
                merged[col] = 0
        return merged.tail(periods)

    async def load_capital_flow(self, code: str, days: int = 30) -> List[Dict]:
        """加载个股资金流向 (主力/散户/超大单)"""
        try:
            from app.domain.market_data.sources.push2 import get_capital_flow
            return await get_capital_flow(code, days)
        except Exception as e:
            logger.warning(f"[Capital flow load failed for {code}: {e}]")
            return []


    async def search_web(self, query: str, num: int = 5) -> List[Dict]:
        """网络搜索 — Brave + Tavily 双源并行 → DDG (免费兜底)
        通过 Clash 代理 (127.0.0.1:7890) 访问海外服务。
        Brave: 英文/全球视野, 速度快, 独立30B+索引
        Tavily: AI优化, 结构化输出, 免费1000次/月
        """
        from app.framework.config import settings
        import asyncio
        CLASH_PROXY = "http://127.0.0.1:7890"
        all_results = []

        async def _search_brave():
            if not settings.BRAVE_API_KEY:
                return []
            try:
                import httpx
                url = "https://api.search.brave.com/res/v1/web/search"
                headers = {
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": settings.BRAVE_API_KEY,
                }
                params = {"q": query, "count": min(num, 10)}
                async with httpx.AsyncClient(proxy=CLASH_PROXY, timeout=15.0) as client:
                    resp = await client.get(url, headers=headers, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        results = []
                        for r in (data.get("web", {}).get("results", []) or [])[:num]:
                            results.append({
                                "title": r.get("title", "")[:150],
                                "url": r.get("url", ""),
                                "snippet": r.get("description", "")[:400],
                                "source": "brave",
                            })
                        if results:
                            logger.info(f"[Brave] {len(results)} results for '{query[:40]}'")
                        return results
                    else:
                        logger.warning(f"[Brave] HTTP {resp.status_code}: {resp.text[:100]}")
            except Exception as e:
                logger.warning(f"[Brave] Failed: {type(e).__name__}: {e}")
            return []

        async def _search_tavily():
            if not settings.TAVILY_API_KEY:
                return []
            try:
                import httpx
                url = "https://api.tavily.com/search"
                headers = {"Content-Type": "application/json"}
                body = {
                    "api_key": settings.TAVILY_API_KEY,
                    "query": query,
                    "max_results": min(num, 10),
                    "search_depth": "basic",
                    "include_answer": False,
                }
                async with httpx.AsyncClient(proxy=CLASH_PROXY, timeout=20.0) as client:
                    resp = await client.post(url, headers=headers, json=body)
                    if resp.status_code == 200:
                        data = resp.json()
                        results = []
                        for r in (data.get("results", []) or [])[:num]:
                            results.append({
                                "title": r.get("title", "")[:150],
                                "url": r.get("url", ""),
                                "snippet": r.get("content", "")[:400],
                                "source": "tavily",
                            })
                        if results:
                            logger.info(f"[Tavily] {len(results)} results for '{query[:40]}'")
                        return results
                    else:
                        logger.warning(f"[Tavily] HTTP {resp.status_code}: {resp.text[:100]}")
            except Exception as e:
                logger.warning(f"[Tavily] Failed: {type(e).__name__}: {e}")
            return []

        # 双源并行搜索
        brave_results, tavily_results = await asyncio.gather(
            _search_brave(), _search_tavily()
        )

        # 合并去重 (按 URL)
        seen_urls = set()
        for r in brave_results + tavily_results:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append(r)

        if all_results:
            logger.info(f"[Search] Merged {len(brave_results)}B + {len(tavily_results)}T → {len(all_results)} unique for '{query[:40]}'")
            return all_results[:num]

        # 2. DDG 兜底 (Brave+Tavily 均失败时)
        try:
            import re, httpx
            url = "https://html.duckduckgo.com/html/"
            data = {"q": query}
            async with httpx.AsyncClient(proxy=CLASH_PROXY, timeout=15.0,
                    headers={"User-Agent": "Mozilla/5.0"}) as client:
                resp = await client.post(url, data=data)
                if resp.status_code == 200:
                    results = []
                    links = re.findall(r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', resp.text)
                    snippets = re.findall(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', resp.text)
                    for i, (url, title) in enumerate(links[:num]):
                        title_clean = re.sub(r'<[^>]+>', '', title).strip()
                        snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip() if i < len(snippets) else ""
                        if title_clean:
                            results.append({"title": title_clean[:150], "url": url, "snippet": snippet[:300]})
                    if results:
                        logger.info(f"[DDG search OK: {len(results)} results for '{query[:40]}']")
                        return results
                else:
                    logger.warning(f"[DDG returned {resp.status_code}]")
        except Exception as e:
            logger.warning(f"[DDG search failed: {type(e).__name__}: {e}]")

        return []

    async def scrape_url(self, url: str) -> Dict:
        """抓取单个URL并抽取正文"""
        from app.domain.research.services.web_scraper import WebScraper
        return await WebScraper.fetch_and_extract(url)

    async def scrape_urls(self, urls: List[str]) -> List[Dict]:
        """批量抓取多个URL"""
        from app.domain.research.services.web_scraper import WebScraper
        return await WebScraper.batch_fetch(urls)

    async def deep_research(self, query: str, rounds: int = 3) -> Dict:
        """多轮深研 — 初始搜索 → 提取关键线索 → 逐轮深入"""
        all_sources = []
        current_query = query

        for r in range(rounds):
            results = await self.search_web(current_query, num=5)
            if not results:
                break
            all_sources.append({"round": r + 1, "query": current_query, "results": results})
            # 从结果中提取关键词做下一轮搜索
            if r < rounds - 1:
                keywords = []
                for res in results[:3]:
                    words = res.get("snippet", "").split()[:5]
                    keywords.extend(words)
                if keywords:
                    # 用前3个最长的词作为下轮搜索关键词
                    long_words = sorted(set(w for w in keywords if len(w) > 3), key=len, reverse=True)[:3]
                    current_query = f"{query} {' '.join(long_words)}"

        return {"original_query": query, "rounds": rounds, "sources": all_sources,
                "total_sources": sum(len(s["results"]) for s in all_sources)}

    # ═══════════════════════════════════════════
    # 另类数据接口 (Alternative Data) - JIT
    # ═══════════════════════════════════════════

    _patent_cache = {}
    _physics_cache = {}

    async def load_patent_vectors(self, code: str, company_name: str) -> Dict[str, float]:
        """按需(JIT)拉取公司的专利 IPC 分类向量，含简易内存缓存防护"""
        if code in self._patent_cache:
            return self._patent_cache[code]
            
        from app.domain.market_data.sources.patent_provider import GlobalPatentAggregator
        import asyncio
        
        aggregator = GlobalPatentAggregator()
        try:
            # 限制拉取时间，防止阻塞整个推演流
            vectors = await asyncio.wait_for(
                aggregator.get_aggregated_ipc_vectors(company_name), timeout=15.0
            )
            self._patent_cache[code] = vectors
            return vectors
        except asyncio.TimeoutError:
            logger.warning(f"[Alternative] Patent fetching timed out for {company_name}")
            return {}
        except Exception as e:
            logger.error(f"[Alternative] Patent fetching failed for {company_name}: {e}")
            return {}

    async def load_physical_parameters(self, query: str, keys: List[str]) -> Dict[str, Optional[float]]:
        """按需(JIT)全网搜索获取最新的硬科技物理/经济学参数"""
        cache_key = f"{query}_{','.join(keys)}"
        if cache_key in self._physics_cache:
            return self._physics_cache[cache_key]
            
        from app.domain.quant.data.physical_extractor import PhysicalParameterExtractor
        from app.framework.ai.providers.deepseek import DeepSeekProvider
        import asyncio
        
        provider = DeepSeekProvider()
        extractor = PhysicalParameterExtractor(provider)
        try:
            result = await asyncio.wait_for(
                extractor.extract_parameters(query, keys), timeout=30.0
            )
            self._physics_cache[cache_key] = result
            return result
        except asyncio.TimeoutError:
            logger.warning(f"[Alternative] Physics extracting timed out for '{query}'")
            return {k: None for k in keys}
        except Exception as e:
            logger.error(f"[Alternative] Physics extracting failed: {e}")
            return {k: None for k in keys}


# 全局单例
data_loader = ResearchDataLoader()
