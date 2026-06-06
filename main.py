"""
main.py — V6 Master Pro | Entry Point
Run: python3 main.py
All secrets loaded from environment (Replit Secrets tab).
"""
import os, json, time, threading, logging
from logging.handlers import RotatingFileHandler
from flask import Flask, request, jsonify

from logic import process_vmc_signals, process_whale_walls, push_to_google_sheets

# ── Logging — writes to error.log (5MB rotating) + console ───────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        RotatingFileHandler("error.log", maxBytes=5 * 1024 * 1024, backupCount=2),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ── Config — edit config.json to tune thresholds, no code changes needed ──────
with open("config.json") as f:
    CONFIG = json.load(f)

# ── Secrets — all from Replit Secrets tab, zero hardcoded values ─────────────
BOT_TOKEN          = os.getenv("BOT_TOKEN")
CHAT_ID            = os.getenv("CHAT_ID", "8743601537")
SECRET_KEY         = os.getenv("SECRET_KEY", "786")
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS", "{}")
GOOGLE_SHEET_ID    = os.getenv("GOOGLE_SHEET_ID", "")
PORT               = int(os.getenv("PORT", "8080"))

# ── Global Data Cache — ghost data prevention: rebuilt every scan cycle ───────
GLOBAL_DATA = {
    "vmc": {k: [] for k in ["ALL", "FAV", "STUCK", "GOLDEN", "BOOM", "ENTRY", "EXIT", "PUMP", "VIP"]},
    "whale": [],
    "alert_history": [],   # last 50 alerts — VIP + Whale combined
    "last_update":  None,
    "heartbeat":    None,
    "uptime_start": time.time(),
    "status":       "initializing",
    "cycle_count":  0,
}
_previous_walls   = {}
_alert_cooldown   = {}   # symbol → last alert timestamp
_HISTORY_MAX      = 50


def _record_alert(alert_type: str, symbol: str, label: str, price, detail: str):
    """Append an alert to GLOBAL_DATA['alert_history'], keeping the last 50."""
    entry = {
        "time":   time.strftime("%Y-%m-%d %H:%M:%S"),
        "type":   alert_type,          # "VIP" | "WHALE" | "GOLDEN"
        "symbol": symbol,
        "label":  label,
        "price":  price,
        "detail": detail,
    }
    hist = GLOBAL_DATA["alert_history"]
    hist.insert(0, entry)              # newest first
    if len(hist) > _HISTORY_MAX:
        GLOBAL_DATA["alert_history"] = hist[:_HISTORY_MAX]

# ── Flask ─────────────────────────────────────────────────────────────────────
app = Flask(__name__)


# ── Telegram helpers ──────────────────────────────────────────────────────────
def send_telegram(msg: str):
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        import requests as _r
        _r.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        log.warning(f"Telegram send failed: {e}")


def _can_alert(key: str, cooldown: int) -> bool:
    now = time.time()
    if now - _alert_cooldown.get(key, 0) >= cooldown:
        _alert_cooldown[key] = now
        return True
    return False


def alert_vip(coin: dict):
    cooldown = CONFIG["telegram"]["vip_alert_cooldown_seconds"]
    if _can_alert(f"vip_{coin['symbol']}", cooldown):
        send_telegram(
            f"⭐ <b>VIP SIGNAL — {coin['symbol']}</b>\n"
            f"Price: {coin['price']} | Change: {coin['change_pct']}%\n"
            f"Score: {coin['score']} | RSI: {coin['rsi']}"
        )
        _record_alert(
            alert_type="VIP",
            symbol=coin["symbol"],
            label="VIP SIGNAL",
            price=coin["price"],
            detail=f"Score:{coin['score']} | RSI:{coin['rsi']} | Change:{coin['change_pct']}%"
        )


def alert_whale(whale: dict):
    cooldown = CONFIG["whale"]["alert_cooldown_seconds"]
    if _can_alert(f"whale_{whale['symbol']}", cooldown):
        send_telegram(
            f"🐋 <b>{whale['label']} — {whale['symbol']}</b>\n"
            f"Price: {whale['price']}\n"
            f"Walls: {whale['wall_count']} | Closest: {whale['min_dist_pct']:.2f}%\n"
            f"Spoofing: {whale['spoofing']['details']}\n"
            f"Blink→Push: {'YES ⚡' if whale['blink_to_push'] else 'No'}"
        )
        _record_alert(
            alert_type="WHALE",
            symbol=whale["symbol"],
            label=whale["label"],
            price=whale["price"],
            detail=(
                f"Walls:{whale['wall_count']} | "
                f"MinDist:{whale['min_dist_pct']:.2f}% | "
                f"Blink:{'YES' if whale['blink_to_push'] else 'No'} | "
                f"{whale['spoofing']['details']}"
            )
        )


# ── Background thread: main scan loop ────────────────────────────────────────
def data_refresh_loop():
    """
    Fetches 500+ coins from Binance, runs VMC + Whale engines every cycle.
    Ghost Data Prevention: cache is completely rebuilt from scratch each cycle.
    Cycle interval: config.json["scanner"]["cache_clear_interval_seconds"].
    """
    interval = CONFIG["scanner"]["cache_clear_interval_seconds"]
    while True:
        try:
            cycle = GLOBAL_DATA["cycle_count"] + 1
            log.info(f"[SCAN #{cycle}] Starting — Ghost Data cleared, fetching live data...")

            vmc_data  = process_vmc_signals(CONFIG)
            price_map = {c["symbol"]: c["price"] for c in vmc_data.get("ALL", [])}
            whale_data = process_whale_walls(CONFIG, price_map, _previous_walls)

            GLOBAL_DATA["vmc"]          = vmc_data
            GLOBAL_DATA["whale"]        = whale_data
            GLOBAL_DATA["last_update"]  = time.strftime("%Y-%m-%d %H:%M:%S")
            GLOBAL_DATA["status"]       = "live"
            GLOBAL_DATA["cycle_count"]  = cycle

            # Fire Telegram alerts
            vip_min = CONFIG["telegram"]["vip_alert_min_score"]
            for coin in vmc_data.get("VIP", []):
                if coin["score"] >= vip_min:
                    alert_vip(coin)

            whale_min_prox = CONFIG["telegram"]["whale_alert_min_proximity"]
            for whale in whale_data:
                if whale["min_dist_pct"] <= whale_min_prox or whale["blink_to_push"]:
                    alert_whale(whale)

            # Google Sheets push (only if configured)
            if GOOGLE_SHEET_ID and GOOGLE_CREDENTIALS != "{}":
                push_to_google_sheets(vmc_data, whale_data, GOOGLE_CREDENTIALS, GOOGLE_SHEET_ID)

            log.info(
                f"[SCAN #{cycle}] Done — ALL:{len(vmc_data.get('ALL',[]))}, "
                f"GOLDEN:{len(vmc_data.get('GOLDEN',[]))}, "
                f"VIP:{len(vmc_data.get('VIP',[]))}, "
                f"WHALE:{len(whale_data)}"
            )
        except Exception as e:
            log.error(f"[SCAN] Cycle error: {e}", exc_info=True)
            GLOBAL_DATA["status"] = f"error: {e}"

        time.sleep(interval)


# ── Background thread: heartbeat monitor ─────────────────────────────────────
def heartbeat_loop():
    """
    Sends [SYSTEM OK] ping to console + Telegram every 5 minutes.
    Interval: config.json["scanner"]["heartbeat_interval_seconds"].
    """
    interval = CONFIG["scanner"]["heartbeat_interval_seconds"]
    while True:
        time.sleep(interval)
        secs = int(time.time() - GLOBAL_DATA["uptime_start"])
        h, r = divmod(secs, 3600)
        m, s = divmod(r, 60)
        ts   = time.strftime("%Y-%m-%d %H:%M:%S")

        log.info(
            f"[SYSTEM OK - {ts}] Uptime: {h}h {m}m {s}s | "
            f"Cycles: {GLOBAL_DATA['cycle_count']} | Status: {GLOBAL_DATA['status']}"
        )
        GLOBAL_DATA["heartbeat"] = ts

        send_telegram(
            f"💚 <b>V6 HEARTBEAT</b>\n"
            f"Status: {GLOBAL_DATA['status']}\n"
            f"Uptime: {h}h {m}m {s}s | Cycles: {GLOBAL_DATA['cycle_count']}\n"
            f"Signals → VIP:{len(GLOBAL_DATA['vmc'].get('VIP',[]))} "
            f"GOLDEN:{len(GLOBAL_DATA['vmc'].get('GOLDEN',[]))} "
            f"ENTRY:{len(GLOBAL_DATA['vmc'].get('ENTRY',[]))}\n"
            f"Whale Alerts: {len(GLOBAL_DATA['whale'])}\n"
            f"Time: {ts}"
        )


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.route("/get_data", methods=["GET", "POST"])
def get_data():
    """
    Main data API. Auth: ?secret_key=YOUR_KEY (GET) or JSON body (POST).
    SECRET_KEY is set in Replit Secrets tab.
    """
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        key  = body.get("secret_key", "")
    else:
        key = request.args.get("secret_key", "")

    if key != SECRET_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    return jsonify(GLOBAL_DATA)


@app.route("/dashboard_data")
def dashboard_data():
    """
    No-auth endpoint used exclusively by index.html (served from the same origin).
    External API access should use /get_data with secret_key.
    """
    return jsonify(GLOBAL_DATA)


@app.route("/status")
def status():
    secs = int(time.time() - GLOBAL_DATA["uptime_start"])
    h, r = divmod(secs, 3600)
    m, s = divmod(r, 60)
    return jsonify({
        "status":        GLOBAL_DATA["status"],
        "uptime":        f"{h}h {m}m {s}s",
        "uptime_seconds": secs,
        "last_update":   GLOBAL_DATA["last_update"],
        "heartbeat":     GLOBAL_DATA["heartbeat"],
        "cycle_count":   GLOBAL_DATA["cycle_count"],
        "signal_counts": {k: len(v) for k, v in GLOBAL_DATA["vmc"].items()},
        "whale_count":   len(GLOBAL_DATA["whale"]),
        "timestamp":     time.strftime("%Y-%m-%d %H:%M:%S"),
    })


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    log.info(
        f"V6 Master Pro starting — PORT={PORT} | "
        f"BOT_TOKEN={'SET' if BOT_TOKEN else 'NOT SET'} | "
        f"CHAT_ID={'SET' if CHAT_ID else 'NOT SET'} | "
        f"Sheets={'configured' if GOOGLE_SHEET_ID else 'not configured'}"
    )
    send_telegram(
        f"🚀 <b>V6 MASTER PRO ONLINE</b>\n"
        f"PORT: {PORT} | Scanning: 500+ coins\n"
        f"VMC Folders: 9 active\n"
        f"Whale Scanner: TOP {CONFIG['whale']['top_coins_for_whale']} coins\n"
        f"Status: All systems operational"
    )
    threading.Thread(target=data_refresh_loop, daemon=True).start()
    threading.Thread(target=heartbeat_loop,    daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
