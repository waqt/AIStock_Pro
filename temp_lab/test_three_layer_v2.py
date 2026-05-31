"""
三层抽象模型 LLM 推理测试 V2
=========================
V1 问题: chat_pro 的 thinking 模式消耗了全部 token, max_tokens 不够。
V2 改进: 用 chat() 直接调用, max_tokens=16384, 关闭 thinking (纯推理输出)。
"""

import sys, os, json, asyncio
sys.path.insert(0, r'E:\workspace\AIResearch\AIStock_Pro\backend')

from app.framework.ai.providers.deepseek import DeepSeekProvider

# HBM→GPU 已知工艺链 (事实基准)
KNOWN_PROCESSES = [
    {"step": 1, "process": "DRAM Wafer Fabrication — HBM基础晶圆制造(EUV光刻/DRAM单元)", "players": ["SK Hynix", "Samsung", "Micron"]},
    {"step": 2, "process": "TSV (Through Silicon Via) — 硅通孔电极形成", "players": ["SK Hynix", "Samsung", "Micron"]},
    {"step": 3, "process": "Micro Bump Formation — 微凸点制作(电镀/光刻)", "players": ["SK Hynix", "Samsung", "Micron"]},
    {"step": 4, "process": "Stack Bonding (TCB/Hybrid Bonding) — 芯片堆叠键合", "players": ["SK Hynix", "Samsung"]},
    {"step": 5, "process": "Molding & Underfill — 底部填充+塑封", "players": ["Nagase", "Henkel", "Namics"]},
    {"step": 6, "process": "Dicing & Singulation — 切割成单颗HBM", "players": ["Disco", "Tokyo Seimitsu"]},
    {"step": 7, "process": "HBM Test & KGD —  Known Good Die测试", "players": ["Advantest", "Teradyne"]},
    {"step": 8, "process": "CoW (Chip-on-Wafer) — HBM堆叠到CoWoS中介层", "players": ["TSMC"]},
    {"step": 9, "process": "oS (on-Substrate) — 中介层贴装到基板", "players": ["ASE", "Amkor", "SPIL"]},
    {"step": 10, "process": "ABF Substrate — 封装基板制造", "players": ["Ibiden", "Unimicron", "AT&S"]},
    {"step": 11, "process": "TIM & Thermal Solutions — 热界面材料", "players": ["Honeywell", "Henkel", "ShinEtsu"]},
    {"step": 12, "process": "Final Test & SLT — 最终测试/系统级测试", "players": ["Advantest", "Teradyne", "Chroma"]},
    {"step": 13, "process": "System Assembly / GPU Card — 整卡组装", "players": ["Nvidia", "Wistron", "Foxconn"]},
]


async def test():
    provider = DeepSeekProvider()

    # 加载瓶颈节点
    with open(r'E:\workspace\AIResearch\AIStock_Pro\temp_lab\pipeline_cache\step3_bottlenecks.json', encoding='utf-8') as f:
        nodes = json.load(f)
    l1_node = nodes[0]

    print(f"{'='*80}")
    print(f"测试瓶颈节点: L{l1_node['level']} {l1_node['name']}")
    print(f"  瓶颈描述: {l1_node['bottleneck_narrative']}")
    print(f"{'='*80}\n")

    prompt = f"""你是一位半导体供应链资深分析师. 请将以下瓶颈节点拆解为**具体的子工艺步骤**.

## 瓶颈节点
- 名称: {l1_node['name']}
- 描述: {l1_node['bottleneck_narrative']}
- 竞争格局: {json.dumps(l1_node['competitive_landscape'], ensure_ascii=False)}

## 任务
"HBM先进封装 (CoWoS/TSV)" 不是单一工艺, 而是包含多个物理工艺步骤的**环节**.
请你沿着真实的物理制造流程, 将"HBM从DRAM晶圆到最终算力卡"的过程拆解为具体工艺步骤.

对每一步, 标注:
1. 工艺名称及一句话描述
2. global_players: 谁是全球主要参与者? 分3类: 原厂自研自用(IDM) / 第三方代工厂(Foundry/Fab) / 设备材料供应商(Equipment/Material)
3. value_magnitude: 该环节的全球市场规模级别的数量级:
   - <1B: 不到10亿美元
   - 1B_10B: 10亿~100亿美元
   - 10B_100B: 100亿~1000亿美元
   - 100B+: 超过1000亿美元
   请给出估算依据(如占HBM总成本x%, 或行业报告通常给出的市场规模)
4. pricing_behavior: 定价行为 (请**独立判断**, 不能从竞争格局structure自动推导):
   - monopoly: 独家供应, 价格由供应商决定
   - collusive_oligopoly: 几家巨头不打价格战, 默契定价
   - capacity_war: 产能扩张竞赛, 价格竞争激烈
   - price_taker: 充分竞争, 没有定价权
5. a_stock: A股是否有相关公司? 如有请写出具体代码和逻辑

## 输出格式
直接输出JSON数组, 不要markdown包裹:

[
  {{
    "sub_process": "步骤名",
    "description": "一句话描述",
    "global_players": ["公司1 — 角色说明"],
    "value_magnitude": {{"order": "<1B|1B_10B|10B_100B|100B+", "basis": "估算依据"}},
    "pricing_behavior": "monopoly|collusive_oligopoly|capacity_war|price_taker",
    "a_stock": ["建议: 相关A股公司(代码)"]
  }}
]

尽量覆盖从DRAM晶圆到最终算力卡的完整流程, 不要合并关键步骤.
"""

    print(">>> LLM 推理中 (chat_pro, max_tokens=16384, 无thinking, 约60-120s)...")
    result_text = await provider.chat(
        prompt, max_tokens=16384, model="pro", thinking=False
    )

    if not result_text or len(result_text.strip()) == 0:
        print("ERROR: LLM 返回空结果")
        return

    print(f"   返回长度: {len(result_text)} 字符")
    print(f"   前200字: {result_text[:200]}")

    # 解析 JSON
    result = None
    try:
        result = json.loads(result_text)
    except json.JSONDecodeError:
        # 尝试提取 JSON
        import re
        m = re.search(r'\[.*\]', result_text, re.DOTALL)
        if m:
            try:
                result = json.loads(m.group(0))
            except json.JSONDecodeError as e:
                print(f"JSON 解析失败: {e}")
                print(f"原始输出:\n{result_text[:1000]}")
                return
        else:
            print(f"未找到 JSON 数组, 原始输出:\n{result_text[:1000]}")
            return

    # === 输出 ===
    print(f"\n{'='*80}")
    print(f"LLM 推理结果 ({len(result)} 个步骤)")
    print(f"{'='*80}")
    for i, sp in enumerate(result):
        print(f"\n  [{i+1}] {sp.get('sub_process', '?')}")
        print(f"     描述: {sp.get('description', '?')}")
        players = sp.get('global_players', [])
        print(f"     Global: {players}")
        vm = sp.get('value_magnitude', {})
        print(f"     价值量: {vm.get('order', '?')} — {vm.get('basis', '?')}")
        print(f"     定价: {sp.get('pricing_behavior', '?')}")
        a_stock = sp.get('a_stock', [])
        if a_stock:
            print(f"     A股: {a_stock}")

    # === 对比 ===
    print(f"\n{'='*80}")
    print(f"与已知 13 步工艺链对比")
    print(f"{'='*80}")

    llm_names = [sp.get('sub_process', '') for sp in result]
    known_simple = [kp['process'].split(' — ')[0] for kp in KNOWN_PROCESSES]

    # Fuzzy matching
    covered = []
    missing = list(known_simple)
    for li, llm_name in enumerate(llm_names):
        llm_lower = llm_name.lower()
        matched = False
        for ki, known in enumerate(known_simple):
            known_lower = known.lower()
            if known_lower in llm_lower or llm_lower in known_lower:
                covered.append((known, li))
                missing.remove(known)
                matched = True
                break
        if not matched:
            # 尝试关键词匹配
            for ki, known in enumerate(known_simple):
                known_lower = known.lower()
                # 拿掉括号里的内容, 匹配核心词
                core = known_lower.split(' (')[0].split('(')[0].strip()
                words = core.replace('/', ' ').split()
                kw_match = sum(1 for w in words if len(w) > 3 and w in llm_lower)
                if kw_match >= 1:
                    covered.append((known, li))
                    if known in missing:
                        missing.remove(known)
                    matched = True
                    break

    print(f"\n  ✅ 覆盖: {len(set(c[0] for c in covered))}/{len(known_simple)}")
    for c in sorted(set(c[0] for c in covered)):
        print(f"     ✓ {c}")
    if missing:
        print(f"  ❌ 缺失: {len(missing)}/{len(known_simple)}")
        for m in missing:
            print(f"     ✗ {m}")

    print(f"\n  LLM 额外步骤 (不在13步基准中):")
    covered_known = set(c[0] for c in covered)
    for li, llm_name in enumerate(llm_names):
        llm_lower = llm_name.lower()
        is_extra = True
        for known in known_simple:
            if known in covered_known:
                k = known.lower().split(' (')[0].split('(')[0].strip()
                words = k.replace('/', ' ').split()
                kw_match = sum(1 for w in words if len(w) > 3 and w in llm_lower)
                if kw_match >= 1:
                    is_extra = False
                    break
        if is_extra:
            print(f"     + {llm_name[:60]}")

    # === 保存 ===
    output_path = r'E:\workspace\AIResearch\AIStock_Pro\temp_lab\pipeline_cache\three_layer_test_v2.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            "node": l1_node['name'],
            "llm_raw_output": result_text,
            "llm_structured": result,
            "comparison": {
                "covered": list(set(c[0] for c in covered)),
                "missing": missing
            }
        }, f, ensure_ascii=False, indent=2)
    print(f"\n结果保存: {output_path}")


if __name__ == '__main__':
    asyncio.run(test())
