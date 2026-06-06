"""
StockHealthChecker V1.0 — 个股全方位健康体检

定位: LLM 自主工具编排, 不预设硬编码分析步骤。
      系统提供工具(财务/技术/搜索/基本面), LLM 自行决定:
      查什么 → 什么顺序 → 怎么综合判断 → 输出结构化报告

替代: 原有的 FinancialAuditor(Step7) + HumanCapitalDetective(Step8) 固定步骤
"""
import json, re
from typing import Dict, Any, List, Optional

from app.domain.research.agents.base import ResearchAgent, HEALTH_CHECK_TOOLS
from app.framework.logger import logger


# ═══ Prompt 模板 ═══════════════════════════════════

HEALTH_CHECK_SYSTEM_PROMPT = """你是一位专业的投资研究分析师，负责对个股进行全方位健康体检。
请使用提供的工具，自主规划分析路径，对目标股票进行深入检查。

## 可用工具

1. **query_financial_data(code, indicators, raw_fields)**
   查询财务指标或原始财报数据。
   - indicators 参数: 获取已注册的计算指标 (如 roic_pct, gross_margin_pct, revenue_yoy, scissor_gap, ocf_health, beneish_m_score 等)
   - raw_fields 参数: 获取原始财报字段 (如 revenue, op_cashflow, rd_expense, inventory 等)

2. **query_technical_indicators(code, fields, days)**
   查询技术指标时序数据。
   - fields: RSI, MACD, KDJ, CCI, BB_WIDTH, MA5/MA20/MA60, OBV, crowding_ratio 等
   - days: 返回最近 N 个交易日数据

3. **query_fundamentals(code)**
   查询基本面估值快照。返回 PE_TTM, PB, 市值, ROE, 股息率, 营收/利润增速等。

4. **web_search(query, num)**
   搜索网络获取实时行业/公司/市场信息。用于获取团队背景、专利布局、
   竞争格局、行业动态等无法从财务数据直接获取的信息。

## 分析建议框架

建议从以下四个维度展开分析，但你可以根据获取到的信息灵活调整：

### 1️⃣ 财务健康
- 盈利能力: ROIC, ROE, 毛利率, 净利率趋势
- 成长性: 营收增速, 利润增速, 剪刀差 (revenue_yoy vs profit_yoy)
- 财务质量: 经营现金流健康度, Beneish M-Score, 应收账款, 存货
- 资本效率: ROIIC, 营运资本效率

### 2️⃣ 技术面分析
- 趋势: MACD 方向, 均线排列 (MA5/MA20/MA60)
- 动量: RSI 位置, CCI 信号
- 波动率: 布林带宽度
- 量能: OBV 趋势, 拥挤度
- 筹码: 集中度变化, 筹码形态

### 3️⃣ 人才与专利
- 创始团队背景 (教育、行业经验、行业地位)
- 核心技术团队 (CTO 履历、研发人员占比)
- 专利质量 (总量、发明专利占比、技术自主可控)
- 股权激励与核心团队稳定性

### 4️⃣ 估值合理性
- 当前 PE/PB 绝对值及历史分位数
- PEG: 估值 vs 增速匹配度
- EV/EBITDA, PS 等辅助估值
- 与全球同行的估值对比

## 输出要求

请根据你的分析结果，输出以下 JSON 结构（不要额外说明，只返回 JSON）:

```json
{{
  "stock_code": "股票代码",
  "stock_name": "股票名称",
  "overall": {{
    "verdict": "BUY | HOLD | SELL | WATCH",
    "confidence": "high | medium | low",
    "summary": "30字以内的综合判断"
  }},
  "dimensions": [
    {{
      "name": "财务健康",
      "verdict": "PASS | CAUTION | FAIL | INSUFFICIENT_DATA",
      "confidence": "high | medium | low",
      "evidence": ["关键证据1", "关键证据2"],
      "analysis": "详细推理过程(100-200字)",
      "data_summary": {{}}
    }},
    {{
      "name": "技术面",
      "verdict": "BULLISH | NEUTRAL | BEARISH",
      "confidence": "high | medium | low",
      "evidence": ["关键证据1"],
      "analysis": "详细推理过程",
      "data_summary": {{}}
    }},
    {{
      "name": "人才与专利",
      "verdict": "STRONG | ADEQUATE | WEAK | UNKNOWN",
      "confidence": "high | medium | low",
      "evidence": ["关键证据1"],
      "analysis": "详细推理过程",
      "data_summary": {{}}
    }},
    {{
      "name": "估值合理性",
      "verdict": "OVERPRICED | FAIR | UNDERVALUED",
      "confidence": "high | medium | low",
      "evidence": ["关键证据1"],
      "analysis": "详细推理过程",
      "data_summary": {{}}
    }}
  ],
  "key_risks": ["风险1", "风险2"],
  "key_catalysts": ["催化剂1", "催化剂2"],
  "overall_analysis": "四维度综合判断(200-300字)"
}}
```

注意：
- 如果某个维度因数据不足无法判断，verdict 使用 INSUFFICIENT_DATA/UNKNOWN
- evidence 中的证据必须是可验证的事实，不是主观判断
- 如果搜索或工具调用失败，在 analysis 中说明数据获取情况"""  # noqa: W293


class StockHealthChecker(ResearchAgent):
    """个股健康体检 — LLM 自主工具编排"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=None)
        self.name = "StockHealthChecker"

    def build_prompt(self, context: Dict[str, Any]) -> str:
        """构建体检 prompt"""
        stock_code = context.get("stock_code", "未知")
        stock_name = context.get("stock_name", "")
        dimensions = context.get("dimensions", [])
        industry = context.get("industry", "")

        dim_filter = ""
        if dimensions and len(dimensions) > 0:
            dim_filter = f"\n## 限定分析维度\n请仅分析以下维度: {', '.join(dimensions)}\n"

        stock_info = f"股票代码: {stock_code}"
        if stock_name:
            stock_info += f" ({stock_name})"
        if industry:
            stock_info += f"\n所属行业: {industry}"

        # 注入财务数据字典
        catalog_placeholder = "{{FINANCIAL_CATALOG}}"

        prompt = f"""## 任务
对 {stock_info} 做全方位健康体检。

{dim_filter}

## 可用工具说明

根据分析需要，自主选择合适的工具和查询顺序。
建议先从 query_fundamentals 获取基本面快照，再根据情况调用其他工具深入分析。
{catalog_placeholder}

{HEALTH_CHECK_SYSTEM_PROMPT}
"""
        return prompt

    def parse_result(self, text: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """解析 LLM 输出 JSON"""
        result = self._extract_json(text)
        if result:
            # 补充元信息
            if "stock_code" not in result:
                result["stock_code"] = context.get("stock_code", "")
            result["agent"] = self.name
            return result

        # 解析失败时的兜底
        logger.warning(f"[{self.name}] Failed to parse LLM output as JSON, returning raw text")
        return {
            "agent": self.name,
            "stock_code": context.get("stock_code", ""),
            "error": "Failed to parse LLM output as JSON",
            "raw_text": text[:2000],
            "overall": {"verdict": "UNKNOWN", "confidence": "low", "summary": "解析失败"},
            "dimensions": [],
            "key_risks": [],
            "key_catalysts": [],
            "overall_analysis": "",
        }

    @staticmethod
    def _extract_json(text: str) -> Optional[dict]:
        """从 LLM 输出中提取 JSON"""
        text = text.strip()
        # 去除 markdown 代码块标记
        if text.startswith("```"):
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)
        text = text.strip()

        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试提取第一个 { ... } 块
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

        # 尝试修复常见格式问题 (单引号替代双引号)
        try:
            fixed = text[start:end + 1]
            fixed = re.sub(r"(?<!\")\'([^\']+)\'(?!\")", r'"\1"', fixed)
            return json.loads(fixed)
        except (json.JSONDecodeError, ValueError, IndexError):
            return None

    async def analyze(self, ctx: Dict[str, Any] = None, trace=None) -> Dict[str, Any]:
        """主入口 — 使用工具增强版分析"""
        ctx = ctx or {}
        stock_code = ctx.get("stock_code", "")
        stock_name = ctx.get("stock_name", "")

        logger.info(f"[{self.name}] === Health Check: {stock_code} {stock_name} ===")

        # 使用 analyze_with_tools 执行多轮工具调用
        result = await self.analyze_with_tools(
            context=ctx,
            tool_defs=HEALTH_CHECK_TOOLS,
            max_rounds=8,
        )

        # 确保结果包含基本字段
        if "stock_code" not in result:
            result["stock_code"] = stock_code
        if "agent" not in result:
            result["agent"] = self.name

        logger.info(f"[{self.name}] Complete: {stock_code} → verdict={result.get('overall', {}).get('verdict', '?')}")
        return result
