import asyncio
import sys
import os

# 确保能导入 app 模块
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import engine, Base
from app.models.models import TaskDefinition, TaskExecution

async def init_db():
    print("[*] Connecting to database...")
    async with engine.begin() as conn:
        print("[*] Creating new Task tables (V5.0)...")
        await conn.run_sync(Base.metadata.create_all)
    print("[✅] Database V5.0 schema initialized successfully.")

if __name__ == "__main__":
    asyncio.run(init_db())
