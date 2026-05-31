"""
三层抽象模型 — 人工复核评估
======================
基于 V2 的 LLM 输出, 眼动匹配到真实的 13 步基准
"""

import json
with open(r'E:\workspace\AIResearch\AIStock_Pro\temp_lab\pipeline_cache\three_layer_test_v2.json', encoding='utf-8') as f:
    data = json.load(f)
result = data['llm_structured']

# 人工匹配: (llm_index, benchmark_id, vm_ok, pb_ok, note)
MATCHES = [
    (0, "DRAM Wafer Fab", False, True, "LLM估HBM专用DRAM=10B_100B, 基准估整体=100B+, 角度不同"),
    (1, "TSV", False, True, "LLM估1B_10B(设备市场), 基准估10B_100B(含工艺价值)"),
    (2, "Dicing/Singulation", False, True, "晶圆减薄是细化分解, 价值量基准<1B, LLM估1B_10B(偏高)"),
    (3, "Micro Bump", True, True, "完全一致: 1B_10B + collusive_oligopoly"),
    (4, None, None, None, "➕ EXTRA: 逻辑控制芯片制造 (HBM Base Die, 基准遗漏了)"),
    (5, "Stack Bonding", True, True, "完全一致: 1B_10B + collusive_oligopoly"),
    (6, "Molding & Underfill", True, False, "VM一致, PB: LLM说collusive_oligopoly, 实为capacity_war(材料竞争激烈)"),
    (7, None, None, None, "➕ EXTRA: 硅中介层制造 (CoW的前置步骤, 细化合理)"),
    (8, "CoW", True, True, "完全一致: 10B_100B + monopoly (TSMC独家)"),
    (9, "oS+ABF(合并)", False, False, "LLM合并了oS和ABF, VM偏高, PB应拆分"),
    (10, "System Assembly", True, False, "VM一致: 100B+, PB: LLM说collusive, 实为capacity_war(Nvidia强势但组装竞争)"),
]

print(f"{'='*100}")
print("人工复核: LLM 11步 → 13步基准")
print(f"{'='*100}")

print(f"\n{'─'*100}")
print(f"{'#':<3} {'LLM 步骤':<30} {'匹配基准':<24} {'VM':<8} {'PB':<8} {'说明'}")
print(f"{'─'*100}")

vm_ok = 0
pb_ok = 0
vm_total = 0
pb_total = 0

for idx, sp in enumerate(result):
    m = MATCHES[idx]
    label = sp.get('sub_process', '?')
    bench = m[1] if m[1] else "—"
    vm = "✅" if m[2] == True else ("🟡" if m[2] == False else "—")
    pb = "✅" if m[3] == True else ("❌" if m[3] == False else "—")
    note = m[4]
    if m[2] is True: vm_ok += 1
    if m[2] is False: vm_ok += 0
    if m[2] is not None: vm_total += 1
    if m[3] is True: pb_ok += 1
    if m[3] is False: pb_ok += 0
    if m[3] is not None: pb_total += 1
    print(f"{idx:<3} {label:<30} {bench:<24} {vm:<8} {pb:<8} {note}")

print(f"{'─'*100}")

# Extra steps from LLM
print(f"\n➕ LLM 额外识别 (基准未拆分):")
print(f"   4. 逻辑控制芯片制造 — HBM Base Die 真实存在, 台积电为海力士代工")
print(f"   8. 硅中介层制造 — CoW的前置步骤, 台积电独家, 合理细化")

# Missing benchmark steps
print(f"\n📋 LLM 合并或遗漏的基准步骤:")
print(f"   减薄划片 → LLM拆为第3步'晶圆减薄'(更细) ✓")
print(f"   HBM测试 → 未独立列出, 合并入第11步最终集成 ❌ (遗漏)")
print(f"   TIM散热 → 未独立列出, 合并入第11步 ❌")
print(f"   最终测试 → 未独立列出, 合并入第11步 ❌")
print(f"   ABF载板 → 合并入第10步'基板集成', 未单独列出 ❌")

# Overall assessment
print(f"\n{'='*100}")
print(f"评估汇总")
print(f"{'='*100}")
print(f"")
print(f"【sub_process 分解能力】⭐⭐⭐⭐")
print(f"  从 HBM→DRAM→TSV→Bump→Stack→Mold→CoW→oS→Assembly 的主流程全部覆盖")
print(f"  额外识别了逻辑控制芯片(基准遗漏)和硅中介层(合理细化)")
print(f"  合并了测试和散热环节, 粒度略粗但可接受")
print(f"")
print(f"【value_magnitude 估测】⭐⭐⭐ (准确率 {vm_ok}/{vm_total} 基于人工匹配)")
print(f"  偏差都在 1 个数量级内, 没有离谱的错误")
print(f"  DRAM分歧: LLM估HBM专用部分, 基准估整体市场, 角度不同")
print(f"  最大偏差: 减薄环节估1B_10B偏高, 实际<1B (Disco独家但市场小)")
print(f'  建议: prompt中明确"是此环节全球市场规模, 不是占HBM总成本比例"')
print(f"")
print(f"【pricing_behavior 判断】⭐⭐⭐⭐ (准确率 {pb_ok}/{pb_total} 基于人工匹配)")
print(f"  正确识别: DRAM寡头=collusive, TSV设备=monopoly, CoW=monopoly, Stack=oligopoly")
print(f"  偏差: 底部填充材料实际是capacity_war(多家竞争), 整机组装实际是capacity_war")
print(f"  注: 这两个偏差有讨论空间 — Nvidia定价权强但代工竞争激烈")
print(f"")
print(f"【a_stock_mapping 质量】⭐⭐⭐⭐")
print(f"  长电科技→bumping/CoW, 中微→TSV刻蚀, 兴森→ABF, 工业富联→组装")
print(f"  全部给出了具体代码和逻辑, 无'建议关注'这种空泛描述")
print(f"  不足: 部分标注了'暂无直接A股'但未区分是确实没有还是没搜到")
print(f"")
print(f"【结论】纯LLM推理(无搜索)的三层抽象质量已经很高。")
print(f"  瓶颈→子工艺分解: ✅ 无需搜索, LLM领域知识足够")
print(f"  value_magnitude:   🟡 需要搜索锚定精确量级")
print(f"  pricing_behavior:  ✅ 独立判断能力好, 不从structure推导")
print(f"  a_stock_mapping:   🟡 需要搜索验证最新进展")
print(f"{'='*100}")
