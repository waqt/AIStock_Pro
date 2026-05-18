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
        """加载财务数据 — 当前返回 PE/PB/市值作为代理指标 (营收/利润待付费API接入)"""
        return await self.load_fundamentals(codes)

    async def load_capital_flow(self, code: str, days: int = 30) -> List[Dict]:
        """加载个股资金流向 (主力/散户/超大单)"""
        try:
            from app.domain.market_data.sources.push2 import get_capital_flow
            return await get_capital_flow(code, days)
        except Exception as e:
            logger.warning(f"[Capital flow load failed for {code}: {e}]")
            return []


    async def search_web(self, query: str, num: int = 5) -> List[Dict]:
        """网络搜索 — Brave Search API (优先) → DDG (兜底)"""
        from app.framework.config import settings

        # 1. Brave Search (付费 Key, 高质量结果)
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
                async with httpx.AsyncClient(proxy=None, timeout=10.0) as client:
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
                            return results
            except Exception as e:
                logger.warning(f"[Brave search failed: {e}]")

        # 2. DDG 兜底 (无需 Key)
        try:
            import re, httpx
            url = "https://html.duckduckgo.com/html/"
            data = {"q": query}
            async with httpx.AsyncClient(proxy=None, timeout=10.0,
                    headers={"User-Agent": "Mozilla/5.0"}) as client:
                resp = await client.post(url, data=data)
                if resp.status_code != 200:
                    return []
                results = []
                links = re.findall(r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', resp.text)
                snippets = re.findall(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', resp.text)
                for i, (url, title) in enumerate(links[:num]):
                    title_clean = re.sub(r'<[^>]+>', '', title).strip()
                    snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip() if i < len(snippets) else ""
                    if title_clean:
                        results.append({"title": title_clean[:150], "url": url, "snippet": snippet[:300]})
                return results
        except Exception as e:
            logger.warning(f"[DDG search failed: {e}]")
            return []

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
