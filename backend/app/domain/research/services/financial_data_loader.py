"""
财务数据双通道加载器 — DB + Web Search
统一入口: 先试 DB → 不足则 web search + LLM提取
"""
import re
from typing import Dict, Any, List
from app.framework.logger import logger


async def load_financials(code: str, name: str = "", periods: int = 8, provider=None) -> dict:
    """
    统一入口: 加载股票财务数据
    返回: {"quarters": [...], "source": "db"|"web_estimated", "confidence": "high"|"medium"|"low"}
    """
    result = await _load_from_db(code, periods)
    if result["quarters"] and len(result["quarters"]) >= 4:
        result["source"] = "db"
        result["confidence"] = "high"
        return result

    # DB 不足 → web search 兜底
    logger.info(f"[FinData] {code}: DB has <4Q, falling back to web search")
    result = await _load_from_web(code, name, provider)
    result["source"] = "web_estimated"
    return result


async def _load_from_db(code: str, periods: int = 8) -> dict:
    """DB 优先路径"""
    from app.domain.research.services.data_loader import data_loader
    try:
        fin = await data_loader.load_financial_statements(code, periods=periods)
        return {"quarters": fin.get("quarters", []), "source": "db"}
    except Exception as e:
        logger.warning(f"[FinData] DB load failed for {code}: {e}")
        return {"quarters": [], "source": "db"}


async def _load_from_web(code: str, name: str = "", provider=None) -> dict:
    """Web Search 兜底 — 搜索 → LLM 提取 → 生成简化的 quarters"""
    from app.domain.research.services.data_loader import data_loader

    label = f"{code} {name}".strip()
    try:
        # 搜索财务数据
        results = await data_loader.search_web(
            f"{label} 营收 净利润 毛利率 2025年报 2026一季报 财务数据", num=5)
        if not results:
            return {"quarters": [], "confidence": "low", "error": "web search returned no results"}

        # LLM 提取
        if not provider:
            from app.framework.ai.providers.deepseek import DeepSeekProvider
            provider = DeepSeekProvider()

        prompt = _build_extraction_prompt(label, results)
        text = await provider.chat_flash(prompt, max_tokens=1024)

        quarters = _parse_web_extraction(text)
        return {
            "quarters": quarters,
            "confidence": "low" if len(quarters) < 2 else "medium",
            "web_raw": text[:500],
        }
    except Exception as e:
        logger.warning(f"[FinData] Web load failed for {code}: {e}")
        return {"quarters": [], "confidence": "low", "error": str(e)[:200]}


def _build_extraction_prompt(label: str, results: List[Dict]) -> str:
    snippets = ""
    for i, r in enumerate(results[:5]):
        snippets += f"[{i+1}] {r.get('title','')}: {r.get('snippet','')[:200]}\n"

    return f"""从以下搜索结果提取 {label} 的最新财务数据 (仅输出JSON, 不输出其他内容):

{ snippets }

## 提取规则
- 从搜索结果中找到最近2-4个季度的营收(revenue)和归母净利润(profit)
- 如果找到用毛利率数据则提取 gross_margin
- 如果找到研发费用数据则提取 rd_expense
- 将数据整理为以下格式, 单位为亿元:

```json
{{
  "quarters": [
    {{"period": "2025Q4", "revenue_estimated": 12.5, "profit_estimated": 2.1, "gross_margin": 45.0, "rd_expense_estimated": 1.2}},
    {{"period": "2025Q3", "revenue_estimated": 11.0, "profit_estimated": 1.8}}
  ],
  "note": "数据来源说明"
}}
```

- 如果没有找到具体数值, 返回空的 quarters 数组
- 数字直接从搜索结果取, 不要自己编造
- 标注 _estimated 字段表示从web搜索估计而非精确季报数据"""


def _parse_web_extraction(text: str) -> list:
    """解析 LLM 返回的季度数据"""
    import json as _json
    try:
        # 提取 JSON 块
        text = text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        data = _json.loads(text)
        raw_quarters = data.get("quarters", [])
        # 转换为标准格式 (与 DB 路径的字段名对齐)
        quarters = []
        for q in raw_quarters:
            quarters.append({
                "report_date": q.get("period", "") if not q.get("period", "").startswith("20") else q.get("period", "") + "-01",
                "revenue": q.get("revenue_estimated", 0) * 1e8 if q.get("revenue_estimated") else 0,
                "profit": q.get("profit_estimated", 0) * 1e8 if q.get("profit_estimated") else 0,
                "parent_profit": q.get("profit_estimated", 0) * 1e8 if q.get("profit_estimated") else 0,
                "gross_margin_pct": q.get("gross_margin"),
                "rd_expense": q.get("rd_expense_estimated", 0) * 1e8 if q.get("rd_expense_estimated") else 0,
                "operate_cost": 0, "sale_expense": 0, "manage_expense": 0,
                "op_cashflow": 0, "inventory": 0, "contract_liability": 0,
                "accounts_receivable": 0, "total_assets": 0, "current_assets": 0,
                "total_liabilities": 0, "total_equity": 0, "fixed_assets": 0,
                "cash": 0, "current_liabilities": 0, "short_loan": 0,
                "data_quality": "web_estimated",
            })
        return quarters
    except Exception as e:
        logger.warning(f"[FinData] Failed to parse web extraction: {e}")
        return []
