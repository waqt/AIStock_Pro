"""
MarketScanner — AI 主动发现引擎
无需输入, 自动扫宏观/资金流/持仓数据, 用 LLM 识别热门赛道并生成每日简报
"""
import asyncio, json
from decimal import Decimal
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger

class _SafeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal): return float(obj)
        return super().default(obj)

def _j(obj): return json.dumps(obj, ensure_ascii=False, cls=_SafeEncoder)

class MarketScanner(ResearchAgent):
    """主动发现智能体 — 每天扫市场找机会"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "MarketScanner"

    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await self.load_context({})
        if not self.provider:
            return {"error": "No AI provider"}

        # Step 1: 收集全局信号 (本地数据, 无 LLM)
        signals = await self._collect_signals(ctx)

        # Step 2: LLM 识别热门赛道
        industries = await self._identify_hot_industries(signals)

        # Step 3: LLM 生成每日简报
        briefing = await self._generate_briefing(signals, industries)

        return {
            "agent": self.name,
            "macro": signals["macro"],
            "portfolio_summary": signals["portfolio_summary"],
            "volume_alerts": signals["volume_alerts"],
            "hot_industries": industries,
            "briefing": briefing,
        }

    async def _collect_signals(self, ctx: Dict) -> Dict:
        """收集全局市场信号"""
        macro = ctx.get("macro", {})
        positions = ctx.get("positions", [])
        fundamentals = ctx.get("fundamentals", {})
        market_data = ctx.get("market_data", {})

        # 持仓概要
        pos_summary = {
            "count": len(positions),
            "total_value": sum(p.get("market_value", 0) or 0 for p in positions),
            "stocks": [{
                "code": p["stock_code"], "name": p.get("stock_name",""),
                "pe_ttm": fundamentals.get(p["stock_code"], {}).get("pe_ttm"),
                "pb": fundamentals.get(p["stock_code"], {}).get("pb"),
                "change_pct": None,  # filled below
                "volume_alert": False,
            } for p in positions[:20]]
        }

        # 成交量异动检测
        volume_alerts = []
        for code, rows in market_data.items():
            if len(rows) < 10: continue
            recent = sum(r.get("volume", 0) for r in rows[:3])
            prev = sum(r.get("volume", 0) for r in rows[3:6])
            if prev > 0 and recent > prev * 1.3:
                volume_alerts.append({
                    "code": code,
                    "ratio": round(recent / prev, 2),
                    "recent_vol": recent,
                })
                # mark in summary
                for s in pos_summary["stocks"]:
                    if s["code"] == code:
                        s["volume_alert"] = True
                        s["change_pct"] = rows[0].get("change_pct") if rows else None

        return {
            "macro": macro,
            "portfolio_summary": {
                "count": pos_summary["count"],
                "total_value": pos_summary["total_value"],
                "top5": pos_summary["stocks"][:5],
            },
            "volume_alerts": volume_alerts[:10],
        }

    async def _identify_hot_industries(self, signals: Dict) -> List[Dict]:
        """LLM 识别当前最热赛道"""
        prompt = f"""你是一位全球宏观策略师。请基于以下市场信号, 识别当前 A 股最值得关注的 3-5 个行业/投资主题。

## 宏观环境
{_j(signals['macro'])}

## 持仓概要
{_j(signals['portfolio_summary'])}

## 成交量异动 (放量>30%)
{_j(signals['volume_alerts'])}

## 要求
1. 每个行业给出: name, score(1-10), reason(核心逻辑), a_stock_codes(相关A股代码列表)
2. 结合全球宏观环境(美联储/央行政策/大宗商品/地缘政治)判断行业景气度
3. 优先关注有成交量异动支撑的行业
4. 优先关注持仓中已有的行业(可持续跟踪)

请输出纯 JSON 数组, 不要 Markdown:
[{{"name":"AI算力","score":9,"reason":"NVIDIA Blackwell量产+TSMC CoWoS扩产","global_drivers":"英伟达/台积电capex创新高","a_stock_codes":["688256","300308"]}}]"""

        text = await self._safe_call(prompt)
        return self._parse_json(text)

    async def _generate_briefing(self, signals: Dict, industries: List) -> str:
        """生成每日简报"""
        prompt = f"""你是一位资深投资顾问。请基于以下数据生成今日投资简报。

## 宏观环境
{_j(signals['macro'])}

## 持仓 (Top 5)
{_j(signals['portfolio_summary'].get('top5', []))}

## 热门赛道
{_j(industries)}

## 输出格式 (Markdown)
### 今日市场环境
(2-3句宏观定调)

### 热门赛道 TOP 3
| 排名 | 行业 | 景气评分 | 核心逻辑 | 关注标的 |
|------|------|---------|---------|---------|

### 操作建议
(基于持仓的调仓建议)

### 风险提示
(1-2句今日需要关注的风险事件)"""

        return await self._safe_call(prompt)

    async def _safe_call(self, prompt: str) -> str:
        try:
            return await asyncio.wait_for(self.provider.chat(prompt), timeout=45) or ""
        except asyncio.TimeoutError:
            logger.warning("[MarketScanner] LLM call timed out")
            return "分析超时, 请重试"
        except Exception as e:
            logger.warning(f"[MarketScanner] LLM call failed: {e}")
            return f"分析异常: {e}"

    def _parse_json(self, text: str) -> List:
        import re
        text = text.strip()
        if "```" in text:
            m = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
            if m: text = m.group(1).strip()
        try: return json.loads(text)
        except: return [{"raw": text[:300]}]
