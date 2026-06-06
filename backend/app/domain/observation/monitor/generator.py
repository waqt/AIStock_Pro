"""LLM 辅助生成监控计划 — 从研报 + 观察事件生成 MonitorPlan 建议"""
import json
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.framework.logger import logger
from app.framework.ai.providers.deepseek import DeepSeekProvider


GENERATE_PLANS_PROMPT = """你是一位专业的投资研究监控策略师。你的任务是分析一份研究报告中涉及待观察的关键变量，然后生成一份结构化的监控计划列表。

这些监控计划将在后续被用于自动化执行搜索，通过这些搜索内容来帮助你判断一个投资观点是否得到验证或被证伪。

## 输入数据

### 研究报告摘要
{report_summary}

### 研究流程关键发现
{pipeline_context}

### 已提取的可观察事件
{observations}

## 输出规则

根据上面提供的研究报告、关键发现和可观察事件，我需要你帮助我生成一份监控计划建议列表，用于后续搜索和验证。

1. 首先通读报告，理解核心投资逻辑和预期差所在。明确报告的核心推荐逻辑和反向条件。
2. 判断哪些信息是**可以通过搜索验证 / 证伪**的客观信号。比如，一个公司的阶段可以观察，但不容易通过搜索验证，那就不适合作为监控计划。而一个催化事件的时间窗口是否通过客户认证，这个是可以搜索到的，就适合。
3. 把同类型的多个观察合并为一个监控计划（比如同一个股票的多个观察，或者同一个产业的不同企业，尽量合并）。
4. 为每个监控计划设计合理的搜索策略和触发判断逻辑。

### 搜索策略设计指南
- 每条 query 应该具体、可执行，能直接粘到搜索引擎里用的
- 不同的 query 可以有不同的检查频率：关键事件每周查，背景信息可以双周查
- 搜索来源目前支持: brave (Web搜索), financial (财务指标查询)

### 触发判断逻辑设计指南
- 写清楚什么算"命中"、什么算"未命中"
- 区分信号强度：关键公告 vs 传闻 vs 间接证据
- 考虑真伪辨别：如何判断新闻是正式公告还是市场传闻

### 信号方向设计
- buy: 这个事件/趋势如果发生，应该买入/加仓
- sell: 这个事件/趋势如果发生，应该卖出/减仓
- neutral: 这个事件/趋势如果发生，需要重新评估现有观点

### 行业级计划注意
如果是行业级监控（如瓶颈迁移、供需变化），需要在 cascade_to_stocks 中列出受影响的个股代码和逻辑。

## 输出格式

返回 JSON 对象，包含 context_summary 和 proposed_plans 数组。

```json
{{
  "context_summary": "对研报核心逻辑的一次性概括, 用于后续关联引用",
  "proposed_plans": [
    {{
      "name": "计划名称, 简短明确",
      "description": "计划描述, 说明监控什么、为什么重要",
      "source_focus": "哪个步骤/哪个观察触发的",
      "level": "stock 或 industry",
      "target_stock_code": "个股代码 (level=stock时)",
      "target_stock_name": "个股名称 (level=stock时)",
      "target_industry": "行业名称 (level=industry时)",
      "cascade_to_stocks": ["如果行业级, 受影响个股代码列表, 如 ['688012','002371']"],
      "search_config": [
        {{
          "engine": "brave",
          "query": "具体搜索关键词",
          "interval_days": 7,
          "lang": "zh"
        }}
      ],
      "trigger_instruction": "清晰描述如何判断搜索命中, 区分信号强度",
      "positive_keywords": ["命中关键词"],
      "negative_keywords": ["反证关键词"],
      "min_match_count": 1,
      "signal_direction": "buy/sell/neutral",
      "signal_strength": "strong/medium/weak",
      "check_interval_hours": 168,
      "reasoning": "为什么设计这个监控计划"
    }}
  ]
}}
```

只返回 JSON, 不要其他说明。"""


async def generate_monitor_plans(
    report_data: dict,
    observations: List[dict],
    report_id: str = "",
    run_id: str = "",
) -> List[dict]:
    """LLM 辅助生成监控计划

    Args:
        report_data: 研报完整 data 字段
        observations: 已提取的观察事件列表 (来自该研报)
        report_id: 报告 ID
        run_id: Pipeline run_id

    Returns:
        建议的监控计划列表 (dict 格式, 可直接存入 monitor_plans 表)
    """
    provider = DeepSeekProvider()

    # 构建输入摘要
    report_summary = _build_report_summary(report_data)
    pipeline_context = _build_pipeline_context(report_data)
    obs_text = _format_observations(observations)

    prompt = GENERATE_PLANS_PROMPT.format(
        report_summary=report_summary,
        pipeline_context=pipeline_context,
        observations=obs_text,
    )

    logger.info(f"[MonitorGenerator] Generating plans from report={report_id}, observations={len(observations)}")

    try:
        response = await provider.chat_pro(prompt)
        plans = _parse_llm_response(response, report_id, run_id)
        logger.info(f"[MonitorGenerator] Generated {len(plans)} plan proposals")
        return plans
    except Exception as e:
        logger.error(f"[MonitorGenerator] Failed: {e}")
        return []


def _build_report_summary(report_data: dict) -> str:
    """从研报 JSON 中提取关键摘要信息"""
    parts = []

    # 顶层信息
    for key in ('final_summary', 'summary', 'industry', 'title', 'final_synthesis'):
        val = report_data.get(key)
        if val and isinstance(val, str) and len(val) > 10:
            parts.append(f"[{key}]\n{val[:2000]}")
            break

    # Step 6 核心输出
    ranked = report_data.get('ranked_stocks', report_data.get('future_strong_candidates', []))
    if ranked:
        names = [f"{s.get('name','?')}({s.get('code','?')})" for s in ranked[:10]]
        parts.append(f"[关键股票]\n" + ", ".join(names))

    # 核心结论
    for field in ('profit_capture_thesis', 'recommendation', 'verdict'):
        val = report_data.get(field)
        if val and isinstance(val, str):
            parts.append(f"[{field}]\n{val[:500]}")

    return "\n\n".join(parts) if parts else "(无摘要信息)"


def _build_pipeline_context(report_data: dict) -> str:
    """提取 Pipeline 关键背景"""
    parts = []

    # Step 2 信息
    cp = report_data.get('cycle_position', {})
    if cp:
        parts.append(f"周期阶段: {cp.get('phase','?')} ({cp.get('sub_phase','?')})")

    mm = report_data.get('mismatch_analysis', {})
    if mm:
        active = {k: v for k, v in mm.items() if v and v not in ('uncertain', 'none')}
        if active:
            parts.append(f"错配分析: {json.dumps(active, ensure_ascii=False)}")

    # Step 3 信息: 瓶颈节点
    scm = report_data.get('supply_chain_map', [])
    if scm:
        bottlenecks = []
        for node in scm[:5]:
            cl = node.get('chokepoint_checklist', {})
            sev = cl.get('bottleneck_severity', '?')
            if sev and sev != 'none':
                bottlenecks.append(f"{node.get('name','?')}({sev})")
        if bottlenecks:
            parts.append(f"瓶颈节点: {', '.join(bottlenecks)}")

    # 时间框架
    th = report_data.get('time_horizon', {})
    if th:
        parts.append(f"Alpha窗口: {th.get('alpha_window','?')}")

    return "\n".join(parts) if parts else "(无背景信息)"


def _format_observations(observations: List[dict]) -> str:
    """将观察事件格式化为 LLM 可读文本"""
    if not observations:
        return "(无观察事件)"

    lines = []
    for i, obs in enumerate(observations, 1):
        title = obs.get('title', '')
        desc = obs.get('description', '')
        cat = obs.get('category', '')
        direction = obs.get('direction', '')
        confidence = obs.get('confidence', '')
        search_q = obs.get('search_query', '')
        lines.append(
            f"{i}. [{direction}] [{cat}] (conf={confidence})\n"
            f"   标题: {title}\n"
            f"   描述: {desc[:200]}\n"
            f"   搜索: {search_q}"
        )
    return "\n\n".join(lines)


def _parse_llm_response(response: str, report_id: str, run_id: str) -> List[dict]:
    """解析 LLM 返回的 JSON, 注入 report_id/run_id 等溯源信息"""
    # 尝试提取 JSON 块
    text = response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
    text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 尝试找第一个 {
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                logger.warning(f"[MonitorGenerator] Failed to parse LLM response as JSON")
                return []
        else:
            return []

    plans = data.get("proposed_plans", data.get("plans", []))
    context_summary = data.get("context_summary", "")

    result = []
    for p in plans:
        # 注入溯源
        p['source_report_id'] = report_id
        p['source_run_id'] = run_id
        p['source_summary'] = p.get('reasoning', context_summary)
        if not p.get('source_step'):
            p['source_step'] = 'step6'  # 默认, 可覆盖

        # 确保 JSON 字段是字符串
        for jf in ('search_config', 'positive_keywords', 'negative_keywords', 'cascade_to_stocks'):
            val = p.get(jf)
            if isinstance(val, (list, dict)):
                p[jf] = json.dumps(val, ensure_ascii=False)
            elif not val:
                p[jf] = '[]'

        # 状态默认为 draft, 等用户审核后改为 active
        p['status'] = 'draft'
        result.append(p)

    return result
