import importlib
import sys

dependencies = [
    "fastapi",
    "uvicorn",
    "pydantic",
    "pydantic_settings",
    "sqlalchemy",
    "sqlalchemy.ext.asyncio",
    "aiomysql",
    "pymysql",
    "loguru",
    "httpx",
    "pandas",
    "numpy",
    "dotenv", # python-dotenv
    "greenlet"
]

missing = []

print("--- AIStock_Pro Dependency Health Check ---")
for dep in dependencies:
    try:
        importlib.import_module(dep.split('.')[0] if '.' in dep else dep)
        # Special check for submodules
        if '.' in dep:
             importlib.import_module(dep)
        print(f"[OK] {dep}")
    except ImportError:
        print(f"[MISSING] {dep}")
        missing.append(dep)

if missing:
    print("\n--- ACTION REQUIRED ---")
    # Map module names to pip package names
    pkg_map = {
        "dotenv": "python-dotenv",
        "pydantic_settings": "pydantic-settings",
        "sqlalchemy.ext.asyncio": "sqlalchemy"
    }
    pip_pkgs = [pkg_map.get(m, m) for m in missing]
    print(f"Please run: pip install --upgrade --force-reinstall {' '.join(pip_pkgs)} -i https://pypi.tuna.tsinghua.edu.cn/simple")
else:
    print("\n[SUCCESS] All dependencies are ready!")
