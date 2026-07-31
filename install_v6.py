import os, sys, subprocess, time

FILES = {}

FILES["v6_database.py"] = """
import sqlite3, json, os, time, threading
from contextlib import contextmanager

DB_PATH = "v6_master.db"
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
        db.executescript(\"\"\"
        CREATE TABLE IF NOT EXISTS backtest_signals (
            id TEXT PRIMARY KEY, symbol TEXT, folder TEXT,
            entry_price REAL, entry_time TEXT, entry_ts REAL,
            tp1 REAL, tp2 REAL, tp3 REAL, stop_loss REAL, original_sl REAL,
            trailing TEXT, traffic TEXT, reason TEXT, confidence INTEGER,
            status TEXT, tp1_hit INTEGER, tp2_hit INTEGER, tp3_hit INTEGER,
            sl_hit INTEGER, exit_price REAL, exit_time TEXT,
            result TEXT, pnl_pct REAL, learning_recorded INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS paper_trades (
            id TEXT PRIMARY KEY, symbol TEXT, side TEXT, strategy TEXT,
            amount_usdt REAL, price REAL, qty REAL, mode TEXT,
            manual INTEGER, reason TEXT, status TEXT, time TEXT
        );
        CREATE TABLE IF NOT EXISTS whale_copy_trades (
            id TEXT PRIMARY KEY, symbol TEXT, direction TEXT,
            entry_price REAL, wall_price REAL, wall_size_usdt REAL,
            wall_qty REAL, stop_loss REAL, original_sl REAL,
            trailing TEXT, target REAL, obi REAL, obi_velocity REAL,
            confidence REAL, funding_rate REAL, liq_status TEXT,
            eta TEXT, entry_time TEXT, entry_ts REAL, mode TEXT,
            status TEXT, exit_price REAL, exit_time TEXT,
            result TEXT, pnl_pct REAL
        );
        CREATE TABLE IF NOT EXISTS api_keys (
            exchange TEXT PRIMARY KEY, api_key TEXT, secret_key TEXT,
            passphrase TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS clients (
            name TEXT PRIMARY KEY, uid TEXT, password TEXT,
            status TEXT, expiry TEXT, sig_limit TEXT, role TEXT, added TEXT
        );
        CREATE TABLE IF NOT EXISTS holdings (
            symbol TEXT PRIMARY KEY, quantity REAL, buy_price REAL,
            target_pct REAL, added TEXT
        );
        CREATE TABLE IF NOT EXISTS price_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT,
            target_price REAL, direction TEXT, note TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT,
            user_id TEXT, action TEXT, result TEXT, extra TEXT
        );
        CREATE TABLE IF NOT EXISTS learning_data (
            key TEXT PRIMARY KEY, value TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_bt_symbol ON backtest_signals(symbol);
        CREATE INDEX IF NOT EXISTS idx_bt_status ON backtest_signals(status);
        CREATE INDEX IF NOT EXISTS idx_pt_symbol ON paper_trades(symbol);
        CREATE INDEX IF NOT EXISTS idx_wct_symbol ON whale_copy_trades(symbol);
        \"\"\")
"""

FILES["v6_crypto.py"] = """
from cryptography.fernet import Fernet
import os, base64

_KEY_FILE = ".v6_key"
_cipher = None

def _get_or_create_key():
    if os.path.exists(_KEY_FILE):
        with open(_KEY_FILE, "rb") as f:
            return f.read()
    key = Fernet.generate_key()
    with open(_KEY_FILE, "wb") as f:
        f.write(key)
    os.chmod(_KEY_FILE, 0o600)
    return key

def get_cipher():
    global _cipher
    if _cipher is None:
        _cipher = Fernet(_get_or_create_key())
    return _cipher

def encrypt(text: str) -> str:
    return get_cipher().encrypt(text.encode()).decode()

def decrypt(token: str) -> str:
    return get_cipher().decrypt(token.encode()).decode()
"""

FILES["v6_oco.py"] = """
import time, json, threading
from v6_database import get_db

class OCOManager:
    def __init__(self, paper_mode=True, fund_limit_usdt=10.0):
        self.paper_mode = paper_mode
        self.fund_limit_usdt = fund_limit_usdt
        self._lock = threading.Lock()
        self._orders = {}
    
    def place_oco(self, symbol, side, amount_usdt, entry_price, stop_price, limit_price):
        oid = "OCO-%d-%s" % (int(time.time()), symbol[:4])
        with self._lock:
            self._orders[oid] = {
                "id": oid, "symbol": symbol, "side": side,
                "amount_usdt": amount_usdt, "entry_price": entry_price,
                "stop_price": stop_price, "limit_price": limit_price,
                "status": "OPEN", "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        return {"ok": True, "order_id": oid}
    
    def cancel_oco(self, order_id):
        with self._lock:
            if order_id in self._orders:
                self._orders[order_id]["status"] = "CANCELLED"
                return True
        return False
    
    def get_open(self):
        with self._lock:
            return [o for o in self._orders.values() if o["status"] == "OPEN"]
"""

FILES["v6_websocket.py"] = """
import websocket, json, threading, time

_ws = None
_prices = {}
_lock = threading.Lock()

def on_message(ws, message):
    global _prices
    try:
        data = json.loads(message)
        if "s" in data and "c" in data:
            with _lock:
                _prices[data["s"]] = float(data["c"])
    except Exception:
        pass

def on_error(ws, error):
    pass

def on_close(ws, close_status_code, close_msg):
    pass

def on_open(ws):
    pass

def start_websocket_feed():
    global _ws
    url = "wss://stream.binance.com:9443/ws/!ticker@arr"
    while True:
        try:
            ws = websocket.WebSocketApp(url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close)
            _ws = ws
            ws.run_forever(ping_interval=20, ping_timeout=10)
        except Exception:
            pass
        time.sleep(5)

def get_ws_price(symbol):
    with _lock:
        return _prices.get(symbol)
"""

FILES["v6_partial_tp.py"] = """
import time, threading

class PartialTPManager:
    def __init__(self, config):
        self.config = config
        self._positions = {}
        self._lock = threading.Lock()
    
    def add_position(self, symbol, entry_price, qty, tp_levels, stop_loss):
        with self._lock:
            self._positions[symbol] = {
                "entry_price": entry_price, "qty": qty,
                "tp1": tp_levels.get("tp1"), "tp2": tp_levels.get("tp2"),
                "tp3": tp_levels.get("tp3"), "sl": stop_loss,
                "tp1_done": False, "tp2_done": False, "tp3_done": False,
                "remaining_qty": qty
            }
    
    def check_and_scale(self, symbol, current_price):
        with self._lock:
            pos = self._positions.get(symbol)
            if not pos:
                return None
            actions = []
            if not pos["tp1_done"] and pos["tp1"] and current_price >= pos["tp1"]:
                sell_qty = round(pos["remaining_qty"] * 0.3, 6)
                pos["remaining_qty"] -= sell_qty
                pos["tp1_done"] = True
                actions.append({"tp": 1, "qty": sell_qty, "price": current_price})
            if not pos["tp2_done"] and pos["tp2"] and current_price >= pos["tp2"]:
                sell_qty = round(pos["remaining_qty"] * 0.5, 6)
                pos["remaining_qty"] -= sell_qty
                pos["tp2_done"] = True
                actions.append({"tp": 2, "qty": sell_qty, "price": current_price})
            if not pos["tp3_done"] and pos["tp3"] and current_price >= pos["tp3"]:
                sell_qty = pos["remaining_qty"]
                pos["remaining_qty"] = 0
                pos["tp3_done"] = True
                actions.append({"tp": 3, "qty": sell_qty, "price": current_price})
                pos["status"] = "CLOSED"
            return actions
"""

FILES["v6_multitimeframe.py"] = """
from logic import fetch_klines, calculate_rsi, calculate_macd

def get_mtf_signal(symbol):
    result = {}
    for tf, limit in [("15m", 50), ("1h", 50), ("4h", 30)]:
        klines = fetch_klines(symbol, tf, limit)
        if not klines or len(klines) < 20:
            result[tf] = {"trend": "UNKNOWN", "rsi": 50, "macd_hist": 0}
            continue
        closes = [float(k[4]) for k in klines]
        rsi = calculate_rsi(closes)
        macd = calculate_macd(closes)
        ema20 = sum(closes[-20:]) / 20
        trend = "UP" if closes[-1] > ema20 else "DOWN"
        result[tf] = {"trend": trend, "rsi": rsi, "macd_hist": macd.get("hist", 0)}
    
    trends = [result[tf]["trend"] for tf in ["15m", "1h", "4h"]]
    up_count = trends.count("UP")
    down_count = trends.count("DOWN")
    
    if up_count >= 2 and down_count == 0:
        result["confluence"] = "STRONG_BUY"
    elif down_count >= 2 and up_count == 0:
        result["confluence"] = "STRONG_SELL"
    elif up_count > down_count:
        result["confluence"] = "WEAK_BUY"
    elif down_count > up_count:
        result["confluence"] = "WEAK_SELL"
    else:
        result["confluence"] = "NEUTRAL"
    
    return result
"""

FILES["migrate_to_sqlite.py"] = """
import json, os, time
from v6_database import init_db, get_db

def migrate():
    init_db()
    print("[MIGRATE] Database initialized.")
    
    files = {
        "backtest_signals.json": "backtest",
        "paper_trades.json": "paper_trades", 
        "whale_copy_trades.json": "whale_copy_trades",
        "api_keys.json": "api_keys",
        "clients.json": "clients",
        "holdings.json": "holdings",
        "learning_data.json": "learning_data"
    }
    
    for fname, key in files.items():
        if not os.path.exists(fname):
            continue
        try:
            with open(fname) as f:
                data = json.load(f)
        except Exception as e:
            print("[SKIP] %s: %s" % (fname, e))
            continue
        
        bak = "backups/%s.%d.bak" % (fname, int(time.time()))
        os.makedirs("backups", exist_ok=True)
        with open(bak, "w") as f:
            json.dump(data, f, indent=2)
        print("[BACKUP] %s -> %s" % (fname, bak))
        
        with get_db() as db:
            if key == "backtest":
                for item in data:
                    db.execute(\"\"\"
                        INSERT OR REPLACE INTO backtest_signals VALUES (
                            :id, :symbol, :folder, :entry_price, :entry_time, :entry_ts,
                            :tp1, :tp2, :tp3, :stop_loss, :original_sl, :trailing,
                            :traffic, :reason, :confidence, :status, :tp1_hit, :tp2_hit,
                            :tp3_hit, :sl_hit, :exit_price, :exit_time, :result, :pnl_pct, 0
                        )
                    \"\"\", item)
            elif key == "paper_trades":
                for item in data:
                    db.execute(\"\"\"
                        INSERT OR REPLACE INTO paper_trades VALUES (
                            :id, :symbol, :side, :strategy, :amount_usdt, :price,
                            :qty, :mode, :manual, :reason, :status, :time
                        )
                    \"\"\", item)
            elif key == "whale_copy_trades":
                for item in data:
                    db.execute(\"\"\"
                        INSERT OR REPLACE INTO whale_copy_trades VALUES (
                            :id, :symbol, :direction, :entry_price, :wall_price,
                            :wall_size_usdt, :wall_qty, :stop_loss, :original_sl,
                            :trailing, :target, :obi, :obi_velocity, :confidence,
                            :funding_rate, :liq_status, :eta, :entry_time, :entry_ts,
                            :mode, :status, :exit_price, :exit_time, :result, :pnl_pct
                        )
                    \"\"\", item)
            elif key == "api_keys":
                for ex, creds in data.items():
                    db.execute(\"\"\"
                        INSERT OR REPLACE INTO api_keys VALUES (?, ?, ?, ?, ?)
                    \"\"\", (ex, creds.get("api_key", ""), creds.get("secret_key", ""),
                          creds.get("passphrase", ""), time.strftime("%Y-%m-%d %H:%M:%S")))
            elif key == "clients":
                for c in data:
                    db.execute(\"\"\"
                        INSERT OR REPLACE INTO clients VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    \"\"\", (c.get("name"), c.get("uid"), c.get("password"),
                          c.get("status", "ACTIVE"), c.get("expiry", "UNLIMITED"),
                          c.get("sig_limit", "100"), c.get("role", "CLIENT"), c.get("added", "")))
            elif key == "holdings":
                for h in data:
                    db.execute(\"\"\"
                        INSERT OR REPLACE INTO holdings VALUES (?, ?, ?, ?, ?)
                    \"\"\", (h.get("symbol"), h.get("quantity"), h.get("buy_price"),
                          h.get("target_pct", 15), h.get("added", "")))
            elif key == "learning_data":
                db.execute("INSERT OR REPLACE INTO learning_data VALUES (?, ?)",
                           ("data", json.dumps(data)))
        
        print("[MIGRATED] %s -> SQLite" % fname)
    
    print("[DONE] Migration complete. JSON files backed up to ./backups/")

if __name__ == "__main__":
    migrate()
"""

FILES["patch_main.py"] = '''
import re

MAIN_FILE = "main.py"

with open(MAIN_FILE, "r") as f:
    content = f.read()

if "_V6_UPGRADE" in content:
    print("[SKIP] main.py already patched.")
    sys.exit(0)

# 1. Add imports
old_import = \'\'\'from logic import (
    process_vmc_signals, process_whale_walls, push_to_google_sheets,
    fetch_btc_sentiment, push_midnight_report,
    compute_institutional_score, compute_tp_levels, compute_position_size,
    compute_whale_power, calculate_atr, fetch_order_book, calculate_obi,
    detect_obi_spike, compute_confidence_score, fetch_ticker_price,
    detect_market_regime, compute_vwap, detect_rsi_divergence, fetch_klines,
    fetch_macd_for_symbol, compute_v6_final_score,
    calculate_wall_proximity, detect_spoofing, blink_to_push_check,
    detect_whale_copy_signals, is_stablecoin_pair,
    fetch_ticker_24h, score_coin, fetch_rsi_for_symbol,
    estimate_time_to_target, fetch_large_trades, fetch_eth_exchange_flows,
)\'\'\'

new_import = \'\'\'from logic import (
    process_vmc_signals, process_whale_walls, push_to_google_sheets,
    fetch_btc_sentiment, push_midnight_report,
    compute_institutional_score, compute_tp_levels, compute_position_size,
    compute_whale_power, calculate_atr, fetch_order_book, calculate_obi,
    detect_obi_spike, compute_confidence_score, fetch_ticker_price,
    detect_market_regime, compute_vwap, detect_rsi_divergence, fetch_klines,
    fetch_macd_for_symbol, compute_v6_final_score,
    calculate_wall_proximity, detect_spoofing, blink_to_push_check,
    detect_whale_copy_signals, is_stablecoin_pair,
    fetch_ticker_24h, score_coin, fetch_rsi_for_symbol,
    estimate_time_to_target, fetch_large_trades, fetch_eth_exchange_flows,
)

# V6 UPGRADE IMPORTS (P0: SQLite + Crypto + OCO | P1: WS + Partial TP + MTF)
try:
    from v6_database import init_db, get_db
    from v6_crypto import encrypt, decrypt
    from v6_oco import OCOManager
    from v6_websocket import start_websocket_feed, get_ws_price
    from v6_partial_tp import PartialTPManager
    from v6_multitimeframe import get_mtf_signal
    _V6_UPGRADE = True
except Exception as _e:
    print("[V6 UPGRADE] Import warning: %s" % _e)
    _V6_UPGRADE = False

_V6_WS  = _V6_UPGRADE
_V6_OCO = _V6_UPGRADE
_V6_PTP = _V6_UPGRADE
_V6_MTF = _V6_UPGRADE\'\'\'

content = content.replace(old_import, new_import)
print("[PATCH] Imports added.")

# 2. Add init_db() after CONFIG load
config_load = \'\'\'with open("config.json") as f:
    CONFIG = json.load(f)\'\'\'

new_config_load = \'\'\'with open("config.json") as f:
    CONFIG = json.load(f)

# V6 UPGRADE: Initialize SQLite Database
if _V6_UPGRADE:
    try:
        init_db()
        log.info("[V6 DB] SQLite initialized.")
    except Exception as _e:
        log.warning("[V6 DB] init failed: %s" % _e)\'\'\'

content = content.replace(config_load, new_config_load)
print("[PATCH] SQLite init hook added.")

# 3. Add startup hooks before app.run()
startup = \'\'\'    # V6 UPGRADE: WebSocket + OCO + Partial TP + Multi-Timeframe
    if _V6_WS:
        threading.Thread(target=start_websocket_feed, daemon=True).start()
        log.info("[V6 WS] Price feed started.")
    if _V6_OCO:
        GLOBAL_DATA["oco_manager"] = OCOManager(
            paper_mode=GLOBAL_DATA.get("paper_mode", True),
            fund_limit_usdt=CONFIG.get("bot_fund_limit_usdt", 10.0)
        )
        log.info("[V6 OCO] Manager ready.")
    if _V6_PTP:
        GLOBAL_DATA["ptp_manager"] = PartialTPManager(CONFIG)
        log.info("[V6 PTP] Partial TP manager ready.")
    if _V6_MTF:
        GLOBAL_DATA["mtf_enabled"] = True
        log.info("[V6 MTF] Multi-timeframe enabled.")
    # end V6 upgrade\'\'\'

content = re.sub(
    r\'(    app\\.run\\(host="0\\.0\\.0\\.0", port=PORT, debug=False, use_reloader=False\\))\',
    startup + "\\n\\n\\1",
    content
)
print("[PATCH] Startup hooks added.")

with open(MAIN_FILE, "w") as f:
    f.write(content)

print("[DONE] main.py patched successfully.")
'''

def run(cmd, check=True):
    print("\n>>> %s" % cmd)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.stdout:
        print(r.stdout)
    if r.stderr:
        print(r.stderr, file=sys.stderr)
    if check and r.returncode != 0:
        print("[ERROR] Command failed: %s" % cmd)
    return r.returncode == 0

def main():
    print("=" * 60)
    print("  V6 MASTER PRO — FULL UPGRADE INSTALLER")
    print("  SQLite | Crypto | OCO | WebSocket | Partial TP | MTF")
    print("=" * 60)

    for fname, fcontent in FILES.items():
        if os.path.exists(fname):
            print("[SKIP] %s already exists." % fname)
            continue
        with open(fname, "w") as f:
            f.write(fcontent.strip() + "\n")
        print("[CREATE] %s" % fname)

    print("\n[DEPS] Installing cryptography + websocket-client...")
    run("pip install -q cryptography websocket-client")

    reqs = set()
    if os.path.exists("requirements.txt"):
        with open("requirements.txt") as f:
            reqs = set(line.strip().split(">=")[0].split("==")[0].lower() for line in f if line.strip())
    additions = []
    if "cryptography" not in reqs:
        additions.append("cryptography>=41.0")
    if "websocket-client" not in reqs:
        additions.append("websocket-client>=1.6")
    if additions:
        with open("requirements.txt", "a") as f:
            f.write("\n" + "\n".join(additions) + "\n")
        print("[REQS] Added: %s" % ", ".join(additions))

    print("\n[MIGRATE] JSON -> SQLite...")
    run("python3 migrate_to_sqlite.py", check=False)

    print("\n[PATCH] Injecting imports + hooks into main.py...")
    run("python3 patch_main.py", check=False)

    print("\n[RESTART] Restarting V6 Master Pro...")
    run("bash v6-cmd.sh restart", check=False)

    print("\n" + "=" * 60)
    print("  UPGRADE COMPLETE!")
    print("=" * 60)
    print("""
Next steps:
  Check logs:  bash v6-cmd.sh logs
  DB status:   bash v6-cmd.sh db-status
  Admin panel: /admin
""")

if __name__ == "__main__":
    main()
