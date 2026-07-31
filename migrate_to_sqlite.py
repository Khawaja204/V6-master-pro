#!/usr/bin/env python3
import json
import os
import shutil
try:
    from pysqlite3 import dbapi2 as sqlite3
except ImportError:
    import sqlite3
from v6_database import (
    init_db, save_paper_trades, save_whale_copy_trades,
    save_backtest_signals, save_learning_data, save_api_keys,
    save_holdings, save_clients, save_wc_learning,
    load_paper_trades, load_backtest_signals, DB_PATH
)

FILES = {
    "paper_trades": "paper_trades.json",
    "whale_copy_trades": "whale_copy_trades.json",
    "backtest_signals": "backtest_signals.json",
    "learning_data": "learning_data.json",
    "api_keys": "api_keys.json",
    "holdings": "holdings.json",
    "clients": "clients.json",
    "whale_copy_learning": "whale_copy_learning.json",
}

def backup_json():
    for name, fname in FILES.items():
        if os.path.exists(fname):
            shutil.copy2(fname, fname + ".bak")
            print(f"  Backed up {fname} -> {fname}.bak")

def migrate():
    print("=" * 50)
    print("  V6 Master Pro — JSON to SQLite Migration")
    print("=" * 50)
    print(f"\n  DB path: {DB_PATH}")
    print("\n  [1/3] Backing up JSON files...")
    backup_json()
    print("\n  [2/3] Initializing SQLite database...")
    init_db()
    print("\n  [3/3] Migrating data...")
    total = 0

    if os.path.exists(FILES["paper_trades"]):
        with open(FILES["paper_trades"]) as f:
            data = json.load(f)
        if isinstance(data, list):
            save_paper_trades(data)
            print(f"    paper_trades: {len(data)} rows")
            total += len(data)

    if os.path.exists(FILES["whale_copy_trades"]):
        with open(FILES["whale_copy_trades"]) as f:
            data = json.load(f)
        if isinstance(data, list):
            save_whale_copy_trades(data)
            print(f"    whale_copy_trades: {len(data)} rows")
            total += len(data)

    if os.path.exists(FILES["backtest_signals"]):
        with open(FILES["backtest_signals"]) as f:
            data = json.load(f)
        if isinstance(data, list):
            save_backtest_signals(data)
            print(f"    backtest_signals: {len(data)} rows")
            total += len(data)

    if os.path.exists(FILES["learning_data"]):
        with open(FILES["learning_data"]) as f:
            data = json.load(f)
        if isinstance(data, dict):
            save_learning_data(data)
            print(f"    learning_data: {len(data)} keys")
            total += 1

    if os.path.exists(FILES["api_keys"]):
        with open(FILES["api_keys"]) as f:
            data = json.load(f)
        if isinstance(data, dict):
            save_api_keys(data)
            print(f"    api_keys: {len(data)} exchanges")
            total += len(data)

    if os.path.exists(FILES["holdings"]):
        with open(FILES["holdings"]) as f:
            data = json.load(f)
        if isinstance(data, list):
            save_holdings(data)
            print(f"    holdings: {len(data)} rows")
            total += len(data)

    if os.path.exists(FILES["clients"]):
        with open(FILES["clients"]) as f:
            data = json.load(f)
        if isinstance(data, list):
            save_clients(data)
            print(f"    clients: {len(data)} rows")
            total += len(data)

    if os.path.exists(FILES["whale_copy_learning"]):
        with open(FILES["whale_copy_learning"]) as f:
            data = json.load(f)
        if isinstance(data, dict):
            save_wc_learning(data)
            print(f"    whale_copy_learning: {len(data)} keys")
            total += 1

    pt = load_paper_trades()
    bt = load_backtest_signals()
    print(f"\n  Verification: {len(pt)} paper trades, {len(bt)} backtest signals loaded from DB")
    print(f"\n  Migration complete! {total} total records migrated.")
    print("=" * 50)

if __name__ == "__main__":
    migrate()
