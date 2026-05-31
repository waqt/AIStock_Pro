"""
三层抽象模型结果评估 — 人工智能对比
=============================
读取 V2 的 LLM 输出, 用更智能的方式与基准对比
"""

import sys, json

with open(r'E:\workspace\AIResearch\AIStock_Pro\temp_lab\pipeline_cache\three_layer_test_v2.json', encoding='utf-8') as f:
    data = json.load(f)

result = data['llm_structured']

# 基准 (中英文 + 中文翻译)
BENCHMARK = [
    {"id": "DRAM晶圆", "en": "DRAM Wafer Fabrication", "players": ["SK Hynix", "Samsung", "Micron"],
     "vm": "100B+", "price": "collusive_oligopoly", "a": "设备: 中微/北方华创"},
    {"id": "TSV", "en": "TSV (Through Silicon Via)", "players": ["SK Hynix", "Samsung", "Micron"],
     "vm": "10B_100B", "price": "collusive_oligopoly", "a": "设备: 中微/北方华创/盛美"},
    {"id": "微凸点", "en": "Micro Bump Formation", "players": ["SK Hynix", "Samsung", "Micron"],
     "vm": "1B_10B", "price": "collusive_oligopoly", "a": "封测: 长电/通富"},
    {"id": "堆叠键合", "en": "Stack Bonding (TCB/Hybrid Bonding)", "players": ["SK Hynix", "Samsung"],
     "vm": "1B_10B", "price": "collusive_oligopoly", "a": "设备: 无直接A股"},
    {"id": "塑封填充", "en": "Molding & Underfill", "players": ["Nagase", "Henkel", "Namics"],
     "vm": "1B_10B", "price": "capacity_war", "a": "华海诚科/德邦科技"},
    {"id": "减薄划片", "en": "Dicing & Singulation", "players": ["Disco", "Tokyo Seimitsu"],
     "vm": "<1B", "price": "monopoly", "a": "光力科技(弱)"},
    {"id": "HBM测试", "en": "HBM Test & KGD", "players": ["Advantest", "Teradyne"],
     "vm": "1B_10B", "price": "monopoly", "a": "长川科技/华峰测控"},
    {"id": "CoW", "en": "CoW (Chip-on-Wafer)", "players": ["TSMC"],
     "vm": "10B_100B", "price": "monopoly", "a": "无"},
    {"id": "oS基板", "en": "oS (on-Substrate)", "players": ["ASE", "Amkor"],
     "vm": "1B_10B", "price": "capacity_war", "a": "长电/通富"},
    {"id": "ABF载板", "en": "ABF Substrate", "players": ["Ibiden", "Unimicron", "AT&S"],
     "vm": "10B_100B", "price": "collusive_oligopoly", "a": "兴森/深南"},
    {"id": "TIM散热", "en": "TIM & Thermal", "players": ["Honeywell", "Henkel", "ShinEtsu"],
     "vm": "1B_10B", "price": "collusive_oligopoly", "a": "飞荣达"},
    {"id": "最终测试", "en": "Final Test & SLT", "players": ["Advantest", "Teradyne"],
     "vm": "1B_10B", "price": "collusive_oligopoly", "a": "长川/华峰"},
    {"id": "整卡组装", "en": "System Assembly / GPU Card", "players": ["Nvidia", "Wistron", "Foxconn"],
     "vm": "100B+", "price": "capacity_war", "a": "工业富联/浪潮"},
]

print(f"{'='*100}")
print(f"LLM 输出: {len(result)} 步骤 vs 基准: {len(BENCHMARK)} 步骤")
print(f"{'='*100}")

# 人工匹配: 每个 LLM 步骤匹配最接近的基准步骤
import re

def match_llm_to_benchmark(llm_step):
    """返回匹配的基准 ID 列表 (可能匹配多个基准步骤)"""
    name = (llm_step.get('sub_process', '') + ' ' + llm_step.get('description', '')).lower()
    matches = []
    for b in BENCHMARK:
        keywords = b['id'].lower()
        if keywords in name:
            matches.append(b['id'])
    return matches

def evaluate_dimension(llm_val, bench_val, dim_name, step_name):
    """评价单个维度的准确度"""
    if not llm_val or llm_val == 'unknown' or llm_val == '?':
        return '⚠️ 缺失'
    if isinstance(llm_val, dict):
        llm_val = llm_val.get('order', '')
    llm_lower = llm_val.lower().strip()
    bench_lower = bench_val.lower().strip()
    if llm_lower == bench_lower:
        return '✅'
    # 允许相邻量级
    if dim_name == 'value_magnitude':
        levels = ['<1b', '1b_10b', '10b_100b', '100b+']
        if llm_lower in levels and bench_lower in levels:
            li = levels.index(llm_lower)
            bi = levels.index(bench_lower)
            if abs(li - bi) <= 1:
                return '🟡 偏差1档'
    if dim_name == 'pricing_behavior':
        # 允许相似归类
        similar = {
            'monopoly': ['monopoly'],
            'collusive_oligopoly': ['collusive_oligopoly', 'oligopoly'],
            'capacity_war': ['capacity_war', 'price_war', 'competitive'],
            'price_taker': ['price_taker', 'fully_competitive'],
        }
        for k, vals in similar.items():
            if bench_lower in vals and llm_lower in vals:
                return '✅'
            if bench_lower in vals and llm_lower.replace('_', '') in k.replace('_', ''):
                return '✅'
    return '❌'

used_benchmarks = set()
match_results = []

for i, sp in enumerate(result):
    sp_name = sp.get('sub_process', '?')
    matches = match_llm_to_benchmark(sp)

    if not matches:
        # 尝试更宽松的匹配
        desc = sp.get('description', '')
        combined = (sp_name + ' ' + desc).lower()
        for b in BENCHMARK:
            bid = b['id'].lower()
            # 检查关键工艺词
            process_words = {'dram': 'dram', 'tsv': 'tsv', 'bump': '微凸', 'stack': '堆叠', 'mold': '塑封',
                           'dicing': '划片', 'bond': '键合', 'coW': 'chip on wafer', 'cv': 'cv',
                           'substrate': '基板', 'tim': '热', 'test': '测试', 'assembly': '组装', 'card': '卡'}
            for word, label in process_words.items():
                if word in combined and word in bid:
                    matches.append(b['id'])
                    break
        if not matches:
            matches = ['(无匹配)']

    for mi, m in enumerate(matches):
        used_benchmarks.add(m)
        bid = m
        b = next((x for x in BENCHMARK if x['id'] == bid), None)
        if b:
            vm = sp.get('value_magnitude', {})
            if isinstance(vm, dict):
                vm_order = vm.get('order', '?')
                vm_basis = vm.get('basis', '')
            else:
                vm_order = str(vm)
                vm_basis = ''
            pb = sp.get('pricing_behavior', '?')
            a_stock = sp.get('a_stock', [])

            vm_result = evaluate_dimension(sp.get('value_magnitude', {}), b['vm'], 'value_magnitude', sp_name)
            pb_result = evaluate_dimension(sp.get('pricing_behavior', ''), b['price'], 'pricing_behavior', sp_name)

            match_results.append({
                'llm_step': sp_name,
                'benchmark': bid,
                'vm': f"{vm_order} vs {b['vm']} → {vm_result}",
                'pb': f"{pb} vs {b['price']} → {pb_result}",
                'a_stock': a_stock,
                'a_bench': b['a'],
            })

# === 打印评估表 ===
print(f"\n{'─'*100}")
print(f"{'LLM 步骤':<28} {'基准步骤':<18} {'价值量':<32} {'定价行为':<32}")
print(f"{'─'*100}")

vm_correct = 0
vm_total = 0
pb_correct = 0
pb_total = 0

for r in match_results:
    vm_tag = '✅' if '✅' in r['vm'] else ('🟡' if '🟡' in r['vm'] else '❌')
    pb_tag = '✅' if '✅' in r['pb'] else '❌'
    vm_total += 1
    pb_total += 1
    if '✅' in r['vm']: vm_correct += 1
    if '✅' in r['pb']: pb_correct += 1
    print(f"{r['llm_step']:<28} {r['benchmark']:<18} {r['vm']:<32} {r['pb']:<32}")

print(f"{'─'*100}")

# 未覆盖的基准
uncovered = [b for b in BENCHMARK if b['id'] not in used_benchmarks]
if uncovered:
    print(f"\n❌ 基准中有但 LLM 未覆盖的步骤 ({len(uncovered)}):")
    for b in uncovered:
        print(f"   ✗ {b['id']:12s} ({b['en']})")

# LLM 额外步骤
extra_steps = []
for i, sp in enumerate(result):
    sp_name = sp.get('sub_process', '?')
    matches = match_llm_to_benchmark(sp)
    has_match = any(m in used_benchmarks for m in matches) if matches else False
    if not has_match:
        extra_steps.append(sp_name)
if extra_steps:
    print(f"\n➕ LLM 额外步骤 (基准未独立列出):")
    for s in extra_steps:
        print(f"   + {s}")

print(f"\n{'='*100}")
print(f"评估总结:")
print(f"  价值量 (value_magnitude): {vm_correct}/{vm_total} 正确 ({vm_correct/vm_total*100:.0f}%)")
print(f"  定价行为 (pricing_behavior): {pb_correct}/{pb_total} 正确 ({pb_correct/pb_total*100:.0f}%)")
print(f"  LLM 步骤覆盖: {len(used_benchmarks)}/{len(BENCHMARK)} 基准步骤")
print(f"  LLM 额外步骤: {len(extra_steps)} 个 (合理细化或合并)")
print(f"{'='*100}")
