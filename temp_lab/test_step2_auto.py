"""Test Step 2 auto mode — read Step1 macro_report, scan benefited_sectors (no emoji)"""
import sys,os,asyncio,json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

async def main():
    from app.framework.ai.providers.deepseek import DeepSeekProvider
    from app.domain.research.agents.market_scanner import MarketScanner

    macro_path = os.path.join(os.path.dirname(__file__), "..", "backend", "data", "macro_report.json")
    with open(macro_path, "r", encoding="utf-8") as f:
        macro = json.load(f)
    sectors = macro.get("data", {}).get("benefited_sectors", [])
    if not sectors:
        sectors = macro.get("data", {}).get("macro_conclusion", {}).get("benefited_sectors", [])

    out_lines = []
    out_lines.append(f"Step1 benefited_sectors ({len(sectors)}):")
    for s in sectors:
        out_lines.append(f"  {s.get('sector','?')} [{s.get('confidence','?')}]")

    provider = DeepSeekProvider()
    scanner = MarketScanner(provider=provider)
    out_lines.append(f"\nScanning {len(sectors)} industries...")
    result = await scanner.analyze({"mode": "auto", "hypothesis_sectors": sectors})

    industries = result.get("industries", [])
    priority_order = {"高": 0, "中": 1, "低": 2, "跳过": 3}
    industries.sort(key=lambda i: priority_order.get(
        i.get("verdict", {}).get("priority", "低"), 3))

    out_lines.append(f"\n{'='*60}")
    out_lines.append(f"Results: {len(industries)} industries evaluated\n")

    for idx, ind in enumerate(industries):
        v = ind.get("verdict", {})
        cp = ind.get("cycle_position", {})
        pr = ind.get("prosperity", {})
        pp = ind.get("propagation", {})
        th = ind.get("time_horizon", {})
        pa = ind.get("payoff", {})

        enter = "[ENTER]" if v.get("enter_step3") else "[SKIP]"
        out_lines.append(f"{idx+1}. {enter} {ind.get('industry','?')} [{v.get('priority','?')}]")
        out_lines.append(f"   Phase: {cp.get('phase','?')}/{cp.get('sub_phase','?')} | Type: {pr.get('type','?')} | Demand: {pr.get('demand_quality','?')}")
        out_lines.append(f"   Payoff: {pa.get('asymmetry','?')} | Depth: {pp.get('depth','?')} | Alpha: {th.get('alpha_window','?')}")
        out_lines.append(f"   Contradiction: {pr.get('core_contradiction','?')[:150]}")
        if v.get('rationale'):
            out_lines.append(f"   Rationale: {v['rationale'][:200]}")
        kr = ind.get("kill_reasons", [])
        if kr: out_lines.append(f"   Kill reasons: {', '.join(kr)}")
        out_lines.append("")

    # Write to file to avoid conda gbk encoding issues
    out_path = os.path.join(os.path.dirname(__file__), "step2_auto_result.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines))
    print(f"Done. Results saved to {out_path}")
    print("\n".join(out_lines[:5]))
    print(f"... ({len(out_lines)} lines total)")

asyncio.run(main())
