"""网页抓取与信息抽取 — 给投研Agent提供深度阅读能力"""
import re
import httpx
from typing import List, Dict, Optional
from app.framework.logger import logger

CLASH_PROXY = "http://127.0.0.1:7890"
USER_AGENT = "Mozilla/5.0 (compatible; AIStockResearch/1.0)"


class WebScraper:
    """轻量网页抓取器 — 取页面 → 抽主文 → 结构化"""

    @staticmethod
    async def fetch(url: str, timeout: int = 15) -> Optional[str]:
        """抓取单页HTML"""
        try:
            async with httpx.AsyncClient(proxy=CLASH_PROXY, timeout=timeout,
                    headers={"User-Agent": USER_AGENT},
                    follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    logger.warning(f"[Scraper] HTTP {resp.status_code}: {url[:80]}")
                    return None
                return resp.text
        except Exception as e:
            logger.warning(f"[Scraper] Fetch failed: {type(e).__name__}: {url[:80]}")
            return None

    @staticmethod
    async def fetch_and_extract(url: str, timeout: int = 15) -> Dict:
        """抓取并抽取正文 (标题+段落+元数据)"""
        html = await WebScraper.fetch(url, timeout)
        if not html:
            return {"url": url, "error": "Fetch failed", "title": "", "text": ""}

        title = WebScraper._extract_title(html)
        text = WebScraper._extract_text(html)

        logger.info(f"[Scraper] Extracted: {url[:60]} → {len(text)} chars")
        return {
            "url": url,
            "title": title,
            "text": text[:8000],  # 限制长度, 避免token爆炸
            "text_length": len(text),
        }

    @staticmethod
    async def batch_fetch(urls: List[str], timeout: int = 15) -> List[Dict]:
        """批量抓取多个URL"""
        import asyncio
        tasks = [WebScraper.fetch_and_extract(u, timeout) for u in urls]
        return await asyncio.gather(*tasks)

    @staticmethod
    async def fetch_structured(url: str, fields: List[str] = None,
                               timeout: int = 15) -> Dict:
        """抓取并抽取半结构化信息 (表格/列表/关键数据)"""
        html = await WebScraper.fetch(url, timeout)
        if not html:
            return {"url": url, "error": "Fetch failed"}

        result = {
            "url": url,
            "title": WebScraper._extract_title(html),
            "tables": WebScraper._extract_tables(html),
            "lists": WebScraper._extract_lists(html),
            "numbers": WebScraper._extract_numbers(html),
        }
        return result

    # ═══ 抽取方法 ═══════════════════════════════

    @staticmethod
    def _extract_title(html: str) -> str:
        m = re.search(r'<title[^>]*>(.*?)</title>', html, re.I | re.S)
        return re.sub(r'<[^>]+>', '', m.group(1)).strip() if m else ""

    @staticmethod
    def _extract_text(html: str) -> str:
        """提取主要正文 (基于段落密度)"""
        # 移除脚本和样式
        html = re.sub(r'<(script|style|noscript|iframe)[^>]*>.*?</\1>', '', html, flags=re.I | re.S)
        # 提取所有段落文本
        paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', html, re.I | re.S)
        lines = []
        for p in paragraphs:
            text = re.sub(r'<[^>]+>', '', p).strip()
            text = re.sub(r'\s+', ' ', text)
            if len(text) > 30:  # 过滤过短的段落
                lines.append(text)
        return '\n\n'.join(lines)

    @staticmethod
    def _extract_tables(html: str) -> List[List[List[str]]]:
        """抽取HTML表格"""
        tables = []
        for table_html in re.findall(r'<table[^>]*>(.*?)</table>', html, re.I | re.S):
            rows = []
            for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.I | re.S):
                cells = []
                for td in re.findall(r'<(td|th)[^>]*>(.*?)</\1>', tr, re.I | re.S):
                    text = re.sub(r'<[^>]+>', '', td[1]).strip()
                    cells.append(text)
                if cells:
                    rows.append(cells)
            if rows:
                tables.append(rows)
        return tables[:5]  # 最多5个表

    @staticmethod
    def _extract_lists(html: str) -> List[str]:
        """抽取列表项"""
        items = re.findall(r'<li[^>]*>(.*?)</li>', html, re.I | re.S)
        return [re.sub(r'<[^>]+>', '', item).strip() for item in items
                if len(re.sub(r'<[^>]+>', '', item).strip()) > 10][:30]

    @staticmethod
    def _extract_numbers(html: str) -> List[str]:
        """抽取关键数字 (如: 营收 100亿, 增速 25%)"""
        text = WebScraper._extract_text(html)
        # 匹配数字+单位的模式
        patterns = re.findall(
            r'(\d+(?:\.\d+)?\s*(?:亿|万|%|亿美元|亿元|万亿|万吨|万片|亿元|亿美元|%|倍))',
            text)
        return list(set(patterns))[:20]
