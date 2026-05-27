"""
SystemDynamicsAgent V1.1 — Step 4: 系统动力学推演
定位: 消费 Step 3 的静态产业链图谱, 推演结构受压后如何变形
核心问题: 瓶颈怎么迁移? 谁的资源被挤占? 谁被忽视了? 什么会打破推演?
V1.1: +Step3反向校验 +search_queries替代china_stocks +monitoring_metric +evidence_type +confidence
"""
import asyncio, re
from decimal import Decimal
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger


class SystemDynamicsAgent(ResearchAgent):
    """系统动力学推演 V1.1 — 瓶颈迁移 + 资源挤占 + 隐藏受益者 + Step3反向校验"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "SystemDynamicsAgent"

    # ═══ 工具 ═══════════════════════════════

    @staticmethod
    def _clean_snippet(text: str) -> str:
        if not text: return ""
        if "%PDF" in text or "endstream" in text: return ""
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
        return text[:250]

    async def _search_adaptive(self, chains: List[List[str]], num: int = 4, trace=None) -> List[Dict]:
        all_data = []
        for chain in chains:
            items = []
            for q in chain:
                results = await self.data_loader.search_web(q, num=num)
                items = []
                for r in results:
                    snippet = self._clean_snippet(r.get("snippet", ""))
                    if snippet:
                        items.append({"title": r.get("title", ""), "snippet": snippet})
                if trace: trace.record_search(q, items)
                if items: break
            all_data.append({"query": chain[0] if not items else q, "results": items})
        return all_data

    # ═══ 主入口 ═══════════════════════════════

    async def analyze(self, ctx: Dict[str, Any] = None, trace=None) -> Dict[str, Any]:
        ctx = await self.load_context(ctx or {})
        if not self.provider:
            return {"agent": self.name, "error": "No AI provider"}

        industry = ctx.get("industry", "未指定")
        # Step 3 输出
        chain_map = ctx.get("supply_chain_map", [])
        scarcity = ctx.get("scarcity_ranking", [])
        core_stocks = ctx.get("core_stocks", [])

        logger.info(f"[{self.name}] Deduction: {industry} ({len(chain_map)} chain nodes)")

        # 2+1 轮搜索: 瓶颈迁移 + 隐藏受益者 + 兜底(不依赖 top_node)
        top_node = (scarcity[0].get("segment", industry) if scarcity else industry)
        top_node_conf = (scarcity[0].get("confidence", "?") if scarcity else "?") if isinstance(scarcity, list) and scarcity and isinstance(scarcity[0], dict) else "?"
        search_chains = [
            [f"{industry} {top_node} 扩产 瓶颈迁移 新瓶颈 制约 2026",
             f"{industry} 产能扩张 瓶颈转移 新约束",
             f"{industry} supply chain bottleneck shift constraint"],
            [f"{industry} 供应链 意外受益 被忽视 隐性 受益方 受损",
             f"{industry} 产业链 隐藏 受益 挤占 受损 2026",
             f"{industry} hidden beneficiary crowding out supply chain"],
            # 兜底: 不依赖 Step 3 的 top_node, 从整个产业链视角搜索
            [f"{industry} 产业链 结构变形 利润迁移 赢家 输家 2026",
             f"{industry} 产能 释放 CAPEX 受益者 受损者 2026",
             f"{industry} supply chain winners losers structural shift 2026"],
        ]
        search_data = await self._search_adaptive(search_chains, num=4, trace=trace)

        # LLM 推演
        prompt = self._build_prompt(industry, chain_map, scarcity, core_stocks, search_data)

        try:
            text = await asyncio.wait_for(
                self.provider.chat_pro(prompt, max_tokens=6144), timeout=480)
            if trace: trace.record_llm(prompt, text, model="deepseek-v4-pro")
            result = self.parse_json(text)
            if isinstance(result, dict):
                sd = result.get("system_dynamics", {})
                n_dynamics = len(sd.get("bottleneck_migration", {}).get("migration_drivers", []))
                n_crowding = len(sd.get("resource_crowding", []))
                n_hidden = len(sd.get("hidden_beneficiaries", []))
                sanity = result.get("step3_sanity_check", {})
                n_questioned = len(sanity.get("questioned", []))
                confidence = result.get("confidence", "?")
                logger.info(f"[{self.name}] Done: confidence={confidence}, sanity={n_questioned}, migration={n_dynamics}, crowding={n_crowding}, hidden={n_hidden}")
                if trace:
                    trace.record_note("summary", f"confidence={confidence}, sanity_checks={n_questioned}, crowding={n_crowding}, hidden={n_hidden}")
                return result
        except asyncio.TimeoutError:
            logger.warning(f"[{self.name}] Timeout: {industry}")
        except Exception as e:
            logger.warning(f"[{self.name}] Failed: {e}")

        return {"agent": self.name, "error": "Analysis failed", "system_dynamics": {}}

    # ═══ Prompt 构建 ═══════════════════════════

    def _build_prompt(self, industry, chain_map, scarcity, core_stocks, search_data) -> str:
        chain_summary = ""
        for node in chain_map[:3]:
            sr = node.get("supply_rigidity", {})
            node_conf = node.get("confidence", "?")
            margin_est = node.get("profit_pool", {}).get("margin_estimated", "?")
            chain_summary += f"- L{node.get('level','?')} {node.get('name','?')}: severity={sr.get('severity','?')}, root_cause={sr.get('root_cause','?')}, expand={sr.get('expand_cycle','?')}, confidence={node_conf} | margin_estimated={margin_est}\n"

        scarcity_summary = "\n".join(
            f"{s.get('rank','?')}. {s.get('segment','?')}: {s.get('rigidity_narrative','')[:80]}"
            for s in (scarcity or [])[:3])

        stocks_str = ", ".join(s.get("code","?")+" "+s.get("name","?") for s in (core_stocks or [])[:5])

        search_summary = ""
        for sd in search_data:
            search_summary += f"\n### {sd['query']}\n"
            for r in sd["results"][:3]:
                search_summary += f"  - {r['title']}: {r['snippet'][:180]}\n"

        return f"""你是系统动力学专家。输入是 Step 3 输出的产业链静态结构, 你的任务是推演这个结构在压力下**怎么变形**。

## ★ 强制: Step 3 反向校验 (推演前必须)

在开始推演之前, 先审视 Step 3 的输出:
1. 哪个瓶颈的 severity 可能被高估/低估? (注意: margin_level 是 LLM 估计值, 见 margin_estimated=true 标记, 需 Step 6 财务审计后回写真实值)
2. 哪个 profit_pool 判断可能因搜索片段偏差而不准确?
3. 哪个环节的"零替代"断言可能有例外?

→ 找出 1-2 个"可能不准确"的 Step 3 判断, 在输出的 step3_sanity_check 字段中写明质疑和调整。
→ 如果没有质疑出任何问题, 说明审视不够。至少找出 1 个。
→ 基于质疑调整后续推演的前提假设 (如: severity=extreme 被质疑 → 推演中降低该节点的确定性, 标记 confidence=medium)。

## 核心方法: 六步链式推演
需求变化 → 资源变化 → 供给变化 → 价格变化 → 利润变化 → CAPEX变化 → 再平衡

## 六个参考案例 (few-shot)
1. 资源挤占: HBM消耗3x晶圆 → 挤占DDR产能 → DRAM涨价 → 二线DRAM厂受益
2. 联产经济学: 炼油减产 → 硫磺供给收缩 → 磷肥飞涨 → 化肥企业受益
3. 瓶颈迁移: GPU短缺 → 云厂自研芯片 → CoWoS成新瓶颈 → 封装设备受益
4. CAPEX错配: 成熟制程CAPEX不足 → MCU缺货2年 → 成熟代工厂暴利
5. 利润池迁移: AI从硬件 → 软件 → 云服务 → 应用, 利润流向不同阶段
6. 供给刚性: 高纯石英砂只有北卡矿 → 光伏扩产 → 石英砂2年涨价10倍

## Step 3 产业链结构 (注意: margin_estimated=true 表示该值为 LLM 估计, 待 Step 6 修正)
行业: {industry}
核心标的: {stocks_str}
瓶颈图谱:
{chain_summary}
稀缺排序:
{scarcity_summary}

## 补充搜索
{search_summary}

## 输出纯 JSON (全定性, 不做数值评分)

{{
  "confidence": "high/medium/low/insufficient_data — 基于 Step 3 数据质量 + 补充搜索覆盖度综合判断",
  "confidence_note": "说明数据缺口或不确定性来源",

  "step3_sanity_check": {{
    "questioned": [
      {{"claim": "Step 3 中哪个具体判断", "doubt": "为什么可能不准确"}}
    ],
    "adjustment": "基于质疑, 调整了推演中的哪些前提假设"
  }},

  "system_dynamics": {{

    "bottleneck_migration": {{
      "current": "当前最主要的瓶颈环节",
      "next_12m": "12个月后哪个环节可能成为新瓶颈",
      "next_24m": "24个月后",
      "next_36m": "36个月后",
      "migration_drivers": [
        {{
          "from": "从哪个瓶颈", "to": "迁移到哪个瓶颈", "trigger": "触发条件是什么",
          "monitoring_metric": "可观测的量化监控指标 (如: 台积电CoWoS月产能 wpm)",
          "trigger_threshold": "触发新瓶颈的量化阈值 (如: CoWoS月产能突破200K wpm时)",
          "evidence": [
            {{"fact":"事实","from":"search[1.X]·来源","quality":{{"level":"high","source_type":"company_filing"}},"evidence_type":"hard_data_confirmation"}}
          ]
        }}
      ],
      "evidence": [...]
    }},

    "resource_crowding": [
      {{
        "resource": "被挤占的资源",
        "squeezed_from": "从哪个环节被挤走",
        "squeezed_by": "被哪个环节挤占",
        "victim_sector": "受害方 — 谁被迫承受涨价/断供",
        "hidden_beneficiary": "谁意外受益 — 替代供应商或关联方",
        "visibility": "very_low/low/moderate — 如实判断市场关注度, 不因Alpha大而压低",
        "time_to_impact": "immediate/medium_term/long_term",
        "monitoring_metric": "监控指标 (如: ABF基板交期 周)",
        "trigger_threshold": "触发受益标的筛查的量化阈值 (如: 交期突破26周时)",
        "search_queries": ["用于下游标的映射的精准搜索词", "禁止输出股票代码"],
        "evidence": [
          {{"fact":"事实","from":"search[X]·来源","quality":{{"level":"high","source_type":"industry_data"}},"evidence_type":"forward_looking_rumor"}}
        ]
      }}
    ],

    "profit_pool_shift": [
      {{
        "from_segment": "利润从哪个环节流出",
        "to_segment": "利润流向哪个环节",
        "trigger": "触发利润迁移的条件",
        "timeline": "6-12个月/12-24个月/24-36个月",
        "confidence": "high/medium/low/speculative",
        "monitoring_metric": "监控指标",
        "trigger_threshold": "触发阈值",
        "evidence": [...]
      }}
    ],

    "hidden_beneficiaries": [
      {{
        "sector": "被市场忽视的受益方",
        "reason": "为什么受益, 为什么市场没注意到",
        "visibility": "very_low/low/moderate — 如实判断, 禁止为追求Alpha压低",
        "time_to_impact": "immediate/medium_term/long_term",
        "search_queries": ["用于下游标的映射的搜索词"],
        "evidence": [...]
      }}
    ],

    "thesis_breakers": [
      {{
        "thesis": "推演出的核心论点",
        "break_condition": "什么具体条件变化会打破这个论点 (必须是可量化/可观测的)",
        "watch_signal": "监控什么指标来验证 (必须是可获取的高频数据)",
        "evidence": [...]
      }}
    ]

  }}
}}

## 枚举约束 (★ 强制)
- confidence (整体): high / medium / low / insufficient_data
- profit_pool_shift.confidence: high / medium / low / speculative
- visibility: very_low / low / moderate — 如实判断, 禁止为追求Alpha而压低
- time_to_impact: immediate(<3月) / medium_term(3-12月) / long_term(12-36月)
- migration_drivers.from/to: 必须是具体的产业环节名称 (不是行业分类)
- evidence_type: forward_looking_rumor / hard_data_confirmation

## 证据要求
- 每个结论块必须附 evidence 数组, 至少 1 条
- from 格式: "search[轮次]·来源简称"
- quality.level: high/medium/low
- quality.source_type: company_filing/industry_data/official_policy/sell_side_report/news_media
- evidence_type: forward_looking_rumor (前瞻信号/传闻→试探仓) / hard_data_confirmation (财报/公告→重仓)
- self_media/ai_summary 仅参考, 不得单独支撑关键推演

## 质量自检 — 推演十问 (逐条确认)
1.真正驱动力? 2.哪个资源最稀缺? 3.高利润会吸走谁的资源?
4.谁会供给下降? 5.谁会意外涨价? 6.谁拥有定价权?
7.哪个瓶颈最难扩产? 8.利润会迁移到哪里? 9.市场还没发现谁?
10.什么信号会证伪我?
确保你的推演回答了以上所有问题。resource_crowding 和 hidden_beneficiaries 至少各 1 条。
禁止 LLM 直接输出股票代码 (china_stocks 已删除, 用 search_queries 替代)。
不做数值评分, 不做行业分类描述, 聚焦跨环节推演。"""

    # ═══ 基类 ═══════════════════════════════

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return await super().load_context(ctx)

    @staticmethod
    def build_prompt(ctx): return "SystemDynamicsAgent V1.1"

    @staticmethod
    async def stream(ctx): yield "streaming not implemented"
