"""Clean up temp_lab directories"""
import os, shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(ROOT, "..", "backend", "temp_lab")

# Root temp_lab: keep only current tools
root_keep = {
    "run_step.py", "test_step2_auto.py", "step2_auto_result.txt"
}
for fn in os.listdir(ROOT):
    fp = os.path.join(ROOT, fn)
    if os.path.isfile(fp) and fn not in root_keep and not fn.startswith("cleanup"):
        os.remove(fp)
        print(f"  RM root: {fn}")

# Backend temp_lab: keep valuable artifacts, remove old tests
bk_keep_prefix = ("chart_chip", "SOFC_", "sofc_", "CPU_", "chip_")
bk_keep_files = {"chip_result.txt", "decay_result.txt", "chip_compare.txt"}
for fn in os.listdir(BACKEND):
    fp = os.path.join(BACKEND, fn)
    if os.path.isdir(fp):
        if fn == "__pycache__":
            shutil.rmtree(fp)
            print(f"  RM backend/__pycache__")
        continue
    keep = fn.startswith(bk_keep_prefix) or fn in bk_keep_files
    if not keep:
        os.remove(fp)
        print(f"  RM backend: {fn}")

print("Done")
