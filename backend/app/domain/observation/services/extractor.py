"""观察事件提取器 — 从 Pipeline Step 输出提取结构化观察事件"""
import re, json
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from typing import List, Optional, Dict, Any

from app.framework.logger import logger


# ═══ 工具函数 ═══════════════════════════════════

def resolve_relative_time(relative_text: str, anchor_date: str) -> dict:
    """将 LLM 的相对时间描述转为绝对日期

    Args:
        relative_text: "6-12个月", "2026-H2", "2026-Q3", "1-3个月", "immediate"
        anchor_date: 锚点日期, 如 "2026-05-30"

    Returns:
        {"window_description": str, "window_start": str|None, "window_end": str|None}
    """
    if not relative_text:
        return {"window_description": "", "window_start": None, "window_end": None}

    text = relative_text.strip()
    anchor = datetime.strptime(anchor_date[:10], '%Y-%m-%d')

    # 绝对日期: 2026-H2
    m = re.match(r'(\d{4})-H([12])', text)
    if m:
        year = int(m.group(1))
        half = int(m.group(2))
        if half == 1:
            return {"window_description": text, "window_start": f"{year}-01-01", "window_end": f"{year}-06-30"}
        else:
            return {"window_description": text, "window_start": f"{year}-07-01", "window_end": f"{year}-12-31"}

    # 季度: 2026-Q1, 2026-Q2, 2026-Q3, 2026-Q4
    m = re.match(r'(\d{4})-Q([1234])', text)
    if m:
        year = int(m.group(1))
        q = int(m.group(2))
        q_start = {1: f"{year}-01-01", 2: f"{year}-04-01", 3: f"{year}-07-01", 4: f"{year}-10-01"}
        q_end = {1: f"{year}-03-31", 2: f"{year}-06-30", 3: f"{year}-09-30", 4: f"{year}-12-31"}
        return {"window_description": text, "window_start": q_start[q], "window_end": q_end[q]}

    # 半年区间: 6-12个月, 12-24个月
    m = re.match(r'(\d+)\s*[-~]\s*(\d+)\s*个月?', text)
    if m:
        start_months = int(m.group(1))
        end_months = int(m.group(2))
        ws = anchor + relativedelta(months=start_months)
        we = anchor + relativedelta(months=end_months)
        return {"window_description": text, "window_start": ws.strftime('%Y-%m-%d'), "window_end": we.strftime('%Y-%m-%d')}

    # 单个月份: 3个月, 6个月
    m = re.match(r'(\d+)\s*个月?', text)
    if m:
        months = int(m.group(1))
        we = anchor + relativedelta(months=months)
        return {"window_description": text, "window_start": anchor.strftime('%Y-%m-%d'), "window_end": we.strftime('%Y-%m-%d')}

    # 年区间: 3-5年
    m = re.match(r'(\d+)\s*[-~]\s*(\d+)\s*年', text)
    if m:
        start_years = int(m.group(1))
        end_years = int(m.group(2))
        ws = anchor + relativedelta(years=start_years)
        we = anchor + relativedelta(years=end_years)
        return {"window_description": text, "window_start": ws.strftime('%Y-%m-%d'), "window_end": we.strftime('%Y-%m-%d')}

    # 单年: 3年
    m = re.match(r'(\d+)\s*年', text)
    if m:
        years = int(m.group(1))
        we = anchor + relativedelta(years=years)
        return {"window_description": text, "window_start": anchor.strftime('%Y-%m-%d'), "window_end": we.strftime('%Y-%m-%d')}

    # over_24m
    m = re.match(r'over_?24m?', text)
    if m:
        ws = anchor + relativedelta(months=24)
        return {"window_description": text, "window_start": ws.strftime('%Y-%m-%d'), "window_end": None}

    # 12_24m
    m = re.match(r'(\d+)_(\d+)m', text)
    if m:
        ws = anchor + relativedelta(months=int(m.group(1)))
        we = anchor + relativedelta(months=int(m.group(2)))
        return {"window_description": text, "window_start": ws.strftime('%Y-%m-%d'), "window_end": we.strftime('%Y-%m-%d')}

    # immediate
    if text in ('immediate', 'now', '近期'):
        we = anchor + relativedelta(months=1)
        return {"window_description": text, "window_start": anchor.strftime('%Y-%m-%d'), "window_end": we.strftime('%Y-%m-%d')}

    # 未知格式, 原文返回
    return {"window_description": text, "window_start": None, "window_end": None}


def _safe_str(val) -> str:
    if val is None:
        return ""
    if isinstance(val, dict) or isinstance(val, list):
        return json.dumps(val, ensure_ascii=False)
    return str(val)


def _make_source_info(source_type: str, **detail) -> str:
    return json.dumps({"type": source_type, "detail": detail}, ensure_ascii=False)


def _industry_from_output(output: dict) -> str:
    return output.get('industry', output.get('industry_name', ''))


def _get_level_tag(direction: str, source: str) -> str:
    """根据方向和来源推断观察层级"""
    if direction == 'negative':
        return '证伪信号'
    return '待验证'


# ═══ Step 2 提取器 ═══════════════════════════════

def extract_step2_observations(output: dict, run_id: str, run_created_at: str) -> List[dict]:
    """从 Step 2 (MarketScanner) 输出提取观察事件"""
    observations = []
    anchor = run_created_at[:10]
    industry = _industry_from_output(output)

    # 1. kill_reasons → direction=negative, 证伪信号
    for kr in output.get('kill_reasons', []):
        reason = kr.get('reason', '')
        if not reason:
            continue
        resolved = resolve_relative_time('immediate', anchor)
        obs = {
            'source_step': 'step2',
            'level': 'industry',
            'title': f"证伪信号: {reason[:60]}",
            'description': reason,
            'category': '证伪类/条件',
            'direction': 'negative',
            'confidence': 'high',
            'window_description': resolved['window_description'],
            'window_start': resolved['window_start'],
            'window_end': resolved['window_end'],
            'monitor_metric': kr.get('monitor_signal', ''),
            'data_source_hint': kr.get('data_source_hint', ''),
            'search_query': kr.get('monitor_signal', ''),
            'industry': industry,
            'metadata': json.dumps({"source": "kill_reason", "verdict_enter_step3": output.get('verdict', {}).get('enter_step3')}, ensure_ascii=False),
            'source_info': _make_source_info('pipeline', run_id=run_id, step='step2', field='kill_reasons'),
            'status': 'active',
            'notes': f"来自 Step 2 证伪条件 — {industry}",
        }
        observations.append(obs)

    # 2. catalysts → direction=positive, 待验证催化
    for cat in output.get('catalysts', []):
        catalyst_text = cat.get('catalyst', '')
        if not catalyst_text:
            continue
        expected = cat.get('expected_date', '')
        watch_signal = cat.get('watch_signal', '')
        resolved = resolve_relative_time(expected, anchor) if expected else resolve_relative_time('immediate', anchor)
        obs = {
            'source_step': 'step2',
            'level': 'industry',
            'title': f"催化: {catalyst_text[:60]}",
            'description': f"{catalyst_text}\n\n观察信号: {watch_signal}" if watch_signal else catalyst_text,
            'category': '基本面类/生命周期',
            'direction': 'positive',
            'confidence': 'medium',
            'expected_date': expected,
            'window_description': resolved['window_description'],
            'window_start': resolved['window_start'],
            'window_end': resolved['window_end'],
            'monitor_metric': watch_signal,
            'search_query': watch_signal or catalyst_text[:40],
            'industry': industry,
            'metadata': json.dumps({"source": "catalyst", "type": cat.get('type', '')}, ensure_ascii=False),
            'source_info': _make_source_info('pipeline', run_id=run_id, step='step2', field='catalysts'),
            'status': 'active',
        }
        observations.append(obs)

    # 3. key_uncertainties → confidence=low, 待验证
    for uk in output.get('verdict', {}).get('key_uncertainties', []):
        if not uk:
            continue
        resolved = resolve_relative_time('3-6个月', anchor)
        obs = {
            'source_step': 'step2',
            'level': 'industry',
            'title': f"不确定性: {uk[:60]}",
            'description': uk,
            'category': '认知类/认知差',
            'direction': 'neutral',
            'confidence': 'low',
            'window_description': resolved['window_description'],
            'window_start': resolved['window_start'],
            'window_end': resolved['window_end'],
            'industry': industry,
            'metadata': json.dumps({"source": "key_uncertainty"}, ensure_ascii=False),
            'source_info': _make_source_info('pipeline', run_id=run_id, step='step2', field='key_uncertainties'),
            'status': 'active',
        }
        observations.append(obs)

    # 4. time_horizon → 时间框架观察
    th = output.get('time_horizon', {})
    if th.get('alpha_window'):
        resolved = resolve_relative_time(th['alpha_window'], anchor)
        obs = {
            'source_step': 'step2',
            'level': 'industry',
            'title': f"Alpha窗口: {th['alpha_window']}",
            'description': f"Alpha窗口: {th.get('alpha_window', '')}\n利润扩张窗口: {th.get('profit_expansion_window', '')}\n产能缓解ETA: {th.get('capacity_relief_eta', '')}\n市场重定价阶段: {th.get('market_repricing_stage', '')}",
            'category': '时间类/时间错配',
            'direction': 'neutral',
            'confidence': 'medium',
            'expected_date': th.get('capacity_relief_eta', ''),
            'window_description': th.get('alpha_window', ''),
            'window_start': resolved['window_start'],
            'window_end': resolved['window_end'],
            'industry': industry,
            'metadata': json.dumps({"source": "time_horizon", "profit_expansion_window": th.get('profit_expansion_window'), "capacity_relief_eta": th.get('capacity_relief_eta')}, ensure_ascii=False),
            'source_info': _make_source_info('pipeline', run_id=run_id, step='step2', field='time_horizon'),
            'status': 'active',
        }
        observations.append(obs)

    # 5. cycle_position → 周期阶段观察
    cp = output.get('cycle_position', {})
    if cp.get('phase_switch_trigger'):
        resolved = resolve_relative_time(cp.get('estimated_duration', '12-18个月'), anchor)
        next_phase = cp.get('next_phase', '')
        obs = {
            'source_step': 'step2',
            'level': 'industry',
            'title': f"周期切换: {cp.get('phase','')}→{next_phase}" if next_phase else f"周期阶段: {cp.get('phase','')}",
            'description': f"当前阶段: {cp.get('phase','')}({cp.get('sub_phase','')})\n下一阶段: {next_phase}\n持续时间: {cp.get('estimated_duration','')}\n切换信号: {cp.get('phase_switch_trigger','')}",
            'category': '时间类/节奏变化',
            'direction': 'neutral',
            'confidence': 'medium',
            'window_description': cp.get('estimated_duration', ''),
            'window_start': resolved['window_start'],
            'window_end': resolved['window_end'],
            'monitor_metric': cp.get('phase_switch_trigger', ''),
            'search_query': cp.get('phase_switch_trigger', '')[:80],
            'industry': industry,
            'metadata': json.dumps({"source": "cycle_position", "phase": cp.get('phase'), "sub_phase": cp.get('sub_phase'), "next_phase": next_phase}, ensure_ascii=False),
            'source_info': _make_source_info('pipeline', run_id=run_id, step='step2', field='cycle_position'),
            'status': 'active',
        }
        observations.append(obs)

    # 6. mismatch_analysis → 错配信号提取 (每个错配类型转为观察)
    mm = output.get('mismatch_analysis', {})
    mismatch_labels = {
        'supply_demand_mismatch': ('供需类/供需错配', '供需错配'),
        'timing_mismatch': ('时间类/时间错配', '时间错配'),
        'expectation_gap': ('认知类/认知差', '认知差'),
        'profit_redistribution': ('利润类/利润迁移', '利润迁移'),
        'pricing_gap': ('估值类/定价缺口', '定价缺口'),
    }
    for key, (cat, label) in mismatch_labels.items():
        val = mm.get(key)
        if val and val not in ('uncertain', 'none'):
            strength_map = {'strong': '强', 'moderate': '中', 'weak': '弱'}
            strength = strength_map.get(val, val)
            obs = {
                'source_step': 'step2',
                'level': 'industry',
                'title': f"{label}: {strength}",
                'description': f"{label}强度: {strength}",
                'category': cat,
                'direction': 'neutral',
                'confidence': 'high' if val == 'strong' else 'medium',
                'industry': industry,
                'metadata': json.dumps({"source": "mismatch_analysis", "mismatch_type": key, "strength": val}, ensure_ascii=False),
                'source_info': _make_source_info('pipeline', run_id=run_id, step='step2', field='mismatch_analysis'),
                'status': 'active',
            }
            observations.append(obs)

    logger.info(f"[Extractor] Step 2: {len(observations)} observations extracted (industry={industry})")
    return observations


# ═══ Step 3 提取器 ═══════════════════════════════

def extract_step3_observations(output: dict, run_id: str, run_created_at: str) -> List[dict]:
    """从 Step 3 (SupplyChainHacker) 输出提取观察事件"""
    observations = []
    anchor = run_created_at[:10]
    industry = _industry_from_output(output)

    # 1. 产业链各节点的 value_node_tags → 个股/节点级观察
    for node in output.get('supply_chain_map', []):
        node_name = node.get('name', '')
        for tag in node.get('value_node_tags', []):
            if not tag:
                continue
            resolved = resolve_relative_time('12-24个月', anchor)
            obs = {
                'source_step': 'step3',
                'level': 'supply_chain_node',
                'title': f"价值节点: {tag}",
                'description': f"所属环节: {node_name}\n瓶颈评分: {node.get('chokepoint_checklist', {}).get('chokepoint_score', 'N/A')}\n供给刚性: {node.get('supply_rigidity', {}).get('severity', '')}\n利润率: {node.get('profit_pool', {}).get('margin_level', '')}\n\n{node.get('a_stock_transmission', '')}",
                'category': '利润类/利润迁移',
                'direction': 'positive',
                'confidence': 'medium',
                'window_description': resolved['window_description'],
                'window_start': resolved['window_start'],
                'window_end': resolved['window_end'],
                'industry': industry,
                'metadata': json.dumps({
                    "source": "value_node_tag", "node_name": node_name,
                    "chokepoint_score": node.get('chokepoint_checklist', {}).get('chokepoint_score'),
                    "severity": node.get('supply_rigidity', {}).get('severity'),
                    "market_attention": node.get('value_capture', {}).get('market_attention'),
                }, ensure_ascii=False),
                'source_info': _make_source_info('pipeline', run_id=run_id, step='step3', field='supply_chain_map.value_node_tags'),
                'status': 'active',
            }
            observations.append(obs)

    # 2. catalysts → 产业事件
    for cat in output.get('catalysts', []):
        catalyst_text = cat.get('catalyst', '')
        if not catalyst_text:
            continue
        expected = cat.get('expected_date', '')
        resolved = resolve_relative_time(expected, anchor) if expected else resolve_relative_time('immediate', anchor)
        obs = {
            'source_step': 'step3',
            'level': 'industry',
            'title': f"产业链催化: {catalyst_text[:60]}",
            'description': f"{catalyst_text}\n影响环节: {cat.get('affected_segment', '')}\n观察信号: {cat.get('watch_signal', '')}",
            'category': '基本面类/生命周期',
            'direction': 'positive',
            'confidence': 'medium',
            'expected_date': expected,
            'window_description': resolved['window_description'],
            'window_start': resolved['window_start'],
            'window_end': resolved['window_end'],
            'monitor_metric': cat.get('watch_signal', ''),
            'search_query': cat.get('watch_signal', '') or catalyst_text[:40],
            'industry': industry,
            'metadata': json.dumps({"source": "catalyst", "type": cat.get('type', ''), "affected_segment": cat.get('affected_segment', '')}, ensure_ascii=False),
            'source_info': _make_source_info('pipeline', run_id=run_id, step='step3', field='catalysts'),
            'status': 'active',
        }
        observations.append(obs)

    # 3. scarcity_ranking → 瓶颈排名观察
    for idx, sr in enumerate(output.get('scarcity_ranking', [])):
        segment = sr.get('segment', '')
        if not segment:
            continue
        resolved = resolve_relative_time('12-24个月', anchor)
        obs = {
            'source_step': 'step3',
            'level': 'supply_chain_node',
            'title': f"瓶颈#{sr.get('rank', idx+1)}: {segment}",
            'description': sr.get('rigidity_narrative', ''),
            'category': '产能类/瓶颈转移',
            'direction': 'negative',
            'confidence': 'high',
            'window_description': resolved['window_description'],
            'window_start': resolved['window_start'],
            'window_end': resolved['window_end'],
            'industry': industry,
            'metadata': json.dumps({"source": "scarcity_ranking", "rank": sr.get('rank', idx+1), "segment": segment}, ensure_ascii=False),
            'source_info': _make_source_info('pipeline', run_id=run_id, step='step3', field='scarcity_ranking'),
            'status': 'active',
        }
        observations.append(obs)

    # 4. chain_timeline → 时间线观察 (景气传导节奏)
    ct = output.get('chain_timeline', {})
    if ct.get('rotation_strategy'):
        resolved_sales = resolve_relative_time(ct.get('sales_lead_months', '1-3') + '个月', anchor)
        resolved_exp = resolve_relative_time(ct.get('expansion_lag_months', '6-12') + '个月', anchor)
        obs = {
            'source_step': 'step3',
            'level': 'industry',
            'title': f"景气传导节奏: 模组先导{ct.get('sales_lead_months','')}月, 设备滞后{ct.get('expansion_lag_months','')}月",
            'description': ct.get('rotation_strategy', ''),
            'category': '时间类/节奏变化',
            'direction': 'neutral',
            'confidence': 'medium',
            'window_description': ct.get('sales_lead_months', ''),
            'window_start': resolved_sales['window_start'],
            'window_end': resolved_exp['window_end'],
            'industry': industry,
            'metadata': json.dumps({"source": "chain_timeline", "sales_lead": ct.get('sales_lead_months'), "expansion_lag": ct.get('expansion_lag_months')}, ensure_ascii=False),
            'source_info': _make_source_info('pipeline', run_id=run_id, step='step3', field='chain_timeline'),
            'status': 'active',
        }
        observations.append(obs)

    logger.info(f"[Extractor] Step 3: {len(observations)} observations extracted")
    return observations


# ═══ Step 4 提取器 (骨架) ═════════════════════════

def extract_step4_observations(output: dict, run_id: str, run_created_at: str) -> List[dict]:
    """从 Step 4 (SystemDynamics) 输出提取观察事件"""
    observations = []
    anchor = run_created_at[:10]
    industry = _industry_from_output(output)

    # thesis_breakers
    for tb in output.get('thesis_breakers', []):
        thesis = tb.get('thesis', '')
        if not thesis:
            continue
        obs = {
            'source_step': 'step4',
            'level': 'industry',
            'title': f"证伪: {thesis[:60]}",
            'description': f"结论: {thesis}\n触发条件: {tb.get('break_condition', '')}\n观察信号: {tb.get('watch_signal', '')}",
            'category': '证伪类/预警',
            'direction': 'negative',
            'confidence': 'medium',
            'window_description': tb.get('time_window', ''),
            'monitor_metric': tb.get('watch_signal', ''),
            'industry': industry,
            'metadata': json.dumps({"source": "thesis_breaker"}, ensure_ascii=False),
            'source_info': _make_source_info('pipeline', run_id=run_id, step='step4', field='thesis_breakers'),
            'status': 'active',
        }
        observations.append(obs)

    # bottleneck_migration
    for bm in output.get('bottleneck_migration', []):
        name = bm.get('name', bm.get('bottleneck', ''))
        if not name:
            continue
        resolved = resolve_relative_time(bm.get('expected_timing', '3-6个月'), anchor)
        obs = {
            'source_step': 'step4',
            'level': 'supply_chain_node',
            'title': f"瓶颈迁移: {name}",
            'description': f"瓶颈: {name}\n监控指标: {bm.get('monitoring_metric', '')}\n触发阈值: {bm.get('trigger_threshold', '')}\n预期时间: {bm.get('expected_timing', '')}",
            'category': '产能类/瓶颈转移',
            'direction': 'neutral',
            'confidence': 'medium',
            'window_description': bm.get('expected_timing', ''),
            'window_start': resolved['window_start'],
            'window_end': resolved['window_end'],
            'monitor_metric': bm.get('monitoring_metric', ''),
            'trigger_threshold': bm.get('trigger_threshold', ''),
            'industry': industry,
            'metadata': json.dumps({"source": "bottleneck_migration"}, ensure_ascii=False),
            'source_info': _make_source_info('pipeline', run_id=run_id, step='step4', field='bottleneck_migration'),
            'status': 'active',
        }
        observations.append(obs)

    # resource_crowding
    for rc in output.get('resource_crowding', []):
        resource = rc.get('resource', rc.get('name', ''))
        if not resource:
            continue
        obs = {
            'source_step': 'step4',
            'level': 'industry',
            'title': f"资源挤占: {resource}",
            'description': f"资源: {resource}\n可见度: {rc.get('visibility', '')}\n影响时间: {rc.get('time_to_impact', '')}",
            'category': '供需类/资源挤占',
            'direction': 'negative',
            'confidence': 'medium',
            'window_description': rc.get('time_to_impact', ''),
            'industry': industry,
            'metadata': json.dumps({"source": "resource_crowding", "visibility": rc.get('visibility'), "time_to_impact": rc.get('time_to_impact')}, ensure_ascii=False),
            'source_info': _make_source_info('pipeline', run_id=run_id, step='step4', field='resource_crowding'),
            'status': 'active',
        }
        observations.append(obs)

    logger.info(f"[Extractor] Step 4: {len(observations)} observations extracted")
    return observations


# ═══ Step 5 提取器 (骨架) ═════════════════════════

def extract_step5_observations(output: dict, run_id: str, run_created_at: str) -> List[dict]:
    """从 Step 5 (CrossIndustryLinkage) 输出提取观察事件"""
    observations = []
    anchor = run_created_at[:10]
    industry = _industry_from_output(output)

    for linkage in output.get('cross_industry_linkages', []):
        target = linkage.get('target_industry', linkage.get('industry', ''))
        if not target:
            continue
        impact_dir = linkage.get('impact_direction', 'neutral')
        resolved = resolve_relative_time(linkage.get('time_to_impact', '3-6个月'), anchor)
        obs = {
            'source_step': 'step5',
            'level': 'cross_industry',
            'title': f"跨产业: {target}",
            'description': f"目标行业: {target}\n影响方向: {impact_dir}\n传导机制: {linkage.get('linkage_method', '')}\n可见度: {linkage.get('visibility', '')}\n重要性: {linkage.get('materiality', '')}",
            'category': '供需类/跨产业波及',
            'direction': impact_dir if impact_dir in ('positive', 'negative') else 'neutral',
            'confidence': 'medium',
            'window_description': linkage.get('time_to_impact', ''),
            'window_start': resolved['window_start'],
            'window_end': resolved['window_end'],
            'industry': industry,
            'related_stock_code': linkage.get('related_stock_code') or linkage.get('stock_code'),
            'metadata': json.dumps({"source": "cross_industry_linkage", "target_industry": target, "impact_direction": impact_dir, "linkage_method": linkage.get('linkage_method')}, ensure_ascii=False),
            'source_info': _make_source_info('pipeline', run_id=run_id, step='step5', field='cross_industry_linkages'),
            'status': 'active',
        }
        observations.append(obs)

    logger.info(f"[Extractor] Step 5: {len(observations)} observations extracted")
    return observations


# ═══ Step 6 提取器 (骨架) ═════════════════════════

def extract_step6_observations(output: dict, run_id: str, run_created_at: str) -> List[dict]:
    """从 Step 6 (CoreScreening) 输出提取个股级观察事件"""
    observations = []
    anchor = run_created_at[:10]
    industry = _industry_from_output(output)

    # 每只股票的 thesis_breakers
    for stock in output.get('ranked_stocks', []):
        code = stock.get('code', '')
        name = stock.get('name', '')
        score = stock.get('total_score', stock.get('score', ''))
        for tb in stock.get('thesis_breakers', []):
            thesis = tb.get('thesis', tb) if isinstance(tb, dict) else str(tb)
            if not thesis or thesis == '无':
                continue
            obs = {
                'source_step': 'step6',
                'level': 'stock',
                'title': f"{name}({code}): {str(thesis)[:60]}",
                'description': f"股票: {name}({code})\n总分: {score}\n证伪条件: {thesis}",
                'category': '证伪类/条件',
                'direction': 'negative',
                'confidence': 'medium',
                'industry': industry,
                'related_stock_code': code,
                'metadata': json.dumps({"source": "thesis_breaker", "stock_name": name, "total_score": score}, ensure_ascii=False),
                'source_info': _make_source_info('pipeline', run_id=run_id, step='step6', field='thesis_breakers'),
                'status': 'active',
            }
            observations.append(obs)

        # company_stage
        stage = stock.get('company_stage', '')
        if stage:
            obs = {
                'source_step': 'step6',
                'level': 'stock',
                'title': f"{name}({code}): 阶段={stage}",
                'description': f"股票: {name}({code})\n公司阶段: {stage}\n指标: {stock.get('stage_indicators', '')}\n审计结论: {stock.get('audit', {}).get('verdict', '')}",
                'category': '基本面类/生命周期',
                'direction': 'neutral',
                'confidence': 'medium',
                'industry': industry,
                'related_stock_code': code,
                'metadata': json.dumps({"source": "company_stage", "stock_name": name, "stage": stage}, ensure_ascii=False),
                'source_info': _make_source_info('pipeline', run_id=run_id, step='step6', field='company_stage'),
                'status': 'active',
            }
            observations.append(obs)

    logger.info(f"[Extractor] Step 6: {len(observations)} observations extracted")
    return observations


# ═══ Path A / Path B 提取器 ═══════════════════════════

def extract_step2a_observations(output: dict, run_id: str, run_created_at: str) -> List[dict]:
    """从 Path A (Direct Asset Mining) 输出提取个股级观察事件"""
    observations = []
    industry = _industry_from_output(output)

    for stock in output.get('ranked_stocks', []):
        code = stock.get('code', '')
        name = stock.get('name', '')
        for tb in stock.get('thesis_breakers', []):
            thesis = tb.get('thesis', tb) if isinstance(tb, dict) else str(tb)
            if not thesis or thesis == '无':
                continue
            observations.append({
                'source_step': 'step2a_direct_asset',
                'level': 'stock',
                'title': f"直挖: {name}({code}): {str(thesis)[:60]}",
                'description': f"股票: {name}({code})\n证伪条件: {thesis}",
                'category': '证伪类/条件',
                'direction': 'negative',
                'confidence': 'medium',
                'industry': industry,
                'related_stock_code': code,
                'source_info': _make_source_info('pipeline', run_id=run_id, step='step2a_direct_asset',
                                                  field='thesis_breakers'),
                'status': 'active',
            })

        # company_stage
        stage = stock.get('company_stage', '')
        if stage:
            observations.append({
                'source_step': 'step2a_direct_asset',
                'level': 'stock',
                'title': f"直挖: {name}({code}): 阶段={stage}",
                'description': f"股票: {name}({code})\n公司阶段: {stage}",
                'category': '基本面类/生命周期',
                'direction': 'neutral',
                'confidence': 'medium',
                'industry': industry,
                'related_stock_code': code,
                'source_info': _make_source_info('pipeline', run_id=run_id, step='step2a_direct_asset',
                                                  field='company_stage'),
                'status': 'active',
            })

    logger.info(f"[Extractor] Step 2a: {len(observations)} observations extracted")
    return observations


def extract_step2b_observations(output: dict, run_id: str, run_created_at: str) -> List[dict]:
    """从 Path B (Second-Order Extrapolation) 输出提取跨产业预期差观察"""
    observations = []
    anchor = run_created_at[:10]
    industry = _industry_from_output(output)

    for adj in output.get('adjacent_industries', []):
        name = adj.get('name', '未命名产业')
        resolved = resolve_relative_time(adj.get('time_to_impact', '3-6个月'), anchor)

        observations.append({
            'source_step': 'step2b_second_order',
            'level': 'cross_industry',
            'title': f"二阶推演: {name}",
            'description': adj.get('expectation_gap_analysis', ''),
            'category': '认知类/预期差',
            'direction': 'positive',
            'confidence': 'high' if adj.get('expectation_gap') == 'strong' else 'medium',
            'industry': industry,
            'window_start': resolved['window_start'],
            'window_end': resolved['window_end'],
            'window_description': adj.get('time_to_impact', ''),
            'source_info': _make_source_info('pipeline', run_id=run_id, step='step2b_second_order',
                                              field='adjacent_industries'),
            'status': 'active',
        })

    logger.info(f"[Extractor] Step 2b: {len(observations)} observations extracted")
    return observations


# ═══ 路由  ═══════════════════════════════════════

STEP_EXTRACTORS = {
    "step2": extract_step2_observations,
    "step3": extract_step3_observations,
    "step4": extract_step4_observations,
    "step5": extract_step5_observations,
    "step6": extract_step6_observations,
    # 兼容 key (checkpoint 可能用完整 step name)
    "step2_gatekeeper": extract_step2_observations,
    "step3_sc_hacker": extract_step3_observations,
    "step4_system_dynamics": extract_step4_observations,
    "step5_cross_industry": extract_step5_observations,
    "step6_core_screening": extract_step6_observations,
    # Path A / Path B
    "step2a_direct_asset": extract_step2a_observations,
    "step2b_second_order": extract_step2b_observations,
}


async def save_step_observations(run_id: str, step: str, output: dict, run_created_at: str):
    """Pipeline 集成点: 提取观察并存入 SQLite, 在 save_checkpoint 后调用"""
    extractor = STEP_EXTRACTORS.get(step)
    if not extractor:
        logger.debug(f"[Extractor] No extractor for step={step}, skipping")
        return
    try:
        observations = extractor(output, run_id, run_created_at)
        if observations:
            from app.framework.pipeline.observation_store import ObservationStore
            store = ObservationStore()
            ids = store.save_batch(observations)
            logger.info(f"[Extractor] Saved {len(ids)} observations for {run_id}/{step}")
        else:
            logger.debug(f"[Extractor] No observations extracted for {run_id}/{step}")
    except Exception as e:
        logger.warning(f"[Extractor] Failed for {run_id}/{step}: {e}")
