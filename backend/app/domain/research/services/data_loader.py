"""投研数据加载器 — 为 Agent 提供统一的数据查询接口"""
from typing import List, Dict, Any, Optional
from app.framework.database.session import async_session
from app.models.models import (
    StockInfo, MarketData, StockIndicator, Position, ExchangeRate
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

    async def load_fundamentals(self, codes: List[str]) -> Dict[str, Dict]:
        """加载基本面 (PE/PB/市值)"""
        if not codes:
            return {}
        async with async_session() as db:
            rows = await db.execute(
                select(StockInfo).where(StockInfo.stock_code.in_(codes))
            )
            return {
                r.stock_code: {
                    "name": r.stock_name, "exchange": r.exchange,
                    "pe_ttm": r.pe_ttm, "pb": r.pb,
                    "mcap_yi": r.mcap_yi, "industry": r.industry,
                }
                for r in rows.scalars().all()
            }

    async def load_indicators(self, codes: List[str]) -> Dict[str, Dict]:
        """加载最新技术指标"""
        if not codes:
            return {}
        result = {}
        async with async_session() as db:
            for code in codes:
                row = await db.execute(
                    select(StockIndicator)
                    .where(StockIndicator.stock_code == code)
                    .order_by(StockIndicator.analysis_date.desc())
                    .limit(1)
                )
                ind = row.scalars().first()
                if ind:
                    result[code] = {
                        "date": str(ind.analysis_date),
                        "snapshot": ind.data_json,
                        "findings": ind.logic_chain.get("findings", []) if ind.logic_chain else []
                    }
        return result

    async def load_positions(self) -> List[Dict]:
        """加载当前持仓"""
        async with async_session() as db:
            rows = await db.execute(select(Position))
            return [
                {
                    "stock_code": p.stock_code, "stock_name": p.stock_name,
                    "volume": p.volume, "avg_cost": p.avg_cost,
                    "current_price": p.current_price, "market_value": p.market_value,
                    "profit_loss": p.profit_loss, "profit_loss_ratio": p.profit_loss_ratio,
                }
                for p in rows.scalars().all()
            ]

    async def load_sector_overview(self, industry: str) -> Dict:
        """加载行业概览 (该行业所有股票的估值汇总)"""
        async with async_session() as db:
            rows = await db.execute(
                select(StockInfo)
                .where(StockInfo.industry.isnot(None))
            )
            sector_stocks = [r for r in rows.scalars().all() if industry in (r.industry or "")]
            if not sector_stocks:
                return {"count": 0}

            pe_values = [s.pe_ttm for s in sector_stocks if s.pe_ttm and s.pe_ttm > 0]
            pb_values = [s.pb for s in sector_stocks if s.pb and s.pb > 0]
            return {
                "count": len(sector_stocks),
                "avg_pe": sum(pe_values) / len(pe_values) if pe_values else None,
                "avg_pb": sum(pb_values) / len(pb_values) if pb_values else None,
                "stocks": [
                    {"code": s.stock_code, "name": s.stock_name,
                     "pe_ttm": s.pe_ttm, "pb": s.pb, "mcap_yi": s.mcap_yi}
                    for s in sector_stocks[:20]
                ]
            }

    async def search_stocks(self, keyword: str, limit: int = 20) -> List[Dict]:
        """搜索股票 (代码/名称模糊匹配)"""
        async with async_session() as db:
            rows = await db.execute(
                select(StockInfo.stock_code, StockInfo.stock_name, StockInfo.exchange)
                .where(
                    StockInfo.stock_code.like(f"%{keyword}%") |
                    StockInfo.stock_name.like(f"%{keyword}%")
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
        """搜索行业内所有标的 (StockInfo.industry 模糊匹配)"""
        async with async_session() as db:
            rows = await db.execute(
                select(StockInfo)
                .where(StockInfo.industry.isnot(None))
            )
            matched = [r for r in rows.scalars().all() if keyword in (r.industry or "")]
            return [
                {"code": s.stock_code, "name": s.stock_name, "industry": s.industry,
                 "pe_ttm": s.pe_ttm, "pb": s.pb, "mcap_yi": s.mcap_yi}
                for s in matched
            ]

    async def load_financials(self, codes: List[str]) -> Dict[str, Dict]:
        """加载财务数据 — PE/PB/市值"""
        return await self.load_fundamentals(codes)

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
        import pandas as pd
        from app.framework.config import settings

        prefix = self._code_to_akshare_prefix(code)
        if not prefix:
            logger.warning(f"[Financial] Unsupported code format: {code}")
            return {"code": code, "quarters": [], "error": "Unsupported code format"}

        try:
            # 在线程池中运行同步 akshare 调用
            loop = __import__('asyncio').get_event_loop()

            # 1. 季度利润表 → 营业总收入、净利润
            income_df = await loop.run_in_executor(
                None, self._fetch_income_sheet, prefix)
            # 2. 季度现金流量表 → 经营活动现金流量净额
            cashflow_df = await loop.run_in_executor(
                None, self._fetch_cashflow_sheet, prefix)
            # 3. 资产负债表 → 存货、合同负债
            balance_df = await loop.run_in_executor(
                None, self._fetch_balance_sheet, prefix)

            if income_df is None or income_df.empty:
                return {"code": code, "quarters": [], "error": "No financial data available"}

            # 合并三表, 取最近 N 个季度
            merged = self._merge_financial_sheets(income_df, cashflow_df, balance_df, periods)
            quarters = []
            for _, row in merged.iterrows():
                q = {
                    "report_date": str(row.get("REPORT_DATE", ""))[:10],
                    "revenue": float(row.get("revenue", 0) or 0),
                    "profit": float(row.get("profit", 0) or 0),
                    "operate_cost": float(row.get("operate_cost", 0) or 0),
                    "sale_expense": float(row.get("sale_expense", 0) or 0),
                    "manage_expense": float(row.get("manage_expense", 0) or 0),
                    "op_cashflow": float(row.get("op_cashflow", 0) or 0),
                    "inventory": float(row.get("inventory", 0) or 0),
                    "contract_liability": float(row.get("contract_liability", 0) or 0),
                    "accounts_receivable": float(row.get("accounts_receivable", 0) or 0),
                    "total_assets": float(row.get("total_assets", 0) or 0),
                    "current_assets": float(row.get("current_assets", 0) or 0),
                    "fixed_assets": float(row.get("fixed_assets", 0) or 0),
                    "total_liabilities": float(row.get("total_liabilities", 0) or 0),
                }
                quarters.append(q)

            logger.info(f"[Financial] Loaded {len(quarters)} quarters for {code}")
            return {"code": code, "quarters": quarters}

        except Exception as e:
            logger.warning(f"[Financial] load_financial_statements({code}) failed: {e}")
            return {"code": code, "quarters": [], "error": str(e)}

    @staticmethod
    def _code_to_akshare_prefix(code: str) -> Optional[str]:
        """转换股票代码为 akshare 前缀格式"""
        c = str(code).strip().upper()
        if c.startswith("SH") or c.startswith("SZ") or c.startswith("BJ"):
            return c
        if len(c) == 6:
            if c.startswith(("6", "9")):
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
        """获取资产负债表(按报告期) → 存货/合同负债/应收/总资产/流动资产/固定资产/总负债"""
        import akshare as ak
        import pandas as pd
        df = ak.stock_balance_sheet_by_report_em(symbol=prefix)
        df = df.rename(columns={
            "INVENTORY": "inventory",
            "CONTRACT_LIAB": "contract_liability",
            "ACCOUNTS_RECE": "accounts_receivable",
            "TOTAL_ASSETS": "total_assets",
            "CURRENT_ASSET_BALANCE": "current_assets",
            "FIXED_ASSET": "fixed_assets",
            "TOTAL_LIABILITIES": "total_liabilities",
        })
        df["REPORT_DATE"] = pd.to_datetime(df["REPORT_DATE"])
        cols = ["REPORT_DATE", "inventory", "contract_liability",
                "accounts_receivable", "total_assets", "current_assets",
                "fixed_assets", "total_liabilities"]
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
        """网络搜索 — Brave Search (优先, 高质量) → DDG (免费兜底)
        通过 Clash 代理 (127.0.0.1:7890) 访问海外服务。
        """
        from app.framework.config import settings
        CLASH_PROXY = "http://127.0.0.1:7890"

        # 1. Brave Search 优先 (付费 Key, 高质量结构化结果)
        if settings.BRAVE_API_KEY:
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
                            })
                        if results:
                            logger.info(f"[Brave search OK: {len(results)} results for '{query[:40]}']")
                            return results
                    else:
                        logger.warning(f"[Brave search HTTP {resp.status_code}: {resp.text[:100]}]")
            except Exception as e:
                logger.warning(f"[Brave search failed: {type(e).__name__}: {e}]")

        # 2. DDG 兜底 (免费)
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


# 全局单例
data_loader = ResearchDataLoader()
