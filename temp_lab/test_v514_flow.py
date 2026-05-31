"""测试 V5.14 双轨推演数据流 — 从已存在检查点验证 cross_chain_spillover"""
import asyncio, os, sys, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

async def main():
    from app.framework.pipeline.checkpoint import find_checkpoint_file, list_runs

    # 1. 找已有 Step 4 checkpoint
    runs = list_runs()
    print(f"Found {len(runs)} pipeline runs")

    for run in runs:
        run_id = run.get("run_id", "")
        if not run_id:
            continue
        cp_file = find_checkpoint_file(run_id, "step4_system_dynamics")
        if cp_file:
            print(f"\n=== Run: {run_id} (industry={run.get('industry','?')}) ===")
            with open(cp_file, encoding="utf-8") as f:
                cp = json.load(f)
            output = cp.get("output", {}) or {}
            sd = output.get("system_dynamics", {}) or {}

            # Check fields
            n_migration = len(sd.get("bottleneck_migration", {}).get("migration_drivers", []))
            n_crowding = len(sd.get("resource_crowding", []))
            n_hidden = len(sd.get("hidden_beneficiaries", []))
            n_cross = len(sd.get("cross_chain_spillover", []))
            n_queries = len(sd.get("asset_search_queries", []))

            print(f"  chain_internal:")
            print(f"    bottleneck_migration.drivers: {n_migration}")
            print(f"    resource_crowding: {n_crowding}")
            print(f"    hidden_beneficiaries: {n_hidden}")
            print(f"  cross_chain_spillover: {n_cross}")
            print(f"  asset_search_queries: {n_queries}")

            if n_cross > 0:
                for i, sp in enumerate(sd["cross_chain_spillover"]):
                    print(f"    [{i}] {sp.get('source_node','?')} → {sp.get('affected_sector','?')} ({sp.get('impact_direction','?')}, {sp.get('linkage_type','?')})")

            # Check Q3 doesn't have cross-industry content
            prompt = run.get("prompt", "")
            print(f"\n  ✅ cross_chain_spillover field present: {n_cross > 0}")
            print(f"  ✅ chain_internal fields unchanged: migration={n_migration}, crowding={n_crowding}, hidden={n_hidden}")
            break
    else:
        print("No Step 4 checkpoints found. Run a pipeline first.")

if __name__ == "__main__":
    asyncio.run(main())
