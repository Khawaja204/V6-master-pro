import functools
import sys
from flask import Blueprint

def _main():
    return sys.modules.get("main") or sys.modules.get("__main__")

def _sync_main_state(fn):
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        m=_main()
        if m is None: raise RuntimeError("main module is not loaded")
        for k,v in vars(m).items():
            if k not in _LOCAL_NAMES and k not in {"bp", "wrapped", "fn"}: globals()[k]=v
        return fn(*args, **kwargs)
    return wrapped

def _admin_required_proxy(fn):
    return _main()._admin_required(fn)

def _limiter_limit(rule):
    return _main().limiter.limit(rule)

_LOCAL_NAMES = {'chart_data', 'rsi_scan', 'get_data', 'status', 'whale_copy_data_route', 'live_score_route', 'large_trades_summary_route', 'api_wc_learning', 'dashboard_data', 'large_trades_data_route', 'sniper_data', 'focus_mode', 'health_check', 'focus_data', 'large_trades_list_route', 'combo_bot_data_route', 'v6_bot_data_route', 'whale_detail_route', 'api_onchain', 'eth_onchain_data_route', 'system_health'}
bp = Blueprint("api", __name__)

@bp.route("/dashboard_data")
@_sync_main_state
def dashboard_data():
    try:
        # oco_manager / ptp_manager are live internal objects used for real
        # trading (OCO brackets, partial TP) — they were never meant to be
        # sent to the frontend and aren't JSON-serializable. Exclude them
        # from the API response without touching GLOBAL_DATA itself.
        _safe_data = {k: v for k, v in GLOBAL_DATA.items() if k not in ("oco_manager", "ptp_manager")}
        return jsonify(_safe_data)
    except Exception:
        import traceback
        tb = traceback.format_exc()
        log.error(f"[dashboard_data] serialization crash:\n{tb}")
        return f"<pre>{tb}</pre>", 500


@bp.route("/get_data", methods=["GET", "POST"])
@_sync_main_state
def get_data():
    # SECURITY: prefer the X-API-Key header (never logged by proxies/servers
    # the way a URL query string is). The query-string form still works for
    # backward compatibility with any existing integration, but logs a
    # deprecation warning so it can be phased out.
    key = request.headers.get("X-API-Key", "")
    if not key:
        key = (request.get_json(silent=True) or {}).get("secret_key", "") if request.method == "POST" \
              else request.args.get("secret_key", "")
        if key:
            log.warning("[SECURITY] /get_data called with secret_key in URL/body — "
                       "prefer the X-API-Key header instead (URL params can leak into logs).")
    if key != SECRET_KEY_VAL:
        audit(request.remote_addr, "API_ACCESS", "DENIED", "")
        return jsonify({"error": "Unauthorized"}), 401
    audit(request.remote_addr, "API_ACCESS", "GRANTED", "")
    return jsonify(GLOBAL_DATA)


@bp.route("/status")
@_sync_main_state
def status():
    secs = int(time.time() - GLOBAL_DATA["uptime_start"])
    h, r = divmod(secs, 3600); m, s = divmod(r, 60)
    return jsonify({
        "status": GLOBAL_DATA["status"], "uptime": f"{h}h {m}m {s}s",
        "cycle_count": GLOBAL_DATA["cycle_count"], "last_update": GLOBAL_DATA["last_update"],
        "btc": GLOBAL_DATA["btc"], "btc_pause": GLOBAL_DATA["btc_pause"],
        "signal_counts": {k: len(v) for k, v in GLOBAL_DATA["vmc"].items()},
        "whale_count": len(GLOBAL_DATA["whale"]),
        "win_rate": GLOBAL_DATA["win_rate"], "win_streak": _win_streak,
        "hot_coins": len(GLOBAL_DATA["hot_coins"]),
        "active_exchange": GLOBAL_DATA["active_exchange"],
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    })


@bp.route("/sniper_data")
@_sync_main_state
def sniper_data():
    """Single-coin sniper data endpoint."""
    symbol = request.args.get("symbol", "").upper()
    if not symbol:
        return jsonify({"error": "No symbol provided"})
    all_coins = GLOBAL_DATA["vmc"].get("ALL", [])
    coin = next((c for c in all_coins if c["symbol"] == symbol), None)
    folders_found = [f for f, coins in GLOBAL_DATA["vmc"].items()
                     if any(c["symbol"] == symbol for c in coins)]
    whale  = next((w for w in GLOBAL_DATA["whale"] if w["symbol"] == symbol), None)
    inst   = next((s for s in GLOBAL_DATA["inst_signals"] if s["symbol"] == symbol), None)
    alerts = [a for a in GLOBAL_DATA["alert_history"] if a["symbol"] == symbol]
    bt     = [b for b in BACKTEST_SIGNALS if b["symbol"] == symbol]
    # Fetch VWAP for sniper
    try:
        vwap = compute_vwap(symbol)
    except Exception:
        vwap = 0.0
    return jsonify({
        "symbol":   symbol,
        "coin":     coin,
        "folders":  folders_found,
        "whale":    whale,
        "inst":     inst,
        "alerts":   alerts[:10],
        "backtest": bt[:5],
        "vwap":     vwap,
        "hot":      any(h["symbol"] == symbol for h in GLOBAL_DATA["hot_coins"]),
        "signal_count_1h": len(_coin_signal_times.get(symbol, [])),
    })


@bp.route("/system_health")
@_sync_main_state
def system_health():
    tg_ok = bool(BOT_TOKEN and CHAT_ID)
    gs_ok = bool(GOOGLE_CREDENTIALS and GOOGLE_CREDENTIALS != "{}" and GOOGLE_SHEET_ID)

    # Live Binance connectivity — read the latest snapshot maintained by the
    # background health monitor + scan loop. No network work happens in this
    # request path (keeps the public endpoint fast and abuse-resistant).
    try:
        from logic import get_binance_health
        health = get_binance_health()
    except Exception as e:
        health = {"reachable": False, "last_ok": None, "last_error": str(e),
                  "active_host": ""}

    binance_up = bool(health.get("reachable"))
    has_keys   = "BINANCE" in _API_KEYS
    if binance_up:
        exchange_status = "CONNECTED"          # network reachable
        exchange_detail = "Trading keys set" if has_keys else "Public data only (no API key)"
    else:
        exchange_status = "DISCONNECTED"
        exchange_detail = health.get("last_error", "Unreachable")

    return jsonify({
        "telegram":         "CONNECTED" if tg_ok else "NOT_SET",
        "google_sheets":    "CONNECTED" if gs_ok else "NOT_SET",
        "exchange_api":     exchange_status,
        "exchange_detail":  exchange_detail,
        "exchange_host":    health.get("active_host", ""),
        "exchange_last_ok": health.get("last_ok"),
        "has_api_keys":     has_keys,
        "paper_mode":       GLOBAL_DATA.get("paper_mode", True),
        "status":           GLOBAL_DATA["status"],
        "fund_limit":       CONFIG.get("bot_fund_limit_usdt", 10.0),
    })


@bp.route("/health")
@_sync_main_state
def health_check():
    """Lightweight liveness endpoint for Render health checks and uptime monitors.
    Returns HTTP 200 with a small JSON payload; never raises an exception."""
    _last_external_ping["ts"] = time.time()
    _log_uptime_event("PING", source_ip=request.remote_addr or "")
    try:
        uptime_secs = int(time.time() - GLOBAL_DATA.get("uptime_start", time.time()))
        hours, rem  = divmod(uptime_secs, 3600)
        mins, secs  = divmod(rem, 60)
        uptime_str  = f"{hours}h {mins}m {secs}s"
        pkt_ts      = time.strftime(
            "%Y-%m-%d %H:%M:%S PKT",
            time.gmtime(time.time() + 5 * 3600)   # UTC+5
        )
        return jsonify({
            "status":      "live",
            "timestamp":   pkt_ts,
            "cycle_count": GLOBAL_DATA.get("cycle_count", 0),
            "uptime":      uptime_str,
            "paper_mode":  GLOBAL_DATA.get("paper_mode", True),
            "scan_status": GLOBAL_DATA.get("status", "unknown"),
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 200


@bp.route("/focus")
@_sync_main_state
def focus_mode():
    with open("focus.html", "r", encoding="utf-8") as f:
        return f.read()


@bp.route("/focus_data")
@_sync_main_state
def focus_data():
    inst_signals = GLOBAL_DATA.get("inst_signals", [])
    vmc_data     = GLOBAL_DATA.get("vmc", {})
    whale_data   = GLOBAL_DATA.get("whale", [])
    hot_syms     = [h["symbol"] for h in GLOBAL_DATA.get("hot_coins", [])]
    seen = set(); coins = []
    for sig in inst_signals:
        sym = sig["symbol"]
        if sym in seen: continue
        seen.add(sym)
        inst_i = sig.get("inst", {})
        wp     = inst_i.get("whale_power", 0)
        conf   = sig.get("confidence", 0)
        coins.append({**sig, "combined_score": round((wp + conf) / 2, 1), "is_hot": sym in hot_syms})
    for folder in ["VIP", "GOLDEN", "BOOM", "ENTRY"]:
        for coin in vmc_data.get(folder, []):
            sym = coin["symbol"]
            if sym in seen: continue
            seen.add(sym)
            wh  = next((w for w in whale_data if w["symbol"] == sym), None)
            wp  = wh.get("whale_power", 0) if wh else 0
            coins.append({**coin, "folder": folder,
                "combined_score": round(wp / 2, 1), "is_hot": sym in hot_syms,
                "inst": {"traffic":"RED","inst_score":0,"whale_power":wp,"confirms":0,"spike":False},
                "tp_zones": {}, "sizing": {}, "confidence": 0})
    coins.sort(key=lambda x: x["combined_score"], reverse=True)
    return jsonify({
        "coins": coins[:60], "total": len(coins),
        "last_update": GLOBAL_DATA.get("last_update"),
        "win_rate": GLOBAL_DATA.get("win_rate"), "total_wins": _total_wins,
        "total_losses": _total_losses,
        "market_regime": GLOBAL_DATA.get("market_regime", "RANGING"),
        "btc": GLOBAL_DATA.get("btc", {}),
    })


@bp.route("/chart_data")
@_sync_main_state
def chart_data():
    from logic import fetch_klines as _fk
    symbol   = request.args.get("symbol", "").upper()
    interval = request.args.get("interval", "1h")
    limit    = min(int(request.args.get("limit", "60")), 200)
    if not symbol:
        return jsonify({"error": "No symbol"})
    klines = _fk(symbol, interval, limit)
    if not klines:
        return jsonify({"candles": [], "vwap_line": [], "symbol": symbol, "interval": interval})
    candles = []; vwap_line = []; cum_pv = 0; cum_v = 0
    for k in klines:
        ts  = int(k[0]) // 1000
        o,h,l,c = float(k[1]), float(k[2]), float(k[3]), float(k[4])
        v   = float(k[5]); tp = (h + l + c) / 3
        cum_pv += tp * v; cum_v += v
        vwap   = round(cum_pv / cum_v, 8) if cum_v else 0
        candles.append({"time": ts, "open": o, "high": h, "low": l, "close": c})
        vwap_line.append({"time": ts, "value": vwap})
    inst_s = next((s for s in GLOBAL_DATA["inst_signals"] if s["symbol"] == symbol), None)
    tp_z   = inst_s.get("tp_zones", {}) if inst_s else {}
    # ── VMC Signal Markers (BUY / SELL labels on chart) ───────────────────────
    markers = []
    buy_folders = [
        ("VIP",    "belowBar", "#da70d6", "arrowUp",   "✅ BUY — VIP"),
        ("GOLDEN", "belowBar", "#FFD700", "arrowUp",   "✅ BUY — GOLDEN"),
        ("ENTRY",  "belowBar", "#3fb950", "arrowUp",   "✅ BUY — ENTRY"),
        ("BOOM",   "belowBar", "#FF6B35", "arrowUp",   "✅ BUY — BOOM"),
    ]
    sell_folders = [
        ("EXIT",   "aboveBar", "#FF4500", "arrowDown", "🚫 SELL — EXIT"),
        ("STUCK",  "aboveBar", "#888888", "arrowDown", "⚠️ STUCK"),
    ]
    for folder, pos, col, shp, label in buy_folders + sell_folders:
        coins_in_folder = GLOBAL_DATA["vmc"].get(folder, [])
        if any(c["symbol"] == symbol for c in coins_in_folder) and candles:
            markers.append({"time": candles[-1]["time"], "position": pos,
                            "color": col, "shape": shp, "text": label})
    # ── Inst signal spike marker ───────────────────────────────────────────────
    inst_s2 = next((s for s in GLOBAL_DATA["inst_signals"] if s["symbol"] == symbol), None)
    if inst_s2 and inst_s2.get("inst", {}).get("spike") and candles:
        markers.append({"time": candles[-1]["time"], "position": "belowBar",
                        "color": "#00FFFF", "shape": "arrowUp", "text": "⚡ SPIKE"})
    wh = next((w for w in GLOBAL_DATA["whale"] if w["symbol"] == symbol), None)
    whale_walls = [{"price": w["price_level"], "side": w["side"], "size_usdt": w["size_usdt"]}
                   for w in (wh.get("walls", []) if wh else [])]
    return jsonify({
        "symbol": symbol, "interval": interval, "candles": candles, "vwap_line": vwap_line,
        "tp1": tp_z.get("tp1",0), "tp2": tp_z.get("tp2",0), "tp3": tp_z.get("tp3",0),
        "stop_loss": tp_z.get("stop_loss",0), "entry_low": tp_z.get("entry_low",0),
        "entry_high": tp_z.get("entry_high",0), "markers": markers, "whale_walls": whale_walls,
    })


@bp.route("/rsi_scan")
@_sync_main_state
def rsi_scan():
    """Return live RSI values for the requested timeframe and category."""
    from logic import fetch_klines as _fk

    allowed = {"1m", "5m", "1h", "4h", "8h", "1d"}
    interval = request.args.get("interval", "1h").lower()
    category = request.args.get("category", "all").lower()
    if interval not in allowed:
        return jsonify({"error": "Unsupported RSI timeframe", "allowed": sorted(allowed)}), 400
    if category not in {"all", "oversold", "low", "momentum", "overbought"}:
        return jsonify({"error": "Unsupported RSI category"}), 400

    symbols = []
    for signal in GLOBAL_DATA.get("inst_signals", []):
        symbol = signal.get("symbol")
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    if not symbols:
        for coin in GLOBAL_DATA.get("vmc", {}).get("ALL", []):
            symbol = coin.get("symbol")
            if symbol and symbol not in symbols:
                symbols.append(symbol)

    def calculate_rsi(klines, period=14):
        closes = [float(k[4]) for k in klines if len(k) > 4]
        if len(closes) < period + 1:
            return None
        gains = []; losses = []
        for idx in range(1, len(closes)):
            delta = closes[idx] - closes[idx - 1]
            gains.append(max(delta, 0.0))
            losses.append(max(-delta, 0.0))
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        for idx in range(period, len(gains)):
            avg_gain = ((avg_gain * (period - 1)) + gains[idx]) / period
            avg_loss = ((avg_loss * (period - 1)) + losses[idx]) / period
        if avg_loss == 0:
            return 100.0
        return round(100 - (100 / (1 + (avg_gain / avg_loss))), 1)

    def matches(value):
        if value is None:
            return False
        if category == "oversold":
            return value < 30
        if category == "low":
            return 30 <= value < 40
        if category == "momentum":
            return 50 <= value <= 60
        if category == "overbought":
            return value > 70
        return True

    results = []
    for symbol in symbols[:60]:
        try:
            value = calculate_rsi(_fk(symbol, interval, 60))
        except Exception as exc:
            log.debug("[RSI scan] %s %s failed: %s", symbol, interval, exc)
            continue
        if matches(value):
            results.append({"symbol": symbol, "rsi": value, "interval": interval})
    results.sort(key=lambda item: item["rsi"])
    return jsonify({
        "interval": interval, "category": category,
        "results": results, "total": len(results),
    })


@bp.route("/eth_onchain_data")
@_sync_main_state
def eth_onchain_data_route():
    return jsonify({"flows": GLOBAL_DATA.get("eth_onchain_flows", [])[:30]})


@bp.route("/large_trades_data")
@_sync_main_state
def large_trades_data_route():
    return jsonify({"trades": GLOBAL_DATA.get("large_trades", [])[:50]})


@bp.route("/large_trades_summary")
@_sync_main_state
def large_trades_summary_route():
    window = request.args.get("window", "daily")
    hours = 24 if window == "daily" else 168
    return jsonify({"window": window, "summary": _get_lt_summary(hours)})


@bp.route("/large_trades_list")
@_sync_main_state
def large_trades_list_route():
    window = request.args.get("window", "daily")
    hours = 24 if window == "daily" else 168
    try:
        conn = sqlite3.connect(_LT_HISTORY_DB)
        cur = conn.execute(
            "SELECT symbol, side, usdt, price, ts FROM large_trades_history WHERE ts >= ? ORDER BY ts DESC LIMIT 200",
            (time.time() - hours * 3600,)
        )
        rows = cur.fetchall()
        conn.close()
        trades = [{
            "symbol": r[0], "side": r[1], "usdt": r[2], "price": r[3],
            "time": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(r[4] + 5 * 3600))
        } for r in rows]
        total_usdt = sum(r[2] for r in rows)
        return jsonify({"window": window, "trades": trades, "total_usdt": round(total_usdt, 0), "count": len(rows)})
    except Exception as _e:
        log.warning(f"[LT HISTORY] list query failed: {_e}")
        return jsonify({"window": window, "trades": [], "total_usdt": 0, "count": 0})


@bp.route("/whale_copy_data")
@_sync_main_state
def whale_copy_data_route():
    _wct = [t for t in WHALE_COPY_TRADES if not _is_fiat_symbol(t.get("symbol", ""))]
    closed = [t for t in _wct if t.get("status") == "CLOSED"]
    wins   = sum(1 for t in closed if t.get("result") == "WIN")
    losses = sum(1 for t in closed if t.get("result") == "LOSS")
    total  = wins + losses
    _pnl_vals = [t.get("pnl_pct", 0) or 0 for t in closed]
    _total_pnl_pct = round(sum(_pnl_vals), 3)
    _fund = GLOBAL_DATA.get("fund_limit_usdt", 10.0)
    _total_pnl_usdt_est = round(sum(v / 100 * _fund for v in _pnl_vals), 2)
    return jsonify({
        "signals":  GLOBAL_DATA.get("whale_copy_signals", []),
        "trades":   _attach_market_cap(_attach_live_price(_wct[:50])),
        "wins":     wins,
        "losses":   losses,
        "win_rate": round(wins / total * 100, 1) if total else 0.0,
        "total_pnl_pct": _total_pnl_pct,
        "total_pnl_usdt_est": _total_pnl_usdt_est,
        "pnl_est_note": f"Estimated at ${_fund}/trade (fund_limit_usdt)",
    })


@bp.route("/v6_bot_data")
@_sync_main_state
def v6_bot_data_route():
    """V6 SCORE BOT — full trade history + PnL, mirrors /whale_copy_data."""
    trades = _attach_market_cap(_attach_live_price(BACKTEST_SIGNALS[:50]))
    closed = [t for t in BACKTEST_SIGNALS if t.get("status") == "CLOSED"]
    wins   = sum(1 for t in closed if t.get("result") == "WIN")
    losses = sum(1 for t in closed if t.get("result") == "LOSS")
    total  = wins + losses
    _pnl_vals = [t.get("pnl_pct", 0) or 0 for t in closed]
    _total_pnl_pct = round(sum(_pnl_vals), 3)
    _fund = CONFIG.get("bots", {}).get("v6", {}).get("fund_limit_usdt", CONFIG.get("bot_fund_limit_usdt", 10.0))
    _total_pnl_usdt_est = round(sum(v / 100 * _fund for v in _pnl_vals), 2)
    return jsonify({
        "trades": trades,
        "open_count": sum(1 for t in BACKTEST_SIGNALS if t.get("status") == "OPEN"),
        "wins": wins, "losses": losses,
        "win_rate": round(wins / total * 100, 1) if total else 0.0,
        "total_pnl_pct": _total_pnl_pct,
        "total_pnl_usdt_est": _total_pnl_usdt_est,
        "pnl_est_note": f"Estimated at ${_fund}/trade (bots.v6.fund_limit_usdt)",
        "mode": CONFIG.get("bots", {}).get("v6", {}).get("mode", "paper"),
    })


@bp.route("/combo_bot_data")
@_sync_main_state
def combo_bot_data_route():
    """COMBO CONFLUENCE BOT — full trade history + PnL, mirrors /whale_copy_data."""
    trades = _attach_market_cap(_attach_live_price(COMBO_TRADES[:50]))
    closed = [t for t in COMBO_TRADES if t.get("status") == "CLOSED"]
    wins   = sum(1 for t in closed if t.get("result") == "WIN")
    losses = sum(1 for t in closed if t.get("result") == "LOSS")
    total  = wins + losses
    _pnl_vals = [t.get("pnl_pct", 0) or 0 for t in closed]
    _total_pnl_pct = round(sum(_pnl_vals), 3)
    _fund = CONFIG.get("bots", {}).get("combo", {}).get("fund_limit_usdt", CONFIG.get("bot_fund_limit_usdt", 10.0))
    _total_pnl_usdt_est = round(sum(v / 100 * _fund for v in _pnl_vals), 2)
    return jsonify({
        "trades": trades,
        "signals": GLOBAL_DATA.get("combo_signals", []),
        "open_count": sum(1 for t in COMBO_TRADES if t.get("status") == "OPEN"),
        "wins": wins, "losses": losses,
        "win_rate": round(wins / total * 100, 1) if total else 0.0,
        "total_pnl_pct": _total_pnl_pct,
        "total_pnl_usdt_est": _total_pnl_usdt_est,
        "pnl_est_note": f"Estimated at ${_fund}/trade (bots.combo.fund_limit_usdt)",
        "mode": CONFIG.get("bots", {}).get("combo", {}).get("mode", "paper"),
    })


@bp.route("/live_score")
@_sync_main_state
def live_score_route():
    symbol = request.args.get("symbol", "").upper()
    if not symbol:
        return jsonify({"error": "No symbol"})
    try:
        sig = _compute_live_signal(symbol)
        return jsonify(sig or {"error": "not found"})
    except Exception as e:
        log.warning(f"live_score failed for {symbol}: {e}")
        return jsonify({"error": str(e)})


@bp.route("/whale_detail")
@_sync_main_state
def whale_detail_route():
    from logic import compute_whale_detail
    symbol = request.args.get("symbol", "").upper()
    if not symbol:
        return jsonify({"error": "No symbol"})
    coin   = next((c for c in GLOBAL_DATA["vmc"].get("ALL",[]) if c["symbol"] == symbol), None)
    price  = coin["price"] if coin else fetch_ticker_price(symbol)
    tkr    = {"quoteVolume": coin.get("volume_usdt",0) if coin else 0,
              "priceChangePercent": coin.get("change_pct",0) if coin else 0}
    wd = compute_whale_detail(symbol, price, tkr, CONFIG)
    wd["top_moves_24h"] = [w for w in GLOBAL_DATA.get("whale_24h",[]) if w["symbol"]==symbol][:3]
    if not wd["top_moves_24h"]:
        wd["top_moves_24h"] = GLOBAL_DATA.get("whale_24h",[])[:3]
    return jsonify(wd)


@bp.route("/api/wc-learning")
@_sync_main_state
def api_wc_learning():
    """Whale Copy AI Learning stats for admin dashboard."""
    ld = GLOBAL_DATA.get("whale_copy_learning", {})
    return jsonify({
        "total_closed": ld.get("total_closed", 0),
        "wins": ld.get("wins", 0),
        "losses": ld.get("losses", 0),
        "timeouts": ld.get("timeouts", 0),
        "win_rate": ld.get("win_rate", 0.0),
        "avg_win_obi": ld.get("avg_win_obi", 0.0),
        "avg_loss_obi": ld.get("avg_loss_obi", 0.0),
        "avg_win_wall_usdt": ld.get("avg_win_wall_usdt", 0.0),
        "avg_loss_wall_usdt": ld.get("avg_loss_wall_usdt", 0.0),
        "avg_win_confidence": ld.get("avg_win_confidence", 0.0),
        "avg_loss_confidence": ld.get("avg_loss_confidence", 0.0),
        "avg_win_funding": ld.get("avg_win_funding", 0.0),
        "avg_loss_funding": ld.get("avg_loss_funding", 0.0),
        "gate_adjustment": ld.get("confidence_threshold_adjustment", 0),
        "last_adjustment": ld.get("last_adjustment"),
        "adjustment_log": ld.get("adjustment_log", [])[-10:],
    })


@bp.route("/api/onchain")
@_sync_main_state
def api_onchain():
    """Serve cached on-chain exchange flow + whale trade data."""
    import os
    eth_key = os.environ.get("ETHERSCAN_API_KEY", "")
    bsc_key = os.environ.get("BSCSCAN_API_KEY", "")
    log.info(f"[OnChain-API] ETHERSCAN_KEY present: {bool(eth_key)} | BSCSCAN_KEY present: {bool(bsc_key)}")
    
    try:
        from logic import get_onchain_data
        log.info("[OnChain-API] Imported get_onchain_data successfully")
        data = get_onchain_data(refresh=True)
        log.info(f"[OnChain-API] Data returned: eth_flows={len(data.get('eth_flows',[]))} large_trades={len(data.get('large_trades',[]))}")
        return jsonify({
            "eth_flows": data.get("eth_flows", []),
            "large_trades": data.get("large_trades", []),
            "dex_swaps": data.get("dex_swaps", []),
            "last_updated": time.strftime("%H:%M:%S", time.gmtime(data.get("ts", 0)))
        })
    except Exception as e:
        log.error(f"[OnChain-API] ERROR: {e}")
        import traceback
        log.error(traceback.format_exc())
        return jsonify({"error": str(e), "eth_flows": [], "large_trades": [], "last_updated": "ERROR"}), 500

