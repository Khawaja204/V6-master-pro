"""Trade execution functions for V6 Master Pro.

State remains owned by main.py; the decorator synchronizes references at call time
so extraction does not create duplicate ledgers or circular imports.
"""
import functools
import sys


_EXTRACTED_NAMES = {
    "_execute_paper_trade", "_execute_real_binance_spot",
    "_execute_real_binance_spot_grid", "_execution_guard",
    "_save_paper_trades", "_record_backtest_signal",
    "_record_whale_copy_trade", "_save_whale_copy_trades",
    "_save_combo_trades",
}
_LEDGER_NAMES = ("BACKTEST_SIGNALS", "WHALE_COPY_TRADES", "PAPER_TRADES", "COMBO_TRADES")

def _with_main_state(fn):
    """Bind dependency names to the live main-module objects for each call."""
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        main = sys.modules.get("main")
        if main is None:
            raise RuntimeError("main module is not loaded")
        local_names = set(globals()) | _EXTRACTED_NAMES
        for name, value in vars(main).items():
            if name not in _EXTRACTED_NAMES and name not in {"wrapped", "fn"}:
                globals()[name] = value
        result = fn(*args, **kwargs)
        for name in _LEDGER_NAMES:
            if name in globals() and hasattr(main, name):
                setattr(main, name, globals()[name])
        return result
    return wrapped


@_with_main_state
def _save_whale_copy_trades():
    try:
        with open(_WC_TRADES_FILE, "w") as f:
            json.dump(WHALE_COPY_TRADES[-500:], f, indent=2)
    except Exception as e:
        log.debug(f"Whale copy trades save failed: {e}")
    if _V6_UPGRADE:
        try:
            _db_save("whale_copy_trades", WHALE_COPY_TRADES[-500:])
        except Exception as e:
            log.debug(f"[V6 DB] whale_copy_trades save failed: {e}")


@_with_main_state
def _save_paper_trades():
    try:
        with open(_TRADES_FILE, "w") as f:
            json.dump(PAPER_TRADES[-500:], f, indent=2)
    except Exception as e:
        log.debug(f"Paper trades save failed: {e}")
    if _V6_UPGRADE:
        try:
            _db_save("paper_trades", PAPER_TRADES[-500:])
        except Exception as e:
            log.debug(f"[V6 DB] paper_trades save failed: {e}")


@_with_main_state
def _record_whale_copy_trade(sig: dict):
    """WHALE COPY MODE — separate paper-trade ledger, independent of the
    v6-score auto-trade system. Fires on a wall+OBI-confirmed COPY_BUY
    (confirmed across 2 consecutive scan cycles) above the confidence
    threshold. 30-min dedup per symbol + the shared daily circuit-breaker
    both still apply. Trades stay OPEN until whale_copy_check_loop resolves
    them against the SL/target levels."""
    global WHALE_COPY_TRADES
    if not _entries_allowed("wall") or not _weekly_entries_allowed("wall"):
        return None
    sym = sig["symbol"]
    _held_by = _symbol_open_elsewhere(sym, "wall")
    if _held_by:
        log.info(f"[EXPOSURE-GUARD] {sym} WALL entry skipped — already OPEN on {_held_by} bot")
        return None
    now = time.time()
    if now - _wc_dedup.get(sym, 0) < 1800:
        return None
    # Guard against duplicate OPEN entries even after a redeploy resets the
    # in-memory dedup timer above — never record a second OPEN trade for a
    # symbol that already has one.
    if any(t.get("symbol") == sym and t.get("status") == "OPEN" for t in WHALE_COPY_TRADES):
        return None
    with _ledger_lock:
        _wc_dedup[sym] = now
    _long_liq  = sig.get("long_liq_usdt", 0)
    _short_liq = sig.get("short_liq_usdt", 0)
    if _short_liq >= _long_liq and _short_liq > 0:
        _liq_status = f"Short-Liq ${_short_liq:,.0f}"
    elif _long_liq > 0:
        _liq_status = f"Long-Liq ${_long_liq:,.0f}"
    else:
        _liq_status = "N/A"
    entry = {
        "id":             f"WC-{int(now)}-{sym[:4]}",
        "symbol":         sym,
        "direction":      sig["direction"],
        "entry_price":    sig.get("price", sig["wall_price"]),
        "wall_price":     sig["wall_price"],
        "wall_size_usdt": sig["wall_size_usdt"],
        "wall_qty":       sig["wall_qty"],
        "stop_loss":      sig.get("stop_loss", 0),
        "original_sl":    sig.get("stop_loss", 0),
        "trailing":       "",
        "target":         sig.get("target", 0),
        "obi":            sig["obi"],
        "obi_velocity":   sig["obi_velocity"],
        "confidence":     sig["confidence"],
        "funding_rate":   sig.get("funding_rate", 0),
        "liq_status":     _liq_status,
        "eta":            sig.get("eta", "—"),
        "entry_time":     _pkt_ts(),
        "entry_ts":       now,
        "mode":           "PAPER (WHALE COPY)",
        "status":         "OPEN",
        "exit_price":     None,
        "exit_time":      None,
        "result":         None,
        "pnl_pct":        None,
    }
    with _ledger_lock:
        WHALE_COPY_TRADES.insert(0, entry)
        if len(WHALE_COPY_TRADES) > 500:
            WHALE_COPY_TRADES.pop()
    _save_whale_copy_trades()
    _record_trade_open("wall")
    log.info(f"[WHALE COPY] {sig['direction']} {sym} @ {sig['wall_price']} (conf {sig['confidence']}%)")
    if sig["direction"] == "COPY_BUY":
        wc_msg = (f"🐋 <b>WHALE COPY BUY — {sym.replace('USDT','')}</b>\n"
                  f"Wall Price: {_fmtP(sig['wall_price'])} | Size: ${sig['wall_size_usdt']:,.0f}\n"
                  f"🎯 Target: {_fmtP(sig['target'])} | 🛡 SL: {_fmtP(sig['stop_loss'])}\n"
                  f"⏱ Est. Time to Target: {sig.get('eta','—')}\n"
                  f"Confidence: {sig['confidence']}% | OBI: {sig['obi']}\n"
                  f"💰 Funding Rate: {sig.get('funding_rate',0)}% | Liq Status: {_liq_status}\n"
                  f"📋 Wall + OBI confirmed — strict 3-scan-cycle architecture, independent of V6")
        notify_all(f"V6 Whale Copy BUY — {sym.replace('USDT','')}", wc_msg)
    return entry


@_with_main_state
def _execute_paper_trade(symbol: str, side: str, amount_usdt: float,
                          strategy: str, manual: bool = False,
                          reason: str = "") -> dict:
    """Simulate a trade — records result, no real money moved."""
    from logic import fetch_ticker_price as _ftp
    price = _ftp(symbol)
    if not price:
        return {"ok": False, "error": "Cannot fetch current price for simulation"}
    qty      = round(amount_usdt / price, 6) if price else 0
    trade_id = f"PT-{int(time.time())}-{symbol[:4]}"
    rec = {
        "id":          trade_id,
        "symbol":      symbol,
        "side":        side.upper(),
        "strategy":    strategy,
        "amount_usdt": amount_usdt,
        "price":       price,
        "qty":         qty,
        "mode":        "PAPER",
        "manual":      manual,
        "reason":      reason or ("Manual admin trade" if manual else "Auto trade"),
        "status":      "FILLED (SIMULATED)",
        "time":        _pkt_ts(),
    }
    with _ledger_lock:
        PAPER_TRADES.insert(0, rec)
        if len(PAPER_TRADES) > 500:
            PAPER_TRADES.pop()
    _save_paper_trades()
    log.info(f"[PAPER TRADE] {side} {amount_usdt} USDT of {symbol} @ {price} ({strategy})")
    return {"ok": True, "trade": rec}


@_with_main_state
def _record_backtest_signal(symbol: str, entry_price: float, folder: str,
                            tp_zones: dict, confidence: int,
                            traffic: str = "", reason: str = "",
                            score_breakdown: dict = None):
    """Record signal as a tracked entry. Returns the entry dict, or None if the
    entry was filtered out (GREEN-only rule, circuit-breaker, or dedup window).
    Dedup: same coin not tracked twice in 30 min."""
    global BACKTEST_SIGNALS
    tm = CONFIG.get("trade_management", {})

    # ── GREEN-only entries: skip RED signals; allow YELLOW in paper mode ────────
    paper = GLOBAL_DATA.get("paper_mode", True)
    if tm.get("green_only_entries", True) and traffic:
        if traffic == "RED":
            return None                           # always skip RED
        if traffic == "YELLOW" and not paper:
            return None                           # skip YELLOW in real mode only
    # ── Daily circuit-breaker: no new entries once tripped ────────────────────
    if not _entries_allowed("v6") or not _weekly_entries_allowed("v6"):
        return None
    _held_by = _symbol_open_elsewhere(symbol, "v6")
    if _held_by:
        log.info(f"[EXPOSURE-GUARD] {symbol} V6 entry skipped — already OPEN on {_held_by} bot")
        return None

    now = time.time()
    with _ledger_lock:
        if now - _bt_dedup.get(symbol, 0) < 1800:
            return None
        _bt_dedup[symbol] = now

    sl = tp_zones.get("stop_loss", 0)
    entry = {
        "id":          f"{symbol}_{int(now)}",
        "symbol":      symbol,
        "folder":      folder,
        "entry_price": entry_price,
        "entry_time":  _pkt_ts(),
        "entry_ts":    now,
        "tp1":         tp_zones.get("tp1", 0),
        "tp2":         tp_zones.get("tp2", 0),
        "tp3":         tp_zones.get("tp3", 0),
        "stop_loss":   sl,
        "original_sl": sl,          # preserved for trailing-stop display
        "trailing":    "",          # "" | "BREAKEVEN" | "TP1"
        "traffic":     traffic,
        "reason":      reason or f"{folder} signal | conf {confidence}%",
        "confidence":  confidence,
        "status":      "OPEN",
        "tp1_hit":     False,
        "tp2_hit":     False,
        "tp3_hit":     False,
        "sl_hit":      False,
        "exit_price":  None,
        "exit_time":   None,
        "result":      None,   # WIN / LOSS / TIMEOUT / STALE_EXIT
        "pnl_pct":     None,
        "score_breakdown": json.dumps(score_breakdown) if score_breakdown else None,
        "price_source":    "rest_scan",  # entry_price comes from the scan cycle's REST ticker data
    }
    with _ledger_lock:
        BACKTEST_SIGNALS.insert(0, entry)
        if len(BACKTEST_SIGNALS) > 100:
            BACKTEST_SIGNALS = BACKTEST_SIGNALS[:100]
        GLOBAL_DATA["backtest"] = BACKTEST_SIGNALS
    _record_trade_open("v6")
    return entry


@_with_main_state
def _execute_real_binance_spot_grid(symbol: str, amount_usdt: float,
                                     levels: int = 5, spacing_pct: float = 0.5) -> dict:
    """Place a grid of LIMIT BUY orders below current price on Binance.
    Runs through _execution_guard() first for staleness protection."""
    ex = "BINANCE"
    if ex not in _API_KEYS:
        return {"ok": False, "error": "No Binance API key configured"}
    guard = _execution_guard(symbol)
    if not guard["ok"]:
        log.warning(f"[EXEC-GUARD] {symbol} GRID blocked: {guard['error']}")
        audit("SYSTEM", "EXEC_GUARD_BLOCK", "BLOCKED", f"sym={symbol} side=GRID err={guard['error']}")
        return {"ok": False, "error": f"Execution guard: {guard['error']}"}
    price = guard["price"]
    if not price:
        return {"ok": False, "error": "Cannot fetch current price for grid"}
    try:
        import hmac as _hmac, hashlib as _hl, urllib.parse as _up
        import requests as _rq
        key = _API_KEYS[ex]["api_key"]
        sec = _API_KEYS[ex]["secret_key"]
        per_level = amount_usdt / levels
        results   = []
        for i in range(1, levels + 1):
            lvl_price = round(price * (1 - spacing_pct / 100 * i), 8)
            qty       = round(per_level / lvl_price, 6)
            ts        = int(time.time() * 1000)
            params    = {
                "symbol":      symbol, "side": "BUY", "type": "LIMIT",
                "timeInForce": "GTC",  "price": lvl_price,
                "quantity":    qty,    "timestamp": ts,
            }
            qs  = _up.urlencode(params)
            sig = _hmac.new(sec.encode(), qs.encode(), _hl.sha256).hexdigest()
            r   = _rq.post(
                f"https://api.binance.com/api/v3/order?{qs}&signature={sig}",
                headers={"X-MBX-APIKEY": key}, timeout=10
            )
            data = r.json()
            results.append({
                "level": i, "price": lvl_price, "qty": qty,
                "ok":    r.status_code == 200,
                "order_id": data.get("orderId"),
                "error": data.get("msg", "") if r.status_code != 200 else ""
            })
        ok = any(r["ok"] for r in results)
        log.info(f"[REAL GRID] {symbol} {levels} levels × ${per_level:.2f} — ok={ok}")
        return {"ok": ok, "grid_orders": results, "levels": levels, "symbol": symbol}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@_with_main_state
def _execution_guard(symbol: str, expected_price: float = None) -> dict:
    """Pre-trade guard for REAL orders — protects against stale prices and
    excessive slippage before any exchange order is placed.
    Config: execution_guard.max_slippage_pct / max_order_delay_seconds.
    Returns {"ok", "price", "error"}."""
    eg = CONFIG.get("execution_guard", {})
    max_slip  = eg.get("max_slippage_pct", 0.3)
    max_delay = eg.get("max_order_delay_seconds", 5)

    t0 = time.time()
    live_price = fetch_ticker_price(symbol)
    fetch_elapsed = time.time() - t0

    if not live_price:
        return {"ok": False, "price": 0, "error": "Could not fetch a live price for guard check"}

    if fetch_elapsed > max_delay:
        return {"ok": False, "price": live_price,
                "error": f"Price fetch took {fetch_elapsed:.2f}s > {max_delay}s limit — aborting stale execution"}

    if expected_price and expected_price > 0:
        slip_pct = abs(live_price - expected_price) / expected_price * 100
        if slip_pct > max_slip:
            return {"ok": False, "price": live_price,
                    "error": f"Slippage {slip_pct:.3f}% > {max_slip}% limit (expected {expected_price}, live {live_price})"}

    return {"ok": True, "price": live_price, "error": ""}


@_with_main_state
def _execute_real_binance_spot(symbol: str, side: str, amount_usdt: float, expected_price: float = None) -> dict:
    """Execute a real Binance MARKET order via REST API (HMAC-signed).
    Runs through _execution_guard() first — aborts on stale price fetch
    or excessive slippage vs. the signal's expected entry price."""
    ex = "BINANCE"
    if ex not in _API_KEYS:
        return {"ok": False, "error": "No Binance API key configured in Admin Portal → API Key Management"}
    guard = _execution_guard(symbol, expected_price)
    if not guard["ok"]:
        log.warning(f"[EXEC-GUARD] {symbol} {side} blocked: {guard['error']}")
        audit("SYSTEM", "EXEC_GUARD_BLOCK", "BLOCKED", f"sym={symbol} side={side} err={guard['error']}")
        return {"ok": False, "error": f"Execution guard: {guard['error']}"}
    try:
        import hmac as _hmac, hashlib as _hl, urllib.parse as _up
        import requests as _rq
        key = _API_KEYS[ex]["api_key"]
        sec = _API_KEYS[ex]["secret_key"]
        ts  = int(time.time() * 1000)
        params = {
            "symbol":        symbol,
            "side":          side.upper(),
            "type":          "MARKET",
            "quoteOrderQty": amount_usdt,
            "timestamp":     ts,
        }
        qs  = _up.urlencode(params)
        sig = _hmac.new(sec.encode(), qs.encode(), _hl.sha256).hexdigest()
        r   = _rq.post(
            f"https://api.binance.com/api/v3/order?{qs}&signature={sig}",
            headers={"X-MBX-APIKEY": key}, timeout=10
        )
        data = r.json()
        if r.status_code == 200:
            log.info(f"[REAL TRADE] SPOT {side} {amount_usdt} USDT of {symbol} — orderId={data.get('orderId')}")
            return {"ok": True, "order_id": data.get("orderId"), "data": data}
        return {"ok": False, "error": data.get("msg", f"Binance HTTP {r.status_code}")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@_with_main_state
def _save_combo_trades():
    try:
        with open(_COMBO_TRADES_FILE, "w") as f:
            json.dump(COMBO_TRADES[-500:], f, indent=2)
    except Exception as e:
        log.debug(f"Combo trades save failed: {e}")

