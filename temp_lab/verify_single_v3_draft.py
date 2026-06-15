"""
_verify_single v3 — Plan-Execute-Synthesize 概念驱动设计

架构核心:
  1. LLM 在概念层思考 (资本回报效率/利润质量/客户锁定)
  2. Concept Registry 将概念映射到具体数据源 (SQLite指标/搜索)
  3. 系统确定性执行数据收集
  4. LLM 基于真实数据做综合研判

设计原则:
  - 面向概念而非面向字段: 提示词只谈"概念"，不谈"表名/字段名"
  - 可扩展: 新概念加一行注册，无需改提示词
  - 可测试: 概念→数据的映射是纯 Python 函数
"""

from typing import Dict, List, Callable, Awaitable, Any
from dataclasses import dataclass, field
from enum import Enum, auto

# ═══════════════════════════════════════════════
# 概念层 — 面向投资逻辑，不关心具体数据源
# ═══════════════════════════════════════════════

class VerdictDimension(Enum):
    """分析维度的概念分类 — 每个维度是 LLM 能理解的投资概念"""
    CAPITAL_RETURN_EFFICIENCY = auto()   # 资本回报效率: ROIC vs WACC
    PROFIT_QUALITY = auto()              # 利润质量: 毛利率趋势/利润真实性
    GROWTH_SUSTAINABILITY = auto()       # 增长可持续性: 营收增长/剪刀差
    CUSTOMER_LOCK_IN = auto()            # 客户锁定: 认证壁垒/切换成本
    COMPETITIVE_MOAT = auto()            # 竞争护城河: 份额/技术壁垒
    SUPPLY_CHAIN_POSITION = auto()       # 供应链地位: 瓶颈环节必要参与者
    FINANCIAL_HEALTH = auto()            # 财务健康: 现金流/负债/流动性
    MANAGEMENT_QUALITY = auto()          # 管理层质量 (搜索定性)
    REGULATORY_RISK = auto()             # 政策风险
    TECHNOLOGY_ROADMAP = auto()          # 技术路线风险

@dataclass
class ConceptSpec:
    """LLM 计划中的一条概念需求"""
    concept: VerdictDimension
    priority: str                        # "must_have" | "important" | "nice_to_have"
    hypothesis: str = ""                 # 待验证的具体假设
    # 不包含任何具体字段名或表名

@dataclass
class InformationGap:
    """LLM 认为现有信息不足以判断的方向 — 需要外部搜索"""
    target: str                          # 想了解什么 (概念层描述)
    query_type: str = "web_search"       # 搜索类型

@dataclass
class VerificationPlan:
    """Phase 1 输出: LLM 的验证计划 (全是概念，无具体字段)"""
    preliminary_judgment: str
    concepts_to_investigate: List[ConceptSpec]  # 想查什么概念
    information_gaps: List[InformationGap]      # 缺失的信息→需要搜索
    note: str = ""


# ═══════════════════════════════════════════════
# 概念注册表 — 概念的"真相源"
# 新概念只需在此注册，无需改提示词
# ═══════════════════════════════════════════════

@dataclass
class ConceptMapping:
    """一个概念→数据源的映射定义"""
    indicators: List[str] = field(default_factory=list)    # 对应 FINANCIAL_REGISTRY 指标
    raw_fields: List[str] = field(default_factory=list)    # 对应 FinancialStatement 字段
    needs_search: bool = False                             # 是否需要 web search 补充

CONCEPT_REGISTRY: Dict[VerdictDimension, ConceptMapping] = {
    VerdictDimension.CAPITAL_RETURN_EFFICIENCY: ConceptMapping(
        indicators=["roic_pct", "roic_interpretation"],
        raw_fields=["net_profit", "total_asset", "total_liability"],
    ),
    VerdictDimension.PROFIT_QUALITY: ConceptMapping(
        indicators=["gross_margin_trend", "operating_margin_stability"],
        raw_fields=["operate_revenue", "operate_cost",
                     "sell_expense", "admin_expense", "rd_expense",
                     "net_profit", "operate_profit"],
    ),
    VerdictDimension.GROWTH_SUSTAINABILITY: ConceptMapping(
        indicators=["revenue_growth", "profit_growth", "scissor_gap"],
        raw_fields=["operate_revenue", "net_profit"],
    ),
    VerdictDimension.CUSTOMER_LOCK_IN: ConceptMapping(
        indicators=["contract_liability"],
        raw_fields=["accounts_receivable", "accounts_receivable",
                     "contract_liability"],
        needs_search=True,
    ),
    VerdictDimension.COMPETITIVE_MOAT: ConceptMapping(
        indicators=["roic_stability", "operating_margin_stability"],
        needs_search=True,
    ),
    VerdictDimension.SUPPLY_CHAIN_POSITION: ConceptMapping(
        needs_search=True,
    ),
    VerdictDimension.FINANCIAL_HEALTH: ConceptMapping(
        indicators=["ocf_health", "inventory_turnover"],
        raw_fields=["operate_cash_flow", "net_profit",
                     "total_current_assets", "total_current_liability",
                     "inventory"],
    ),
    VerdictDimension.MANAGEMENT_QUALITY: ConceptMapping(
        needs_search=True,
    ),
    VerdictDimension.REGULATORY_RISK: ConceptMapping(
        needs_search=True,
    ),
    VerdictDimension.TECHNOLOGY_ROADMAP: ConceptMapping(
        needs_search=True,
    ),
}


# ═══════════════════════════════════════════════
# Phase 1: LLM 计划 (纯概念, 无 SQL/字段名)
# ═══════════════════════════════════════════════

def build_plan_prompt(name: str, code: str, industry: str,
                      source_context: str, node_context: str) -> str:
    """构建计划阶段提示词 — 只描述概念，不暴露具体数据字段。

    LLM 只需思考:
      - 验证对象在产业链中的角色
      - 需要确认哪些维度的竞争地位
      - 哪些信息已有、哪些需要搜索补充
    """
    # 列出所有可用概念及其含义 (供 LLM 选)
    concept_catalog = "\n".join(
        f"  - {c.name}: {_concept_meaning(c)}" for c in VerdictDimension
    )

    return f"""你正在验证一家公司在 {industry} 产业链中是否能捕获利润。

标的: {name}({code})
来源线索: {source_context}
产业链背景: {node_context}

## 可用分析概念

{concept_catalog}

## 任务

设计一份验证计划。**只需要做计划，不要执行任何数据查询。**

输出结构:
{{
  "preliminary_judgment": "基于现有线索的初步判断",
  "concepts": [
    {{
      "concept": "CONCEPT_NAME",        // 从可用概念中选择
      "priority": "must_have/important/nice_to_have",
      "hypothesis": "需要验证的具体假设"  // 结合产业链角色
    }}
  ],
  "information_gaps": [
    {{
      "target": "想了解什么信息",        // 自由描述
      "search_direction": "可能的搜索方向"
    }}
  ]
}}

约束:
  - concepts 最多 4 条, 优先选择与产业链定位最相关的
  - information_gaps 最多 2 条, 仅当现有信息确实不足时提出
  - 不要编造数据, 不要直接输出投资建议
"""


# ═══════════════════════════════════════════════
# Phase 2: 系统执行 (确定性, 零 LLM)
# ═══════════════════════════════════════════════

class PlanExecutor:
    """将 LLM 的概念计划翻译为具体数据查询并执行"""

    def __init__(self, code: str):
        self.code = code

    async def execute(self, plan: VerificationPlan) -> Dict[str, Any]:
        """执行计划 → 返回按概念分组的证据"""
        # 1. 汇总所有概念的 indicators + raw_fields
        all_indicators = set()
        all_raw_fields = set()
        search_agenda = []

        for spec in plan.concepts_to_investigate:
            mapping = CONCEPT_REGISTRY[spec.concept]
            all_indicators.update(mapping.indicators)
            all_raw_fields.update(mapping.raw_fields)
            if mapping.needs_search:
                search_agenda.append(spec)

        # 2. 财务数据查询 (确定性 SQL)
        fin_data = {}
        if all_indicators or all_raw_fields:
            from app.domain.quant.engine.financial_query_service import FinancialQueryService
            svc = FinancialQueryService()
            fin_data = await svc.query(
                self.code,
                indicators=list(all_indicators),
                raw_fields=list(all_raw_fields)
            )

        # 3. 搜索信息缺口
        search_results = []
        for gap in plan.information_gaps[:2]:
            from app.domain.research.services.data_loader import data_loader
            raw = await data_loader.search_web(gap.target, num=5)
            search_results.append({
                "target": gap.target,
                "results": [{"snippet": r.get("snippet","")[:300]}
                           for r in raw if r.get("snippet")],
            })

        # 4. 按概念分组整理 (每概念一份证据包)
        evidence_packages = {}
        for spec in plan.concepts_to_investigate:
            mapping = CONCEPT_REGISTRY[spec.concept]
            ev = {"concept": spec.concept.name, "hypothesis": spec.hypothesis}

            # 该概念对应的财务数据
            ev["financial_evidence"] = {
                k: fin_data.get(k) for k in mapping.indicators + mapping.raw_fields
                if fin_data.get(k) is not None
            }

            # 该概念相关的搜索结果
            ev["search_evidence"] = [
                r for r in search_results
                if spec.hypothesis in r.get("target", "")
                or any(w in r.get("target", "") for w in spec.hypothesis.split())
            ]

            evidence_packages[spec.concept.name] = ev

        return {
            "evidence_packages": evidence_packages,
            "financial_raw": fin_data,
        }


# ═══════════════════════════════════════════════
# Phase 3: LLM 综合研判 (数据已备好)
# ═══════════════════════════════════════════════

def build_synthesis_prompt(name: str, code: str, industry: str,
                            plan: VerificationPlan,
                            evidence: Dict[str, Any]) -> str:
    """构建综合研判提示词 — 数据皆已备好, LLM 只需做判断。

    输入是 plan 时的概念列表 + 每条概念对应的实际证据。
    LLM 不需要知道数据从哪来的, 只需要基于证据做判断。
    """
    evidence_block = ""
    for pkg in evidence.get("evidence_packages", {}).values():
        evidence_block += f"\n### {pkg['concept']}\n"
        evidence_block += f"待验证假设: {pkg['hypothesis']}\n"
        fe = pkg.get("financial_evidence", {})
        if fe:
            evidence_block += f"财务证据: {fe}\n"
        se = pkg.get("search_evidence", [])
        if se:
            evidence_block += f"搜索证据: {se}\n"

    return f"""基于以下证据, 对 {name}({code}) 在 {industry} 中的竞争地位做出判断。

## 验证计划
计划概念: {[s.concept.name for s in plan.concepts_to_investigate]}

## 证据包
{evidence_block}

## 任务
基于以上真实证据, 输出结构化结论。

{{
  "analysis_dimensions": [
    {{
      "dimension": "维度名",
      "rating": "strong/medium/weak/emerging",
      "evidence": ["证据1", "证据2"],
      "reasoning": "判断理由"
    }}
  ],
  "lifecycle_stage": "startup/inflection/growth/mature/cyclical_bottom/cyclical_decline",
  "category_suggestion": "current_strong/future_strong/watchlist",
  "profit_capture_thesis": "靠什么机制捕获利润",
  "thesis_breakers": ["推翻条件"],
  "data_gaps": ["缺什么数据"],
  "watch_events": [
    {{"event": "事件", "trigger_condition": "信号",
      "expected_timeframe": "时间", "event_type": "类型"}}
  ]
}}

规则:
  - 每条 evidence 必须来自证据包, 禁止编造
  - 证据不足的维度降级或标记 data_gaps
"""


def _concept_meaning(dimension: VerdictDimension) -> str:
    """概念含义描述 — 给 LLM 理解每个概念代表什么"""
    descriptions = {
        VerdictDimension.CAPITAL_RETURN_EFFICIENCY: "公司投入资本是否产生超额回报",
        VerdictDimension.PROFIT_QUALITY: "利润是否真实、可持续、有议价权支撑",
        VerdictDimension.GROWTH_SUSTAINABILITY: "增长来源于量价齐升还是会计操纵",
        VerdictDimension.CUSTOMER_LOCK_IN: "客户认证壁垒、切换成本、供应集中度",
        VerdictDimension.COMPETITIVE_MOAT: "技术/品牌/规模壁垒、市场份额趋势",
        VerdictDimension.SUPPLY_CHAIN_POSITION: "在产业链瓶颈环节中的地位、被替代风险",
        VerdictDimension.FINANCIAL_HEALTH: "现金流是否覆盖投资、偿债压力",
        VerdictDimension.MANAGEMENT_QUALITY: "管理层战略执行力、历史诚信记录",
        VerdictDimension.REGULATORY_RISK: "政策变化对业务的影响方向与幅度",
        VerdictDimension.TECHNOLOGY_ROADMAP: "技术路线是否匹配产业趋势、被颠覆风险",
    }
    return descriptions.get(dimension, "")
