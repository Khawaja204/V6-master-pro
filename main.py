import time, requests, random, json, threading, os, uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
PORT = int(os.environ.get('PORT', 8080))
GOOGLE_WEBAPP_URL = "https://script.google.com/macros/s/AKfycbx1SOPCmi-6AJeIWZTQWVKSzIR5pSLaAuL3zo52tpjo9vDCD3a8rf4R-4Cge4QbloLVZA/exec"
GLOBAL_DATA = {"signals": [], "whales": []}
def data_engine():
    while True:
        try:
            res = requests.get(f"{GOOGLE_WEBAPP_URL}?action=get_terminal_data&secret_key=Sargodha_V6_Secure_Key_786").json()
            GLOBAL_DATA.update(res)
        except: pass
        time.sleep(3)
@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("index.html", "r", encoding="utf-8") as f: return f.read()
@app.post("/v6_live_stream")
def stream(req: Request): return GLOBAL_DATA
if __name__ == "__main__":
    threading.Thread(target=data_engine, daemon=True).start()
    uvicorn.run(app, host='0.0.0.0', port=PORT)
