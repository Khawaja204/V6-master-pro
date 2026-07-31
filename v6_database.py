"""
v6_database.py — V6 Master Pro | SQLite Migration (P0)
Replaces JSON files with SQLite. Backward-compatible fallback.
"""
import os, json, time, sqlite3, threading
from contextlib import contextmanager

DB_PATH = os.getenv("V6_DB_PATH", "v6_master.db")
_db_lock = threading.Lock()

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS paper_trades (
            id TEXT PRIMARY KEY, symbol TEXT, side TEXT, strategy TEXT,
            amount_usdt REAL, price REAL, qty REAL, mode TEXT,
            manual INTEGER, reason TEXT, status TEXT, time TEXT,
            created_at INTEGER DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS whale_copy_trades (
            id TEXT PRIMARY KEY, symbol TEXT, direction TEXT,
            entry_price REAL, wall_price REAL, wall_size_usdt REAL,
            wall_qty REAL, stop_loss REAL, original_sl REAL,
            trailing TEXT, target REAL, obi REAL, obi_velocity REAL,
            confidence REAL, funding_rate REAL, liq_status TEXT,
            eta TEXT, entry_time TEXT, entry_ts INTEGER, mode TEXT,
            status TEXT, exit_price REAL, exit_time TEXT,
            result TEXT, pnl_pct REAL,
            created_at INTEGER DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS backtest_signals (
            id TEXT PRIMARY KEY, symbol TEXT, folder TEXT,
            entry_price REAL, entry_time TEXT, entry_ts INTEGER,
            tp1 REAL, tp2 REAL, tp3 REAL, stop_loss REAL,
            original_sl REAL, trailing TEXT, traffic TEXT,
            reason TEXT, confidence INTEGER, status TEXT,
            tp1_hit INTEGER, tp2_hit INTEGER, tp3_hit INTEGER,
            sl_hit INTEGER, exit_price REAL, exit_time TEXT,
            result TEXT, pnl_pct REAL, learning_recorded INTEGER DEFAULT 0,
            created_at INTEGER DEFAULT (strftime('%s','now'))
        );
        CREATE TABLE IF NOT EXISTS api_keys (
            exchange TEXT PRIMARY KEY, api_key TEXT, secret_key TEXT,
            passphrase TEXT, updated_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS clients (
            name TEXT PRIMARY KEY, uid TEXT, password TEXT,
            status TEXT, expiry TEXT, sig_limit TEXT, role TEXT,
            added TEXT
        );
        CREATE TABLE IF NOT EXISTS holdings (
            symbol TEXT PRIMARY KEY, quantity REAL, buy_price REAL,
            target_pct REAL, added TEXT
        );
        CREATE TABLE IF NOT EXISTS learning_data (
            key TEXT PRIMARY KEY, value TEXT
        );
        CREATE TABLE IF NOT EXISTS price_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT,
            target_price REAL, direction TEXT, note TEXT, created_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_bt_symbol ON backtest_signals(symbol);
        CREATE INDEX IF NOT EXISTS idx_pt_symbol ON paper_trades(symbol);
        CREATE INDEX IF NOT EXISTS idx_wc_symbol ON whale_copy_trades(symbol);
        """)

# ── Paper Trades ──
def save_paper_trades(trades: list):
    with get_db() as db:
        db.execute("DELETE FROM paper_trades")
        for t in trades[-500:]:
            db.execute("""
                INSERT OR REPLACE INTO paper_trades
                (id,symbol,side,strategy,amount_usdt,price,qty,mode,manual,reason,status,time)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (t.get("id"), t.get("symbol"), t.get("side"), t.get("strategy"),
                  t.get("amount_usdt"), t.get("price"), t.get("qty"), t.get("mode"),
                  int(t.get("manual", False)), t.get("reason"), t.get("status"), t.get("time")))

def load_paper_trades() -> list:
    with get_db() as db:
        rows = db.execute("SELECT * FROM paper_trades ORDER BY created_at DESC LIMIT 500").fetchall()
        return [dict(r) for r in rows]

# ── Whale Copy Trades ──
def save_whale_copy_trades(trades: list):
    with get_db() as db:
        db.execute("DELETE FROM whale_copy_trades")
        for t in trades[-500:]:
            db.execute("""
                INSERT OR REPLACE INTO whale_copy_trades
                (id,symbol,direction,entry_price,wall_price,wall_size_usdt,wall_qty,
                stop_loss,original_sl,trailing,target,obi,obi_velocity,confidence,
                funding_rate,liq_status,eta,entry_time,entry_ts,mode,status,
                exit_price,exit_time,result,pnl_pct)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (t.get("id"), t.get("symbol"), t.get("direction"), t.get("entry_price"),
                  t.get("wall_price"), t.get("wall_size_usdt"), t.get("wall_qty"),
                  t.get("stop_loss"), t.get("original_sl"), t.get("trailing"), t.get("target"),
                  t.get("obi"), t.get("obi_velocity"), t.get("confidence"),
                  t.get("funding_rate"), t.get("liq_status"), t.get("eta"),
                  t.get("entry_time"), t.get("entry_ts"), t.get("mode"), t.get("status"),
                  t.get("exit_price"), t.get("exit_time"), t.get("result"), t.get("pnl_pct")))

def load_whale_copy_trades() -> list:
    with get_db() as db:
        rows = db.execute("SELECT * FROM whale_copy_trades ORDER BY entry_ts DESC LIMIT 500").fetchall()
        return [dict(r) for r in rows]

# ── Backtest Signals ──
def save_backtest_signals(signals: list):
    with get_db() as db:
        db.execute("DELETE FROM backtest_signals")
        for s in signals[:100]:
            db.execute("""
                INSERT OR REPLACE INTO backtest_signals
                (id,symbol,folder,entry_price,entry_time,entry_ts,tp1,tp2,tp3,
                stop_loss,original_sl,trailing,traffic,reason,confidence,status,
                tp1_hit,tp2_hit,tp3_hit,sl_hit,exit_price,exit_time,result,pnl_pct,learning_recorded)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (s.get("id"), s.get("symbol"), s.get("folder"), s.get("entry_price"),
                  s.get("entry_time"), s.get("entry_ts"), s.get("tp1"), s.get("tp2"), s.get("tp3"),
                  s.get("stop_loss"), s.get("original_sl"), s.get("trailing"), s.get("traffic"),
                  s.get("reason"), s.get("confidence"), s.get("status"),
                  int(s.get("tp1_hit", False)), int(s.get("tp2_hit", False)), int(s.get("tp3_hit", False)),
                  int(s.get("sl_hit", False)), s.get("exit_price"), s.get("exit_time"),
                  s.get("result"), s.get("pnl_pct"), int(s.get("learning_recorded", False))))

def load_backtest_signals() -> list:
    with get_db() as db:
        rows = db.execute("""
            SELECT * FROM backtest_signals
            WHERE status='CLOSED' OR (strftime('%s','now') - entry_ts) < 21600
            ORDER BY entry_ts DESC LIMIT 100
        """).fetchall()
        return [dict(r) for r in rows]

# ── API Keys ──
def save_api_keys(keys: dict):
    with get_db() as db:
        db.execute("DELETE FROM api_keys")
        for ex, k in keys.items():
            db.execute("""
                INSERT INTO api_keys (exchange,api_key,secret_key,passphrase,updated_at)
                VALUES (?,?,?,?,?)
            """, (ex, k.get("api_key"), k.get("secret_key"), k.get("passphrase"), int(time.time())))

def load_api_keys() -> dict:
    with get_db() as db:
        rows = db.execute("SELECT * FROM api_keys").fetchall()
        out = {}
        for r in rows:
            d = dict(r)
            out[d["exchange"]] = {k: d[k] for k in ["api_key","secret_key","passphrase"] if d.get(k)}
        return out

# ── Clients ──
def save_clients(clients: list):
    with get_db() as db:
        db.execute("DELETE FROM clients")
        for c in clients:
            db.execute("""
                INSERT INTO clients (name,uid,password,status,expiry,sig_limit,role,added)
                VALUES (?,?,?,?,?,?,?,?)
            """, (c.get("name"), c.get("uid"), c.get("password"), c.get("status"),
                  c.get("expiry"), c.get("sig_limit"), c.get("role"), c.get("added")))

def load_clients() -> list:
    with get_db() as db:
        rows = db.execute("SELECT * FROM clients").fetchall()
        return [dict(r) for r in rows]

# ── Holdings ──
def save_holdings(holdings: list):
    with get_db() as db:
        db.execute("DELETE FROM holdings")
        for h in holdings:
            db.execute("""
                INSERT INTO holdings (symbol,quantity,buy_price,target_pct,added)
                VALUES (?,?,?,?,?)
            """, (h.get("symbol"), h.get("quantity"), h.get("buy_price"),
                  h.get("target_pct"), h.get("added")))

def load_holdings() -> list:
    with get_db() as db:
        rows = db.execute("SELECT * FROM holdings").fetchall()
        return [dict(r) for r in rows]

# ── Learning Data ──
def save_learning_data(data: dict):
    with get_db() as db:
        db.execute("DELETE FROM learning_data")
        for k, v in data.items():
            db.execute("INSERT INTO learning_data (key,value) VALUES (?,?)", (k, json.dumps(v)))

def load_learning_data(default: dict = None) -> dict:
    with get_db() as db:
        rows = db.execute("SELECT * FROM learning_data").fetchall()
        if not rows:
            return default or {}
        out = {}
        for r in rows:
            try:
                out[r["key"]] = json.loads(r["value"])
            except Exception:
                out[r["key"]] = r["value"]
        return out

# ── Price Alerts ──
def save_price_alerts(alerts: list):
    with get_db() as db:
        db.execute("DELETE FROM price_alerts")
        for a in alerts:
            db.execute("""
                INSERT INTO price_alerts (id,symbol,target_price,direction,note,created_at)
                VALUES (?,?,?,?,?,?)
            """, (a.get("id"), a.get("symbol"), a.get("target_price"),
                  a.get("direction"), a.get("note"), a.get("created_at")))

def load_price_alerts() -> list:
    with get_db() as db:
        rows = db.execute("SELECT * FROM price_alerts ORDER BY id").fetchall()
        return [dict(r) for r in rows]

def db_status() -> dict:
    size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    with get_db() as db:
        tables = {}
        for t in ["paper_trades","whale_copy_trades","backtest_signals","api_keys",
                  "clients","holdings","learning_data","price_alerts"]:
            tables[t] = db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    return {"db_path": DB_PATH, "db_size_bytes": size, "tables": tables}
