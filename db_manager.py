"""
db_manager.py — V6 Master Pro SQLite Layer (P0)
Replaces all JSON file I/O with SQLite.
Usage: from db_manager import *
"""
import sqlite3
import json
import time
import os
from threading import Lock

DB_PATH = os.getenv("V6_DB_PATH", "v6_master.db")
_lock = Lock()

def _conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with _conn() as conn:
        conn.executescript(open("schema.sql").read() if os.path.exists("schema.sql") else _SCHEMA)
        conn.commit()
    return True

_SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_trades (
    id TEXT PRIMARY KEY, symbol TEXT, side TEXT, strategy TEXT,
    amount_usdt REAL, price REAL, qty REAL, mode TEXT, manual INTEGER,
    reason TEXT, status TEXT, time TEXT, pnl_pct REAL,
    exit_price REAL, exit_time TEXT
);
CREATE TABLE IF NOT EXISTS backtest_signals (
    id TEXT PRIMARY KEY, symbol TEXT, folder TEXT, entry_price REAL,
    entry_time TEXT, entry_ts REAL, tp1 REAL, tp2 REAL, tp3 REAL,
    stop_loss REAL, original_sl REAL, trailing TEXT, traffic TEXT,
    reason TEXT, confidence INTEGER, status TEXT,
    tp1_hit INTEGER, tp2_hit INTEGER, tp3_hit INTEGER, sl_hit INTEGER,
    exit_price REAL, exit_time TEXT, result TEXT, pnl_pct REAL
);
CREATE TABLE IF NOT EXISTS api_keys (
    exchange TEXT PRIMARY KEY, api_key TEXT, secret_key TEXT,
    passphrase TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS clients (
    name TEXT PRIMARY KEY, uid TEXT, password TEXT, status TEXT,
    expiry TEXT, sig_limit TEXT, role TEXT, added TEXT
);
CREATE TABLE IF NOT EXISTS holdings (
    symbol TEXT PRIMARY KEY, quantity REAL, buy_price REAL,
    target_pct REAL, added TEXT
);
CREATE TABLE IF NOT EXISTS learning_data (
    key TEXT PRIMARY KEY, value TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS whale_copy_trades (
    id TEXT PRIMARY KEY, symbol TEXT, direction TEXT, entry_price REAL,
    wall_price REAL, wall_size_usdt REAL, wall_qty REAL, stop_loss REAL,
    original_sl REAL, trailing TEXT, target REAL, obi REAL,
    obi_velocity REAL, confidence REAL, funding_rate REAL,
    liq_status TEXT, eta TEXT, entry_time TEXT, entry_ts REAL,
    mode TEXT, status TEXT, exit_price REAL, exit_time TEXT,
    result TEXT, pnl_pct REAL
);
CREATE TABLE IF NOT EXISTS price_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT,
    target_price REAL, direction TEXT, note TEXT, created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_bt_symbol ON backtest_signals(symbol);
CREATE INDEX IF NOT EXISTS idx_bt_status ON backtest_signals(status);
CREATE INDEX IF NOT EXISTS idx_pt_symbol ON paper_trades(symbol);
CREATE INDEX IF NOT EXISTS idx_wct_symbol ON whale_copy_trades(symbol);
"""

# ── Paper Trades ──
def load_paper_trades(limit=500):
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM paper_trades ORDER BY time DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

def save_paper_trade(trade: dict):
    cols = ["id","symbol","side","strategy","amount_usdt","price","qty",
            "mode","manual","reason","status","time","pnl_pct","exit_price","exit_time"]
    vals = [trade.get(c, 0 if c in ["manual"] else "") for c in cols]
    with _lock:
        with _conn() as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO paper_trades ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})",
                vals
            )
            conn.commit()

# ── Backtest Signals ──
def load_backtest_signals(limit=100):
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM backtest_signals ORDER BY entry_ts DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

def save_backtest_signal(sig: dict):
    cols = ["id","symbol","folder","entry_price","entry_time","entry_ts",
            "tp1","tp2","tp3","stop_loss","original_sl","trailing","traffic",
            "reason","confidence","status","tp1_hit","tp2_hit","tp3_hit","sl_hit",
            "exit_price","exit_time","result","pnl_pct"]
    vals = [sig.get(c, 0 if c in ["tp1_hit","tp2_hit","tp3_hit","sl_hit","confidence"] else "") for c in cols]
    with _lock:
        with _conn() as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO backtest_signals ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})",
                vals
            )
            conn.commit()

# ── API Keys ──
def load_api_keys() -> dict:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM api_keys").fetchall()
        return {r["exchange"]: dict(r) for r in rows}

def save_api_key(exchange: str, api_key: str, secret_key: str, passphrase: str = ""):
    with _lock:
        with _conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO api_keys (exchange,api_key,secret_key,passphrase,updated_at) VALUES (?,?,?,?,?)",
                (exchange, api_key, secret_key, passphrase, time.strftime("%Y-%m-%d %H:%M:%S"))
            )
            conn.commit()

# ── Clients ──
def load_clients() -> list:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM clients").fetchall()
        return [dict(r) for r in rows]

def save_client(client: dict):
    cols = ["name","uid","password","status","expiry","sig_limit","role","added"]
    vals = [client.get(c, "") for c in cols]
    with _lock:
        with _conn() as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO clients ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})",
                vals
            )
            conn.commit()

def delete_client(name: str):
    with _lock:
        with _conn() as conn:
            conn.execute("DELETE FROM clients WHERE name=?", (name,))
            conn.commit()

# ── Holdings ──
def load_holdings() -> list:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM holdings").fetchall()
        return [dict(r) for r in rows]

def save_holding(h: dict):
    with _lock:
        with _conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO holdings (symbol,quantity,buy_price,target_pct,added) VALUES (?,?,?,?,?)",
                (h.get("symbol"), h.get("quantity"), h.get("buy_price"), h.get("target_pct"), h.get("added"))
            )
            conn.commit()

def delete_holding(symbol: str):
    with _lock:
        with _conn() as conn:
            conn.execute("DELETE FROM holdings WHERE symbol=?", (symbol,))
            conn.commit()

# ── Whale Copy Trades ──
def load_whale_copy_trades(limit=500):
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM whale_copy_trades ORDER BY entry_ts DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

def save_whale_copy_trade(trade: dict):
    cols = ["id","symbol","direction","entry_price","wall_price","wall_size_usdt",
            "wall_qty","stop_loss","original_sl","trailing","target","obi",
            "obi_velocity","confidence","funding_rate","liq_status","eta",
            "entry_time","entry_ts","mode","status","exit_price","exit_time","result","pnl_pct"]
    vals = [trade.get(c, "") for c in cols]
    with _lock:
        with _conn() as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO whale_copy_trades ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})",
                vals
            )
            conn.commit()

# ── Learning Data ──
def load_learning_data() -> dict:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM learning_data").fetchall()
        out = {}
        for r in rows:
            try:
                out[r["key"]] = json.loads(r["value"])
            except Exception:
                out[r["key"]] = r["value"]
        return out

def save_learning_data(data: dict):
    with _lock:
        with _conn() as conn:
            conn.execute("DELETE FROM learning_data")
            for k, v in data.items():
                conn.execute(
                    "INSERT INTO learning_data (key,value,updated_at) VALUES (?,?,?)",
                    (k, json.dumps(v), time.strftime("%Y-%m-%d %H:%M:%S"))
                )
            conn.commit()

# ── Price Alerts ──
def load_price_alerts() -> list:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM price_alerts ORDER BY id").fetchall()
        return [dict(r) for r in rows]

def save_price_alert(alert: dict):
    with _lock:
        with _conn() as conn:
            if alert.get("id"):
                conn.execute(
                    "UPDATE price_alerts SET symbol=?,target_price=?,direction=?,note=?,created_at=? WHERE id=?",
                    (alert["symbol"], alert["target_price"], alert["direction"], alert.get("note",""), alert.get("created_at",""), alert["id"])
                )
            else:
                conn.execute(
                    "INSERT INTO price_alerts (symbol,target_price,direction,note,created_at) VALUES (?,?,?,?,?)",
                    (alert["symbol"], alert["target_price"], alert["direction"], alert.get("note",""), alert.get("created_at",""))
                )
            conn.commit()

def delete_price_alert(aid: int):
    with _lock:
        with _conn() as conn:
            conn.execute("DELETE FROM price_alerts WHERE id=?", (aid,))
            conn.commit()

# ── Init on import ──
if not os.path.exists(DB_PATH):
    init_db()
