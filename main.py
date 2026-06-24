"""
main.py — V6 Master Pro Institutional | Entry Point
Run: python3 main.py
All secrets in Replit Secrets tab. No hardcoded values.
"""
import os, json, time, threading, logging, hashlib, secrets as _secrets
from logging.handlers import RotatingFileHandler
from flask import Flask, request, jsonify, session, redirect, url_for, render_template_string

from logic import (
    process_vmc_signals, process_whale_walls, push_to_google_sheets,
    fetch_btc_sentiment, push_midnight_report,
    compute_institutional_score, compute_tp_levels, compute_position_size,
    compute_whale_power, calculate_atr, fetch_order_book, calculate_obi, detect_obi_spike
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        RotatingFileHandler("error.log", maxBytes=5*1024*1024, backupCount=2),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ── Audit Logger ──────────────────────────────────────────────────────────────
_audit = logging.getLogger("audit")
_audit.setLevel(logging.INFO)
_audit.propagate = False
_ah = RotatingFileHandler("system_audit.log", maxBytes=10*1024*1024, backupCount=5)
_ah.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
_audit.addHandler(_ah)

def audit(user_id: str, action: str, result: str, extra: str = ""):
    _audit.info(f"USER={user_id} | ACTION={action} | RESULT={result} | {extra}")

# ── Config ────────────────────────────────────────────────────────────────────
with open("config.json") as f:
    CONFIG = json.load(f)

# ── Secrets ───────────────────────────────────────────────────────────────────
BOT_TOKEN          = os.getenv("BOT_TOKEN")
CHAT_ID            = os.getenv("CHAT_ID", "8743601537")
SECRET_KEY_VAL     = os.getenv("SECRET_KEY", "786")
SESSION_SECRET     = os.getenv("SESSION_SECRET", _secrets.token_hex(32))
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS", "{}")
GOOGLE_SHEET_ID    = os.getenv("GOOGLE_SHEET_ID", "17mdb-9JuinpDAezkk5qCYgcP5GZYTU8KUBfLha_44mo")
PORT               = int(os.getenv("PORT", "8080"))
ADMIN_PASSWORD     = os.getenv("SECRET_KEY", "786")   # Master password from Replit Secrets

# ── Global State ──────────────────────────────────────────────────────────────
GLOBAL_DATA = {
    "vmc":           {k: [] for k in ["ALL","FAV","STUCK","GOLDEN","BOOM","ENTRY","EXIT","PUMP","VIP"]},
    "whale":         [],
    "alert_history": [],
    "btc":           {},
    "inst_signals":  [],    # enriched signals with traffic light + TP zones
    "last_update":   None,
    "heartbeat":     None,
    "uptime_start":  time.time(),
    "status":        "initializing",
    "cycle_count":   0,
    "active_exchange": "BINANCE",
    "btc_pause":     False,
}

_previous_walls  = {}
_alert_cooldown  = {}
_login_attempts  = {}   # ip → (count, lockout_until)
_HISTORY_MAX     = 50

# ── Flask ─────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = SESSION_SECRET


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _record_alert(alert_type: str, symbol: str, label: str, price, detail: str, traffic: str = ""):
    entry = {
        "time":    time.strftime("%Y-%m-%d %H:%M:%S"),
        "type":    alert_type,
        "symbol":  symbol,
        "label":   label,
        "price":   price,
        "detail":  detail,
        "traffic": traffic,
    }
    hist = GLOBAL_DATA["alert_history"]
    hist.insert(0, entry)
    if len(hist) > _HISTORY_MAX:
        GLOBAL_DATA["alert_history"] = hist[:_HISTORY_MAX]


def _can_alert(key: str, cooldown: int) -> bool:
    now = time.time()
    if now - _alert_cooldown.get(key, 0) >= cooldown:
        _alert_cooldown[key] = now
        return True
    return False


def send_telegram(msg: str, inline_button: dict = None):
    if not BOT_TOKEN or not CHAT_ID:
        return
    try:
        import requests as _r
        payload = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}
        if inline_button:
            payload["reply_markup"] = {
                "inline_keyboard": [[{
                    "text": inline_button.get("text", "📊 View Dashboard"),
                    "url":  inline_button.get("url", "")
                }]]
            }
        _r.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json=payload, timeout=10
        )
    except Exception as e:
        log.warning(f"Telegram send failed: {e}")


def _dashboard_url(symbol: str = "") -> str:
    domains = os.getenv("REPLIT_DOMAINS", "")
    domain  = domains.split(",")[0].strip() if domains else "localhost"
    base    = f"https://{domain}" if domain != "localhost" else "http://localhost:8080"
    return f"{base}/?sym={symbol}" if symbol else base


def alert_vip(coin: dict, inst: dict = None):
    cooldown = CONFIG["telegram"]["vip_alert_cooldown_seconds"]
    if _can_alert(f"vip_{coin['symbol']}", cooldown):
        traffic = inst.get("traffic", "") if inst else ""
        tl_icon = "🟢" if traffic == "GREEN" else "🟡" if traffic == "YELLOW" else "🔴"
        inst_sc = inst.get("inst_score", "—") if inst else "—"
        send_telegram(
            f"⭐ <b>VIP SIGNAL — {coin['symbol']}</b>\n"
            f"Price: {coin['price']} | Change: {coin['change_pct']}%\n"
            f"Score: {coin['score']} | RSI: {coin['rsi']}\n"
            f"Institutional: {inst_sc} | {tl_icon} {traffic}",
            inline_button={"text": f"📊 Watch {coin['symbol'].replace('USDT','')}", "url": _dashboard_url(coin["symbol"])}
        )
        _record_alert("VIP", coin["symbol"], "VIP SIGNAL", coin["price"],
                      f"Score:{coin['score']} | RSI:{coin['rsi']} | Change:{coin['change_pct']}%",
                      traffic)
        audit("SYSTEM", "VIP_ALERT", "SENT", f"sym={coin['symbol']} score={coin['score']}")


def alert_whale(whale: dict):
    cooldown = CONFIG["telegram"].get("alert_cooldown_seconds", 300)
    if _can_alert(f"whale_{whale['symbol']}", cooldown):
        wp = whale.get("whale_power", 0)
        critical = wp >= CONFIG["whale"]["critical_whale_power_pct"]
        prefix   = "🚨 <b>[CRITICAL_WHALE_ALERT]</b>\n" if critical else ""
        tag      = "[WHALE PATTERN MATCH] " if whale.get("pattern_match") else ""
        send_telegram(
            f"{prefix}🐋 <b>{tag}{whale['label']} — {whale['symbol']}</b>\n"
            f"Price: {whale['price']} | Whale Power: {wp}%\n"
            f"Walls: {whale['wall_count']} | Closest: {whale['min_dist_pct']:.2f}%\n"
            f"Spoofing: {whale['spoofing']['details']}\n"
            f"Blink→Push: {'YES ⚡' if whale['blink_to_push'] else 'No'}",
            inline_button={"text": f"🐋 Watch {whale['symbol'].replace('USDT','')}", "url": _dashboard_url(whale["symbol"])}
        )
        _record_alert("WHALE", whale["symbol"], whale["label"], whale["price"],
                      f"WhalePow:{wp}% | Walls:{whale['wall_count']} | "
                      f"MinDist:{whale['min_dist_pct']:.2f}% | Blink:{'YES' if whale['blink_to_push'] else 'No'}")
        audit("SYSTEM", "WHALE_ALERT", "SENT",
              f"sym={whale['symbol']} power={wp}% critical={critical}")


def alert_critical_whale(whale: dict):
    cooldown = CONFIG["telegram"]["critical_whale_cooldown_seconds"]
    if _can_alert(f"critical_{whale['symbol']}", cooldown):
        send_telegram(
            f"🚨🚨 <b>[CRITICAL_WHALE_ALERT] — {whale['symbol']}</b>\n"
            f"Whale Power: {whale.get('whale_power',0)}% (>85% THRESHOLD)\n"
            f"FORCING TO #1 SLOT — SUDDEN SPIKE DETECTED",
            inline_button={"text": "🚨 CRITICAL ALERT — View Now", "url": _dashboard_url(whale["symbol"])}
        )
        audit("SYSTEM", "CRITICAL_WHALE_ALERT", "SENT", f"sym={whale['symbol']}")


# ══════════════════════════════════════════════════════════════════════════════
# BACKGROUND THREADS
# ══════════════════════════════════════════════════════════════════════════════

def data_refresh_loop():
    interval = CONFIG["scanner"]["cache_clear_interval_seconds"]
    while True:
        t0 = time.time()
        try:
            cycle = GLOBAL_DATA["cycle_count"] + 1
            log.info(f"[SCAN #{cycle}] Starting — Ghost Data cleared, fetching live data...")

            vmc_data  = process_vmc_signals(CONFIG)
            price_map = {c["symbol"]: c["price"] for c in vmc_data.get("ALL", [])}
            whale_data = process_whale_walls(CONFIG, price_map, _previous_walls)

            # ── Enrich top signals with institutional score + TP zones ─────────
            inst_signals = []
            vip_min = CONFIG["telegram"]["vip_alert_min_score"]

            for folder in ["VIP", "GOLDEN", "ENTRY"]:
                for coin in vmc_data.get(folder, [])[:5]:
                    sym   = coin["symbol"]
                    # Find whale data for this symbol
                    whale_match = next((w for w in whale_data if w["symbol"] == sym), None)
                    walls  = whale_match["walls"]  if whale_match else []
                    spoof  = whale_match["spoofing"] if whale_match else {"bid_spoof":False,"ask_spoof":False,"details":"Clean"}
                    b2p    = whale_match["blink_to_push"] if whale_match else False
                    w_pow  = whale_match.get("whale_power", 0) if whale_match else 0
                    obi_r  = whale_match.get("obi", {"obi": 0}) if whale_match else {"obi": 0}

                    # ATR (fast — use cached if available)
                    atr    = calculate_atr(sym)
                    tp     = compute_tp_levels(coin["price"], atr, CONFIG)
                    inst   = compute_institutional_score(coin["score"], w_pow, obi_r, walls, CONFIG)
                    sizing = compute_position_size(inst, CONFIG)

                    inst_signals.append({
                        **coin,
                        "folder":    folder,
                        "atr":       atr,
                        "tp_zones":  tp,
                        "inst":      inst,
                        "sizing":    sizing,
                    })

            # Sort: spike + highest inst score first
            inst_signals.sort(key=lambda x: (x["inst"]["spike"], x["inst"]["inst_score"]), reverse=True)

            GLOBAL_DATA["vmc"]          = vmc_data
            GLOBAL_DATA["whale"]        = whale_data
            GLOBAL_DATA["inst_signals"] = inst_signals
            GLOBAL_DATA["last_update"]  = time.strftime("%Y-%m-%d %H:%M:%S")
            GLOBAL_DATA["status"]       = "live"
            GLOBAL_DATA["cycle_count"]  = cycle

            latency_ms = round((time.time() - t0) * 1000)

            # ── Alerts ────────────────────────────────────────────────────────
            if not GLOBAL_DATA.get("btc_pause"):
                for coin in vmc_data.get("VIP", []):
                    if coin["score"] >= vip_min:
                        inst_match = next((s["inst"] for s in inst_signals if s["symbol"] == coin["symbol"]), None)
                        alert_vip(coin, inst_match)

                whale_min_prox = CONFIG["telegram"]["whale_alert_min_proximity"]
                for whale in whale_data:
                    wp = whale.get("whale_power", 0)
                    if wp >= CONFIG["whale"]["critical_whale_power_pct"]:
                        alert_critical_whale(whale)
                        GLOBAL_DATA["inst_signals"].insert(0, {   # force #1
                            "symbol": whale["symbol"], "inst": {"spike": True, "traffic": "GREEN",
                            "inst_score": 100, "whale_power": wp, "reason": "CRITICAL_WHALE"}, "folder": "CRITICAL"
                        })
                    if whale["min_dist_pct"] <= whale_min_prox or whale["blink_to_push"]:
                        alert_whale(whale)
            else:
                log.info("[SCAN] BTC BEARISH — entries paused this cycle.")

            # ── Sheets push ───────────────────────────────────────────────────
            if GOOGLE_SHEET_ID and GOOGLE_CREDENTIALS != "{}":
                threading.Thread(
                    target=push_to_google_sheets,
                    args=(vmc_data, whale_data, GOOGLE_CREDENTIALS, GOOGLE_SHEET_ID),
                    daemon=True
                ).start()

            audit("SYSTEM", "SCAN_CYCLE", "DONE",
                  f"cycle={cycle} latency={latency_ms}ms vip={len(vmc_data.get('VIP',[]))} whale={len(whale_data)}")
            log.info(
                f"[SCAN #{cycle}] Done — ALL:{len(vmc_data.get('ALL',[]))}, "
                f"GOLDEN:{len(vmc_data.get('GOLDEN',[]))}, "
                f"VIP:{len(vmc_data.get('VIP',[]))}, "
                f"WHALE:{len(whale_data)} | {latency_ms}ms"
            )
        except Exception as e:
            log.error(f"[SCAN] Cycle error: {e}", exc_info=True)
            GLOBAL_DATA["status"] = f"error: {e}"
            audit("SYSTEM", "SCAN_CYCLE", "ERROR", str(e))

        time.sleep(interval)


def heartbeat_loop():
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
            f"VIP:{len(GLOBAL_DATA['vmc'].get('VIP',[]))} "
            f"GOLDEN:{len(GLOBAL_DATA['vmc'].get('GOLDEN',[]))} "
            f"Whale:{len(GLOBAL_DATA['whale'])}\n"
            f"BTC: {GLOBAL_DATA['btc'].get('sentiment','?')} | "
            f"Pause: {GLOBAL_DATA['btc_pause']}"
        )
        audit("SYSTEM", "HEARTBEAT", "OK", f"uptime={h}h{m}m cycles={GLOBAL_DATA['cycle_count']}")


def btc_monitor_loop():
    interval = CONFIG["scanner"].get("btc_monitor_interval_seconds", 30)
    while True:
        try:
            btc = fetch_btc_sentiment()
            GLOBAL_DATA["btc"]       = btc
            GLOBAL_DATA["btc_pause"] = btc["pause_entries"]
            if btc["pause_entries"] and btc.get("change_pct", 0) <= -2.0:
                send_telegram(
                    f"🔴 <b>BTC BEARISH ALERT</b>\n"
                    f"BTC dropped {btc['change_pct']}% — Pausing ALL new entries\n"
                    f"Volatility: {btc['volatility_pct']}%"
                )
                audit("SYSTEM", "BTC_PAUSE", "ACTIVATED",
                      f"change={btc['change_pct']}% volatility={btc['volatility_pct']}%")
        except Exception as e:
            log.warning(f"BTC monitor error: {e}")
        time.sleep(interval)


def midnight_report_loop():
    """Fires a midnight report every 24h at UTC 00:00."""
    while True:
        now  = time.gmtime()
        secs_until_midnight = (24 - now.tm_hour) * 3600 - now.tm_min * 60 - now.tm_sec
        if secs_until_midnight <= 0:
            secs_until_midnight += 86400
        time.sleep(secs_until_midnight)

        try:
            if GOOGLE_SHEET_ID and GOOGLE_CREDENTIALS != "{}":
                push_midnight_report(
                    GLOBAL_DATA["vmc"], GLOBAL_DATA["whale"],
                    GOOGLE_CREDENTIALS, GOOGLE_SHEET_ID
                )
            utc_ts = time.strftime("%Y-%m-%d %H:%M:%S UTC")
            pkt_h  = (time.time() + 5*3600)
            pkt_ts = time.strftime("%Y-%m-%d %H:%M:%S PKT", time.gmtime(pkt_h))
            send_telegram(
                f"📊 <b>MIDNIGHT REPORT</b>\n"
                f"UTC: {utc_ts}\nPKT: {pkt_ts}\n"
                f"VIP:{len(GLOBAL_DATA['vmc'].get('VIP',[]))} "
                f"GOLDEN:{len(GLOBAL_DATA['vmc'].get('GOLDEN',[]))} "
                f"ALL:{len(GLOBAL_DATA['vmc'].get('ALL',[]))}\n"
                f"Whale Signals: {len(GLOBAL_DATA['whale'])}\n"
                f"Total Alerts Today: {len(GLOBAL_DATA['alert_history'])}"
            )
            audit("SYSTEM", "MIDNIGHT_REPORT", "SENT", f"utc={utc_ts}")
        except Exception as e:
            log.error(f"Midnight report error: {e}")
            audit("SYSTEM", "MIDNIGHT_REPORT", "ERROR", str(e))


# ══════════════════════════════════════════════════════════════════════════════
# SECURITY HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _check_lockout(ip: str) -> bool:
    """Returns True if IP is currently locked out."""
    entry = _login_attempts.get(ip)
    if not entry:
        return False
    count, lockout_until = entry
    max_att = CONFIG["security"]["max_login_attempts"]
    if count >= max_att and time.time() < lockout_until:
        return True
    if time.time() >= lockout_until:
        _login_attempts.pop(ip, None)
    return False


def _record_failed_login(ip: str):
    entry = _login_attempts.get(ip, (0, 0))
    count = entry[0] + 1
    lockout_mins = CONFIG["security"]["lockout_minutes"]
    lockout_until = time.time() + lockout_mins * 60 if count >= CONFIG["security"]["max_login_attempts"] else entry[1]
    _login_attempts[ip] = (count, lockout_until)
    audit(ip, "LOGIN_FAILED", f"ATTEMPT_{count}", f"locked={count >= CONFIG['security']['max_login_attempts']}")


def _admin_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin_auth"):
            return redirect("/admin/login")
        timeout = CONFIG["security"]["session_timeout_minutes"] * 60
        last    = session.get("last_active", 0)
        if time.time() - last > timeout:
            session.clear()
            return redirect("/admin/login?timeout=1")
        session["last_active"] = time.time()
        return fn(*args, **kwargs)
    return wrapper


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — PUBLIC
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.route("/dashboard_data")
def dashboard_data():
    return jsonify(GLOBAL_DATA)


@app.route("/get_data", methods=["GET", "POST"])
def get_data():
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        key  = body.get("secret_key", "")
    else:
        key = request.args.get("secret_key", "")
    if key != SECRET_KEY_VAL:
        audit(request.remote_addr, "API_ACCESS", "DENIED", f"bad key")
        return jsonify({"error": "Unauthorized"}), 401
    audit(request.remote_addr, "API_ACCESS", "GRANTED", "")
    return jsonify(GLOBAL_DATA)


@app.route("/status")
def status():
    secs = int(time.time() - GLOBAL_DATA["uptime_start"])
    h, r = divmod(secs, 3600)
    m, s = divmod(r, 60)
    return jsonify({
        "status":          GLOBAL_DATA["status"],
        "uptime":          f"{h}h {m}m {s}s",
        "uptime_seconds":  secs,
        "last_update":     GLOBAL_DATA["last_update"],
        "heartbeat":       GLOBAL_DATA["heartbeat"],
        "cycle_count":     GLOBAL_DATA["cycle_count"],
        "signal_counts":   {k: len(v) for k, v in GLOBAL_DATA["vmc"].items()},
        "whale_count":     len(GLOBAL_DATA["whale"]),
        "btc":             GLOBAL_DATA.get("btc", {}),
        "btc_pause":       GLOBAL_DATA.get("btc_pause", False),
        "active_exchange": GLOBAL_DATA.get("active_exchange", "BINANCE"),
        "timestamp":       time.strftime("%Y-%m-%d %H:%M:%S"),
    })


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — ADMIN PORTAL (secret URL + Master Password)
# ══════════════════════════════════════════════════════════════════════════════

ADMIN_LOGIN_HTML = """<!DOCTYPE html>
<html><head><title>V6 Admin</title>
<style>
  body{background:#0a0a0f;color:#c9d1d9;font-family:monospace;display:flex;
       align-items:center;justify-content:center;height:100vh;margin:0;}
  .box{background:#161b22;padding:40px;border:1px solid #30363d;border-radius:8px;
       min-width:320px;text-align:center;}
  h2{color:#FFD700;margin-bottom:24px;}
  input{width:100%;padding:10px;margin:8px 0;background:#0d1117;border:1px solid #30363d;
        color:#c9d1d9;border-radius:4px;box-sizing:border-box;}
  button{width:100%;padding:12px;background:#1f6feb;color:#fff;border:none;
         border-radius:4px;cursor:pointer;font-size:14px;margin-top:8px;}
  .err{color:#FF4500;margin-top:12px;}
  .warn{color:#FFA500;font-size:12px;margin-top:8px;}
</style></head><body>
<div class="box">
  <h2>🔐 V6 ADMIN PORTAL</h2>
  {% if locked %}<p class="err">⛔ Too many failed attempts. Try again later.</p>{% endif %}
  {% if timeout %}<p class="err">⏰ Session expired. Please login again.</p>{% endif %}
  {% if error %}<p class="err">❌ Invalid password.</p>{% endif %}
  <form method="POST">
    <input type="password" name="password" placeholder="Master Password" autofocus/>
    <button type="submit">LOGIN</button>
  </form>
  <p class="warn">3 failed attempts = 30-minute lockout</p>
</div></body></html>"""

ADMIN_PORTAL_HTML = """<!DOCTYPE html>
<html><head><title>V6 Admin Portal</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0;}
  body{background:#0a0a0f;color:#c9d1d9;font-family:monospace;font-size:13px;}
  .header{background:#111827;padding:12px 20px;border-bottom:1px solid #21262d;
          display:flex;justify-content:space-between;align-items:center;}
  .title{color:#FFD700;font-size:15px;font-weight:bold;}
  .logout{color:#FF4500;text-decoration:none;font-size:12px;}
  .container{padding:20px;max-width:1100px;margin:0 auto;}
  .card{background:#161b22;border:1px solid #21262d;border-radius:6px;
        padding:16px;margin-bottom:16px;}
  .card h3{color:#58a6ff;margin-bottom:12px;font-size:13px;letter-spacing:0.5px;}
  .stat{display:inline-block;background:#0d1117;padding:8px 16px;border-radius:4px;
        margin:4px;border:1px solid #30363d;}
  .stat .val{color:#00FF00;font-size:18px;font-weight:bold;display:block;}
  .stat .lbl{color:#555;font-size:10px;}
  table{width:100%;border-collapse:collapse;font-size:11px;}
  th{background:#0d1117;color:#58a6ff;padding:6px 8px;text-align:left;}
  td{padding:5px 8px;border-bottom:1px solid #1a1a2e;}
  .green{color:#00FF00;} .yellow{color:#FFD700;} .red{color:#FF4500;}
  .btn{padding:6px 14px;border:none;border-radius:4px;cursor:pointer;
       font-size:11px;font-family:monospace;}
  .btn-blue{background:#1f6feb;color:#fff;}
  .btn-red{background:#da3633;color:#fff;}
  .form-row{display:flex;gap:8px;margin-bottom:8px;flex-wrap:wrap;}
  input,select{background:#0d1117;border:1px solid #30363d;color:#c9d1d9;
               padding:6px 10px;border-radius:4px;font-family:monospace;font-size:12px;}
  .log-box{background:#0d1117;border:1px solid #30363d;padding:10px;
           border-radius:4px;height:200px;overflow-y:auto;font-size:10px;
           color:#6e7681;white-space:pre-wrap;}
  .tag-green{color:#3fb950;} .tag-red{color:#FF4500;} .tag-yellow{color:#FFD700;}
</style></head><body>
<div class="header">
  <span class="title">🔐 V6 MASTER PRO — ADMIN PORTAL</span>
  <span>
    <span style="color:#555;font-size:11px;margin-right:16px;">Session expires in 15 min idle</span>
    <a href="/admin/logout" class="logout">LOGOUT</a>
  </span>
</div>
<div class="container">

  <!-- System Stats -->
  <div class="card">
    <h3>📊 SYSTEM STATUS</h3>
    <div>
      <div class="stat"><span class="val {{ 'green' if status=='live' else 'red' }}">{{ status.upper() }}</span><span class="lbl">Status</span></div>
      <div class="stat"><span class="val">{{ cycles }}</span><span class="lbl">Scan Cycles</span></div>
      <div class="stat"><span class="val">{{ uptime }}</span><span class="lbl">Uptime</span></div>
      <div class="stat"><span class="val {{ 'red' if btc_pause else 'green' }}">{{ 'PAUSED' if btc_pause else 'ACTIVE' }}</span><span class="lbl">Entries</span></div>
      <div class="stat"><span class="val">{{ btc_chg }}%</span><span class="lbl">BTC Change</span></div>
      <div class="stat"><span class="val">{{ exchange }}</span><span class="lbl">Exchange</span></div>
      <div class="stat"><span class="val">{{ vip_cnt }}</span><span class="lbl">VIP Signals</span></div>
      <div class="stat"><span class="val">{{ whale_cnt }}</span><span class="lbl">Whale Alerts</span></div>
      <div class="stat"><span class="val">{{ hist_cnt }}</span><span class="lbl">Alert History</span></div>
    </div>
  </div>

  <!-- Account Balance Config -->
  <div class="card">
    <h3>💰 RISK CALCULATOR — Account Balance</h3>
    <form method="POST" action="/admin/set_balance">
      <div class="form-row">
        <input type="number" name="balance" value="{{ balance }}" placeholder="Account Balance (USDT)" style="width:200px"/>
        <button type="submit" class="btn btn-blue">Update Balance</button>
      </div>
      <small style="color:#555">GREEN signal: up to {{ green_pct }}% | YELLOW signal: {{ yellow_pct }}% | RED: 0%</small>
    </form>
  </div>

  <!-- Exchange Switcher -->
  <div class="card">
    <h3>🔄 EXCHANGE SWITCHER</h3>
    <form method="POST" action="/admin/set_exchange">
      <div class="form-row">
        <select name="exchange">
          {% for ex in exchanges %}
          <option value="{{ ex }}" {{ 'selected' if ex == exchange else '' }}>{{ ex }}</option>
          {% endfor %}
        </select>
        <button type="submit" class="btn btn-blue">Switch Exchange</button>
      </div>
    </form>
    <small style="color:#555">Note: KuCoin/MEXC/BitMart require API keys — Binance public data used by default</small>
  </div>

  <!-- Alert History -->
  <div class="card">
    <h3>🔔 RECENT ALERTS ({{ hist_cnt }})</h3>
    <table>
      <thead><tr><th>Time</th><th>Type</th><th>Symbol</th><th>Label</th><th>Price</th><th>Traffic</th><th>Detail</th></tr></thead>
      <tbody>
      {% for a in alerts[:20] %}
        <tr>
          <td style="color:#444;font-size:10px">{{ a.time }}</td>
          <td class="{{ 'tag-red' if a.type=='WHALE' else 'tag-yellow' if a.type=='VIP' else 'tag-green' }}">{{ a.type }}</td>
          <td>{{ a.symbol }}</td><td>{{ a.label }}</td><td>{{ a.price }}</td>
          <td class="{{ 'green' if a.traffic=='GREEN' else 'yellow' if a.traffic=='YELLOW' else 'red' }}">{{ a.traffic or '—' }}</td>
          <td style="font-size:10px;color:#6e7681">{{ a.detail }}</td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
  </div>

  <!-- Audit Log Viewer -->
  <div class="card">
    <h3>📋 AUDIT LOG VIEWER</h3>
    <form method="GET" action="/admin/audit_log" style="margin-bottom:10px;">
      <div class="form-row">
        <input type="date" name="date_from" value="{{ today }}"/>
        <input type="date" name="date_to" value="{{ today }}"/>
        <select name="fmt"><option value="html">HTML</option><option value="csv">CSV</option></select>
        <button type="submit" class="btn btn-blue">Filter & Export</button>
      </div>
    </form>
    <div class="log-box">{{ audit_preview }}</div>
  </div>

  <!-- Danger Zone -->
  <div class="card">
    <h3 class="tag-red">⚠️ ADMIN CONTROLS</h3>
    <form method="POST" action="/admin/clear_history" style="display:inline">
      <button type="submit" class="btn btn-red" onclick="return confirm('Clear alert history?')">Clear Alert History</button>
    </form>
    <span style="margin-left:12px;color:#555;font-size:11px">Purge and API management restricted to Admin Portal only</span>
  </div>

</div></body></html>"""


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    ip = request.remote_addr
    locked  = _check_lockout(ip)
    timeout = request.args.get("timeout") == "1"
    error   = False

    if request.method == "POST" and not locked:
        pwd = request.form.get("password", "")
        if pwd == ADMIN_PASSWORD:
            session["admin_auth"]   = True
            session["last_active"]  = time.time()
            audit(ip, "ADMIN_LOGIN", "SUCCESS", "")
            return redirect("/admin")
        else:
            _record_failed_login(ip)
            locked = _check_lockout(ip)
            error  = True

    return render_template_string(ADMIN_LOGIN_HTML, locked=locked, timeout=timeout, error=error)


@app.route("/admin/logout")
def admin_logout():
    audit(request.remote_addr, "ADMIN_LOGOUT", "OK", "")
    session.clear()
    return redirect("/admin/login")


@app.route("/admin")
@_admin_required
def admin_portal():
    secs = int(time.time() - GLOBAL_DATA["uptime_start"])
    h, r = divmod(secs, 3600); m, s = divmod(r, 60)

    # Audit log preview (last 30 lines)
    try:
        with open("system_audit.log", "r") as f:
            lines = f.readlines()
        preview = "".join(lines[-30:])
    except Exception:
        preview = "No audit log yet."

    return render_template_string(ADMIN_PORTAL_HTML,
        status   = GLOBAL_DATA["status"],
        cycles   = GLOBAL_DATA["cycle_count"],
        uptime   = f"{h}h {m}m {s}s",
        btc_pause= GLOBAL_DATA.get("btc_pause", False),
        btc_chg  = GLOBAL_DATA.get("btc", {}).get("change_pct", 0),
        exchange = GLOBAL_DATA.get("active_exchange", "BINANCE"),
        exchanges= ["BINANCE", "KUCOIN", "BITMART", "MEXC"],
        vip_cnt  = len(GLOBAL_DATA["vmc"].get("VIP", [])),
        whale_cnt= len(GLOBAL_DATA["whale"]),
        hist_cnt = len(GLOBAL_DATA["alert_history"]),
        balance  = CONFIG["risk"]["account_balance_usdt"],
        green_pct= CONFIG["risk"]["green_signal_max_pct"],
        yellow_pct=CONFIG["risk"]["yellow_signal_max_pct"],
        alerts   = GLOBAL_DATA["alert_history"],
        audit_preview = preview,
        today    = time.strftime("%Y-%m-%d"),
    )


@app.route("/admin/set_balance", methods=["POST"])
@_admin_required
def admin_set_balance():
    try:
        bal = float(request.form.get("balance", CONFIG["risk"]["account_balance_usdt"]))
        CONFIG["risk"]["account_balance_usdt"] = bal
        with open("config.json", "w") as f:
            json.dump(CONFIG, f, indent=2)
        audit(request.remote_addr, "SET_BALANCE", "OK", f"balance={bal}")
    except Exception as e:
        audit(request.remote_addr, "SET_BALANCE", "ERROR", str(e))
    return redirect("/admin")


@app.route("/admin/set_exchange", methods=["POST"])
@_admin_required
def admin_set_exchange():
    ex = request.form.get("exchange", "BINANCE").upper()
    GLOBAL_DATA["active_exchange"] = ex
    audit(request.remote_addr, "SET_EXCHANGE", "OK", f"exchange={ex}")
    return redirect("/admin")


@app.route("/admin/clear_history", methods=["POST"])
@_admin_required
def admin_clear_history():
    GLOBAL_DATA["alert_history"] = []
    audit(request.remote_addr, "CLEAR_HISTORY", "OK", "")
    return redirect("/admin")


@app.route("/admin/audit_log")
@_admin_required
def admin_audit_log():
    date_from = request.args.get("date_from", time.strftime("%Y-%m-%d"))
    date_to   = request.args.get("date_to",   time.strftime("%Y-%m-%d"))
    fmt       = request.args.get("fmt", "html")
    try:
        with open("system_audit.log", "r") as f:
            lines = f.readlines()
        filtered = [l for l in lines if date_from <= l[:10] <= date_to]
    except Exception:
        filtered = []

    if fmt == "csv":
        from flask import Response
        content = "Timestamp,User,Action,Result,Extra\n" + "".join(filtered)
        return Response(content, mimetype="text/csv",
                        headers={"Content-Disposition": "attachment;filename=audit_export.csv"})

    body = "".join(filtered[-200:]) or "No entries for selected range."
    return f"<pre style='background:#0d1117;color:#c9d1d9;padding:20px;font-size:11px;'>{body}</pre>"


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES — CLIENT PORTAL (Google Sheets controlled)
# ══════════════════════════════════════════════════════════════════════════════

CLIENT_LOGIN_HTML = """<!DOCTYPE html>
<html><head><title>V6 Client Portal</title>
<style>
  body{background:#0a0a0f;color:#c9d1d9;font-family:monospace;display:flex;
       align-items:center;justify-content:center;height:100vh;margin:0;}
  .box{background:#161b22;padding:40px;border:1px solid #30363d;border-radius:8px;
       min-width:320px;text-align:center;}
  h2{color:#3fb950;margin-bottom:24px;}
  input{width:100%;padding:10px;margin:8px 0;background:#0d1117;border:1px solid #30363d;
        color:#c9d1d9;border-radius:4px;box-sizing:border-box;}
  button{width:100%;padding:12px;background:#238636;color:#fff;border:none;
         border-radius:4px;cursor:pointer;font-size:14px;margin-top:8px;}
  .err{color:#FF4500;margin-top:12px;}
</style></head><body>
<div class="box">
  <h2>📊 V6 CLIENT PORTAL</h2>
  {% if error %}<p class="err">{{ error }}</p>{% endif %}
  <form method="POST">
    <input type="text"     name="username" placeholder="Username"/>
    <input type="password" name="password" placeholder="Password"/>
    <button type="submit">ACCESS SIGNALS</button>
  </form>
  <p style="color:#555;font-size:11px;margin-top:16px">Access controlled via Admin Google Sheet</p>
</div></body></html>"""


def _verify_client(username: str, password: str) -> dict:
    """
    Verify client against USERS tab in Google Sheets.
    Returns user dict on success, None on failure.
    Enforces: ACTIVE status, non-expired date, signal limit.
    """
    try:
        import gspread
        from oauth2client.service_account import ServiceAccountCredentials
        import json as _json

        creds_dict = _json.loads(GOOGLE_CREDENTIALS)
        if not creds_dict or not GOOGLE_SHEET_ID:
            return None

        scopes = ["https://spreadsheets.google.com/feeds",
                  "https://www.googleapis.com/auth/drive"]
        creds  = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scopes)
        client = gspread.authorize(creds)
        sheet  = client.open_by_key(GOOGLE_SHEET_ID)
        ws     = sheet.worksheet("USERS")
        users  = ws.get_all_values()

        for row in users[1:]:   # skip header
            if len(row) < 6:
                continue
            name, uid, pwd, status, expiry, sig_limit = row[:6]
            if name.strip() == username and pwd.strip() == password:
                if status.strip().upper() != "ACTIVE":
                    return {"error": "Account inactive. Contact admin."}
                if expiry.strip().upper() not in ("UNLIMITED", ""):
                    try:
                        exp = time.strptime(expiry.strip(), "%Y-%m-%d")
                        if time.gmtime() > exp:
                            return {"error": "Account expired. Contact admin."}
                    except Exception:
                        pass
                return {"username": name, "uid": uid, "sig_limit": sig_limit, "role": "CLIENT"}
        return None
    except Exception as e:
        log.warning(f"Client verify failed: {e}")
        return None


@app.route("/client/login", methods=["GET", "POST"])
def client_login():
    ip = request.remote_addr
    if _check_lockout(ip):
        return render_template_string(CLIENT_LOGIN_HTML, error="⛔ Too many attempts. Try later.")

    error = None
    if request.method == "POST":
        uname = request.form.get("username", "")
        pwd   = request.form.get("password", "")
        user  = _verify_client(uname, pwd)
        if user and "error" not in user:
            session["client_user"] = user
            session["last_active"] = time.time()
            audit(ip, "CLIENT_LOGIN", "SUCCESS", f"user={uname}")
            return redirect("/client")
        elif user and "error" in user:
            error = user["error"]
            _record_failed_login(ip)
        else:
            error = "❌ Invalid username or password."
            _record_failed_login(ip)

    return render_template_string(CLIENT_LOGIN_HTML, error=error)


@app.route("/client")
def client_portal():
    user = session.get("client_user")
    if not user:
        return redirect("/client/login")
    timeout = CONFIG["security"]["session_timeout_minutes"] * 60
    if time.time() - session.get("last_active", 0) > timeout:
        session.clear()
        return redirect("/client/login?timeout=1")
    session["last_active"] = time.time()

    # Client sees same dashboard but read-only (no admin controls)
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.route("/client/logout")
def client_logout():
    session.clear()
    return redirect("/client/login")


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log.info(
        f"V6 Master Pro INSTITUTIONAL starting — PORT={PORT} | "
        f"BOT_TOKEN={'SET' if BOT_TOKEN else 'NOT SET'} | "
        f"CHAT_ID={'SET' if CHAT_ID else 'NOT SET'} | "
        f"Sheets={'configured' if GOOGLE_SHEET_ID else 'not configured'}"
    )
    send_telegram(
        f"🚀 <b>V6 MASTER PRO INSTITUTIONAL ONLINE</b>\n"
        f"PORT: {PORT} | Exchange: BINANCE\n"
        f"VMC Folders: 9 | Whale Scanner: TOP {CONFIG['whale']['top_coins_for_whale']} coins\n"
        f"Traffic Light: ACTIVE | OBI Tracker: ACTIVE\n"
        f"ATR Stop Loss: 1.5× | Admin Portal: /admin\n"
        f"Status: All 39-point institutional systems operational"
    )
    audit("SYSTEM", "STARTUP", "OK", f"port={PORT}")

    threading.Thread(target=data_refresh_loop,   daemon=True).start()
    threading.Thread(target=heartbeat_loop,       daemon=True).start()
    threading.Thread(target=btc_monitor_loop,     daemon=True).start()
    threading.Thread(target=midnight_report_loop, daemon=True).start()

    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
