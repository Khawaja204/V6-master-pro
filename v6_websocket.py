"""
v6_websocket.py — V6 Master Pro
Binance WebSocket live price feed with:
  • HTTP/SOCKS5 proxy support  (BINANCE_WS_PROXY or BINANCE_PROXY env var)
  • Exponential backoff on geo-block (HTTP 451)
  • Automatic REST polling fallback when WS is consistently blocked
  • Thread-safe price cache shared with logic.py via get_ws_price()
  • Status reporting via get_ws_status()
"""
import os
import threading
import time
import json
import logging
from urllib.parse import urlparse

log = logging.getLogger(__name__)

try:
    import websocket
    _HAS_WS = True
except ImportError:
    _HAS_WS = False
    log.warning("[WS] websocket-client not installed — REST poll fallback will be used")

# ── Proxy configuration ────────────────────────────────────────────────────────
# BINANCE_WS_PROXY takes precedence; falls back to BINANCE_PROXY if not set.
# websocket-client supports HTTP proxies natively.
# SOCKS5 proxies require: pip install websocket-client[optional] PySocks
BINANCE_WS_PROXY: str = os.getenv("BINANCE_WS_PROXY", os.getenv("BINANCE_PROXY", "")).strip()

_ws_proxy_host: str   = ""
_ws_proxy_port: int   = 0
_ws_proxy_auth: tuple = ()

if BINANCE_WS_PROXY:
    try:
        _p = urlparse(BINANCE_WS_PROXY)
        _ws_proxy_host = _p.hostname or ""
        _ws_proxy_port = _p.port or 8080
        _ws_proxy_auth = (_p.username, _p.password) if _p.username else ()
        log.info(f"[WS] Proxy configured → {_ws_proxy_host}:{_ws_proxy_port}")
    except Exception as _pe:
        log.warning(f"[WS] Could not parse BINANCE_WS_PROXY (ignored): {_pe}")

# ── WebSocket stream URLs ──────────────────────────────────────────────────────
# Port 9443 = Binance standard WS port.
# Port 443  = HTTPS port, harder to geo-block; same stream, different port.
_WS_URLS = [
    "wss://stream.binance.com:9443/ws/!ticker@arr",
    "wss://stream.binance.com:443/ws/!ticker@arr",
]

# ── Shared price cache ─────────────────────────────────────────────────────────
_ws_prices: dict = {}       # symbol → {"price": float, "ts": float, "src": str}
_ws_lock = threading.Lock()
_ws_thread = None
_ws_stop = threading.Event()

# ── Feed status ────────────────────────────────────────────────────────────────
_ws_status: dict = {
    "mode":      "starting",  # "websocket" | "rest_poll" | "blocked" | "starting"
    "last_ok":   0.0,         # epoch of last successful price update
    "geo_fails": 0,           # consecutive geo-block (451) errors
}


# ── WebSocket callbacks ────────────────────────────────────────────────────────

def _on_message(ws, message):
    try:
        data = json.loads(message)
        now  = time.time()
        if isinstance(data, list):
            ticks = data
        elif isinstance(data, dict) and "data" in data:
            ticks = [data["data"]]
        elif isinstance(data, dict) and "c" in data:
            ticks = [data]
        else:
            return
        with _ws_lock:
            for tick in ticks:
                sym   = tick.get("s", "")
                price = float(tick.get("c") or 0)
                if sym and price:
                    _ws_prices[sym] = {"price": price, "ts": now, "src": "ws"}
        _ws_status["last_ok"]   = now
        _ws_status["mode"]      = "websocket"
        _ws_status["geo_fails"] = 0   # reset on live data
    except Exception as e:
        log.debug(f"[WS] message parse error: {e}")


def _on_error(ws, error):
    err_str = str(error)
    if "451" in err_str or "Restricted" in err_str or "legal" in err_str.lower():
        _ws_status["geo_fails"] += 1
        log.warning(
            f"[WS] HTTP 451 geo-block (#{_ws_status['geo_fails']}) — "
            "server IP blocked by Binance WebSocket."
        )
    else:
        log.warning(f"[WS] error: {error}")


def _on_close(ws, close_status_code, close_msg):
    log.info(f"[WS] closed (code={close_status_code})")


def _on_open(ws):
    _ws_status["geo_fails"] = 0
    log.info("[WS] connected — subscribed to !ticker@arr")


# ── REST polling fallback ──────────────────────────────────────────────────────

def _rest_poll_prices() -> int:
    """Fetch all USDT prices via data-api.binance.vision (CDN, less geo-blocked).
    Routes through BINANCE_WS_PROXY if configured. Returns count of prices updated."""
    try:
        import requests as _rq
        proxy_dict = (
            {"http": BINANCE_WS_PROXY, "https": BINANCE_WS_PROXY}
            if BINANCE_WS_PROXY else None
        )
        resp = _rq.get(
            "https://data-api.binance.vision/api/v3/ticker/price",
            timeout=8,
            proxies=proxy_dict,
        )
        if resp.status_code == 200:
            now   = time.time()
            count = 0
            with _ws_lock:
                for tick in resp.json():
                    sym   = tick.get("symbol", "")
                    price = float(tick.get("price") or 0)
                    if sym and price and sym.endswith("USDT"):
                        _ws_prices[sym] = {"price": price, "ts": now, "src": "rest"}
                        count += 1
            _ws_status["last_ok"] = now
            _ws_status["mode"]    = "rest_poll"
            return count
        elif resp.status_code == 451:
            log.warning(
                "[WS-POLL] data-api.binance.vision also returned 451 — "
                "all Binance endpoints geo-blocked. Set BINANCE_PROXY to bypass."
            )
            _ws_status["mode"] = "blocked"
    except Exception as e:
        log.debug(f"[WS-POLL] REST poll error: {e}")
    return 0


def _rest_poll_loop():
    """Background REST polling. Activated when WebSocket is consistently unavailable.
    Stops automatically if WebSocket reconnects successfully."""
    log.info("[WS-POLL] REST price polling fallback activated (every 3s)")
    while not _ws_stop.is_set():
        # Yield back to WebSocket if it has recovered
        if _ws_status["mode"] == "websocket" and _ws_status["geo_fails"] == 0:
            log.info("[WS-POLL] WebSocket recovered — stopping REST poll fallback")
            break
        count = _rest_poll_prices()
        if count > 0:
            log.debug(f"[WS-POLL] Updated {count} prices via REST")
        time.sleep(3)
    log.info("[WS-POLL] REST polling stopped")


# ── Main feed ──────────────────────────────────────────────────────────────────

def start_websocket_feed():
    """Start the live price feed. Tries WebSocket first; falls back to REST polling."""
    global _ws_thread
    if not _HAS_WS:
        log.warning("[WS] websocket-client not installed — starting REST poll fallback")
        _ws_stop.clear()
        threading.Thread(target=_rest_poll_loop, daemon=True, name="v6-rest-poll").start()
        return
    if _ws_thread and _ws_thread.is_alive():
        log.info("[WS] already running")
        return
    _ws_stop.clear()

    def _run():
        _url_idx          = 0
        _reconnect_delay  = 5         # seconds before next attempt
        _WS_MAX_BACKOFF   = 300       # 5-minute cap for geo-block scenarios
        _WS_NORM_BACKOFF  = 60        # 1-minute cap for ordinary errors
        _GEO_FAIL_THRESH  = 4         # consecutive geo-fails before REST fallback
        _rest_poll_thread = None

        while not _ws_stop.is_set():

            # ── Geo-block threshold reached: activate REST polling ─────────────
            if _ws_status["geo_fails"] >= _GEO_FAIL_THRESH:
                if _rest_poll_thread is None or not _rest_poll_thread.is_alive():
                    _rest_poll_thread = threading.Thread(
                        target=_rest_poll_loop, daemon=True, name="v6-rest-poll"
                    )
                    _rest_poll_thread.start()
                # Keep retrying WS in the background — very slowly
                log.info(
                    f"[WS] Geo-blocked ×{_ws_status['geo_fails']} — "
                    f"REST polling active. WS retry in {_reconnect_delay}s…"
                )
                time.sleep(_reconnect_delay)
                _reconnect_delay = min(_reconnect_delay * 2, _WS_MAX_BACKOFF)
                _url_idx += 1
                continue

            url         = _WS_URLS[_url_idx % len(_WS_URLS)]
            geo_blocked = False

            try:
                # ── Proxy kwargs (HTTP only — websocket-client native support) ──
                proxy_kwargs: dict = {}
                if _ws_proxy_host:
                    proxy_kwargs["http_proxy_host"] = _ws_proxy_host
                    proxy_kwargs["http_proxy_port"] = _ws_proxy_port
                    if _ws_proxy_auth:
                        proxy_kwargs["http_proxy_auth"] = _ws_proxy_auth

                ws = websocket.WebSocketApp(
                    url,
                    on_open=_on_open,
                    on_message=_on_message,
                    on_error=_on_error,
                    on_close=_on_close,
                )
                ws.run_forever(ping_interval=20, ping_timeout=10, **proxy_kwargs)
                # Clean close — reset backoff, rotate URL for variety
                _reconnect_delay = 5
                _url_idx += 1

            except Exception as e:
                err_str = str(e)
                if "451" in err_str or "Restricted" in err_str or "legal" in err_str.lower():
                    geo_blocked = True
                    _ws_status["geo_fails"] += 1
                    log.warning(
                        f"[WS] HTTP 451 geo-block (#{_ws_status['geo_fails']}) "
                        f"on {url}. Next attempt in {_reconnect_delay}s."
                    )
                    _url_idx += 1   # rotate to alternate port/URL
                else:
                    log.warning(f"[WS] connection error: {e}")

            if not _ws_stop.is_set():
                log.info(f"[WS] reconnecting in {_reconnect_delay}s…")
                time.sleep(_reconnect_delay)
                if geo_blocked:
                    _reconnect_delay = min(_reconnect_delay * 2, _WS_MAX_BACKOFF)
                else:
                    # Gentle growth for ordinary errors; reset after cap
                    next_d = min(_reconnect_delay * 2, _WS_NORM_BACKOFF)
                    _reconnect_delay = next_d if next_d < _WS_NORM_BACKOFF else 5

        log.info("[WS] thread stopped")

    _ws_thread = threading.Thread(target=_run, daemon=True, name="v6-ws-feed")
    _ws_thread.start()
    log.info("[WS] feed thread started")


# ── Public API ─────────────────────────────────────────────────────────────────

def get_ws_price(symbol: str, max_age: float = 10.0):
    """Return latest price for symbol, or None if missing / older than max_age seconds."""
    with _ws_lock:
        rec = _ws_prices.get(symbol.upper())
    if not rec:
        return None
    if time.time() - rec["ts"] > max_age:
        return None
    return rec["price"]


def get_ws_status() -> dict:
    """Return feed status: mode ('websocket'|'rest_poll'|'blocked'|'starting'),
    last_ok (epoch), geo_fails (consecutive 451 count)."""
    return dict(_ws_status)


def stop_websocket_feed():
    """Signal all feed threads (WebSocket + REST poll) to stop."""
    _ws_stop.set()
