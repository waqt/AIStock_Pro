"""
投研工具集合 — 概念能力目录 + Prompt 构建函数

定位:
  不包含任何工具 handler (都在 base.py TOOL_REGISTRY 中注册)
  只包含 LLM Prompt 用到的概念描述和构建函数

设计原则:
  - 面向概念: LLM 看到的是"资本回报效率"，不是 "roic_pct"
  - 可扩展: 新概念加一行描述，不改 prompt
"""
import json
from typing import Dict, Any, List, Optional


# ═══════════════════════════════════════════════════════════
# 概念能力目录 — LLM 理解"我能查什么"的入口
# 从 FINANCIAL_REGISTRY 动态构建，确保与注册表一致
# ═══════════════════════════════════════════════════════════

CONCEPT_LABELS = {
    "capital_return_efficiency": "资本回报效率",
    "profit_quality": "利润质量与盈利结构",
    "growth_scissor_gap": "增长与剪刀差",
    "financial_health": "财务健康",
    "moat_stability": "竞争护城河稳定性",
    "company_profile": "公司画像",
}

CONCEPT_DESCRIPTIONS = {
    "capital_return_efficiency": "公司每投入 1 元资本能产生多少回报，是否超过融资成本。用于判断商业模式是否真正创造价值、护城河是否转化为超额利润。",
    "profit_quality": "毛利率/净利率水平与趋势、费用结构（研发/销售/管理）。用于判断利润是否真实、可持续、议价权在提升还是下降。",
    "growth_scissor_gap": "营收增长率 vs 利润增长率，两者趋势是否匹配。用于判断增长是靠量价齐升还是降价压货驱动，是否存在增收不增利。",
    "financial_health": "经营现金流与净利润的匹配度、库存周转、合同负债趋势。用于判断利润是否真金白银、在手订单是否充足、存货是否积压。",
    "moat_stability": "超额利润是否可持续、利润率是否大起大落、有无财务操纵迹象。用于判断竞争格局是否稳定，龙头地位是否可维持。",
    "company_profile": "TTM营收规模分类（mega/large/medium/small/micro）。用于快速判断公司体量和市场地位。",
}


def build_concepts_catalog() -> str:
    """从 FINANCIAL_REGISTRY 动态构建概念→指标映射表

    遍历所有已注册财务指标，按 concepts 标签分组，带上指标名+label+description。
    确保 LLM 在策划验证计划时能精确知道每个概念下有哪些指标可用。
    """
    from app.domain.quant.indicators.fundamental import FINANCIAL_REGISTRY

    # 按概念分组
    groups: dict = {}
    for indicator_name, cls in FINANCIAL_REGISTRY.items():
        for concept in getattr(cls, 'concepts', []):
            groups.setdefault(concept, []).append(
                f"  - {indicator_name} ({cls.label}): {cls.description[:120]}"
            )

    # 格式化输出
    lines = ["## 可查询的数据维度（按概念分组，附可用指标名+说明）", ""]
    for key in CONCEPT_LABELS:
        items = groups.get(key, [])
        desc = CONCEPT_DESCRIPTIONS.get(key, "")
        lines.append(f"### {CONCEPT_LABELS[key]} ({key})")
        if desc:
            lines.append(desc)
        if items:
            lines.append("可用指标:")
            lines.extend(items)
        else:
            lines.append("（暂无已注册指标）")
        lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# Phase 1: 验证计划 Prompt 构建
# ═══════════════════════════════════════════════════════════

RESEARCH_TOOLS = [
    {
        "name": "query_financial_data",
        "description": "查询财务指标和原始财报数据。覆盖资本回报效率、利润质量、增长、财务健康、竞争护城河等概念所需的数据。",
    },
    {
        "name": "calculate_valuation",
        "description": "定量估值计算。支持 20+ 方法 (VALUATION_REGISTRY)，系统从DB加载真实财务数据执行，返回目标价。",
    },
    {
        "name": "query_fundamentals",
        "description": "基本面快照。返回 PE/PB/市值/ROE 等，快速了解估值水平。",
    },
    {
        "name": "web_search",
        "description": "搜索网络获取实时信息。用于客户认证、竞争格局、技术路线、管理层质量等无法从财务数据获取的定性判断。",
    },
]


def build_plan_prompt(
    name: str,
    code: str,
    industry: str,
    node_context: Dict[str, Any],
    source_context: str = "",
) -> str:
    """构建 Phase 1 验证计划提示词

    LLM 只需做计划，不执行任何查询。
    输出是一个结构化的验证计划，列出要查什么概念、用什么工具、搜什么方向。
    """
    # 从 node_context 提取产业链角色信息
    node_name = node_context.get("name", industry)
    bottleneck = node_context.get("bottleneck_narrative", "")
    profit_pool = node_context.get("profit_pool", {})
    competitive = node_context.get("competitive_landscape", {})
    supply_rigidity = node_context.get("supply_rigidity", {})

    return f"""你正在对一家公司在 {industry} 产业链中的竞争地位做独立验证。

## 标的
名称: {name} ({code})
产业链节点: {node_name}

## 产业链背景 (来自前期分析)
瓶颈描述: {str(bottleneck)[:200] if bottleneck else '该节点在产业中承担的角色由你自行判断'}
利润池描述: {str(profit_pool)[:200] if profit_pool else '待验证'}
竞争格局: {str(competitive)[:200] if competitive else '待验证'}
供给刚性: {str(supply_rigidity)[:200] if supply_rigidity else '待验证'}

## 来源线索
{source_context or '该标的是在前期搜索中被发现的，需要独立验证'}

## 可用工具

{_format_tools()}

## 可查询的数据概念

{build_concepts_catalog()}

## 任务

请为这只标的策划一份验证计划。**只需要做计划，不要执行任何查询。**

你需要决定:
1. 基于产业链角色，需要验证哪些**概念维度**（从目录中选择 2-3 个最相关的）
2. 每个概念用哪个**工具**查询、什么**参数**
3. 哪些信息现有数据无法回答，需要**搜索**补充

## 输出 JSON

{{
  "preliminary_judgment": "基于现有线索的初步定性判断 (1-2句话)",
  "investigations": [
    {{
      "concept": "资本回报效率",
      "tool": "query_financial_data",
      "rationale": "为什么验证这个概念",
      "params": {{
        "code": "{code}",
        "indicators": ["roic_pct", "gross_margin_trend", "revenue_growth"]
      }}
    }}
  ],
  "valuation": {{
    "needed": true,
    "rationale": "为什么需要估值",
    "methods": ["peg", "ev_ebitda"],
    "params": {{
      "eps": 2.5,
      "growth_rate_pct": 25
    }}
  }},
  "search_queries": [
    {{
      "query": "{name} {industry} 市场份额 竞争格局 2026",
      "rationale": "想了解什么"
    }}
  ]
}}

规则:
  - investigations 最多 3 条概念，优先选与产业链定位最相关的
  - valuations.needed 只在确实需要定量估值时设为 true
  - search_queries 最多 2 条，仅当财务数据不足以判断时提出
  - 不要编造数据，不要输出投资建议
"""


# ═══════════════════════════════════════════════════════════
# Phase 3: 综合研判 Prompt 构建
# ═══════════════════════════════════════════════════════════

def build_synthesis_prompt(
    name: str,
    code: str,
    industry: str,
    plan: Dict[str, Any],
    evidence: Dict[str, Any],
) -> str:
    """构建 Phase 3 综合研判提示词

    输入: Phase 1 的原始计划 + Phase 2 的执行证据包
    LLM 不需要知道数据从哪来，只需要基于真实证据做判断。
    """
    # 整理证据包 (按概念分组, 仅财务数据)
    evidence_blocks = []
    for inv in plan.get("investigations", []):
        concept = inv.get("concept", "?")
        ev = evidence.get(concept, {})
        block = f"\n### {concept}\n"
        block += f"验证目标: {inv.get('rationale', '')}\n"
        if ev.get("financial"):
            block += f"财务数据: {_fmt_json(ev['financial'][:800])}\n"
        evidence_blocks.append(block)

    # 全局搜索结果 (不按概念分组 — 搜索-概念关键词匹配不可靠)
    search_all = evidence.get("search_all", [])
    search_block = ""
    if search_all:
        lines = "\n".join(f"- {s}" for s in search_all[:10])
        search_block = f"\n### 搜索证据 (未分组)\n{lines}\n"

    # 估值证据
    val_block = ""
    val_ev = evidence.get("valuation_result", {})
    if val_ev:
        val_block = f"\n### 估值结果\n{_fmt_json(val_ev)}\n"

    return f"""基于以下真实证据，对 {name}({code}) 在 {industry} 中的竞争地位做出独立判断。

## 验证计划摘要
概念: {[i.get('concept','') for i in plan.get('investigations',[])]}
{('估值方法: ' + str(plan.get('valuation',{}).get('methods',[]))) if plan.get('valuation',{}).get('needed') else ''}
搜索方向: {[q.get('query','')[:60] for q in plan.get('search_queries',[])]}

## 证据包
{"".join(evidence_blocks)}
{search_block}
{val_block}

## 任务

基于以上**真实证据**（不是猜测），输出结构化验证结论。

{{
  "analysis_dimensions": [
    {{
      "dimension": "维度名 (如'资本回报效率')",
      "rating": "strong / medium / weak / emerging",
      "evidence": ["具体证据1", "具体证据2"],
      "reasoning": "判断理由"
    }}
  ],
  "industry_context": "{industry}产业链定位判断 (1-2句话)",
  "lifecycle_stage": "startup / inflection / growth / mature / cyclical_bottom / cyclical_decline",
  "category_suggestion": "current_strong / future_strong / watchlist",
  "profit_capture_thesis": "靠什么机制在产业链中捕获利润",
  "thesis_breakers": ["什么条件会推翻这个判断"],
  "risk_tags": ["风险标签1", "风险标签2"],
  "roic_note": "资本回报效率综合判断 (1-2句话)",
  "data_gaps": ["还缺什么数据"],
  "watch_events": [
    {{
      "event": "关键监控事件",
      "trigger_condition": "触发条件/信号",
      "expected_timeframe": "预期时间",
      "event_type": "technology / regulation / competition / demand"
    }}
  ]
}}

规则:
  - 每条 evidence 必须来自上面的证据包，禁止编造
  - 证据不足的维度降级或标记 data_gaps
  - analysis_dimensions **至少输出 1 个维度**, 证据不足时也需输出 1 个维度并在 evidence 中注明"证据有限"
  - category_suggestion 决定标的保留/降级: current_strong(保留), future_strong(保留), watchlist(观察)
  - watch_events 只在确实存在可监控的催化剂时输出
"""


# ═══════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════

def _format_tools() -> str:
    """格式化工具列表供 prompt 使用"""
    lines = []
    for t in RESEARCH_TOOLS:
        lines.append(f"- {t['name']}: {t['description']}")
    return "\n".join(lines)


def _fmt_json(obj: Any, max_len: int = 1000) -> str:
    """格式化 JSON 并截断"""
    try:
        text = json.dumps(obj, ensure_ascii=False, default=str)
        return text[:max_len] + "..." if len(text) > max_len else text
    except Exception:
        return str(obj)[:max_len]
