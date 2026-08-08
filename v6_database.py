"""
v6_database.py — V6 Master Pro | SQLite + JSON Fallback
Replit-safe: uses pysqlite3 first, falls back to sqlite3, then JSON.
"""
import os
import json
import time
import threading

_DB_PATH = "v6_master.db"
_JSON_DIR = "v6_db_fallback"
_lock = threading.Lock()

# ══════════════════════════════════════════════════════════════════════════════
# SQLITE DRIVER SELECTION (Replit-safe)
# ══════════════════════════════════════════════════════════════════════════════

_sqlite = None
_sqlite_ok = False

def _init_sqlite_driver():
    global _sqlite, _sqlite_ok
    try:
        import pysqlite3 as sqlite3
        _sqlite = sqlite3
        _sqlite_ok = True
        print("[V6 DB] Using pysqlite3 (Replit-compatible)")
        return
    except Exception:
        pass
    try:
        import sqlite3
        sqlite3.connect(":memory:").execute("SELECT 1").close()
        _sqlite = sqlite3
        _sqlite_ok = True
        print("[V6 DB] Using built-in sqlite3")
        return
    except Exception as e:
        print(f"[V6 DB] WARNING: sqlite3 import failed -- {e}")
        print("[V6 DB] FALLBACK MODE: using JSON files instead of SQLite")
        _sqlite_ok = False

_init_sqlite_driver()


def _ensure_json_dir():
    if not os.path.exists(_JSON_DIR):
        os.makedirs(_JSON_DIR, exist_ok=True)

def _json_path(table: str) -> str:
    _ensure_json_dir()
    return os.path.join(_JSON_DIR, f"{table}.json")

def _json_load(table: str, default=None):
    path = _json_path(table)
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else []

def _json_save(table: str, data):
    _ensure_json_dir()
    path = _json_path(table)
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[V6 DB] JSON save failed for {table}: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# SCHEMA
# ══════════════════════════════════════════════════════════════════════════════

_TABLES = {
    "paper_trades": """
        CREATE TABLE IF NOT EXISTS paper_trades (
            id TEXT PRIMARY KEY, symbol TEXT, side TEXT, strategy TEXT,
            amount_usdt REAL, price REAL, qty REAL, mode TEXT,
            manual INTEGER, reason TEXT, status TEXT, time TEXT
        )
    """,
    "whale_copy_trades": """
        CREATE TABLE IF NOT EXISTS whale_copy_trades (
            id TEXT PRIMARY KEY, symbol TEXT, direction TEXT, entry_price REAL,
            wall_price REAL, wall_size_usdt REAL, wall_qty REAL, stop_loss REAL,
            original_sl REAL, trailing TEXT, target REAL, obi REAL,
            obi_velocity REAL, confidence REAL, funding_rate REAL, liq_status TEXT,
            eta TEXT, entry_time TEXT, entry_ts REAL, mode TEXT, status TEXT,
            exit_price REAL, exit_time TEXT, result TEXT, pnl_pct REAL
        )
    """,
    "backtest_signals": """
        CREATE TABLE IF NOT EXISTS backtest_signals (
            id TEXT PRIMARY KEY, symbol TEXT, folder TEXT, entry_price REAL,
            entry_time TEXT, entry_ts REAL, tp1 REAL, tp2 REAL, tp3 REAL,
            stop_loss REAL, original_sl REAL, trailing TEXT, traffic TEXT,
            reason TEXT, confidence INTEGER, status TEXT, tp1_hit INTEGER,
            tp2_hit INTEGER, tp3_hit INTEGER, sl_hit INTEGER, exit_price REAL,
            exit_time TEXT, result TEXT, pnl_pct REAL, score_breakdown TEXT, price_source TEXT
        )
    """,
    "api_keys": """
        CREATE TABLE IF NOT EXISTS api_keys (
            exchange TEXT PRIMARY KEY, api_key TEXT, secret_key TEXT, passphrase TEXT
        )
    """,
    "clients": """
        CREATE TABLE IF NOT EXISTS clients (
            name TEXT PRIMARY KEY, uid TEXT, password TEXT, status TEXT,
            expiry TEXT, sig_limit TEXT, role TEXT, added TEXT
        )
    """,
    "holdings": """
        CREATE TABLE IF NOT EXISTS holdings (
            symbol TEXT PRIMARY KEY, quantity REAL, buy_price REAL,
            target_pct REAL, added TEXT
        )
    """,
    "learning_data": """
        CREATE TABLE IF NOT EXISTS learning_data (key TEXT PRIMARY KEY, value TEXT)
    """,
    "price_alerts": """
        CREATE TABLE IF NOT EXISTS price_alerts (
            id INTEGER PRIMARY KEY, symbol TEXT, target_price REAL,
            direction TEXT, note TEXT, created_at TEXT
        )
    """,
}

# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def init_db():
    if not _sqlite_ok:
        return
    with _lock:
        conn = _sqlite.connect(_DB_PATH)
        c = conn.cursor()
        for sql in _TABLES.values():
            c.execute(sql)
        conn.commit()
        conn.close()

def get_db():
    if not _sqlite_ok:
        return None
    return _sqlite.connect(_DB_PATH)


def _db_to_json(conn, table: str):
    c = conn.cursor()
    c.execute(f"SELECT * FROM {table}")
    cols = [d[0] for d in c.description]
    return [dict(zip(cols, row)) for row in c.fetchall()]


# ── paper_trades ─────────────────────────────────────────────────────────────

def save_paper_trades(data: list):
    if _sqlite_ok:
        with _lock:
            conn = get_db()
            c = conn.cursor()
            c.execute("DELETE FROM paper_trades")
            conn.commit()
            for row in data[-500:]:
                c.execute("""
                    INSERT OR REPLACE INTO paper_trades
                    (id, symbol, side, strategy, amount_usdt, price, qty, mode, manual, reason, status, time)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    row.get("id"), row.get("symbol"), row.get("side"), row.get("strategy"),
                    row.get("amount_usdt"), row.get("price"), row.get("qty"), row.get("mode"),
                    1 if row.get("manual") else 0, row.get("reason"), row.get("status"), row.get("time")
                ))
            conn.commit()
            conn.close()
    _json_save("paper_trades", data[-500:])

def load_paper_trades() -> list:
    if _sqlite_ok:
        try:
            with _lock:
                conn = get_db()
                rows = _db_to_json(conn, "paper_trades")
                conn.close()
                if rows:
                    for r in rows:
                        r["manual"] = bool(r.get("manual"))
                    return rows
        except Exception as e:
            print(f"[V6 DB] SQLite load paper_trades failed: {e}")
    return _json_load("paper_trades", [])


# ── whale_copy_trades ────────────────────────────────────────────────────────

def save_whale_copy_trades(data: list):
    if _sqlite_ok:
        with _lock:
            conn = get_db()
            c = conn.cursor()
            c.execute("DELETE FROM whale_copy_trades")
            conn.commit()
            for row in data[-500:]:
                c.execute("""
                    INSERT OR REPLACE INTO whale_copy_trades
                    (id, symbol, direction, entry_price, wall_price, wall_size_usdt, wall_qty,
                     stop_loss, original_sl, trailing, target, obi, obi_velocity, confidence,
                     funding_rate, liq_status, eta, entry_time, entry_ts, mode, status,
                     exit_price, exit_time, result, pnl_pct, score_breakdown, price_source)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    row.get("id"), row.get("symbol"), row.get("direction"), row.get("entry_price"),
                    row.get("wall_price"), row.get("wall_size_usdt"), row.get("wall_qty"),
                    row.get("stop_loss"), row.get("original_sl"), row.get("trailing"), row.get("target"),
                    row.get("obi"), row.get("obi_velocity"), row.get("confidence"), row.get("funding_rate"),
                    row.get("liq_status"), row.get("eta"), row.get("entry_time"), row.get("entry_ts"),
                    row.get("mode"), row.get("status"), row.get("exit_price"), row.get("exit_time"),
                    row.get("result"), row.get("pnl_pct"), row.get("score_breakdown"), row.get("price_source")
                ))
            conn.commit()
            conn.close()
    _json_save("whale_copy_trades", data[-500:])

def load_whale_copy_trades() -> list:
    if _sqlite_ok:
        try:
            with _lock:
                conn = get_db()
                rows = _db_to_json(conn, "whale_copy_trades")
                conn.close()
                if rows:
                    return rows
        except Exception as e:
            print(f"[V6 DB] SQLite load whale_copy_trades failed: {e}")
    return _json_load("whale_copy_trades", [])


# ── backtest_signals ─────────────────────────────────────────────────────────

def save_backtest_signals(data: list):
    if _sqlite_ok:
        with _lock:
            conn = get_db()
            c = conn.cursor()
            c.execute("DELETE FROM backtest_signals")
            conn.commit()
            for row in data[-100:]:
                c.execute("""
                    INSERT OR REPLACE INTO backtest_signals
                    (id, symbol, folder, entry_price, entry_time, entry_ts, tp1, tp2, tp3,
                     stop_loss, original_sl, trailing, traffic, reason, confidence, status,
                     tp1_hit, tp2_hit, tp3_hit, sl_hit, exit_price, exit_time, result, pnl_pct)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    row.get("id"), row.get("symbol"), row.get("folder"), row.get("entry_price"),
                    row.get("entry_time"), row.get("entry_ts"), row.get("tp1"), row.get("tp2"), row.get("tp3"),
                    row.get("stop_loss"), row.get("original_sl"), row.get("trailing"), row.get("traffic"),
                    row.get("reason"), row.get("confidence"), row.get("status"),
                    1 if row.get("tp1_hit") else 0, 1 if row.get("tp2_hit") else 0,
                    1 if row.get("tp3_hit") else 0, 1 if row.get("sl_hit") else 0,
                    row.get("exit_price"), row.get("exit_time"), row.get("result"), row.get("pnl_pct")
                ))
            conn.commit()
            conn.close()
    _json_save("backtest_signals", data[-100:])

def load_backtest_signals() -> list:
    if _sqlite_ok:
        try:
            with _lock:
                conn = get_db()
                rows = _db_to_json(conn, "backtest_signals")
                conn.close()
                if rows:
                    for r in rows:
                        for k in ("tp1_hit", "tp2_hit", "tp3_hit", "sl_hit"):
                            r[k] = bool(r.get(k))
                    return rows
        except Exception as e:
            print(f"[V6 DB] SQLite load backtest_signals failed: {e}")
    return _json_load("backtest_signals", [])


# ── api_keys ─────────────────────────────────────────────────────────────────

def save_api_keys(data: dict):
    if _sqlite_ok:
        with _lock:
            conn = get_db()
            c = conn.cursor()
            c.execute("DELETE FROM api_keys")
            conn.commit()
            for ex, k in data.items():
                c.execute("""
                    INSERT OR REPLACE INTO api_keys (exchange, api_key, secret_key, passphrase)
                    VALUES (?,?,?,?)
                """, (ex, k.get("api_key"), k.get("secret_key"), k.get("passphrase")))
            conn.commit()
            conn.close()
    _json_save("api_keys", data)

def load_api_keys() -> dict:
    if _sqlite_ok:
        try:
            with _lock:
                conn = get_db()
                rows = _db_to_json(conn, "api_keys")
                conn.close()
                if rows:
                    return {r["exchange"]: r for r in rows}
        except Exception as e:
            print(f"[V6 DB] SQLite load api_keys failed: {e}")
    return _json_load("api_keys", {})


# ── clients ──────────────────────────────────────────────────────────────────

def save_clients(data: list):
    if _sqlite_ok:
        with _lock:
            conn = get_db()
            c = conn.cursor()
            c.execute("DELETE FROM clients")
            conn.commit()
            for row in data:
                c.execute("""
                    INSERT OR REPLACE INTO clients
                    (name, uid, password, status, expiry, sig_limit, role, added)
                    VALUES (?,?,?,?,?,?,?,?)
                """, (
                    row.get("name"), row.get("uid"), row.get("password"), row.get("status"),
                    row.get("expiry"), row.get("sig_limit"), row.get("role"), row.get("added")
                ))
            conn.commit()
            conn.close()
    _json_save("clients", data)

def load_clients() -> list:
    if _sqlite_ok:
        try:
            with _lock:
                conn = get_db()
                rows = _db_to_json(conn, "clients")
                conn.close()
                if rows:
                    return rows
        except Exception as e:
            print(f"[V6 DB] SQLite load clients failed: {e}")
    return _json_load("clients", [])


# ── holdings ─────────────────────────────────────────────────────────────────

def save_holdings(data: list):
    if _sqlite_ok:
        with _lock:
            conn = get_db()
            c = conn.cursor()
            c.execute("DELETE FROM holdings")
            conn.commit()
            for row in data:
                c.execute("""
                    INSERT OR REPLACE INTO holdings
                    (symbol, quantity, buy_price, target_pct, added)
                    VALUES (?,?,?,?,?)
                """, (
                    row.get("symbol"), row.get("quantity"), row.get("buy_price"),
                    row.get("target_pct"), row.get("added")
                ))
            conn.commit()
            conn.close()
    _json_save("holdings", data)

def load_holdings() -> list:
    if _sqlite_ok:
        try:
            with _lock:
                conn = get_db()
                rows = _db_to_json(conn, "holdings")
                conn.close()
                if rows:
                    return rows
        except Exception as e:
            print(f"[V6 DB] SQLite load holdings failed: {e}")
    return _json_load("holdings", [])


# ── learning_data ────────────────────────────────────────────────────────────

def save_learning_data(data: dict):
    if _sqlite_ok:
        with _lock:
            conn = get_db()
            c = conn.cursor()
            c.execute("DELETE FROM learning_data")
            conn.commit()
            for k, v in data.items():
                c.execute("INSERT OR REPLACE INTO learning_data (key, value) VALUES (?,?)",
                          (k, json.dumps(v)))
            conn.commit()
            conn.close()
    _json_save("learning_data", data)

def load_learning_data() -> dict:
    if _sqlite_ok:
        try:
            with _lock:
                conn = get_db()
                c = conn.cursor()
                c.execute("SELECT key, value FROM learning_data")
                rows = {k: json.loads(v) for k, v in c.fetchall()}
                conn.close()
                if rows:
                    return rows
        except Exception as e:
            print(f"[V6 DB] SQLite load learning_data failed: {e}")
    return _json_load("learning_data", {})


# ── price_alerts ─────────────────────────────────────────────────────────────

def save_price_alerts(data: list):
    if _sqlite_ok:
        with _lock:
            conn = get_db()
            c = conn.cursor()
            c.execute("DELETE FROM price_alerts")
            conn.commit()
            for row in data:
                c.execute("""
                    INSERT OR REPLACE INTO price_alerts
                    (id, symbol, target_price, direction, note, created_at)
                    VALUES (?,?,?,?,?,?)
                """, (
                    row.get("id"), row.get("symbol"), row.get("target_price"),
                    row.get("direction"), row.get("note"), row.get("created_at")
                ))
            conn.commit()
            conn.close()
    _json_save("price_alerts", data)

def load_price_alerts() -> list:
    if _sqlite_ok:
        try:
            with _lock:
                conn = get_db()
                rows = _db_to_json(conn, "price_alerts")
                conn.close()
                if rows:
                    return rows
        except Exception as e:
            print(f"[V6 DB] SQLite load price_alerts failed: {e}")
    return _json_load("price_alerts", [])


# ── DB Status ────────────────────────────────────────────────────────────────

def db_status() -> dict:
    if _sqlite_ok and os.path.exists(_DB_PATH):
        size = os.path.getsize(_DB_PATH)
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {t[0]: 0 for t in c.fetchall()}
        for t in tables:
            c.execute(f"SELECT COUNT(*) FROM {t}")
            tables[t] = c.fetchone()[0]
        conn.close()
        return {"db_path": _DB_PATH, "db_size_bytes": size, "tables": tables, "driver": "sqlite"}
    else:
        _ensure_json_dir()
        files = os.listdir(_JSON_DIR) if os.path.exists(_JSON_DIR) else []
        return {
            "db_path": _JSON_DIR,
            "db_size_bytes": sum(os.path.getsize(os.path.join(_JSON_DIR, f)) for f in files),
            "tables": {f.replace(".json", ""): len(_json_load(f.replace(".json", ""), [])) for f in files},
            "driver": "json-fallback",
        }
