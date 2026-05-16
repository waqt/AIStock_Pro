import asyncio
import os
import sys
from sqlalchemy import text

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(base_dir)

from dotenv import load_dotenv
load_dotenv(os.path.join(base_dir, ".env"))

from app.core.database import engine

async def check():
    print("\n--- POSITIONS TABLE SCHEMA ---")
    try:
        async with engine.connect() as conn:
            res = await conn.execute(text("DESCRIBE positions"))
            for row in res:
                print(f"Column: {row[0]} | Type: {row[1]} | Null: {row[2]}")
    except Exception as e:
        print(f"[ERROR] Failed to check schema: {e}")
    print("--- END ---\n")

if __name__ == "__main__":
    asyncio.run(check())
