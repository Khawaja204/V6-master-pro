"""
migrate_to_sqlite.py — V6 Master Pro | One-time JSON -> SQLite migration
Reads existing *.json state files and writes them via v6_database.py's
own save_* functions (schema-correct). Safe to re-run (idempotent).
"""
import json
from v6_database import (
    init_db, save_paper_trades, save_whale_copy_trades, save_backtest_signals,
    save_api_keys, save_clients, save_holdings, save_learning_data, db_status,
)

def _load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"[SKIP] {path}: {e}")
        return default

def migrate():
    init_db()

    bt = _load_json("backtest_signals.json", [])
    if bt:
        save_backtest_signals(bt)
        print(f"Migrated {len(bt)} backtest signals")

    pt = _load_json("paper_trades.json", [])
    if pt:
        save_paper_trades(pt)
        print(f"Migrated {len(pt)} paper trades")

    wct = _load_json("whale_copy_trades.json", [])
    if wct:
        save_whale_copy_trades(wct)
        print(f"Migrated {len(wct)} whale copy trades")

    keys = _load_json("api_keys.json", {})
    if keys:
        try:
            from v6_crypto import encrypt
            enc = {}
            for ex, k in keys.items():
                enc[ex] = {
                    "api_key":    encrypt(k.get("api_key", "")),
                    "secret_key": encrypt(k.get("secret_key", "")),
                }
                if k.get("passphrase"):
                    enc[ex]["passphrase"] = encrypt(k["passphrase"])
            save_api_keys(enc)
            print(f"Migrated {len(keys)} API keys (encrypted)")
        except Exception as e:
            print(f"[WARN] api_keys migration failed: {e}")

    clients = _load_json("clients.json", [])
    if clients:
        save_clients(clients)
        print(f"Migrated {len(clients)} clients")

    holdings = _load_json("holdings.json", [])
    if holdings:
        save_holdings(holdings)
        print(f"Migrated {len(holdings)} holdings")

    ld = _load_json("learning_data.json", {})
    if ld:
        save_learning_data(ld)
        print("Migrated learning data")

    print("\nMigration complete!")
    print(db_status())

if __name__ == "__main__":
    migrate()
