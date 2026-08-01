"""
v6_oco.py — V6 Master Pro | OCO (One-Cancels-Other) Order Manager
Handles Binance SPOT OCO brackets: LIMIT TP + STOP-LOSS
Paper mode simulates; Real mode hits Binance REST API.
"""
import os
import time
import hmac
import hashlib
import urllib.parse
import logging
import requests as _rq
from typing import Optional

log = logging.getLogger(__name__)

# ── Binance hosts (same failover list as logic.py) ──
BINANCE_HOSTS = [
    "https://data-api.binance.vision",
    "https://api-gcp.binance.com",
    "https://api3.binance.com",
    "https://api4.binance.com",
    "https://api.binance.com",
]


class OCOManager:
    """
    OCO Bracket Manager for Binance SPOT.

    In REAL mode: places a genuine OCO order (TP limit + STOP-LOSS limit).
    In PAPER mode: logs the simulated bracket to disk/DB.
    """

    def __init__(self, paper_mode: bool = True, fund_limit_usdt: float = 10.0):
        self.paper_mode = paper_mode
        self.fund_limit_usdt = fund_limit_usdt
        self._paper_oco_log: list = []
        self._load_paper_log()

    # ── Paper Log Persistence ──
    def _load_paper_log(self):
        try:
            import json
            if os.path.exists("v6_oco_paper.json"):
                with open("v6_oco_paper.json") as f:
                    self._paper_oco_log = json.load(f)
        except Exception as e:
            log.debug(f"[OCO] paper log load failed: {e}")

    def _save_paper_log(self):
        try:
            import json
            with open("v6_oco_paper.json", "w") as f:
                json.dump(self._paper_oco_log[-200:], f, indent=2)
        except Exception as e:
            log.debug(f"[OCO] paper log save failed: {e}")

    # ── Public API ──
    def place_oco(self, symbol: str, side: str, quantity: float,
                  price: float, stop_price: float, stop_limit_price: float,
                  api_key: str = "", secret_key: str = "",
                  time_in_force: str = "GTC") -> dict:
        """
        Place an OCO bracket on Binance SPOT.

        Args:
            symbol: e.g. "BTCUSDT"
            side: "SELL" (for TP/SL after a BUY entry)
            quantity: coin qty to sell
            price: LIMIT price for the take-profit leg
            stop_price: trigger price for stop-loss
            stop_limit_price: execution price once stop triggers
            api_key / secret_key: Binance API credentials

        Returns:
            {"ok": True, "order_list_id": int, "data": {...}}
            {"ok": False, "error": str, "paper": bool}
        """
        if self.paper_mode:
            return self._paper_oco(symbol, side, quantity, price, stop_price, stop_limit_price)

        if not api_key or not secret_key:
            return {"ok": False, "error": "Missing Binance API key/secret for OCO", "paper": False}

        if quantity <= 0 or price <= 0 or stop_price <= 0 or stop_limit_price <= 0:
            return {"ok": False, "error": "Invalid OCO params (must be > 0)", "paper": False}

        return self._real_oco(symbol, side, quantity, price, stop_price,
                              stop_limit_price, api_key, secret_key, time_in_force)

    # ── Paper Simulation ──
    def _paper_oco(self, symbol: str, side: str, quantity: float,
                   price: float, stop_price: float, stop_limit_price: float) -> dict:
        rec = {
            "id": f"OCO-PAPER-{int(time.time())}",
            "symbol": symbol,
            "side": side.upper(),
            "quantity": round(quantity, 6),
            "tp_price": round(price, 8),
            "stop_price": round(stop_price, 8),
            "stop_limit_price": round(stop_limit_price, 8),
            "status": "SIMULATED (PAPER)",
            "time": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 5 * 3600)),
        }
        self._paper_oco_log.append(rec)
        if len(self._paper_oco_log) > 200:
            self._paper_oco_log = self._paper_oco_log[-200:]
        self._save_paper_log()
        log.info(f"[OCO PAPER] {symbol} {side} Qty:{quantity} TP:{price} SL:{stop_price}")
        return {"ok": True, "paper": True, "order_list_id": rec["id"], "data": rec}

    # ── Real Binance OCO ──
    def _real_oco(self, symbol: str, side: str, quantity: float,
                  price: float, stop_price: float, stop_limit_price: float,
                  api_key: str, secret_key: str, time_in_force: str) -> dict:
        ts = int(time.time() * 1000)
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "quantity": round(quantity, 6),
            "price": round(price, 8),
            "stopPrice": round(stop_price, 8),
            "stopLimitPrice": round(stop_limit_price, 8),
            "stopLimitTimeInForce": time_in_force,
            "timestamp": ts,
        }
        qs = urllib.parse.urlencode(params)
        sig = hmac.new(secret_key.encode(), qs.encode(), hashlib.sha256).hexdigest()
        url = f"{BINANCE_HOSTS[-1]}/api/v3/order/oco?{qs}&signature={sig}"

        last_err = ""
        for host in BINANCE_HOSTS:
            try:
                resp = _rq.post(
                    f"{host}/api/v3/order/oco?{qs}&signature={sig}",
                    headers={"X-MBX-APIKEY": api_key},
                    timeout=10,
                )
                data = resp.json()
                if resp.status_code == 200:
                    log.info(f"[OCO REAL] {symbol} orderListId={data.get('orderListId')}"
                             f" TP:{price} SL:{stop_price}")
                    return {
                        "ok": True,
                        "paper": False,
                        "order_list_id": data.get("orderListId"),
                        "data": data,
                    }
                # Binance error format
                if "code" in data:
                    last_err = f"Binance {data.get('code')}: {data.get('msg', 'Unknown')}"
                    # If it's a non-retryable error (e.g. insufficient balance), break immediately
                    if data.get("code") in [-2010, -2011, -1013]:  # insufficient balance, etc.
                        break
                else:
                    last_err = f"HTTP {resp.status_code}"
            except Exception as e:
                last_err = str(e)
                continue

        log.warning(f"[OCO REAL] Failed for {symbol}: {last_err}")
        return {"ok": False, "error": last_err, "paper": False}

    def get_paper_log(self) -> list:
        """Return simulated OCO history for admin dashboard."""
        return self._paper_oco_log[:]

    def cancel_all_oco(self, api_key: str = "", secret_key: str = "") -> dict:
        """Emergency: cancel ALL open OCO orders on Binance."""
        if self.paper_mode:
            cleared = len(self._paper_oco_log)
            self._paper_oco_log = []
            self._save_paper_log()
            return {"ok": True, "paper": True, "cancelled": cleared}

        if not api_key or not secret_key:
            return {"ok": False, "error": "No API keys"}

        ts = int(time.time() * 1000)
        params = {"timestamp": ts}
        qs = urllib.parse.urlencode(params)
        sig = hmac.new(secret_key.encode(), qs.encode(), hashlib.sha256).hexdigest()

        for host in BINANCE_HOSTS:
            try:
                resp = _rq.delete(
                    f"{host}/api/v3/openOrderList?{qs}&signature={sig}",
                    headers={"X-MBX-APIKEY": api_key},
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    log.info(f"[OCO CANCEL] All open OCOs cancelled: {len(data)} lists")
                    return {"ok": True, "cancelled": len(data), "data": data}
            except Exception as e:
                log.warning(f"[OCO CANCEL] {host} failed: {e}")
                continue
        return {"ok": False, "error": "Failed to cancel OCOs on all hosts"}
