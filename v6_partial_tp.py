"""
v6_partial_tp.py — V6 Master Pro | Partial TP Manager (P1)
Auto-scales out of positions at TP1/TP2/TP3 levels.
"""
import time, threading, logging
from typing import List, Dict

log = logging.getLogger(__name__)

class PartialTPManager:
    def __init__(self, config: dict):
        self.cfg = config
        self._positions: List[Dict] = []   # tracked partial-TF positions
        self._lock = threading.Lock()
        self.interval = 60  # check every 60s

    def add_position(self, symbol: str, side: str, entry_price: float,
                     qty: float, tp1: float, tp2: float, tp3: float,
                     sl: float, mode: str = "PAPER", order_id: str = ""):
        """
        side: BUY (we scale out by selling) or SELL (we scale out by buying back)
        """
        rec = {
            "id": order_id or f"PTP-{int(time.time())}-{symbol[:4]}",
            "symbol": symbol, "side": side.upper(), "entry_price": entry_price,
            "remaining_qty": qty, "original_qty": qty,
            "tp1": tp1, "tp2": tp2, "tp3": tp3, "sl": sl,
            "tp1_done": False, "tp2_done": False, "tp3_done": False,
            "sl_hit": False, "mode": mode, "status": "OPEN",
            "pnl_pct": 0.0, "exit_log": [],
        }
        with self._lock:
            self._positions.append(rec)
        log.info(f"[PTP] Added {symbol} {side} qty:{qty} TP1:{tp1} TP2:{tp2} TP3:{tp3}")
        return rec

    def _execute_partial(self, pos: dict, pct: float, price: float, label: str):
        qty_to_close = round(pos["remaining_qty"] * pct, 6)
        pos["remaining_qty"] = round(pos["remaining_qty"] - qty_to_close, 6)
        pnl = (price - pos["entry_price"]) / pos["entry_price"] * 100
        if pos["side"] == "SELL":
            pnl = -pnl
        pos["exit_log"].append({
            "label": label, "price": price, "qty": qty_to_close,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"), "pnl_pct": round(pnl, 3)
        })
        log.info(f"[PTP] {label} {pos['symbol']} @ {price} qty:{qty_to_close} pnl:{pnl:.2f}%")

    def check_and_scale(self, price_fetcher):
        """
        Call this in a loop or from backtest_check_loop.
        price_fetcher: callable(symbol) -> current price
        """
        with self._lock:
            for pos in self._positions:
                if pos["status"] != "OPEN":
                    continue
                sym = pos["symbol"]
                price = price_fetcher(sym)
                if not price:
                    continue

                # SL check first
                if pos["sl"]:
                    if (pos["side"] == "BUY" and price <= pos["sl"]) or \
                       (pos["side"] == "SELL" and price >= pos["sl"]):
                        self._execute_partial(pos, 1.0, price, "SL_CLOSE")
                        pos["status"] = "CLOSED"
                        pos["sl_hit"] = True
                        continue

                # TP3 (25% remaining -> close all)
                if pos["tp3"] and not pos["tp3_done"]:
                    hit = (pos["side"] == "BUY" and price >= pos["tp3"]) or \
                          (pos["side"] == "SELL" and price <= pos["tp3"])
                    if hit:
                        self._execute_partial(pos, 1.0, price, "TP3_CLOSE")
                        pos["tp3_done"] = True
                        pos["status"] = "CLOSED"
                        continue

                # TP2 (close 35% of original)
                if pos["tp2"] and not pos["tp2_done"] and not pos["tp3_done"]:
                    hit = (pos["side"] == "BUY" and price >= pos["tp2"]) or \
                          (pos["side"] == "SELL" and price <= pos["tp2"])
                    if hit:
                        self._execute_partial(pos, 0.35, price, "TP2_PARTIAL")
                        pos["tp2_done"] = True

                # TP1 (close 40% of original)
                if pos["tp1"] and not pos["tp1_done"] and not pos["tp2_done"] and not pos["tp3_done"]:
                    hit = (pos["side"] == "BUY" and price >= pos["tp1"]) or \
                          (pos["side"] == "SELL" and price <= pos["tp1"])
                    if hit:
                        self._execute_partial(pos, 0.40, price, "TP1_PARTIAL")
                        pos["tp1_done"] = True

    def get_positions(self) -> List[Dict]:
        with self._lock:
            return [dict(p) for p in self._positions]

    def start_monitor(self, price_fetcher):
        def loop():
            while True:
                try:
                    self.check_and_scale(price_fetcher)
                except Exception as e:
                    log.warning(f"[PTP] monitor error: {e}")
                time.sleep(self.interval)
        threading.Thread(target=loop, daemon=True, name="ptp-monitor").start()
