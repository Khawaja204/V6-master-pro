import time, requests, json, threading, os, uvicorn, logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("system.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
PORT = int(os.environ.get('PORT', 8080))
GOOGLE_WEBAPP_URL = "https://script.google.com/macros/s/AKfycbx1SOPCmi-6AJeIWZTQWVKSzIR5pSLaAuL3zo52tpjo9vDCD3a8rf4R-4Cge4QbloLVZA/exec"
GLOBAL_DATA = {"signals": [], "whales": []}

def data_engine():
    log.info("Data engine started.")
    while True:
        try:
            res = requests.get(f'{GOOGLE_WEBAPP_URL}?action=get_terminal_data&secret_key=Sargodha_V6_Secure_Key_786', timeout=10).json()
            GLOBAL_DATA.update(res)
            log.info(f"Data synced — signals: {len(GLOBAL_DATA.get('signals', []))}, whales: {len(GLOBAL_DATA.get('whales', []))}")
        except Exception as e:
            log.warning(f"Google Sheets sync failed (serving cached data): {e}")
        time.sleep(3)

@app.get("/", response_class=HTMLResponse)
def read_root():
    log.info("Dashboard requested.")
    with open("index.html", "r", encoding="utf-8") as f: return f.read()

@app.post("/v6_live_stream")
def stream(req: Request):
    return GLOBAL_DATA

if __name__ == '__main__':
    log.info(f"V6 Elite Terminal starting on port {PORT}")
    threading.Thread(target=data_engine, daemon=True).start()
    uvicorn.run(app, host='0.0.0.0', port=PORT)
