"""
v6_oco.py — V6 Master Pro | OCO Order Manager (P0)
One-Cancels-Other: LIMIT TP + STOP-LIMIT SL in a single order.
"""
import time, hmac, hashlib, urllib.parse, json, threading, logging
from typing import Optional

log = logging.getLogger(__name__)

class OCOManager:
    def __init__(self, paper_mode: bool = True, fund_limit_usdt: float = 10.0):
        self.paper_mode = paper_mode
        self.fund_limit_usdt = fund_limit_usdt
        self._orders: dict = {}      # order_id -> order dict
        self._lock = threading.Lock()

    def _binance_post(self, path: str, params: dict, api_key: str, secret_key: str):
        import requests as rq
        ts = int(time.time() * 1000)
        params["timestamp"] = ts
        qs = urllib.parse.urlencode(params)
        sig = hmac.new(secret_key.encode(), qs.encode(), hashlib.sha256).hexdigest()
        url = f"https://api.binance.com/api/v3{path}?{qs}&signature={sig}"
        r = rq.post(url, headers={"X-MBX-APIKEY": api_key}, timeout=10)
        return r.json() if r.status_code == 200 else {"ok": False, "error": r.text}

    def place_oco(self, symbol: str, side: str, quantity: float,
                  price: float, stop_price: float, stop_limit_price: float,
                  api_key: str, secret_key: str) -> dict:
        """
        side: BUY or SELL
        price: take-profit limit price
        stop_price: trigger price for stop
        stop_limit_price: limit price once stop triggers
        """
        if self.paper_mode:
            oid = f"OCO-PAPER-{int(time.time()*1000)}"
            rec = {
                "orderId": oid, "symbol": symbol, "side": side.upper(),
                "quantity": quantity, "price": price,
                "stopPrice": stop_price, "stopLimitPrice": stop_limit_price,
                "status": "PAPER_PLACED", "mode": "PAPER",
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            with self._lock:
                self._orders[oid] = rec
            log.info(f"[OCO PAPER] {side} {symbol} Qty:{quantity} TP:{price} SL:{stop_limit_price}")
            return {"ok": True, "order": rec}

        params = {
            "symbol": symbol,
            "side": side.upper(),
            "quantity": round(quantity, 6),
            "price": str(price),
            "stopPrice": str(stop_price),
            "stopLimitPrice": str(stop_limit_price),
            "stopLimitTimeInForce": "GTC",
            "recvWindow": 5000,
        }
        data = self._binance_post("/order/oco", params, api_key, secret_key)
        if "orderListId" in data:
            with self._lock:
                self._orders[data["orderListId"]] = data
            log.info(f"[OCO REAL] {side} {symbol} orderListId={data['orderListId']}")
            return {"ok": True, "order": data}
        return {"ok": False, "error": data.get("msg", str(data))}

    def cancel_oco(self, symbol: str, order_list_id: int,
                   api_key: str, secret_key: str) -> dict:
        if str(order_list_id).startswith("OCO-PAPER"):
            with self._lock:
                self._orders.pop(order_list_id, None)
            return {"ok": True}
        params = {"symbol": symbol, "orderListId": order_list_id}
        data = self._binance_post("/orderList/oco", params, api_key, secret_key)
        return {"ok": "orderListId" in data, "data": data}

    def get_open_orders(self, symbol: Optional[str] = None,
                        api_key: str = "", secret_key: str = "") -> list:
        if self.paper_mode:
            with self._lock:
                return [o for o in self._orders.values() if o.get("status") != "CLOSED"]
        params = {"recvWindow": 5000}
        if symbol:
            params["symbol"] = symbol
        import requests as rq
        ts = int(time.time() * 1000)
        params["timestamp"] = ts
        qs = urllib.parse.urlencode(params)
        sig = hmac.new(secret_key.encode(), qs.encode(), hashlib.sha256).hexdigest()
        url = f"https://api.binance.com/api/v3/openOrderList?{qs}&signature={sig}"
        r = rq.get(url, headers={"X-MBX-APIKEY": api_key}, timeout=10)
        return r.json() if r.status_code == 200 else []

    def list_paper_orders(self) -> list:
        with self._lock:
            return list(self._orders.values())
