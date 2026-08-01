"""
v6_websocket.py — V6 Master Pro P1
Binance WebSocket live price feed. Auto-reconnect. Thread-safe cache.
"""
import threading
import time
import json
import logging

log = logging.getLogger(__name__)

try:
    import websocket
    _HAS_WS = True
except ImportError:
    _HAS_WS = False
    log.warning("[WS] websocket-client not installed — WebSocket feed disabled")

_ws_prices = {}          # symbol -> {"price": float, "ts": float}
_ws_lock = threading.Lock()
_ws_thread = None
_ws_stop = threading.Event()

def _on_message(ws, message):
    try:
        data = json.loads(message)
        if isinstance(data, list):
            for tick in data:
                sym = tick.get("s", "")
                price = float(tick.get("c", 0))
                if sym and price:
                    with _ws_lock:
                        _ws_prices[sym] = {"price": price, "ts": time.time()}
        elif isinstance(data, dict):
            if "c" in data:
                sym = data.get("s", "")
                price = float(data.get("c", 0))
                if sym and price:
                    with _ws_lock:
                        _ws_prices[sym] = {"price": price, "ts": time.time()}
            elif "data" in data:
                d = data["data"]
                sym = d.get("s", "")
                price = float(d.get("c", 0))
                if sym and price:
                    with _ws_lock:
                        _ws_prices[sym] = {"price": price, "ts": time.time()}
    except Exception as e:
        log.debug(f"[WS] message parse error: {e}")

def _on_error(ws, error):
    log.warning(f"[WS] error: {error}")

def _on_close(ws, close_status_code, close_msg):
    log.info(f"[WS] closed ({close_status_code})")

def _on_open(ws):
    log.info("[WS] connected — subscribed to !ticker@arr")

def start_websocket_feed():
    global _ws_thread
    if not _HAS_WS:
        log.warning("[WS] start_websocket_feed() called but websocket-client missing")
        return
    if _ws_thread and _ws_thread.is_alive():
        log.info("[WS] already running")
        return
    _ws_stop.clear()

    def _run():
        url = "wss://stream.binance.com:9443/ws/!ticker@arr"
        while not _ws_stop.is_set():
            try:
                ws = websocket.WebSocketApp(
                    url,
                    on_open=_on_open,
                    on_message=_on_message,
                    on_error=_on_error,
                    on_close=_on_close,
                )
                ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as e:
                log.warning(f"[WS] connection error: {e}")
            if not _ws_stop.is_set():
                log.info("[WS] reconnecting in 5s...")
                time.sleep(5)
        log.info("[WS] thread stopped")

    _ws_thread = threading.Thread(target=_run, daemon=True, name="v6-ws-feed")
    _ws_thread.start()
    log.info("[WS] feed thread started")

def get_ws_price(symbol: str):
    """Return latest WebSocket price, or None if stale (>10s)."""
    with _ws_lock:
        rec = _ws_prices.get(symbol.upper())
    if not rec:
        return None
    if time.time() - rec["ts"] > 10:
        return None
    return rec["price"]

def stop_websocket_feed():
    _ws_stop.set()
