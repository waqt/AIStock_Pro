"""
Step runner — 强缓存/强可回放/强日志
Usage: python run_step.py step2 --industry AI电力基础设施 [--force]
"""
import sys, os, asyncio, json, time, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.dirname(__file__))
from app.framework.pipeline.checkpoint import load_checkpoint, save_checkpoint, hash_input, list_checkpoints


async def run_step1_macro(provider, params):
    from app.domain.research.agents.global_capex_scanner import GlobalCapexScanner
    scanner = GlobalCapexScanner(provider=provider)
    result = await scanner.synthesize_macro_report()
    return result


async def run_step2_gatekeeper(provider, params):
    from app.domain.research.agents.market_scanner import MarketScanner
    scanner = MarketScanner(provider=provider)
    industry = params.get("industry", "")
    if industry:
        return await scanner.analyze({"mode": "manual", "target_industry": industry})
    else:
        sectors = params.get("sectors", [])
        return await scanner.analyze({"mode": "auto", "hypothesis_sectors": sectors})


STEPS = {
    "step1_macro": run_step1_macro,
    "step2_gatekeeper": run_step2_gatekeeper,
}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=list(STEPS.keys()), help="Step to run")
    parser.add_argument("--industry", default="", help="Industry (for step2 manual)")
    parser.add_argument("--slug", default="test", help="Cache slug")
    parser.add_argument("--force", action="store_true", help="Force re-run, skip cache")
    parser.add_argument("--list", action="store_true", help="List cached checkpoints")
    args = parser.parse_args()

    if args.list:
        cps = list_checkpoints()
        print(f"{len(cps)} checkpoints:")
        for c in cps[:20]:
            print(f"  {c['step']:20s} {c['slug']:15s} {c['saved_at'][:19]} {c['elapsed']}s")
        return

    from app.framework.ai.providers.deepseek import DeepSeekProvider
    provider = DeepSeekProvider()

    params = {"industry": args.industry}
    ih = hash_input({"step": args.step, "industry": args.industry, "slug": args.slug})

    # Check cache
    if not args.force:
        cached = load_checkpoint(args.step, args.slug, ih)
        if cached:
            print(f"[CACHE HIT] {args.step} (hash={ih})")
            print(json.dumps(cached, ensure_ascii=False, indent=2, default=str)[:2000])
            return

    # Run
    t0 = time.time()
    print(f"[RUN] {args.step} industry='{args.industry}'...")
    result = await STEPS[args.step](provider, params)
    elapsed = time.time() - t0

    # Save
    path = save_checkpoint(args.step, args.slug, ih, result, {
        "elapsed": round(elapsed, 1),
        "input_summary": f"industry={args.industry}",
    })
    print(f"[SAVED] {path} ({elapsed:.1f}s)")

    # Print summary
    s = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    out_path = os.path.join(os.path.dirname(__file__), f"{args.step}_output.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(s)
    print(f"[OUTPUT] {out_path} ({len(s)} chars)")

if __name__ == "__main__":
    asyncio.run(main())
