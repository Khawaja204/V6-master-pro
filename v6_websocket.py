"""
v6_websocket.py — V6 Master Pro | WebSocket Live Prices (P1)
Binance combined stream for all USDT tickers. Falls back to REST.
"""
import json, threading, time, logging
from collections import defaultdict

log = logging.getLogger(__name__)

_ws = None
_price_cache: dict = {}        # symbol -> {"price": float, "ts": float}
_sub_lock = threading.Lock()
_last_ping = 0

def _on_message(ws, message):
    global _last_ping
    try:
        data = json.loads(message)
        if "stream" in data and "data" in data:
            d = data["data"]
            s = d.get("s", "")
            p = float(d.get("c", 0))
            if s and p:
                _price_cache[s] = {"price": p, "ts": time.time()}
        elif "e" in data and data["e"] == "24hrTicker":
            s = data.get("s", "")
            p = float(data.get("c", 0))
            if s and p:
                _price_cache[s] = {"price": p, "ts": time.time()}
        _last_ping = time.time()
    except Exception as e:
        log.debug(f"[WS] msg error: {e}")

def _on_error(ws, error):
    log.warning(f"[WS] error: {error}")

def _on_close(ws, close_status_code, close_msg):
    log.warning(f"[WS] closed: {close_status_code} {close_msg}")

def _on_open(ws):
    log.info("[WS] connected to Binance stream")
    global _last_ping
    _last_ping = time.time()

def start_websocket_feed():
    import websocket
    global _ws
    # Use combined stream for all miniTickers (~300ms updates)
    url = "wss://stream.binance.com:9443/ws/!miniTicker@arr"
    ws = websocket.WebSocketApp(
        url, on_open=_on_open, on_message=_on_message,
        on_error=_on_error, on_close=_on_close
    )
    _ws = ws
    wst = threading.Thread(target=ws.run_forever, kwargs={"ping_interval": 20, "ping_timeout": 10})
    wst.daemon = True
    wst.start()

    # Watchdog: reconnect if no message for 60s
    def watchdog():
        while True:
            time.sleep(30)
            if time.time() - _last_ping > 60:
                log.warning("[WS] Watchdog: reconnecting...")
                try:
                    ws.close()
                except Exception:
                    pass
                time.sleep(2)
                start_websocket_feed()
                break
    threading.Thread(target=watchdog, daemon=True).start()

def get_ws_price(symbol: str) -> float:
    """Return latest WebSocket price or 0 if not yet received."""
    sym = symbol.upper()
    entry = _price_cache.get(sym)
    if entry and time.time() - entry["ts"] < 120:
        return entry["price"]
    return 0.0

def get_all_ws_prices() -> dict:
    """Return snapshot of all cached prices."""
    now = time.time()
    return {s: v["price"] for s, v in _price_cache.items() if now - v["ts"] < 120}
