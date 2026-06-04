import subprocess, sys

# ── Auto-repair: validate/install critical modules BEFORE anything else ──────
REQUIRED_PACKAGES = {
    "requests":   "requests",
    "fastapi":    "fastapi",
    "uvicorn":    "uvicorn[standard]",
    "dotenv":     "python-dotenv",
}

# Candidate pip executables — tries each in order until one works
_PIP_CANDIDATES = [
    [sys.executable, "-m", "pip"],
    ["/home/runner/workspace/.pythonlibs/bin/pip"],
    ["pip3"],
    ["pip"],
]

def _find_pip():
    for candidate in _PIP_CANDIDATES:
        try:
            subprocess.check_call(
                candidate + ["--version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10
            )
            return candidate
        except Exception:
            continue
    return None

def auto_repair():
    repaired = False
    for module, pip_name in REQUIRED_PACKAGES.items():
        try:
            __import__(module)
        except ImportError:
            print(f"[auto-repair] Missing module '{module}' — attempting install of '{pip_name}'...")
            pip = _find_pip()
            if pip:
                try:
                    subprocess.check_call(pip + ["install", pip_name, "-q"], timeout=120)
                    print(f"[auto-repair] '{pip_name}' installed successfully.")
                    repaired = True
                except Exception as e:
                    print(f"[auto-repair] WARNING: Could not install '{pip_name}': {e}")
            else:
                print(f"[auto-repair] WARNING: No pip found — '{pip_name}' cannot be auto-installed.")
    if repaired:
        print("[auto-repair] Repair complete — continuing startup.")

auto_repair()  # Must run before any third-party imports

# ── Standard imports (safe after auto_repair) ─────────────────────────────────
import time, requests, json, threading, os, uvicorn, logging
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from keep_alive import keep_alive

load_dotenv()

# ── Log rotation ──────────────────────────────────────────────────────────────
LOG_FILE = "system.log"
MAX_LOG_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB

def rotate_log_if_needed():
    try:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > MAX_LOG_SIZE_BYTES:
            with open(LOG_FILE, "w") as f:
                f.write("")
            print("[log-rotation] system.log exceeded 5 MB — truncated.")
    except Exception as e:
        print(f"[log-rotation] Error: {e}")

rotate_log_if_needed()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ── Config from environment secrets (no hard-coded keys) ──────────────────────
PORT              = int(os.environ.get("PORT", 8080))
BOT_TOKEN         = os.getenv("BOT_TOKEN")
SECRET_KEY        = os.getenv("SECRET_KEY")
CHAT_ID           = os.getenv("CHAT_ID", "8743601537")
GOOGLE_WEBAPP_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbx1SOPCmi-6AJeIWZTQWVKSzIR5pSLaAuL3zo52tpjo9vDCD3a8rf4R-4Cge4QbloLVZA/exec"
)

GLOBAL_DATA: dict        = {"signals": [], "whales": []}
START_TIME: float        = time.time()
LAST_SYNC_TIME: str      = "pending"
LAST_SYNC_STATUS: str    = "pending"
LAST_SYNC_SUCCESS_TS: float = time.time()   # tracks time of last good sync for watchdog

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# ── Telegram with retry on unstable internet ──────────────────────────────────
def send_telegram(msg: str, max_retries: int = 3, retry_wait: int = 10):
    if not BOT_TOKEN:
        log.warning("BOT_TOKEN not set — Telegram notification skipped.")
        return
    for attempt in range(1, max_retries + 1):
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            requests.post(
                url,
                json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"},
                timeout=10
            )
            log.info("Telegram notification sent successfully.")
            return
        except Exception as e:
            log.warning(f"Telegram attempt {attempt}/{max_retries} failed: {e}")
            if attempt < max_retries:
                log.info(f"Internet may be unstable — retrying in {retry_wait}s...")
                time.sleep(retry_wait)
    log.warning("Telegram notification failed after all retries — continuing.")

# ── Data engine: syncs signals from Google Sheets ────────────────────────────
def data_engine():
    global LAST_SYNC_TIME, LAST_SYNC_STATUS, LAST_SYNC_SUCCESS_TS
    log.info("Data engine started.")
    while True:
        try:
            res = requests.get(
                f"{GOOGLE_WEBAPP_URL}?action=get_terminal_data&secret_key={SECRET_KEY}",
                timeout=10
            ).json()
            GLOBAL_DATA.update(res)
            LAST_SYNC_TIME       = time.strftime("%Y-%m-%d %H:%M:%S")
            LAST_SYNC_STATUS     = "OK"
            LAST_SYNC_SUCCESS_TS = time.time()
            log.info(
                f"Sync OK — signals: {len(GLOBAL_DATA.get('signals', []))}, "
                f"whales: {len(GLOBAL_DATA.get('whales', []))}"
            )
        except Exception as e:
            LAST_SYNC_STATUS = f"failed: {e}"
            log.warning(f"Google Sheets sync failed — serving cached data. Reason: {e}")
        time.sleep(3)

# ── Hourly heartbeat ──────────────────────────────────────────────────────────
def heartbeat_loop():
    while True:
        time.sleep(3600)
        rotate_log_if_needed()
        log.info(f"[SYSTEM OK - {time.strftime('%Y-%m-%d %H:%M:%S')}]")

# ── Telegram watchdog ─────────────────────────────────────────────────────────
# Fires alerts if data sync goes dark for >10 min; sends recovery notice when it comes back.
WATCHDOG_ALERT_THRESHOLD = 600   # 10 minutes
WATCHDOG_CHECK_INTERVAL  = 120   # check every 2 minutes

def watchdog_loop():
    alerted = False   # avoid spam — only alert once per outage
    time.sleep(60)    # let system fully boot before first check
    log.info("Watchdog started — monitoring sync health every 2 min.")
    while True:
        silence_secs = int(time.time() - LAST_SYNC_SUCCESS_TS)
        if silence_secs > WATCHDOG_ALERT_THRESHOLD and not alerted:
            mins = silence_secs // 60
            msg = (
                f"⚠️ <b>V6 WATCHDOG ALERT</b>\n"
                f"No successful Google Sheets sync for <b>{mins} minutes</b>.\n"
                f"Last status: {LAST_SYNC_STATUS}\n"
                f"Uptime: {int(time.time() - START_TIME)}s\n"
                f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            log.warning(f"[WATCHDOG] Sync silent for {mins}min — sending Telegram alert.")
            send_telegram(msg)
            alerted = True
        elif silence_secs <= WATCHDOG_ALERT_THRESHOLD and alerted:
            msg = (
                f"✅ <b>V6 WATCHDOG: RECOVERED</b>\n"
                f"Google Sheets sync restored.\n"
                f"Last sync: {LAST_SYNC_TIME}\n"
                f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            log.info("[WATCHDOG] Sync recovered — sending Telegram recovery notice.")
            send_telegram(msg)
            alerted = False
        time.sleep(WATCHDOG_CHECK_INTERVAL)

# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/v6_live_stream")
def stream(req: Request):
    return GLOBAL_DATA

@app.get("/status")
def status():
    uptime_secs    = int(time.time() - START_TIME)
    hours, rem     = divmod(uptime_secs, 3600)
    mins, secs     = divmod(rem, 60)
    silence_secs   = int(time.time() - LAST_SYNC_SUCCESS_TS)
    log_size_mb    = round(os.path.getsize(LOG_FILE) / (1024 * 1024), 2) if os.path.exists(LOG_FILE) else 0
    watchdog_state = "ALERT" if silence_secs > WATCHDOG_ALERT_THRESHOLD else "OK"
    return {
        "status":                "online",
        "system_health":         "OK",
        "uptime":                f"{hours}h {mins}m {secs}s",
        "uptime_seconds":        uptime_secs,
        "last_sync_time":        LAST_SYNC_TIME,
        "last_sync_status":      LAST_SYNC_STATUS,
        "sync_silent_seconds":   silence_secs,
        "watchdog":              watchdog_state,
        "signal_count":          len(GLOBAL_DATA.get("signals", [])),
        "whale_count":           len(GLOBAL_DATA.get("whales", [])),
        "log_file_mb":           log_size_mb,
        "port":                  PORT,
        "timestamp":             time.strftime("%Y-%m-%d %H:%M:%S"),
    }

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        log.info(
            f"V6 Elite Terminal starting — PORT={PORT} | "
            f"BOT_TOKEN={'SET' if BOT_TOKEN else 'NOT SET'} | "
            f"SECRET_KEY={'SET' if SECRET_KEY else 'NOT SET'}"
        )
        # Telegram connect AFTER auto_repair and with internet retry
        send_telegram(
            f"🟢 <b>V6 Elite Terminal ONLINE</b>\n"
            f"PORT: {PORT}\n"
            f"Status: All systems operational."
        )
        threading.Thread(target=data_engine,    daemon=True).start()
        threading.Thread(target=keep_alive,     daemon=True).start()
        threading.Thread(target=heartbeat_loop, daemon=True).start()
        threading.Thread(target=watchdog_loop,  daemon=True).start()
        uvicorn.run(app, host="0.0.0.0", port=PORT)
    except Exception as e:
        log.error(f"Fatal error in main.py: {e}", exc_info=True)
        raise
    finally:
        log.info("main.py shutting down — bootstrap.sh will restart automatically.")
