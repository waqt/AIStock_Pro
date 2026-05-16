import asyncio
import os
import sys

# 修正：将 backend 目录加入路径
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(base_dir)

# 强制加载环境配置
from dotenv import load_dotenv
load_dotenv(os.path.join(base_dir, ".env"))

from app.core.database import async_session
from app.models.models import TaskExecution
from sqlalchemy import update

async def force_cleanup():
    print("[*] Starting Cleanup (V5.0)...")
    try:
        async with async_session() as db:
            print("[*] Database connected. Updating status...")
            await db.execute(
                update(TaskExecution).where(TaskExecution.status.in_(["RUNNING", "PENDING", "STOPPING"])).values(
                    status="CANCELLED",
                    result_msg="[FORCE_RESET] Manual Cleanup Done"
                )
            )
            await db.commit()
            print("[SUCCESS] Ghost tasks cleared.")
    except Exception as e:
        print(f"[ERROR] Cleanup failed: {str(e)}")

if __name__ == "__main__":
    asyncio.run(force_cleanup())
