import time, requests, json, threading, os, uvicorn, logging
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

load_dotenv()

LOG_FILE = "system.log"
MAX_LOG_SIZE_BYTES = 5 * 1024 * 1024  # 5MB

def rotate_log_if_needed():
    try:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > MAX_LOG_SIZE_BYTES:
            with open(LOG_FILE, "w") as f:
                f.write("")
            print("[log-rotation] system.log exceeded 5MB — truncated.")
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

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

PORT = int(os.environ.get('PORT', 8080))
BOT_TOKEN = os.getenv('BOT_TOKEN')
SECRET_KEY = os.getenv('SECRET_KEY', '786')
CHAT_ID = os.getenv('CHAT_ID', '8743601537')
GOOGLE_WEBAPP_URL = "https://script.google.com/macros/s/AKfycbx1SOPCmi-6AJeIWZTQWVKSzIR5pSLaAuL3zo52tpjo9vDCD3a8rf4R-4Cge4QbloLVZA/exec"
GLOBAL_DATA = {"signals": [], "whales": []}

def send_telegram(msg: str):
    if not BOT_TOKEN:
        log.warning("BOT_TOKEN not set — Telegram notification skipped.")
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
        log.info("Telegram startup notification sent.")
    except Exception as e:
        log.warning(f"Telegram notification failed: {e}")

def data_engine():
    log.info("Data engine started.")
    while True:
        try:
            res = requests.get(
                f'{GOOGLE_WEBAPP_URL}?action=get_terminal_data&secret_key=Sargodha_V6_Secure_Key_786',
                timeout=10
            ).json()
            GLOBAL_DATA.update(res)
            log.info(f"Sync OK — signals: {len(GLOBAL_DATA.get('signals', []))}, whales: {len(GLOBAL_DATA.get('whales', []))}")
        except Exception as e:
            log.warning(f"Google Sheets sync failed — serving cached data. Reason: {e}")
        time.sleep(3)

def keep_alive_loop():
    time.sleep(30)
    url = f"http://127.0.0.1:{PORT}/"
    log.info(f"Keep-alive started — pinging every 300s")
    while True:
        try:
            r = requests.get(url, timeout=10)
            log.info(f"Keep-alive ping OK: {r.status_code}")
        except Exception as e:
            log.warning(f"Keep-alive ping failed: {e}")
        rotate_log_if_needed()
        time.sleep(300)

@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/v6_live_stream")
def stream(req: Request):
    return GLOBAL_DATA

if __name__ == '__main__':
    log.info(f"V6 Elite Terminal starting — PORT={PORT} | BOT_TOKEN={'SET' if BOT_TOKEN else 'NOT SET'} | SECRET_KEY={'SET' if SECRET_KEY else 'NOT SET'}")
    send_telegram(f"🟢 <b>V6 Elite Terminal ONLINE</b>\nPORT: {PORT}\nStatus: All systems operational.")
    threading.Thread(target=data_engine, daemon=True).start()
    threading.Thread(target=keep_alive_loop, daemon=True).start()
    uvicorn.run(app, host='0.0.0.0', port=PORT)
