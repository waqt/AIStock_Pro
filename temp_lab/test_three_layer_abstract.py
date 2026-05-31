"""
三层抽象模型 LLM 推理测试
=========================
验证 LLM 是否能正确将产业链瓶颈节点分解为子工艺，
并给出准确的 value_magnitude / value_owners / pricing_behavior。

测试数据: 存储产业 Step 3 L1 "HBM先进封装 (CoWoS/TSV)" 瓶颈节点
对比基准: HBM→GPU 已知 13 步工艺链 (来自我们之前的调研)

规则:
- 纯 LLM 推理, 不调 Web Search
- 使用 chat_pro (deepseek-v4-pro + thinking) 模拟分析和推理
- 使用 chat_flash (deepseek-v4-flash) 快速结构化 (两次调用模式)
"""

import sys, os, json
sys.path.insert(0, r'E:\workspace\AIResearch\AIStock_Pro\backend')

from app.framework.ai.providers.deepseek import DeepSeekProvider

# HBM→GPU 已知工艺链 (事实基准)
KNOWN_PROCESSES = [
    {"step": 1, "process": "DRAM Wafer Fabrication", "players": ["SK Hynix", "Samsung", "Micron"],
     "a_stock": [], "value_magnitude": "100B+", "pricing": "collusive_oligopoly"},
    {"step": 2, "process": "TSV (Through Silicon Via)", "players": ["SK Hynix", "Samsung", "Micron"],
     "a_stock": ["中微公司(688012)", "北方华创(002371)"], "value_magnitude": "10B_100B", "pricing": "collusive_oligopoly"},
    {"step": 3, "process": "Micro Bump Formation", "players": ["SK Hynix", "Samsung", "Micron"],
     "a_stock": [], "value_magnitude": "1B_10B", "pricing": "collusive_oligopoly"},
    {"step": 4, "process": "Stack Bonding (TCB/Hybrid Bonding)", "players": ["SK Hynix", "Samsung"],
     "a_stock": [], "value_magnitude": "1B_10B", "pricing": "collusive_oligopoly"},
    {"step": 5, "process": "Molding & Underfill", "players": ["Nagase", "Henkel", "Namics"],
     "a_stock": ["华海诚科(688535)", "飞凯材料(300398)"], "value_magnitude": "1B_10B", "pricing": "capacity_war"},
    {"step": 6, "process": "Dicing & Singulation", "players": ["Disco", "Tokyo Seimitsu"],
     "a_stock": ["光力科技(300480)"], "value_magnitude": "<1B", "pricing": "monopoly"},
    {"step": 7, "process": "HBM Test & KGD", "players": ["Advantest", "Teradyne"],
     "a_stock": ["长川科技(300604)", "华峰测控(688200)"], "value_magnitude": "1B_10B", "pricing": "monopoly"},
    {"step": 8, "process": "CoW (Chip-on-Wafer)", "players": ["TSMC"],
     "a_stock": [], "value_magnitude": "10B_100B", "pricing": "monopoly"},
    {"step": 9, "process": "oS (on-Substrate) / Assembly", "players": ["ASE", "Amkor"],
     "a_stock": ["长电科技(600584)", "通富微电(002156)"], "value_magnitude": "1B_10B", "pricing": "capacity_war"},
    {"step": 10, "process": "ABF Substrate", "players": ["Ibiden", "Unimicron", "AT&S"],
     "a_stock": ["兴森科技(002436)", "深南电路(002916)"], "value_magnitude": "10B_100B", "pricing": "collusive_oligopoly"},
    {"step": 11, "process": "TIM & Thermal Solutions", "players": ["Honeywell", "Henkel", "ShinEtsu"],
     "a_stock": ["飞荣达(300507)"], "value_magnitude": "1B_10B", "pricing": "collusive_oligopoly"},
    {"step": 12, "process": "Final Test & SLT", "players": ["Advantest", "Teradyne", "Chroma"],
     "a_stock": ["长川科技(300604)", "华峰测控(688200)"], "value_magnitude": "1B_10B", "pricing": "collusive_oligopoly"},
    {"step": 13, "process": "System Assembly / GPU Card", "players": ["Nvidia", "Wistron", "Foxconn"],
     "a_stock": ["工业富联(601138)", "浪潮信息(000977)"], "value_magnitude": "100B+", "pricing": "capacity_war"},
]


async def test_llm_reasoning():
    provider = DeepSeekProvider()

    # 加载瓶颈节点数据
    with open(r'E:\workspace\AIResearch\AIStock_Pro\temp_lab\pipeline_cache\step3_bottlenecks.json', encoding='utf-8') as f:
        nodes = json.load(f)

    # 只测 L1 HBM先进封装 (CoWoS/TSV)
    l1_node = nodes[0]
    print(f"{'='*80}")
    print(f"测试瓶颈节点: L{l1_node['level']} {l1_node['name']}")
    print(f"  瓶颈描述: {l1_node['bottleneck_narrative']}")
    print(f"  chokepoint_score: {l1_node['chokepoint_checklist']['chokepoint_score']}")
    print(f"  supply_rigidity: {l1_node['supply_rigidity']['severity']}")
    print(f"{'='*80}\n")

    # === 第一轮: LLM 分析 (chat_pro, 带 thinking) ===
    analysis_prompt = f"""你是一位半导体供应链分析专家。请对以下产业链瓶颈节点进行**子工艺拆解**。

## 上游背景
这是存储产业链 Step 3 分析识别的 L1 瓶颈节点:
- 节点名称: {l1_node['name']}
- 瓶颈描述: {l1_node['bottleneck_narrative']}
- 供给刚性: severity={l1_node['supply_rigidity']['severity']}, root_cause={l1_node['supply_rigidity']['root_cause']}
- 竞争格局: {json.dumps(l1_node['competitive_landscape'], ensure_ascii=False)}
- 利润池: {json.dumps(l1_node['profit_pool'], ensure_ascii=False)}

## 任务
"HBM先进封装 (CoWoS/TSV)" 这个瓶颈节点实际上包含多个**子工艺**步骤。
请将其拆解为具体的、可独立分析的工艺步骤。

思考这个物理过程: HBM颗粒从 DRAM 晶圆完成到最终成为安装在 GPU 基板上的成品，经历了哪些工艺过程？
每个工艺步骤由谁在做、市场规模多大、定价行为如何？

## 输出格式
返回 JSON 数组，每项包含:
```json
[
  {{
    "sub_process": "工艺步骤名称 (中英文)",
    "description": "一句话描述这个工艺做什么",
    "global_players": ["公司1", "公司2"],
    "a_stock_candidates": ["建议: A股相关的公司(如有)"],
    "value_magnitude": {{
      "order_of_magnitude": "<1B | 1B_10B | 10B_100B | 100B+ | unknown",
      "unit_economics_hint": "该环节的价值量估算依据, 如占HBM成本比例或市场规模"
    }},
    "pricing_behavior": "monopoly | collusive_oligopoly | capacity_war | price_taker",
    "reasoning": "为什么这样判断"
  }}
]
```

## 关键要求
1. 从物理工艺过程分解, 不是一个公司一个环节, 而是一个物理步骤一个环节
2. global_players 标注谁在做这个环节 (全球范围)
3. a_stock_candidates 标注 A 股是否有相关公司 (可空数组)
4. pricing_behavior 不能从 competitive_landscape.structure 自动推导, 需要独立判断:
   - monopoly: 独家供应, 价格完全由供应商决定
   - collusive_oligopoly: 几家巨头默契定价, 不打价格战 (如DRAM原厂)
   - capacity_war: 产能扩张竞赛, 价格竞争激烈
   - price_taker: 完全竞争, 没有定价权
5. value_magnitude 估算依据要写清楚
"""

    print(">>> [Round 1] LLM 分析 (chat_pro, thinking)...")
    reasoning = await provider.chat_pro(analysis_prompt)
    print(f"   推理完成, 输出长度: {len(reasoning)} 字符\n")

    # === 第二轮: 结构化输出 (chat_flash) ===
    structure_prompt = f"""你是一位数据提取专家。从以下分析文字中提取结构化的子工艺JSON数组。

分析文字:
{reasoning}

请严格按此 JSON 格式输出, 不要加任何额外文字:

```json
[
  {{
    "sub_process": "工艺步骤名称 (中英文)",
    "description": "一句话描述",
    "global_players": ["公司1", "公司2"],
    "a_stock_candidates": ["A股相关公司(如有)"],
    "value_magnitude": {{
      "order_of_magnitude": "<1B | 1B_10B | 10B_100B | 100B+",
      "unit_economics_hint": "估算依据"
    }},
    "pricing_behavior": "monopoly | collusive_oligopoly | capacity_war | price_taker"
  }}
]
```

注意: 如果分析文字中没有提及某个字段, 用 null 占位。
"""

    print(">>> [Round 2] 结构化输出 (chat_flash)...")
    structured = await provider.chat_flash(structure_prompt)
    print(f"   结构化完成\n")

    # === 解析 JSON ===
    result = None
    try:
        # 尝试从 markdown 代码块提取
        if '```json' in structured:
            json_str = structured.split('```json')[1].split('```')[0].strip()
            result = json.loads(json_str)
        elif '```' in structured:
            json_str = structured.split('```')[1].split('```')[0].strip()
            result = json.loads(json_str)
        else:
            result = json.loads(structured)
    except Exception as e:
        print(f"   JSON 解析失败: {e}")
        print(f"   原始输出前500字: {structured[:500]}")
        return

    # === 输出结果 ===
    print(f"\n{'='*80}")
    print(f"LLM 推理的子工艺分解结果 ({len(result)} 个步骤)")
    print(f"{'='*80}")
    for i, sp in enumerate(result):
        print(f"\n  [{i+1}] {sp.get('sub_process', '?')}")
        print(f"     描述: {sp.get('description', '?')}")
        print(f"     Global: {sp.get('global_players', '?')}")
        a_stock = sp.get('a_stock_candidates', [])
        if a_stock and any(a_stock):
            print(f"     A股: {a_stock}")
        else:
            print(f"     A股: (无)")
        vm = sp.get('value_magnitude', {})
        print(f"     价值量: {vm.get('order_of_magnitude', '?')} — {vm.get('unit_economics_hint', '?')}")
        print(f"     定价行为: {sp.get('pricing_behavior', '?')}")

    # === 对比基准 ===
    print(f"\n{'='*80}")
    print(f"与 HBM→GPU 已知 13 步工艺链对比")
    print(f"{'='*80}")
    llm_names = [sp.get('sub_process', '') for sp in result]
    known_names = [kp['process'] for kp in KNOWN_PROCESSES]

    # 找 LLM 覆盖了哪些
    covered = []
    missing = list(known_names)  # 复制一份
    for llm_name in llm_names:
        matched = False
        for i, known in enumerate(known_names):
            # 模糊匹配: 检查关键词
            llm_lower = llm_name.lower()
            known_lower = known.lower()
            # 检查关键工艺词
            key_words = known_lower.replace(' & ', ' ').replace(' (', ' ').replace(')', '').split()
            match_count = sum(1 for w in key_words if w in llm_lower and len(w) > 2)
            if match_count >= 1 or known_lower in llm_lower or llm_lower in known_lower:
                covered.append(known)
                if known in missing:
                    missing.remove(known)
                matched = True
                break
        if not matched:
            print(f"  ? LLM 步骤 \"{llm_name[:40]}\" — 未匹配到已知步骤")

    print(f"\n  ✅ 已覆盖: {len(covered)}/{len(known_names)}")
    for c in covered:
        print(f"     ✓ {c}")
    if missing:
        print(f"  ❌ 缺失: {len(missing)}/{len(known_names)}")
        for m in missing:
            print(f"     ✗ {m}")

    # === 保存结果 ===
    output = {
        "node": l1_node['name'],
        "node_description": l1_node['bottleneck_narrative'],
        "llm_raw_reasoning": reasoning,
        "llm_structured_result": result,
        "comparison": {
            "covered": covered,
            "missing": missing,
            "coverage_rate": f"{len(covered)}/{len(known_names)}"
        }
    }
    output_path = r'E:\workspace\AIResearch\AIStock_Pro\temp_lab\pipeline_cache\three_layer_test_result.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {output_path}")


if __name__ == '__main__':
    import asyncio
    asyncio.run(test_llm_reasoning())
