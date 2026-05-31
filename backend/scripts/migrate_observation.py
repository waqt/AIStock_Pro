"""回填脚本: 扫描已有 pipeline checkpoints, 提取观察事件写入 observations.db

用法:
    python scripts/migrate_observation.py                 # 全量回填
    python scripts/migrate_observation.py --dry-run       # 只统计, 不写入
    python scripts/migrate_observation.py --run 20260530_存储产业_v1  # 只处理指定 run
"""
import os, sys, json, argparse
from datetime import datetime

# 项目根目录
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.framework.pipeline.observation_store import ObservationStore, init_db
from app.domain.observation.services.extractor import STEP_EXTRACTORS


def scan_checkpoints(data_dir: str) -> list:
    """扫描 pipeline_checkpoints 目录, 返回所有检查点元信息"""
    checkpoints_dir = os.path.join(data_dir, "pipeline_checkpoints")
    if not os.path.isdir(checkpoints_dir):
        print(f"[ERROR] Checkpoints directory not found: {checkpoints_dir}")
        return []

    runs = []
    for run_name in sorted(os.listdir(checkpoints_dir)):
        run_dir = os.path.join(checkpoints_dir, run_name)
        if not os.path.isdir(run_dir):
            continue

        run_checkpoints = []
        for fname in os.listdir(run_dir):
            if not fname.endswith(".json") or fname.endswith(".trace.txt"):
                continue
            # 拆解文件名: step2_gatekeeper_a3493e7da541.json
            parts = fname.replace(".json", "").split("_")
            if len(parts) < 2:
                continue
            # 找 step 前缀
            step_candidates = [p for p in parts if p.startswith("step")]
            step = step_candidates[0] if step_candidates else ""
            run_checkpoints.append({
                "step": step,
                "filepath": os.path.join(run_dir, fname),
                "fname": fname,
            })

        if run_checkpoints:
            runs.append({
                "run_id": run_name,
                "dir": run_dir,
                "checkpoints": run_checkpoints,
            })

    return runs


def process_run(run_info: dict, dry_run: bool = False) -> int:
    """处理一个 run 的所有检查点, 返回提取的观察数量"""
    total = 0

    for cp in run_info["checkpoints"]:
        step_name = cp["step"]
        extractor = STEP_EXTRACTORS.get(step_name)
        if not extractor:
            continue

        try:
            with open(cp["filepath"], "r", encoding="utf-8") as f:
                checkpoint = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"  [SKIP] {cp['fname']}: {e}")
            continue

        output = checkpoint.get("output", {})
        if not output:
            continue

        saved_at = checkpoint.get("saved_at", datetime.now().isoformat())

        try:
            observations = extractor(output, run_info["run_id"], saved_at)
        except Exception as e:
            print(f"  [ERROR] {run_info['run_id']}/{step_name}: extract failed: {e}")
            continue

        if not observations:
            print(f"  [EMPTY] {run_info['run_id']}/{step_name}: 0 observations")
            continue

        if dry_run:
            print(f"  [DRY] {run_info['run_id']}/{step_name}: {len(observations)} observations (skipped)")
        else:
            try:
                store = ObservationStore()
                ids = store.save_batch(observations)
                print(f"  [OK] {run_info['run_id']}/{step_name}: {len(ids)} observations saved")
            except Exception as e:
                print(f"  [FAIL] {run_info['run_id']}/{step_name}: save failed: {e}")
                continue

        total += len(observations)

    return total


def main():
    parser = argparse.ArgumentParser(description="Backfill observations from pipeline checkpoints")
    parser.add_argument("--dry-run", action="store_true", help="Dry run: count only, no writes")
    parser.add_argument("--run", type=str, default=None, help="Process only a specific run_id")
    args = parser.parse_args()

    data_dir = os.path.join(ROOT, "data")
    print(f"Scanning {data_dir}/pipeline_checkpoints/ ...")

    all_runs = scan_checkpoints(data_dir)
    if not all_runs:
        print("No checkpoints found.")
        return

    print(f"Found {len(all_runs)} runs")

    if args.run:
        all_runs = [r for r in all_runs if r["run_id"] == args.run]
        if not all_runs:
            print(f"Run '{args.run}' not found.")
            return
        print(f"Filtered to 1 run: {args.run}")

    if not args.dry_run:
        init_db()
        print("Observation DB initialized.")

    grand_total = 0
    for run in all_runs:
        print(f"\n{'='*60}")
        print(f"Run: {run['run_id']}")
        print(f"Dir: {run['dir']}")
        print(f"Checkpoints: {len(run['checkpoints'])}")
        total = process_run(run, dry_run=args.dry_run)
        grand_total += total
        print(f"Subtotal: {total} observations")

    print(f"\n{'='*60}")
    print(f"Total: {grand_total} observations from {len(all_runs)} runs")
    if args.dry_run:
        print("(dry run — no data written)")
    else:
        print("Backfill complete. Run a query to verify:")
        print("  sqlite3 data/observations.db 'SELECT COUNT(*) FROM observations'")
        print("  sqlite3 data/observations.db 'SELECT source_step, COUNT(*) FROM observations GROUP BY source_step'")


if __name__ == "__main__":
    main()
