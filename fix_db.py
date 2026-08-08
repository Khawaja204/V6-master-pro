#!/usr/bin/env python3
"""
fix_db.py — Standalone DB migration script
Run: python3 fix_db.py
"""
import sqlite3
import os

DB_PATH = "v6_master.db"

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"[OK] Database file '{DB_PATH}' does not exist yet.")
        print("     Fresh DB will be created automatically on next app start.")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Check if backtest_signals table exists
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='backtest_signals'")
    if not c.fetchone():
        print("[OK] Table 'backtest_signals' does not exist yet.")
        print("     It will be created with latest schema on next app start.")
        conn.close()
        return

    # Check existing columns
    c.execute("PRAGMA table_info(backtest_signals)")
    existing = {row[1] for row in c.fetchall()}

    migrations = [
        ("score_breakdown", "ALTER TABLE backtest_signals ADD COLUMN score_breakdown TEXT"),
        ("price_source",    "ALTER TABLE backtest_signals ADD COLUMN price_source TEXT DEFAULT 'rest_scan'"),
    ]

    migrated = 0
    for col, sql in migrations:
        if col in existing:
            print(f"[OK] Column '{col}' already exists.")
        else:
            try:
                c.execute(sql)
                migrated += 1
                print(f"[FIXED] Added missing column: '{col}'")
            except Exception as e:
                print(f"[ERROR] Failed to add '{col}': {e}")

    conn.commit()
    conn.close()

    if migrated:
        print(f"\n✅ Migration complete! {migrated} column(s) added.")
    else:
        print("\n✅ Schema already up-to-date. No changes needed.")

    # Show current columns
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("PRAGMA table_info(backtest_signals)")
    print("\nCurrent 'backtest_signals' columns:")
    for row in c.fetchall():
        print(f"  - {row[1]} ({row[2]})")
    conn.close()

if __name__ == "__main__":
    migrate()
