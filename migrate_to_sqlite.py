#!/usr/bin/env python3
"""
migrate_to_sqlite.py -- V6 Master Pro | JSON to SQLite One-Time Migration
Run: python3 migrate_to_sqlite.py
Migrates all existing JSON files into v6_master.db.
Safe to run multiple times (idempotent -- replaces existing rows).
"""
import os
import json
import sys

def migrate():
    try:
        from v6_database import init_db, _save
    except ImportError as e:
        print("ERROR: v6_database.py not found: " + str(e))
        sys.exit(1)

    init_db()
    print("OK: SQLite database initialized")

    mappings = {
        "paper_trades.json":       ("paper_trades", []),
        "whale_copy_trades.json":  ("whale_copy_trades", []),
        "backtest_signals.json":   ("backtest_signals", []),
        "api_keys.json":           ("api_keys", {}),
        "clients.json":            ("clients", []),
        "holdings.json":           ("holdings", []),
        "learning_data.json":      ("learning_data", {}),
    }

    migrated = 0
    for filename, (table, default) in mappings.items():
        filepath = os.path.join(os.path.dirname(__file__), filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                if data is None:
                    data = default
                _save(table, data)
                count = len(data) if isinstance(data, (list, dict)) else "blob"
                print("  OK: " + filename + " -> " + table + " (" + str(count) + ")")
                migrated += 1
            except Exception as e:
                print("  WARN: " + filename + " failed: " + str(e))
        else:
            print("  SKIP: " + filename + " not found")

    pa_file = "price_alerts.json"
    if os.path.exists(pa_file):
        try:
            with open(pa_file) as f:
                _save("price_alerts", json.load(f))
            print("  OK: " + pa_file + " -> price_alerts")
        except Exception as e:
            print("  WARN: " + pa_file + " failed: " + str(e))

    print("")
    print("Migration complete. " + str(migrated) + " file(s) migrated to v6_master.db")
    print("You can now safely delete the old .json files if desired.")
    print("Run 'db-status' (v6-cmd.sh) to verify.")

if __name__ == "__main__":
    migrate()
