"""
v6_database.py -- V6 Master Pro | SQLite Persistence Layer
Replaces JSON file storage with atomic SQLite operations.

FALLBACK: If sqlite3 fails to import (e.g. Replit Nix glibc mismatch),
          automatically falls back to JSON file storage so the bot
          never crashes on startup.
"""
import os
import json
import time
import threading
from typing import Any

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "v6_master.db")
_db_lock = threading.Lock()

# ── Try to import sqlite3; if it fails, use JSON fallback ──
try:
    import sqlite3
    _SQLITE_OK = True
except ImportError as _e:
    _SQLITE_OK = False
    print("[V6 DB] WARNING: sqlite3 import failed -- " + str(_e))
    print("[V6 DB] FALLBACK MODE: using JSON files instead of SQLite")


# ── JSON Fallback Helpers ──
_json_files = {
    "paper_trades":       "paper_trades.json",
    "whale_copy_trades":  "whale_copy_trades.json",
    "backtest_signals":   "backtest_signals.json",
    "api_keys":           "api_keys.json",
    "clients":            "clients.json",
    "holdings":           "holdings.json",
    "learning_data":      "learning_data.json",
    "price_alerts":       "price_alerts.json",
}


def _json_save(table: str, data: Any) -> None:
    fname = _json_files.get(table, table + ".json")
    try:
        with open(fname, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print("[V6 DB] JSON save failed for " + table + ": " + str(e))


def _json_load(table: str, default: Any = None) -> Any:
    fname = _json_files.get(table, table + ".json")
    try:
        if os.path.exists(fname):
            with open(fname) as f:
                return json.load(f)
    except Exception as e:
        print("[V6 DB] JSON load failed for " + table + ": " + str(e))
    return default


# ── SQLite Core (only if sqlite3 imported successfully) ──
if _SQLITE_OK:
    _TABLES = {
        "paper_trades":       "CREATE TABLE IF NOT EXISTS paper_trades (id INTEGER PRIMARY KEY, key TEXT UNIQUE, value TEXT, updated_at REAL)",
        "whale_copy_trades":  "CREATE TABLE IF NOT EXISTS whale_copy_trades (id INTEGER PRIMARY KEY, key TEXT UNIQUE, value TEXT, updated_at REAL)",
        "backtest_signals":   "CREATE TABLE IF NOT EXISTS backtest_signals (id INTEGER PRIMARY KEY, key TEXT UNIQUE, value TEXT, updated_at REAL)",
        "api_keys":           "CREATE TABLE IF NOT EXISTS api_keys (id INTEGER PRIMARY KEY, key TEXT UNIQUE, value TEXT, updated_at REAL)",
        "clients":            "CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY, key TEXT UNIQUE, value TEXT, updated_at REAL)",
        "holdings":           "CREATE TABLE IF NOT EXISTS holdings (id INTEGER PRIMARY KEY, key TEXT UNIQUE, value TEXT, updated_at REAL)",
        "learning_data":      "CREATE TABLE IF NOT EXISTS learning_data (id INTEGER PRIMARY KEY, key TEXT UNIQUE, value TEXT, updated_at REAL)",
        "price_alerts":       "CREATE TABLE IF NOT EXISTS price_alerts (id INTEGER PRIMARY KEY, key TEXT UNIQUE, value TEXT, updated_at REAL)",
    }

    def _conn():
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _sql_save(table: str, data: Any) -> None:
        with _db_lock:
            conn = _conn()
            try:
                conn.execute(
                    "INSERT INTO " + table + " (key, value, updated_at) VALUES (?, ?, ?)"
                    " ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                    ("default", json.dumps(data), time.time()),
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    def _sql_load(table: str, default: Any = None) -> Any:
        with _db_lock:
            conn = _conn()
            try:
                cur = conn.execute("SELECT value FROM " + table + " WHERE key = ?", ("default",))
                row = cur.fetchone()
                if row and row[0]:
                    return json.loads(row[0])
                return default
            except Exception:
                return default
            finally:
                conn.close()


# ── Unified API ──

def init_db() -> None:
    if not _SQLITE_OK:
        return
    with _db_lock:
        conn = _conn()
        for sql in _TABLES.values():
            conn.execute(sql)
        conn.commit()
        conn.close()


def get_db():
    if not _SQLITE_OK:
        return None
    return _conn()


# Choose backend
_save = _sql_save if _SQLITE_OK else _json_save
_load = _sql_load if _SQLITE_OK else _json_load


# ── Table-specific wrappers (exact names main.py expects) ──

def save_paper_trades(data: list) -> None:
    _save("paper_trades", data)

def load_paper_trades() -> list:
    return _load("paper_trades", default=[])


def save_whale_copy_trades(data: list) -> None:
    _save("whale_copy_trades", data)

def load_whale_copy_trades() -> list:
    return _load("whale_copy_trades", default=[])


def save_backtest_signals(data: list) -> None:
    _save("backtest_signals", data)

def load_backtest_signals() -> list:
    return _load("backtest_signals", default=[])


def save_api_keys(data: dict) -> None:
    _save("api_keys", data)

def load_api_keys() -> dict:
    return _load("api_keys", default={})


def save_clients(data: list) -> None:
    _save("clients", data)

def load_clients() -> list:
    return _load("clients", default=[])


def save_holdings(data: list) -> None:
    _save("holdings", data)

def load_holdings() -> list:
    return _load("holdings", default=[])


def save_learning_data(data: dict) -> None:
    _save("learning_data", data)

def load_learning_data(default: dict = None) -> dict:
    return _load("learning_data", default=default or {})


def save_price_alerts(data: list) -> None:
    _save("price_alerts", data)

def load_price_alerts() -> list:
    return _load("price_alerts", default=[])


# ── Admin diagnostics ──
def db_status() -> dict:
    if not _SQLITE_OK:
        return {
            "db_path": "N/A (JSON fallback mode)",
            "db_size_bytes": 0,
            "tables": {t: "JSON" for t in _json_files.keys()},
            "mode": "JSON_FALLBACK",
            "note": "sqlite3 import failed -- using JSON file storage",
        }
    with _db_lock:
        conn = _conn()
        try:
            tables = {}
            for name in _TABLES.keys():
                cur = conn.execute("SELECT COUNT(*) FROM " + name)
                tables[name] = cur.fetchone()[0]
            size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
            return {
                "db_path": DB_PATH,
                "db_size_bytes": size,
                "tables": tables,
                "mode": "SQLITE",
            }
        finally:
            conn.close()
