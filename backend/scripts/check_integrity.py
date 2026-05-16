import os
import sys
import py_compile
import importlib.util

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(base_dir)

def check_files():
    print(f"[*] Starting project integrity check in: {base_dir}")
    error_count = 0
    
    # 遍历所有 py 文件
    for root, dirs, files in os.walk(os.path.join(base_dir, "app")):
        for file in files:
            if file.endswith(".py"):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, base_dir)
                
                # 1. 语法检查
                try:
                    py_compile.compile(full_path, doraise=True)
                except Exception as e:
                    print(f"[❌] Syntax Error in {rel_path}: {e}")
                    error_count += 1
                    continue
                
                # 2. 静态分析：检查是否存在 SessionLocal 关键字 (防止死灰复燃)
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if "SessionLocal" in content and "database.py" not in rel_path:
                        print(f"[⚠️] Legacy 'SessionLocal' found in {rel_path}")
                        error_count += 1

    if error_count == 0:
        print("[✅] All files passed integrity check.")
    else:
        print(f"[!] Total issues found: {error_count}")

if __name__ == "__main__":
    check_files()
