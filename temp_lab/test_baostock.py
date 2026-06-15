"""Check if baostock is available and test its industry query"""
import sys
try:
    import baostock as bs
    print("baostock found, version:", bs.__version__)
except ImportError:
    print("baostock not found")
    # Check what Chinese stock packages are available
    for mod in sorted(sys.modules.keys()):
        if "stock" in mod.lower() or "baostock" in mod.lower() or "tushare" in mod.lower():
            print("  related modules:", mod)
