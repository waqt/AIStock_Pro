"""
ReportSynthesisAgent V1.0 — Step 11: 综合投研报告
定位: 读取 Step 1~10 的全部输出, 合成为一份可读性强、结构化的中文投研报告
核心原则: LLM 做总结提炼, 系统做数据汇总
"""
import asyncio
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.framework.logger import logger


class ReportSynthesisAgent(ResearchAgent):
    """综合投研报告 V1.0 — 全链路输出合成"""

    def __init__(self, provider=None):
        super().__init__(provider=provider)
        self.name = "ReportSynthesisAgent"

    async def analyze(self, ctx: Dict[str, Any] = None, trace=None) -> Dict[str, Any]:
        if not self.provider:
            return {"agent": self.name, "error": "No AI provider"}

        industry = ctx.get("industry", "未指定")
        steps = ctx.get("steps", {})  # {step_name: output_dict}

        logger.info(f"[{self.name}] Synthesizing report: {industry} ({len(steps)} steps)")

        # 格式化各步骤输入
        summary = self._format_summary(industry, steps)
        sections = self._format_sections(industry, steps)

        prompt = self._build_prompt(industry, summary, sections)

        try:
            text = await self.provider.chat_pro(prompt, max_tokens=16384, timeout=600)
            if trace: trace.record_llm(prompt, text, model="deepseek-v4-pro")
            result = self.parse_json(text)

            if isinstance(result, dict):
                # 确保关键字段存在
                report = result.get("report", {})
                n_sections = len(report.get("sections", []))
                logger.info(f"[{self.name}] Done: {n_sections} sections, quality={result.get('report_quality','?')}")
                if trace:
                    trace.record_note("summary", f"{n_sections} sections, quality={result.get('report_quality','?')}")

                # 附加原始数据引用
                result["_industry"] = industry
                result["_steps_summary"] = {
                    step: list(out.keys())[:5] if isinstance(out, dict) else type(out).__name__
                    for step, out in steps.items() if out
                }
                return result

        except asyncio.TimeoutError:
            logger.warning(f"[{self.name}] Timeout: {industry}")
        except Exception as e:
            logger.warning(f"[{self.name}] Failed: {e}")

        # 回退: 如果 LLM 失败, 返回结构化的基本汇总
        return self._fallback_report(industry, steps)

    def _format_summary(self, industry: str, steps: dict) -> str:
        """生成各步骤摘要"""
        lines = []

        # Step 1b 资本流向
        s1b = steps.get("step1b_capital_flow", {})
        pv = s1b.get("pressure_vectors", [])
        if pv:
            lines.append(f"资本流向: {len(pv)} 个压力向量")

        # Step 2 行业看门人
        s2 = steps.get("step2_gatekeeper", {})
        industries = s2.get("industries", []) or ([] if isinstance(s2, dict) else [])
        if industries:
            verdicts = [f"{i.get('industry','?')}({i.get('verdict',{}).get('path','?')})" for i in industries[:3]]
            lines.append(f"行业扫描: {', '.join(verdicts)}")

        # Step 3 供应链拆解
        s3 = steps.get("step3_sc_hacker", {})
        scm = s3.get("supply_chain_map", [])
        if scm:
            lines.append(f"供应链: {len(scm)} 层")
            bn = [n.get("name", "?") for n in scm if n.get("supply_rigidity", {}).get("severity") in ("extreme", "high")]
            if bn:
                lines.append(f"关键瓶颈: {', '.join(bn[:3])}")

        # Step 4 系统动力学
        s4 = steps.get("step4_system_dynamics", {})
        sd = s4.get("system_dynamics", {}) if isinstance(s4, dict) else {}
        if sd:
            n_cross = len(sd.get("cross_chain_spillover", []))
            n_hidden = len(sd.get("hidden_beneficiaries", []))
            lines.append(f"动力学推演: {n_cross} 跨产业溢出, {n_hidden} 隐藏受益者")

        # Step 6 核心筛选
        s6 = steps.get("step6_core_screening", {})
        ranked = s6.get("ranked_stocks", [])
        future = s6.get("future_strong_candidates", [])
        if ranked:
            lines.append(f"核心筛选: {len(ranked)} 只排名标的, {len(future)} 只未来强势")

        # Step 9 预期差
        s9 = steps.get("step9_expectation_gap", {})
        gaps = s9.get("expectation_gaps", []) if isinstance(s9, dict) else []
        if gaps:
            bullish = sum(1 for g in gaps if g.get("direction") == "bullish")
            bearish = sum(1 for g in gaps if g.get("direction") == "bearish")
            lines.append(f"预期差: {len(gaps)} 项 ({bullish} bullish/{bearish} bearish)")

        # Step 10 风险分析
        s10 = steps.get("step10_risk_analysis", {})
        risks = s10.get("risks", []) if isinstance(s10, dict) else []
        if risks:
            critical = sum(1 for r in risks if r.get("severity") == "critical")
            high = sum(1 for r in risks if r.get("severity") == "high")
            lines.append(f"风险扫描: {len(risks)} 项 ({critical} critical/{high} high)")

        return "\n".join(lines) if lines else "(无可用数据)"

    def _format_sections(self, industry: str, steps: dict) -> str:
        """为 LLM 准备各步骤详细数据 (精简, 不含过长内容)"""
        sections = []

        # Step 1b
        s1b = steps.get("step1b_capital_flow", {})
        if isinstance(s1b, dict):
            sections.append(("STEP1b_资本流向", self._dict_to_text(s1b, max_keys=["global_summary", "capital_flow_summary", "energy_flow_summary", "pressure_vectors"], max_array=3)))

        # Step 2
        s2 = steps.get("step2_gatekeeper", {})
        if isinstance(s2, dict):
            s2_short = {}
            inds = s2.get("industries", [])
            if inds:
                s2_short["industries"] = [{
                    "industry": i.get("industry"),
                    "verdict": i.get("verdict"),
                    "cycle_position": i.get("cycle_position"),
                    "payoff": i.get("payoff"),
                    "mismatch_analysis": {k: v for k, v in i.get("mismatch_analysis", {}).items() if k != "details"}
                } for i in inds[:2]]
            sections.append(("STEP2_行业分析", self._dict_to_text(s2_short, max_array=3)))

        # Step 3
        s3 = steps.get("step3_sc_hacker", {})
        if isinstance(s3, dict):
            s3_short = {
                "supply_chain_map": [{
                    "level": n.get("level"),
                    "name": n.get("name"),
                    "bottleneck_narrative": str(n.get("bottleneck_narrative", ""))[:200],
                    "supply_rigidity": n.get("supply_rigidity"),
                    "profit_pool": {k: v for k, v in n.get("profit_pool", {}).items() if k != "details"},
                } for n in s3.get("supply_chain_map", [])[:4]]
            }
            sections.append(("STEP3_供应链拆解", self._dict_to_text(s3_short, max_array=3)))

        # Step 4
        s4 = steps.get("step4_system_dynamics", {})
        if isinstance(s4, dict):
            sd = s4.get("system_dynamics", {})
            if sd:
                sections.append(("STEP4_系统动力学", self._dict_to_text({
                    "migration": sd.get("bottleneck_migration", {}).get("migration_drivers", [])[:2],
                    "crowding": [{"resource": c.get("resource"), "victim": c.get("victim_sector"), "hidden": c.get("hidden_beneficiary")} for c in sd.get("resource_crowding", [])[:2]],
                    "cross_spillover": [{"source": c.get("source_node"), "direction": c.get("impact_direction"), "sector": c.get("affected_sector")} for c in sd.get("cross_chain_spillover", [])[:3]],
                }, max_array=3)))

        # Step 6
        s6 = steps.get("step6_core_screening", {})
        if isinstance(s6, dict):
            sections.append(("STEP6_核心资产筛选", self._dict_to_text({
                "ranked": [{"code": s.get("code"), "name": s.get("name"), "rank": s.get("rank"), "stage": s.get("company_stage")} for s in s6.get("ranked_stocks", [])[:5]],
                "future": [{"code": s.get("code"), "name": s.get("name")} for s in s6.get("future_strong_candidates", [])[:3]],
            }, max_array=5)))

        # Step 9
        s9 = steps.get("step9_expectation_gap", {})
        if isinstance(s9, dict) and s9.get("expectation_gaps"):
            sections.append(("STEP9_市场预期差", self._dict_to_text({
                "verdict": s9.get("consensus_verdict"),
                "gaps": [{"type": g.get("gap_type"), "direction": g.get("direction"), "magnitude": g.get("gap_magnitude"), "consensus": str(g.get("market_consensus", ""))[:100], "pipeline": str(g.get("pipeline_view", ""))[:100]} for g in s9.get("expectation_gaps", [])[:5]],
            }, max_array=5)))

        # Step 10
        s10 = steps.get("step10_risk_analysis", {})
        if isinstance(s10, dict) and s10.get("risks"):
            sections.append(("STEP10_风险分析", self._dict_to_text({
                "summary": s10.get("risk_summary", ""),
                "risks": [{"cat": r.get("category"), "risk": str(r.get("risk", ""))[:100], "severity": r.get("severity"), "prob": r.get("probability")} for r in s10.get("risks", [])[:6]],
                "scenarios": [{"name": sc.get("name"), "prob": sc.get("probability")} for sc in s10.get("scenario_analysis", {}).get("scenarios", [])],
                "worst_case": s10.get("scenario_analysis", {}).get("worst_case", {}),
            }, max_array=5)))

        result = ""
        for name, text in sections:
            result += f"\n### {name}\n{text}\n"
        return result

    @staticmethod
    def _dict_to_text(d: dict, max_keys: list = None, max_array: int = 5) -> str:
        """dict 转文字, 控制最大长度"""
        import json as _json
        if not d:
            return "(空)"
        try:
            text = _json.dumps(d, ensure_ascii=False, indent=2, default=str)
            if len(text) > 3000:
                text = text[:3000] + "\n...(截断)"
            return text
        except Exception:
            return str(d)[:500]

    def _build_prompt(self, industry: str, summary: str, sections: str) -> str:
        return f"""你是首席投资官 (CIO) 的AI副手。你的任务是基于 Pipeline 全链路分析结果, 撰写一份**专业、可读、有操作性的中文投研综合报告**。

这份报告将呈现给有经验的投资者阅读, 不是给 AI 看的 JSON 数据结构。

## ★ 报告结构要求

必须包含以下 8 个部分, 顺序不能变:

### 1. 报告摘要 (Executive Summary)
- 用 3-5 句概括最重要的结论: 产业方向、核心标的、主要预期差、最大风险
- 让读者只看这部分就能理解全貌

### 2. 宏观与资本流向背景
- 全球 CapEx/资本流向的关键信号 (引用 Step 1a/1b)
- 本产业在宏观背景下的定位
- 什么在驱动这个产业

### 3. 产业定位与竞争格局
- 行业所处的周期阶段 (引用 Step 2)
- 五错配分析的重点结论
- 供需缺口的主要成因

### 4. 供应链瓶颈与利润分配
- 哪些环节是瓶颈, bottleneck_severity 如何 (引用 Step 3)
- 利润在哪里聚集, 价值捕获谁最强
- 供给刚性的根因和持续时间

### 5. 产业链动态演化
- 瓶颈迁移方向 (引用 Step 4)
- 哪些环节会意外受益/受损
- 跨产业溢出效应

### 6. 核心标的筛选结果
- 按排名列出 top 候选 (引用 Step 6)
- 每只标的的: 入选逻辑、生命周期阶段、关键验证维度
- 未来强势候选列表

### 7. 预期差分析 (这是报告的 Alpha 核心)
- 市场共识错在哪里? (引用 Step 9)
- 看多 vs 看空的双面论证
- 最有可能让市场意外的变量

### 8. 风险与情景分析
- 按 severity 排序的风险列表 (引用 Step 10)
- 最坏情况分析
- 需要监控的关键信号

## 输入数据

### 行业
{industry}

### 全链路摘要
{summary}

### 各步骤详细数据
{sections}

## 写作规范 (★ 强制)
- 用**专业、简洁的中文**, 不用夸张词汇 ("惊天"/"暴涨"/"暴雷")
- 每个结论尽量附证据来源 (如: "Step 6 筛选显示...")
- 区分"确定性的判断"和"推测性的观点"
- 风险要前置, 不要只在最后提
- 不使用 LLM 常见的套话 ("值得注意的是"/"在当今复杂的...")
- 不打分、不做量化评分、不输出 LLM 不擅长的精确 PE/PEG 数字
- 报告长度控制在 2000-4000 字, 精炼优先

## 输出 JSON

{{
  "report_quality": "high / medium / low — 基于输入数据完整度",
  "report": {{
    "title": "报告标题 (含行业和日期)",
    "summary": "报告摘要 (3-5句)",
    "sections": [
      {{
        "title": "章节标题",
        "content": "章节正文 (纯文本, 支持 Markdown 格式)",
        "key_points": ["该章节的2-4个核心要点"]
      }}
    ],
    "top_candidates": [
      {{
        "code": "股票代码",
        "name": "股票名称",
        "rationale": "入选核心逻辑 (一句话)",
        "risk_flag": "主要风险点 (如无可写'无')"
      }}
    ],
    "watch_signals": [
      "需要重点监控的 3-5 个信号"
    ]
  }}
}}
"""

    def _fallback_report(self, industry: str, steps: dict) -> Dict:
        """LLM 失败时的文本拼接回退"""
        s6 = steps.get("step6_core_screening", {})
        s9 = steps.get("step9_expectation_gap", {})
        s10 = steps.get("step10_risk_analysis", {})

        ranked = s6.get("ranked_stocks", [])
        gaps = s9.get("expectation_gaps", []) if isinstance(s9, dict) else []
        risks = s10.get("risks", []) if isinstance(s10, dict) else []

        candidates = [
            {"code": s.get("code", "?"), "name": s.get("name", "?"),
             "rationale": str(s.get("why", ""))[:100],
             "risk_flag": "待评估"}
            for s in ranked[:5]
        ]

        sections = []
        sections.append({
            "title": "产业概况",
            "content": f"{industry} 已完成 Pipeline 全链路分析。",
            "key_points": [f"候选标的: {len(ranked)} 只排名标的"]
        })

        if gaps:
            sections.append({
                "title": "预期差",
                "content": f"识别出 {len(gaps)} 项预期差。",
                "key_points": [f"{g.get('gap_type','?')}/{g.get('direction','?')}: {str(g.get('market_consensus',''))[:80]}" for g in gaps[:3]]
            })

        if risks:
            sections.append({
                "title": "风险分析",
                "content": f"识别出 {len(risks)} 项风险。",
                "key_points": [f"[{r.get('severity','?')}] {str(r.get('risk',''))[:80]}" for r in risks[:3]]
            })

        return {
            "report_quality": "low (LLM synthesis failed, template fallback)",
            "report": {
                "title": f"{industry} 投研综合报告 (模板生成)",
                "summary": f"{industry} 产业分析完成。{len(ranked)} 只标的经过筛选, {len(gaps)} 项预期差被识别, {len(risks)} 项风险被标记。请查看各步骤详情。",
                "sections": sections,
                "top_candidates": candidates,
                "watch_signals": [],
            },
            "_industry": industry,
            "_is_fallback": True,
        }

    @staticmethod
    def build_prompt(ctx): return "ReportSynthesisAgent V1.0"

    @staticmethod
    async def stream(ctx): yield "streaming not implemented"
