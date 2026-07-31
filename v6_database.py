"""
v6_database.py — V6 Master Pro SQLite Backend
"""
import json
import os
import threading
from typing import List, Dict, Any, Optional

# Replit fix: broken system sqlite3 -> use pysqlite3-binary
try:
    from pysqlite3 import dbapi2 as sqlite3
except ImportError:
    import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "v6_master.db")
_db_lock = threading.Lock()

def _get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with _db_lock:
        conn = _get_conn()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS paper_trades (
                id TEXT PRIMARY KEY, symbol TEXT, side TEXT, strategy TEXT,
                amount_usdt REAL, price REAL, qty REAL, mode TEXT, manual INTEGER,
                reason TEXT, status TEXT, time TEXT,
                created_ts REAL DEFAULT (strftime('%s','now'))
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS whale_copy_trades (
                id TEXT PRIMARY KEY, symbol TEXT, direction TEXT, entry_price REAL,
                wall_price REAL, wall_size_usdt REAL, wall_qty REAL, stop_loss REAL,
                original_sl REAL, trailing TEXT, target REAL, obi REAL,
                obi_velocity REAL, confidence REAL, funding_rate REAL,
                liq_status TEXT, eta TEXT, entry_time TEXT, entry_ts REAL,
                mode TEXT, status TEXT, exit_price REAL, exit_time TEXT,
                result TEXT, pnl_pct REAL,
                created_ts REAL DEFAULT (strftime('%s','now'))
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS backtest_signals (
                id TEXT PRIMARY KEY, symbol TEXT, folder TEXT, entry_price REAL,
                entry_time TEXT, entry_ts REAL, tp1 REAL, tp2 REAL, tp3 REAL,
                stop_loss REAL, original_sl REAL, trailing TEXT, traffic TEXT,
                reason TEXT, confidence INTEGER, status TEXT, tp1_hit INTEGER,
                tp2_hit INTEGER, tp3_hit INTEGER, sl_hit INTEGER, exit_price REAL,
                exit_time TEXT, result TEXT, pnl_pct REAL, learning_recorded INTEGER DEFAULT 0,
                created_ts REAL DEFAULT (strftime('%s','now'))
            )
        """)
        c.execute("CREATE TABLE IF NOT EXISTS learning_data (key TEXT PRIMARY KEY, value TEXT)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                exchange TEXT PRIMARY KEY, api_key TEXT, secret_key TEXT, passphrase TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS holdings (
                symbol TEXT PRIMARY KEY, quantity REAL, buy_price REAL,
                target_pct REAL, added TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                name TEXT PRIMARY KEY, uid TEXT, password TEXT, status TEXT,
                expiry TEXT, sig_limit TEXT, role TEXT, added TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS oco_orders (
                id TEXT PRIMARY KEY, symbol TEXT, side TEXT, amount_usdt REAL,
                limit_price REAL, stop_price REAL, stop_limit_price REAL,
                tp_price REAL, status TEXT DEFAULT 'PENDING', exchange TEXT,
                created_at TEXT, updated_at TEXT
            )
        """)
        c.execute("CREATE TABLE IF NOT EXISTS whale_copy_learning (key TEXT PRIMARY KEY, value TEXT)")
        conn.commit()
        conn.close()

def _row_to_dict(row):
    return {key: row[key] for key in row.keys()}

def load_paper_trades(limit=500):
    with _db_lock:
        conn = _get_conn()
        rows = conn.execute("SELECT * FROM paper_trades ORDER BY created_ts DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return [_row_to_dict(r) for r in rows]

def save_paper_trade(trade):
    with _db_lock:
        conn = _get_conn()
        conn.execute("""
            INSERT OR REPLACE INTO paper_trades
            (id, symbol, side, strategy, amount_usdt, price, qty, mode, manual, reason, status, time)
            VALUES (:id, :symbol, :side, :strategy, :amount_usdt, :price, :qty, :mode, :manual, :reason, :status, :time)
        """, trade)
        conn.commit()
        conn.close()

def save_paper_trades(trades):
    with _db_lock:
        conn = _get_conn()
        for t in trades:
            conn.execute("""
                INSERT OR REPLACE INTO paper_trades
                (id, symbol, side, strategy, amount_usdt, price, qty, mode, manual, reason, status, time)
                VALUES (:id, :symbol, :side, :strategy, :amount_usdt, :price, :qty, :mode, :manual, :reason, :status, :time)
            """, t)
        conn.commit()
        conn.close()

def load_whale_copy_trades(limit=500):
    with _db_lock:
        conn = _get_conn()
        rows = conn.execute("SELECT * FROM whale_copy_trades ORDER BY entry_ts DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return [_row_to_dict(r) for r in rows]

def save_whale_copy_trade(trade):
    with _db_lock:
        conn = _get_conn()
        conn.execute("""
            INSERT OR REPLACE INTO whale_copy_trades
            (id, symbol, direction, entry_price, wall_price, wall_size_usdt, wall_qty,
             stop_loss, original_sl, trailing, target, obi, obi_velocity, confidence,
             funding_rate, liq_status, eta, entry_time, entry_ts, mode, status,
             exit_price, exit_time, result, pnl_pct)
            VALUES (:id, :symbol, :direction, :entry_price, :wall_price, :wall_size_usdt, :wall_qty,
                    :stop_loss, :original_sl, :trailing, :target, :obi, :obi_velocity, :confidence,
                    :funding_rate, :liq_status, :eta, :entry_time, :entry_ts, :mode, :status,
                    :exit_price, :exit_time, :result, :pnl_pct)
        """, trade)
        conn.commit()
        conn.close()

def save_whale_copy_trades(trades):
    with _db_lock:
        conn = _get_conn()
        for t in trades:
            conn.execute("""
                INSERT OR REPLACE INTO whale_copy_trades
                (id, symbol, direction, entry_price, wall_price, wall_size_usdt, wall_qty,
                 stop_loss, original_sl, trailing, target, obi, obi_velocity, confidence,
                 funding_rate, liq_status, eta, entry_time, entry_ts, mode, status,
                 exit_price, exit_time, result, pnl_pct)
                VALUES (:id, :symbol, :direction, :entry_price, :wall_price, :wall_size_usdt, :wall_qty,
                        :stop_loss, :original_sl, :trailing, :target, :obi, :obi_velocity, :confidence,
                        :funding_rate, :liq_status, :eta, :entry_time, :entry_ts, :mode, :status,
                        :exit_price, :exit_time, :result, :pnl_pct)
            """, t)
        conn.commit()
        conn.close()

def load_backtest_signals():
    with _db_lock:
        conn = _get_conn()
        rows = conn.execute("SELECT * FROM backtest_signals ORDER BY entry_ts DESC").fetchall()
        conn.close()
        return [_row_to_dict(r) for r in rows]

def save_backtest_signals(signals):
    with _db_lock:
        conn = _get_conn()
        conn.execute("DELETE FROM backtest_signals")
        for s in signals:
            conn.execute("""
                INSERT INTO backtest_signals
                (id, symbol, folder, entry_price, entry_time, entry_ts, tp1, tp2, tp3,
                 stop_loss, original_sl, trailing, traffic, reason, confidence, status,
                 tp1_hit, tp2_hit, tp3_hit, sl_hit, exit_price, exit_time, result, pnl_pct, learning_recorded)
                VALUES (:id, :symbol, :folder, :entry_price, :entry_time, :entry_ts, :tp1, :tp2, :tp3,
                        :stop_loss, :original_sl, :trailing, :traffic, :reason, :confidence, :status,
                        :tp1_hit, :tp2_hit, :tp3_hit, :sl_hit, :exit_price, :exit_time, :result, :pnl_pct, :learning_recorded)
            """, s)
        conn.commit()
        conn.close()

def load_learning_data():
    with _db_lock:
        conn = _get_conn()
        rows = conn.execute("SELECT key, value FROM learning_data").fetchall()
        conn.close()
    out = {}
    for r in rows:
        try:
            out[r["key"]] = json.loads(r["value"])
        except Exception:
            out[r["key"]] = r["value"]
    return out

def save_learning_data(data):
    with _db_lock:
        conn = _get_conn()
        conn.execute("DELETE FROM learning_data")
        for k, v in data.items():
            conn.execute("INSERT OR REPLACE INTO learning_data (key, value) VALUES (?, ?)", (k, json.dumps(v)))
        conn.commit()
        conn.close()

def load_wc_learning():
    with _db_lock:
        conn = _get_conn()
        rows = conn.execute("SELECT key, value FROM whale_copy_learning").fetchall()
        conn.close()
    out = {}
    for r in rows:
        try:
            out[r["key"]] = json.loads(r["value"])
        except Exception:
            out[r["key"]] = r["value"]
    return out

def save_wc_learning(data):
    with _db_lock:
        conn = _get_conn()
        conn.execute("DELETE FROM whale_copy_learning")
        for k, v in data.items():
            conn.execute("INSERT OR REPLACE INTO whale_copy_learning (key, value) VALUES (?, ?)", (k, json.dumps(v)))
        conn.commit()
        conn.close()

def load_api_keys():
    with _db_lock:
        conn = _get_conn()
        rows = conn.execute("SELECT exchange, api_key, secret_key, passphrase FROM api_keys").fetchall()
        conn.close()
    return {
        r["exchange"]: {
            "api_key": r["api_key"],
            "secret_key": r["secret_key"],
            **({"passphrase": r["passphrase"]} if r["passphrase"] else {})
        }
        for r in rows
    }

def save_api_keys(keys):
    with _db_lock:
        conn = _get_conn()
        conn.execute("DELETE FROM api_keys")
        for ex, k in keys.items():
            conn.execute("INSERT INTO api_keys (exchange, api_key, secret_key, passphrase) VALUES (?, ?, ?, ?)",
                         (ex, k.get("api_key", ""), k.get("secret_key", ""), k.get("passphrase", "")))
        conn.commit()
        conn.close()

def load_holdings():
    with _db_lock:
        conn = _get_conn()
        rows = conn.execute("SELECT * FROM holdings").fetchall()
        conn.close()
        return [_row_to_dict(r) for r in rows]

def save_holdings(holdings):
    with _db_lock:
        conn = _get_conn()
        conn.execute("DELETE FROM holdings")
        for h in holdings:
            conn.execute("""
                INSERT OR REPLACE INTO holdings (symbol, quantity, buy_price, target_pct, added)
                VALUES (:symbol, :quantity, :buy_price, :target_pct, :added)
            """, h)
        conn.commit()
        conn.close()

def load_clients():
    with _db_lock:
        conn = _get_conn()
        rows = conn.execute("SELECT * FROM clients").fetchall()
        conn.close()
        return [_row_to_dict(r) for r in rows]

def save_clients(clients):
    with _db_lock:
        conn = _get_conn()
        conn.execute("DELETE FROM clients")
        for c in clients:
            conn.execute("""
                INSERT OR REPLACE INTO clients (name, uid, password, status, expiry, sig_limit, role, added)
                VALUES (:name, :uid, :password, :status, :expiry, :sig_limit, :role, :added)
            """, c)
        conn.commit()
        conn.close()

def load_oco_orders(status=None):
    with _db_lock:
        conn = _get_conn()
        if status:
            rows = conn.execute("SELECT * FROM oco_orders WHERE status=? ORDER BY created_at DESC", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM oco_orders ORDER BY created_at DESC").fetchall()
        conn.close()
        return [_row_to_dict(r) for r in rows]

def save_oco_order(order):
    with _db_lock:
        conn = _get_conn()
        conn.execute("""
            INSERT OR REPLACE INTO oco_orders
            (id, symbol, side, amount_usdt, limit_price, stop_price, stop_limit_price, tp_price, status, exchange, created_at, updated_at)
            VALUES (:id, :symbol, :side, :amount_usdt, :limit_price, :stop_price, :stop_limit_price, :tp_price, :status, :exchange, :created_at, :updated_at)
        """, order)
        conn.commit()
        conn.close()

def db_status():
    tables = ["paper_trades","whale_copy_trades","backtest_signals","learning_data","api_keys","holdings","clients","oco_orders","whale_copy_learning"]
    with _db_lock:
        conn = _get_conn()
        counts = {}
        for t in tables:
            counts[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        conn.close()
    size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    return {"tables": counts, "db_size_bytes": size, "db_path": DB_PATH}

init_db()
