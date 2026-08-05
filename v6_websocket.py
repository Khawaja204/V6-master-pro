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
    err_str = str(error)
    if "451" in err_str or "Restricted" in err_str or "legal" in err_str.lower():
        # 451 = Binance blocking this server's IP (geo-restriction).
        # The backoff in _run handles pacing; just log clearly here.
        log.warning("[WS] 451 Restricted Location — server IP is geo-blocked by Binance WebSocket.")
    else:
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
        # Two URLs: port 9443 primary, port 443 fallback (same stream, different port).
        # Some firewalls/proxies block 9443 but allow 443.
        _WS_URLS = [
            "wss://stream.binance.com:9443/ws/!ticker@arr",
            "wss://stream.binance.com:443/ws/!ticker@arr",
        ]
        _url_idx       = 0
        _reconnect_delay = 5        # seconds before next reconnect attempt
        _WS_MAX_BACKOFF  = 300      # cap at 5 minutes (for geo-block scenarios)
        _WS_NORM_BACKOFF = 60       # cap at 1 minute for ordinary errors

        while not _ws_stop.is_set():
            url = _WS_URLS[_url_idx % len(_WS_URLS)]
            geo_blocked = False
            try:
                ws = websocket.WebSocketApp(
                    url,
                    on_open=_on_open,
                    on_message=_on_message,
                    on_error=_on_error,
                    on_close=_on_close,
                )
                ws.run_forever(ping_interval=20, ping_timeout=10)
                # Clean close — reset backoff, rotate to next URL for variety
                _reconnect_delay = 5
                _url_idx += 1
            except Exception as e:
                err_str = str(e)
                if "451" in err_str or "Restricted" in err_str or "legal" in err_str.lower():
                    geo_blocked = True
                    log.warning(
                        f"[WS] HTTP 451 Restricted Location — server IP geo-blocked by "
                        f"Binance WebSocket. Next attempt in {_reconnect_delay}s."
                    )
                    _url_idx += 1  # try the alternate URL/port next
                else:
                    log.warning(f"[WS] connection error: {e}")

            if not _ws_stop.is_set():
                log.info(f"[WS] reconnecting in {_reconnect_delay}s…")
                time.sleep(_reconnect_delay)
                # Progressive backoff: geo-block backs off hard (up to 5 min),
                # ordinary errors back off gently (up to 1 min then reset)
                if geo_blocked:
                    _reconnect_delay = min(_reconnect_delay * 2, _WS_MAX_BACKOFF)
                else:
                    next_delay = min(_reconnect_delay * 2, _WS_NORM_BACKOFF)
                    _reconnect_delay = next_delay if next_delay < _WS_NORM_BACKOFF else 5

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
