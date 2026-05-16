import pandas as pd
from sqlalchemy import create_engine
import pymysql

def migrate_data():
    # Database connections
    db_config = {
        'host': 'localhost',
        'user': 'gemini',
        'password': '123456'
    }
    
    old_db_uri = f"mysql+pymysql://{db_config['user']}:{db_config['password']}@{db_config['host']}/stock_portfolio_manager"
    new_db_uri = f"mysql+pymysql://{db_config['user']}:{db_config['password']}@{db_config['host']}/aistock_pro"
    
    old_engine = create_engine(old_db_uri)
    new_engine = create_engine(new_db_uri)
    
    print("[*] Starting data migration...")
    
    # 1. Migrate Positions
    try:
        print("[*] Migrating Positions...")
        # Read old positions
        df_pos = pd.read_sql("SELECT * FROM positions", old_engine)
        
        # Ensure column mapping if necessary (in this case they match)
        # Drop columns not in new schema if any
        # df_pos = df_pos[['stock_code', 'stock_name', ...]]
        
        # Write to new DB
        df_pos.to_sql('positions', new_engine, if_exists='append', index=False)
        print(f"[+] Migrated {len(df_pos)} positions.")
    except Exception as e:
        print(f"[-] Error migrating positions: {e}")

    # 2. Migrate Stocks (if any)
    try:
        print("[*] Migrating Stocks...")
        df_stocks = pd.read_sql("SELECT * FROM stocks", old_engine)
        df_stocks.to_sql('stocks', new_engine, if_exists='append', index=False)
        print(f"[+] Migrated {len(df_stocks)} stocks.")
    except Exception as e:
        print(f"[-] Error migrating stocks: {e} (Maybe table is empty or schema changed)")

    print("[+] Migration finished!")

if __name__ == "__main__":
    migrate_data()
