"""
模拟 Step 6 _verify_single 6维权力画像 — LLM 自主调用工具对比两家公司

流程:
  1. 注入完整财务数据字典 (FinQueryService + RawDataService)
  2. LLM 自主决定调用 query_financial_data / web_search
  3. 收集证据后输出六维权力对比 JSON
"""
import asyncio, json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.framework.ai.providers.deepseek import DeepSeekProvider
from app.domain.research.agents.base import TOOL_REGISTRY, WEB_SEARCH_TOOL, DEFAULT_TOOL_DEFINITIONS
from app.domain.quant.engine.financial_query_service import FinancialQueryService
from app.domain.market_data.services.financial_data_service import FinancialRawDataService

OUT_DIR = os.path.join(os.path.dirname(__file__))

# ═══ 标的信息 ═══════════════════════════════════════
# 两家同赛道公司用于对比分析
COMPANIES = [
    {"code": "600699", "name": "均胜电子", "industry": "汽车安全电子",
     "desc": "全球汽车安全系统龙头, 被动安全+智能驾驶"},
    {"code": "601689", "name": "拓普集团", "industry": "汽车NVH/底盘/轻量化",
     "desc": "NVH龙头, 向智能底盘+轻量化一体化压铸转型"},
]

INDUSTRY_BG = """
汽车零部件赛道, 新能源车渗透率超50%, 行业面临:
- 传统 Tier1 格局重塑, 国产替代加速
- 智能驾驶+轻量化带来增量市场
- 主机厂降本压力向上游传导, 有定价权的零部件厂才能维持利润率
"""

PROMPT = """你是产业竞争分析专家。比较以下两家公司在汽车零部件赛道的竞争地位。

## 标的 A: {name_a}({code_a})
{desc_a}
## 标的 B: {name_b}({code_b})
{desc_b}

## 行业背景
{industry_bg}

## 可用工具
你可以调用以下工具获取实时数据:

1. **query_financial_data(code, indicators=[...], raw_fields=[...])**
   - indicators: 财务指标 (如 roic_pct, revenue_yoy, margin, rd_intensity, gross_margin_trend 等)
   - raw_fields: 原始财报字段 (如 revenue, parent_profit, op_cashflow, total_assets 等)
   - 两者可同时使用

2. **web_search(query, num=5)**
   - 搜索网络获取行业/公司实时信息

## 财务数据字典
{FINANCIAL_CATALOG}

## 分析要求
- **不要使用任何预设的分析框架或维度**。根据汽车零部件行业的竞争特征, 自主定义最能反映这两家公司竞争力的分析维度
- 每个维度的判断必须来自 tool 调用的真实数据作为证据
- 先查数据再判断, 不要先判断再勉强找证据支持
- 如有需要, 可以自己从原始字段计算财务比率

## 输出结构
{{
  "comparison": [
    {{
      "code": "{code_a}",
      "name": "{name_a}",
      "analysis_dimensions": [
        {{
          "dimension": "自定义维度名称",
          "rating": "strong/medium/weak/emerging",
          "evidence": ["来自 tool 调用的证据"],
          "reasoning": "为什么这个维度重要"
        }}
      ],
      "profit_capture_thesis": "利润捕获能力分析",
      "roic_note": "如查询了 ROIC 数据在此注明"
    }},
    {{
      "code": "{code_b}",
      "name": "{name_b}",
      "analysis_dimensions": [...],
      "profit_capture_thesis": "...",
      "roic_note": "..."
    }}
  ],
  "winner": "哪个标的总体竞争力更强",
  "winner_reasoning": "详细理由",
  "thesis_breakers": ["什么条件会推翻判断"]
}}

## 规则
- 每个维度的 evidence 必须来自 tool 调用返回的真实数据
- 禁止输出投资建议
- 先查数据再判断, 不要先判断再勉强找证据支持"""


async def run():
    provider = DeepSeekProvider()

    # 1. 构建完整数据字典
    print("[1/4] 构建财务数据字典...")
    fin_catalog = FinancialQueryService.format_catalog_for_prompt()
    raw_catalog = FinancialRawDataService.format_catalog_for_prompt()
    full_catalog = fin_catalog + "\n" + raw_catalog
    print(f"      字典长度: {len(full_catalog)} chars")

    # 2. 组装 prompt
    print("[2/4] 组装 prompt...")
    prompt = PROMPT.format(
        name_a=COMPANIES[0]["name"], code_a=COMPANIES[0]["code"],
        desc_a=COMPANIES[0]["desc"],
        name_b=COMPANIES[1]["name"], code_b=COMPANIES[1]["code"],
        desc_b=COMPANIES[1]["desc"],
        industry_bg=INDUSTRY_BG.strip(),
        FINANCIAL_CATALOG=full_catalog,
    )
    print(f"      Prompt: {len(prompt)} chars")

    # 3. 工具定义
    print("[3/4] 初始化工具...")
    tools = DEFAULT_TOOL_DEFINITIONS + [WEB_SEARCH_TOOL]
    msglog = [{"role": "user", "content": prompt}]

    # 4. 工具调用循环
    print("[4/4] 开始 LLM 分析 (max_rounds=12)...\n")
    max_rounds = 12
    all_tool_calls = []
    final_text = ""

    for rnd in range(max_rounds):
        print(f"\n{'='*60}")
        print(f"  Round {rnd + 1}/{max_rounds}")
        print(f"{'='*60}")

        result = await provider.chat_with_tools(
            prompt="", tools=tools, messages=msglog,
            model="pro", max_tokens=16384, timeout=300,
        )

        if result.tool_calls:
            # 先添加 assistant tool_calls 消息 (Anthropic 需要 tool_use → tool_result 配对)
            msglog.append({
                "role": "assistant",
                "content": result.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)}}
                    for tc in result.tool_calls
                ],
            })
            for tc in result.tool_calls:
                all_tool_calls.append(tc)
                fn = TOOL_REGISTRY.get(tc.name)
                args_str = json.dumps(tc.arguments, ensure_ascii=False)
                print(f"  🔧 {tc.name}({args_str})")

                if fn:
                    try:
                        data = await fn(**tc.arguments)
                        content = json.dumps(data, ensure_ascii=False, default=str)
                        snippet = json.dumps(data, ensure_ascii=False, default=str)[:300]
                        print(f"  ✅ → {snippet}...")
                    except Exception as e:
                        content = json.dumps({"error": str(e)})
                        print(f"  ❌ {e}")
                else:
                    content = json.dumps({"error": f"Unknown tool: {tc.name}"})
                    print(f"  ❌ Unknown tool")

                msglog.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": content,
                })
        else:
            final_text = result.content or ""
            print(f"\n  📝 Final response ({len(final_text)} chars)")
            print(f"\n{final_text[:3000]}")
            break
    else:
        print(f"\n  ⚠️  Max rounds ({max_rounds}) reached")

    # 5. 保存中间消息 + 解析 JSON
    print(f"\n{'='*60}")
    print("  保存结果...")

    # 保存完整对话
    with open(os.path.join(OUT_DIR, "step6_mock_messages.json"), "w", encoding="utf-8") as f:
        json.dump({
            "prompt_length": len(prompt),
            "total_rounds": len([m for m in msglog if m["role"] == "assistant"]),
            "tool_calls_count": len(all_tool_calls),
            "messages": msglog,
        }, f, ensure_ascii=False, indent=2)

    # 解析 JSON
    if final_text:
        import re
        text = final_text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        try:
            parsed = json.loads(text)
            out_path = os.path.join(OUT_DIR, "step6_mock_result.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(parsed, f, ensure_ascii=False, indent=2)
            print(f"\n  ✅ JSON 结果已保存: {out_path}")
            print(f"\n{'='*60}")
            print("  PARSED RESULT:")
            print(json.dumps(parsed, ensure_ascii=False, indent=2))
        except (json.JSONDecodeError, IndexError) as e:
            print(f"\n  ⚠️  JSON 解析失败: {e}")
            raw_path = os.path.join(OUT_DIR, "step6_mock_raw.txt")
            with open(raw_path, "w", encoding="utf-8") as f:
                f.write(final_text)
            print(f"  原始响应已保存: {raw_path}")

    print(f"\n  📊 工具调用统计: {len(all_tool_calls)} 次")
    for tc in all_tool_calls:
        print(f"    - {tc.name}: {tc.arguments.get('code', tc.arguments.get('query', ''))}")


if __name__ == "__main__":
    asyncio.run(run())
