"""
v6_partial_tp.py — V6 Master Pro P1
Partial Take-Profit Manager. Auto scale-out at TP1/TP2/TP3.
"""
import threading
import time
import logging

log = logging.getLogger(__name__)

class PartialTPManager:
    def __init__(self, config: dict):
        self.config = config
        self.positions = []
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.monitor_thread = None
        self._price_fn = None

        tm = config.get("trade_management", {})
        self.tp1_pct = tm.get("partial_tp1_pct", 25)
        self.tp2_pct = tm.get("partial_tp2_pct", 35)
        self.tp3_pct = tm.get("partial_tp3_pct", 40)
        self.check_interval = tm.get("partial_tp_check_seconds", 10)

    def add_position(self, symbol: str, side: str, entry_price: float,
                     qty: float, tp1: float, tp2: float, tp3: float,
                     sl: float, mode: str = "PAPER", order_id: str = ""):
        pos = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "entry_price": entry_price,
            "qty": qty,
            "remaining_qty": qty,
            "tp1": tp1, "tp2": tp2, "tp3": tp3, "sl": sl,
            "tp1_hit": False, "tp2_hit": False, "tp3_hit": False, "sl_hit": False,
            "mode": mode,
            "order_id": order_id,
            "entry_time": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 5 * 3600)),
            "entry_ts": time.time(),
            "partial_closes": [],
        }
        with self.lock:
            self.positions.append(pos)
        log.info(f"[PTP] Added {mode} {symbol} qty={qty} TP1={tp1} TP2={tp2} TP3={tp3}")
        return pos

    def get_positions(self):
        with self.lock:
            return [dict(p) for p in self.positions]

    def start_monitor(self, price_fn):
        self._price_fn = price_fn
        if self.monitor_thread and self.monitor_thread.is_alive():
            return
        self.stop_event.clear()
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True, name="v6-ptp")
        self.monitor_thread.start()
        log.info("[PTP] monitor started")

    def _monitor_loop(self):
        while not self.stop_event.is_set():
            try:
                self._check_positions()
            except Exception as e:
                log.error(f"[PTP] check error: {e}")
            time.sleep(self.check_interval)

    def _check_positions(self):
        with self.lock:
            positions = list(self.positions)

        for pos in positions:
            if pos["sl_hit"] or (pos["tp3_hit"] and pos["remaining_qty"] <= 0):
                continue

            price = self._price_fn(pos["symbol"]) if self._price_fn else None
            if not price:
                continue

            side = pos["side"]
            remaining = pos["remaining_qty"]
            if remaining <= 0:
                continue

            # SL check
            if pos["sl"] and not pos["sl_hit"]:
                hit = (side == "BUY" and price <= pos["sl"]) or (side == "SELL" and price >= pos["sl"])
                if hit:
                    self._execute_partial_close(pos, remaining, price, "SL")
                    pos["sl_hit"] = True
                    pos["remaining_qty"] = 0
                    continue

            # TP3 (close all remaining)
            if pos["tp3"] and not pos["tp3_hit"]:
                hit = (side == "BUY" and price >= pos["tp3"]) or (side == "SELL" and price <= pos["tp3"])
                if hit:
                    self._execute_partial_close(pos, remaining, price, "TP3")
                    pos["tp3_hit"] = True
                    pos["remaining_qty"] = 0
                    continue

            # TP2
            if pos["tp2"] and not pos["tp2_hit"]:
                hit = (side == "BUY" and price >= pos["tp2"]) or (side == "SELL" and price <= pos["tp2"])
                if hit:
                    close_qty = remaining * (self.tp2_pct / 100.0)
                    self._execute_partial_close(pos, close_qty, price, "TP2")
                    pos["tp2_hit"] = True
                    pos["remaining_qty"] -= close_qty
                    continue

            # TP1
            if pos["tp1"] and not pos["tp1_hit"]:
                hit = (side == "BUY" and price >= pos["tp1"]) or (side == "SELL" and price <= pos["tp1"])
                if hit:
                    close_qty = remaining * (self.tp1_pct / 100.0)
                    self._execute_partial_close(pos, close_qty, price, "TP1")
                    pos["tp1_hit"] = True
                    pos["remaining_qty"] -= close_qty
                    continue

    def _execute_partial_close(self, pos, qty, price, reason):
        qty = round(qty, 6)
        if qty <= 0:
            return

        if pos["side"] == "BUY":
            pnl = (price - pos["entry_price"]) / pos["entry_price"] * 100
        else:
            pnl = (pos["entry_price"] - price) / pos["entry_price"] * 100

        close_rec = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 5 * 3600)),
            "reason": reason,
            "price": price,
            "qty": qty,
            "pnl_pct": round(pnl, 3),
        }
        pos.setdefault("partial_closes", []).append(close_rec)
        log.info(f"[PTP] {reason} close {pos['mode']} {pos['symbol']} qty={qty} @ {price} (PnL {pnl:.2f}%)")

        if pos["mode"] == "REAL":
            log.warning(f"[PTP] REAL partial close logged only — integrate exchange sell order here: {pos['symbol']} {reason} qty={qty}")

    def stop(self):
        self.stop_event.set()
