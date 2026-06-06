"""Debug: check which SQLite DB has quality_detail data"""
import sqlite3
from pathlib import Path

# Root-level DB (where valuation store actually writes)
db_root = Path(__file__).parent.parent / 'data' / 'indicators.db'
conn = sqlite3.connect(str(db_root))
conn.row_factory = sqlite3.Row

tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print('Root DB tables:', [t[0] for t in tables])

row = conn.execute("SELECT quality_detail, adjusted_pe, quality_bonus_pct FROM valuation_metrics WHERE stock_code=? ORDER BY trade_date DESC LIMIT 1", ('002409',)).fetchone()
if row:
    print('Root DB quality_detail:', repr(row['quality_detail']))
    print('Root DB adjusted_pe:', row['adjusted_pe'])
    print('Root DB quality_bonus_pct:', row['quality_bonus_pct'])
else:
    print('No row for 002409 in root DB')

# Backend-level DB
db_bk = Path(__file__).parent.parent / 'backend' / 'data' / 'indicators.db'
if db_bk.exists():
    conn2 = sqlite3.connect(str(db_bk))
    conn2.row_factory = sqlite3.Row
    tables2 = conn2.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    all_names = [t[0] for t in tables2]
    val_names = [n for n in all_names if 'valuation' in n.lower()]
    print('Backend DB valuation tables:', val_names)
    print('Backend DB all tables:', all_names)
else:
    print('Backend DB does not exist:', db_bk)
