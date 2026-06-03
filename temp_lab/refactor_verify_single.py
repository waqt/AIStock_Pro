"""Refactor _verify_single — line-number based replacement"""
filepath = r'E:\workspace\AIResearch\AIStock_Pro\backend\app\domain\research\agents\core_screening_agent.py'

with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"File has {len(lines)} lines")

# ── Replacement 1: lines 365-497 (ROIC block + moat profiling) ──
# Lines are 0-indexed: 364..496

ind = lines[364][:8]  # capture indentation of line 365 (0-indexed 364)

new_section = [
    ind + '# 2. ROIC/ROIIC 查询 (通过 FinancialQueryService, 自动走 SQLite 缓存或实时计算)\n',
    ind + 'from app.domain.quant.engine.financial_query_service import FinancialQueryService\n',
    ind + 'roic_val, roiic_val = None, None\n',
    ind + 'roic_source = "none"\n',
    ind + 'try:\n',
    ind + '    svc = FinancialQueryService()\n',
    ind + '    fin_data = await svc.query(code, indicators=[\n',
    ind + '        "roic_pct", "roiic_pct",\n',
    ind + '        "roic_pct_adjusted", "roiic_pct_adjusted",\n',
    ind + '    ], latest_only=True)\n',
    ind + '    roic_val = fin_data.get("roic_pct_adjusted") or fin_data.get("roic_pct")\n',
    ind + '    roiic_val = fin_data.get("roiic_pct_adjusted") or fin_data.get("roiic_pct")\n',
    ind + '    if roic_val is not None:\n',
    ind + '        roic_source = "fqs"\n',
    ind + 'except Exception as e:\n',
    ind + '    logger.warning(f"[{self.name}] FQS ROIC query failed for {code}: {e}")\n',
    '\n',
    ind + 'candidate["_roic_val"] = roic_val\n',
    ind + 'candidate["_roic_source"] = roic_source\n',
    '\n',
    ind + '# 3. 6维权力画像 (tool based: LLM 自主调用 query_financial_data + web_search)\n',
    ind + 'src_info = candidate.get("source_node_info", {})\n',
    ind + 'prompt = self._build_moat_tool_prompt(\n',
    ind + '    name, code, industry, candidate.get("source", []),\n',
    ind + '    node_context=src_info, roic=roic_val)\n',
    '\n',
    ind + '# 注入动态财务数据字典\n',
    ind + 'from app.domain.quant.engine.financial_query_service import FinancialQueryService\n',
    ind + 'catalog = FinancialQueryService.format_catalog_for_prompt()\n',
    ind + 'prompt = prompt.replace("{{FINANCIAL_CATALOG}}", catalog)\n',
    '\n',
    ind + 'moat_result = {}\n',
    ind + 'moat_status = "pending"\n',
    ind + 'try:\n',
    ind + '    from app.domain.research.agents.base import WEB_SEARCH_TOOL, DEFAULT_TOOL_DEFINITIONS\n',
    ind + '    text = await self.call_with_tools(prompt,\n',
    ind + '        tool_defs=DEFAULT_TOOL_DEFINITIONS + [WEB_SEARCH_TOOL],\n',
    ind + '        max_rounds=8)\n',
    ind + '    if trace: trace.record_llm(prompt, text, model="deepseek-v4-flash")\n',
    ind + '    result = self.parse_json(text)\n',
    ind + '    if isinstance(result, dict) and result.get("moat_profile"):\n',
    ind + '        moat_result = result\n',
    ind + '        moat_status = "assessed"\n',
    ind + '    else:\n',
    ind + '        moat_status = "failed"\n',
    ind + 'except Exception as e:\n',
    ind + '    logger.warning(f"[{self.name}] Moat tool profiling failed for {code}: {e}")\n',
    ind + '    moat_status = "failed"\n',
]

print(f"Replacing lines 365-497 ({len(lines[364:498])} lines) with {len(new_section)} lines")

updated = lines[:364] + new_section + lines[498:]

print(f"After replacement: {len(updated)} lines")

# ── Replacement 2: Add _build_moat_tool_prompt after _build_moat_prompt ──
# Find the line number of the tools section marker
tools_marker = None
for i, line in enumerate(updated):
    if '# ═══ 工具 ═══════════════════════════════════════' in line:
        tools_marker = i
        break

if tools_marker is None:
    print("ERROR: tools section marker not found")
    import sys; sys.exit(1)

print(f"Tools section marker found at line {tools_marker+1}")

# Find the closing triple-quote of _build_moat_prompt (immediately before tools marker)
# Work backwards from tools_marker to find the last triple-quote
triple_quote_line = None
for i in range(tools_marker - 1, max(0, tools_marker - 20), -1):
    if '"""' in updated[i]:
        triple_quote_line = i + 1  # insert after this line
        break

if triple_quote_line is None:
    print("ERROR: closing triple quote not found")
    import sys; sys.exit(1)

print(f"Placing new method after line {triple_quote_line}")

# Build the new method
t = '\t'  # tab character

new_method = [
    '\n',
    t + 'def _build_moat_tool_prompt(self, name, code, industry, sources,\n',
    t + '                             node_context=None, roic=None) -> str:\n',
    t + '\t"""工具版六维权力画像 prompt — LLM 自主调用 query_financial_data + web_search"""\n',
    t + '\tsource_str = ", ".join(\n',
    t + '\t\tf"{s[\'step\']}/{s[\'field\']}" + (f"({s[\'role\']})" if s.get("role") else "")\n',
    t + '\t\tfor s in sources) if sources else ""\n',
    '\n',
    t + '\tnode_block = ""\n',
    t + '\tif node_context:\n',
    t + '\t\tpn = node_context.get("name", "")\n',
    t + '\t\tpp = node_context.get("profit_pool", "?")\n',
    t + '\t\tvm = node_context.get("value_magnitude", "?")\n',
    t + '\t\tsr = node_context.get("supply_rigidity", "?")\n',
    t + '\t\tcsr = node_context.get("china_substitution_rate", "?")\n',
    t + '\t\tcs = node_context.get("competitive_structure", "?")\n',
    t + '\t\tbn = (node_context.get("bottleneck_narrative", "") or "")[:200]\n',
    t + '\t\tnode_block = f"""\n',
    t + '## 该候选所在瓶颈环节背景 (Step 3)\n',
    t + f'- 环节: {{pn}}\n',
    t + f'- 利润池: {{pp}}  | 市场量级: {{vm}}\n',
    t + f'- 供给刚性: {{sr}}\n',
    t + f'- 国产替代率: {{csr}}\n',
    t + f'- 竞争结构: {{cs}}\n',
    t + f'- 瓶颈描述: {{bn}}\n',
    t + '\t"""\n',
    '\n',
    t + '\troic_block = "\\n- ROIC(投入资本回报率): %.1f%%" % roic if roic is not None else ""\n',
    '\n',
    t + '\treturn f"""你是产业竞争分析专家。评估 {name}({code}) 在 {industry} 赛道中的六维产业权力。\n',
    '\n',
    t + '上游来源: {source_str}{node_block}\n',
    '\n',
    t + '## 财务参考{roic_block}\n',
    '\n',
    t + '## 可用工具\n',
    t + '你有以下工具可实时获取数据，请在每个维度判断前主动使用:\n',
    '\n',
    t + '1. **query_financial_data(code, indicators=[...])** — 查询财务指标\n',
    t + '   可用指标范围见 FINANCIAL_CATALOG。\n',
    t + '   使用场景: ROIC趋势、毛利率变化、研发投入、现金流质量、营收增长等\n',
    '\n',
    t + '2. **web_search(query, num=5)** — 搜索网络获取实时信息\n',
    t + '   使用场景: 行业地位、市场份额、客户关系、竞争格局、技术路线、认证壁垒等\n',
    '\n',
    t + '{{FINANCIAL_CATALOG}}\n',
    '\n',
    t + '**重要**: 每个维度必须至少引用一次 tool 返回的真实数据作为证据。\n',
    '\n',
    t + '## 六维权力判断 (每维: strong/medium/weak/emerging)\n',
    '\n',
    t + '{{\n',
    t + '  "moat_profile": {{\n',
    t + '    "position_power": "strong/medium/weak/emerging",\n',
    t + '    "position_evidence": ["证据: 是否产业链必经节点? 客户能否绕过? (建议 web_search 搜寻)"],\n',
    t + '    "pricing_power": "strong/medium/weak/emerging",\n',
    t + '    "pricing_evidence": ["证据: 能否涨价? 毛利率趋势? 占客户成本比例? (建议 query_financial_data 查 margin)"],\n',
    t + '    "expansion_power": "strong/medium/weak/emerging",\n',
    t + '    "expansion_evidence": ["证据: 产能能否扩张? 在建工程? 设备锁定? (建议 web_search 搜索)"],\n',
    t + '    "certification_power": "strong/medium/weak/emerging",\n',
    t + '    "certification_evidence": ["证据: 客户认证周期? 切换成本? 已进入哪些大客户? (建议 web_search 搜索)"],\n',
    t + '    "resource_power": "strong/medium/weak/emerging",\n',
    t + '    "resource_evidence": ["证据: 掌握稀缺资源/产能/人才/配额? (建议 web_search 搜索)"],\n',
    t + '    "cognitive_power": "strong/medium/weak/emerging",\n',
    t + '    "cognitive_evidence": ["证据: 是否比市场更早押对技术路线/提前布局? (建议 web_search 搜索)"]\n',
    t + '  }},\n',
    t + '  "profit_capture_thesis": {{\n',
    t + '    "why_it_captures_profit": ["为什么这家公司能把产业景气变成自己的利润"],\n',
    t + '    "future_profit_driver": ["未来利润增长的核心驱动力"]\n',
    t + '  }},\n',
    t + '  "growth_asymmetry": {{\n',
    t + '    "growth_type": "nonlinear_breakout/inflection_point/linear/cyclical/unknown",\n',
    t + '    "triggers": ["催化剂事件"],\n',
    t + '    "current_stage": "当前所处阶段"\n',
    t + '  }},\n',
    t + '  "thesis_breakers": ["什么条件会推翻以上判断"]\n',
    t + '}}\n',
    '\n',
    t + '## 规则\n',
    t + '- 每维至少1条 evidence, 并且 evidence 必须来自 tool 调用返回的真实数据\n',
    t + '- 如果某个维度搜索结果不足, 标注"搜索证据不足"而非空想\n',
    t + '- 禁止输出股票代码以外的投资建议\n',
    t + '- 先查数据再判断, 不要先判断再勉强找证据支持"""\n',
]

updated2 = updated[:triple_quote_line] + new_method + updated[triple_quote_line:]

print(f"After adding new method: {len(updated2)} lines")

# Write back
with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(updated2)

print("\n✅ All replacements applied successfully!")

# Verify
content = ''.join(updated2)
assert 'FinancialQueryService' in content, 'FQS import missing'
assert '_build_moat_tool_prompt' in content, 'Tool prompt method missing'
assert 'WEB_SEARCH_TOOL' in content, 'WEB_SEARCH_TOOL reference missing'
assert 'DEFAULT_TOOL_DEFINITIONS + [WEB_SEARCH_TOOL]' in content, 'Explicit tool_defs missing'
assert 'ROIC/ROIIC 查询' in content, 'ROIC block not replaced'
assert '6维权力画像 (tool based' in content, 'Moat block not replaced'
print("✅ All assertions passed")
