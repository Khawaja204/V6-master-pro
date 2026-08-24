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

_LOCAL_NAMES = {'admin_set_price_alert', 'admin_backtest_csv', 'admin_set_balance', 'admin_paper_trades_log', 'admin_logs', 'admin_test_telegram', 'admin_portal', 'admin_delete_holding', 'admin_add_holding', 'admin_set_mode', 'admin_ptp_positions', 'admin_clear_history', 'admin_toggle_client', 'admin_uptime_log', 'admin_symbol_history', 'admin_set_fund_limit', 'admin_audit_log', 'admin_login', 'admin_uptime_monitor_status', 'admin_delete_client', 'admin_holdings_status', 'admin_add_client', 'admin_historical_backtest', 'admin_weekly_report', 'admin_live_binance_holdings', 'admin_whale_history_csv', 'admin_set_exchange', 'admin_reset_weekly_breaker', 'admin_manual_trade', 'admin_test_connection', 'admin_set_bot_config', 'admin_refresh_scan', 'admin_debug_etherscan', 'admin_clear_backtest', 'admin_logout', 'admin_set_api_key', 'admin_weekly_breaker_status', 'admin_delete_price_alert', 'admin_clear_whale_copy', 'admin_bot_comparison', 'admin_uptime_log_csv', 'admin_whale_history_status', 'admin_kill_switch'}
bp = Blueprint("admin", __name__)

@bp.route("/admin/login", methods=["GET", "POST"])
@_limiter_limit("10 per minute")
@_sync_main_state
def admin_login():
    ip = request.remote_addr
    locked  = _check_lockout(ip)
    timeout = request.args.get("timeout") == "1"
    error   = False
    if request.method == "POST" and not locked:
        if hmac.compare_digest(request.form.get("password", ""), ADMIN_PASSWORD):
            session["admin_auth"] = True; session["last_active"] = time.time()
            audit(ip, "ADMIN_LOGIN", "SUCCESS", "")
            return redirect("/admin")
        _record_failed_login(ip); locked = _check_lockout(ip); error = True
    return render_template("admin_login.html", locked=locked, timeout=timeout, error=error)


@bp.route("/admin/logout")
@_sync_main_state
def admin_logout():
    audit(request.remote_addr, "ADMIN_LOGOUT", "OK", "")
    session.clear(); return redirect("/admin/login")


@bp.route("/admin")
@_admin_required_proxy
@_sync_main_state
def admin_portal():
    secs = int(time.time() - GLOBAL_DATA["uptime_start"])
    h, r = divmod(secs, 3600); m, s = divmod(r, 60)
    try:
        with open("system_audit.log") as f: preview = "".join(f.readlines()[-30:])
    except Exception:
        preview = "No audit log yet."
    saved_keys_masked = {ex: {"api_key_mask": _mask(_API_KEYS[ex].get("api_key",""))}
                         for ex in _API_KEYS}
    return render_template("admin_portal.html",
        status=GLOBAL_DATA["status"], cycles=GLOBAL_DATA["cycle_count"],
        uptime=f"{h}h {m}m {s}s", btc_pause=GLOBAL_DATA.get("btc_pause"),
        win_rate=GLOBAL_DATA["win_rate"], win_streak=_win_streak,
        total_wins=_total_wins, total_losses=_total_losses,
        hot_cnt=len(GLOBAL_DATA["hot_coins"]), hist_cnt=len(GLOBAL_DATA["alert_history"]),
        balance=CONFIG["risk"]["account_balance_usdt"],
        green_pct=CONFIG["risk"]["green_signal_max_pct"],
        yellow_pct=CONFIG["risk"]["yellow_signal_max_pct"],
        exchange=GLOBAL_DATA.get("active_exchange", "BINANCE"),
        exchanges=["BINANCE"],
        hot_coins=GLOBAL_DATA["hot_coins"], alerts=GLOBAL_DATA["alert_history"],
        audit_preview=preview, today=time.strftime("%Y-%m-%d", time.gmtime(time.time() + 5 * 3600)),
        paper_mode=GLOBAL_DATA.get("paper_mode", True),
        price_alerts=GLOBAL_DATA.get("price_alerts", []),
        saved_keys=saved_keys_masked,
        ld=GLOBAL_DATA.get("learning_data", {}),
        clients=[type('C', (), c)() for c in _load_clients()],
        fund_limit=CONFIG.get("bot_fund_limit_usdt", 10.0),
        bots_cfg=CONFIG.get("bots", {}),
        csrf_token=_get_csrf_token(),
    )


@bp.route("/admin/set_price_alert", methods=["POST"])
@_admin_required_proxy
@_sync_main_state
def admin_set_price_alert():
    global PRICE_ALERTS, _alert_id_counter
    sym    = request.form.get("symbol", "").upper().strip()
    if not sym.endswith("USDT"): sym += "USDT"
    try:    target = float(request.form.get("target_price", 0))
    except: return redirect("/admin")
    direction = request.form.get("direction", "ABOVE").upper()
    note      = request.form.get("note", "")[:120]
    _alert_id_counter += 1
    alert = {
        "id":           _alert_id_counter,
        "symbol":       sym,
        "target_price": target,
        "direction":    direction,
        "note":         note,
        "created_at":   time.strftime("%Y-%m-%d %H:%M"),
    }
    PRICE_ALERTS.append(alert)
    GLOBAL_DATA["price_alerts"] = PRICE_ALERTS[:]
    audit(request.remote_addr, "SET_PRICE_ALERT", "OK",
          f"{sym} {direction} {target}")
    return redirect("/admin")


@bp.route("/admin/delete_price_alert", methods=["POST"])
@_admin_required_proxy
@_sync_main_state
def admin_delete_price_alert():
    global PRICE_ALERTS
    try:    aid = int(request.form.get("alert_id", -1))
    except: return redirect("/admin")
    PRICE_ALERTS = [a for a in PRICE_ALERTS if a["id"] != aid]
    GLOBAL_DATA["price_alerts"] = PRICE_ALERTS[:]
    audit(request.remote_addr, "DELETE_PRICE_ALERT", "OK", f"id={aid}")
    return redirect("/admin")


@bp.route("/admin/set_api_key", methods=["POST"])
@_admin_required_proxy
@_sync_main_state
def admin_set_api_key():
    ex         = request.form.get("exchange", "").upper()
    api_key    = request.form.get("api_key", "").strip()
    secret_key = request.form.get("secret_key", "").strip()
    passphrase = request.form.get("passphrase", "").strip()
    if not ex or not api_key or not secret_key:
        return redirect("/admin")
    _API_KEYS[ex] = {"api_key": api_key, "secret_key": secret_key}
    if passphrase: _API_KEYS[ex]["passphrase"] = passphrase
    _save_api_keys()
    audit(request.remote_addr, "SET_API_KEY", "OK",
          f"ex={ex} key=...{api_key[-4:]}")
    return redirect("/admin")


@bp.route("/admin/test_connection", methods=["POST"])
@_admin_required_proxy
@_sync_main_state
def admin_test_connection():
    ex = request.form.get("exchange", "").upper()
    if ex not in _API_KEYS:
        return f"<script>alert('No API key saved for {ex}');window.history.back()</script>"
    try:
        import hmac as _hmac, hashlib as _hl, urllib.parse as _up
        import requests as _rq
        key = _API_KEYS[ex]["api_key"]
        sec = _API_KEYS[ex]["secret_key"]
        if ex == "BINANCE":
            ts  = int(time.time() * 1000)
            qs  = f"timestamp={ts}"
            sig = _hmac.new(sec.encode(), qs.encode(), _hl.sha256).hexdigest()
            r   = _rq.get(f"https://api.binance.com/api/v3/account?{qs}&signature={sig}",
                          headers={"X-MBX-APIKEY": key}, timeout=8)
            ok  = r.status_code == 200
        else:
            ok = False  # stub for other exchanges
        audit(request.remote_addr, "TEST_CONNECTION", "OK" if ok else "FAIL", f"ex={ex}")
        msg = f"✅ {ex} Connected!" if ok else f"❌ {ex} Connection Failed (check key/secret)"
    except Exception as e:
        msg = f"❌ Error: {e}"
    return f"<script>alert('{msg}');window.history.back()</script>"


@bp.route("/admin/set_mode", methods=["POST"])
@_admin_required_proxy
@_sync_main_state
def admin_set_mode():
    current = GLOBAL_DATA.get("paper_mode", True)
    # SAFETY: prevent switching to REAL MODE if no Binance API keys are configured
    if current and "BINANCE" not in _API_KEYS:
        audit(request.remote_addr, "SET_MODE", "BLOCKED",
              "REAL MODE blocked — no Binance API keys configured")
        return ("<script>alert('⛔ REAL MODE BLOCKED\\n\\n"
                "Cannot switch to REAL MODE: no Binance API key is configured.\\n"
                "Configure API keys in Admin → API Key Management first.');"
                "window.history.back()</script>")
    GLOBAL_DATA["paper_mode"] = not current
    mode = "PAPER" if GLOBAL_DATA["paper_mode"] else "REAL"
    # Persist to config.json so paper_mode survives server restarts
    CONFIG["paper_mode"] = GLOBAL_DATA["paper_mode"]
    try:
        with open("config.json", "w") as _cf:
            json.dump(CONFIG, _cf, indent=2)
    except Exception as _e:
        log.debug(f"paper_mode save failed: {_e}")
    audit(request.remote_addr, "SET_MODE", "OK", f"mode={mode}")
    return redirect("/admin")


@bp.route("/admin/set_balance", methods=["POST"])
@_admin_required_proxy
@_sync_main_state
def admin_set_balance():
    try:
        CONFIG["risk"]["account_balance_usdt"] = float(request.form.get("balance", 1000))
        with open("config.json", "w") as f: json.dump(CONFIG, f, indent=2)
        audit(request.remote_addr, "SET_BALANCE", "OK", f"balance={CONFIG['risk']['account_balance_usdt']}")
    except Exception as e:
        audit(request.remote_addr, "SET_BALANCE", "ERROR", str(e))
    return redirect("/admin")


@bp.route("/admin/set_exchange", methods=["POST"])
@_admin_required_proxy
@_sync_main_state
def admin_set_exchange():
    ex = request.form.get("exchange", "BINANCE").upper()
    GLOBAL_DATA["active_exchange"] = ex
    audit(request.remote_addr, "SET_EXCHANGE", "OK", f"ex={ex}")
    return redirect("/admin")


@bp.route("/admin/clear_history", methods=["POST"])
@_admin_required_proxy
@_sync_main_state
def admin_clear_history():
    GLOBAL_DATA["alert_history"] = []
    audit(request.remote_addr, "CLEAR_HISTORY", "OK", ""); return redirect("/admin")


@bp.route("/admin/clear_backtest", methods=["POST"])
@_admin_required_proxy
@_sync_main_state
def admin_clear_backtest():
    global BACKTEST_SIGNALS, _total_wins, _total_losses, _win_streak
    BACKTEST_SIGNALS = []; _total_wins = 0; _total_losses = 0; _win_streak = 0
    GLOBAL_DATA["backtest"] = []; GLOBAL_DATA["win_streak"] = 0
    GLOBAL_DATA["total_wins"] = 0; GLOBAL_DATA["total_losses"] = 0; GLOBAL_DATA["win_rate"] = 0.0
    _save_backtest_signals()
    audit(request.remote_addr, "CLEAR_BACKTEST", "OK", ""); return redirect("/admin")


@bp.route("/admin/clear_whale_copy", methods=["POST"])
@_admin_required_proxy
@_sync_main_state
def admin_clear_whale_copy():
    global WHALE_COPY_TRADES
    WHALE_COPY_TRADES = []
    _save_whale_copy_trades()
    GLOBAL_DATA["whale_copy_signals"] = []
    audit(request.remote_addr, "CLEAR_WHALE_COPY", "OK", "")
    return redirect("/admin")


@bp.route("/admin/kill_switch", methods=["POST"])
@_admin_required_proxy
@_sync_main_state
def admin_kill_switch():
    """Emergency kill-switch: cancels all open paper/backtest trades, forces paper
    mode ON, and halts new auto-trade entries by tripping the circuit-breaker."""
    global BACKTEST_SIGNALS, WHALE_COPY_TRADES, PAPER_TRADES
    now_ts  = _pkt_ts()
    closed_bt  = 0
    closed_wc  = 0

    # 1. Close all OPEN backtest signals
    for s in BACKTEST_SIGNALS:
        if s.get("status") == "OPEN":
            s["status"]     = "CLOSED"
            s["result"]     = "CANCELLED"
            s["exit_time"]  = now_ts
            s["exit_price"] = s.get("entry_price", 0)
            s["pnl_pct"]    = 0.0
            closed_bt += 1

    # 2. Close all OPEN whale-copy trades
    for t in WHALE_COPY_TRADES:
        if t.get("status") == "OPEN":
            t["status"]     = "CLOSED"
            t["result"]     = "CANCELLED"
            t["exit_time"]  = now_ts
            t["exit_price"] = t.get("entry_price", 0)
            t["pnl_pct"]    = 0.0
            closed_wc += 1

    # 3. Force paper mode ON
    GLOBAL_DATA["paper_mode"] = True
    CONFIG["paper_mode"]      = True

    # 4. Trip the daily circuit-breaker so no new entries fire
    _daily_stats["tripped"]       = True
    _daily_stats["tripped_reason"] = "MANUAL KILL-SWITCH activated"

    # 5. Persist changes
    _save_backtest_signals()
    _save_whale_copy_trades()
    try:
        with open("config.json", "w") as _cf:
            json.dump(CONFIG, _cf, indent=2)
    except Exception:
        pass

    audit(request.remote_addr, "KILL_SWITCH", "OK",
          f"bt_closed={closed_bt} wc_closed={closed_wc}")

    # 6. Telegram alert
    _kill_msg = (
        f"🛑 <b>EMERGENCY KILL-SWITCH ACTIVATED</b>\n"
        f"All open trades cancelled.\n"
        f"Backtest closed: {closed_bt} | Whale Copy closed: {closed_wc}\n"
        f"System forced to PAPER MODE.\n"
        f"New entries blocked until daily reset.\n"
        f"⏱ {now_ts}"
    )
# Bypassed:     send_telegram(_kill_msg)
    log.warning(f"[KILL-SWITCH] Activated — bt_closed={closed_bt} wc_closed={closed_wc}")
    return redirect("/admin")


@bp.route("/admin/bot_comparison")
@_admin_required_proxy
@_sync_main_state
def admin_bot_comparison():
    """Live comparison stats for the 3-bot admin table."""
    v6_closed = _total_wins + _total_losses
    v6_wr = round(_total_wins / v6_closed * 100, 1) if v6_closed else 0.0

    wc_closed = [t for t in WHALE_COPY_TRADES if t.get("status") == "CLOSED"]
    wc_wins = sum(1 for t in wc_closed if t.get("result") == "WIN")
    wc_wr = round(wc_wins / len(wc_closed) * 100, 1) if wc_closed else 0.0

    cb_closed = [t for t in COMBO_TRADES if t.get("status") == "CLOSED"]
    cb_wins = sum(1 for t in cb_closed if t.get("result") == "WIN")
    cb_wr = round(cb_wins / len(cb_closed) * 100, 1) if cb_closed else 0.0

    def _cb_stats(bot):
        s = _daily_stats_by_bot.get(bot, {})
        return {"tripped": s.get("tripped", False), "reason": s.get("tripped_reason", ""),
                "losses_today": s.get("losses", 0), "pnl_today": s.get("realized_pnl_pct", 0.0)}

    bots_cfg = CONFIG.get("bots", {})
    return jsonify({
        "v6": {
            "mode": bots_cfg.get("v6", {}).get("mode", "paper"),
            "fund_limit": bots_cfg.get("v6", {}).get("fund_limit_usdt", 10),
            "open": sum(1 for b in BACKTEST_SIGNALS if b.get("status") == "OPEN"),
            "closed": v6_closed, "wins": _total_wins, "losses": _total_losses,
            "win_rate": v6_wr, "circuit": _cb_stats("v6"),
        },
        "wall": {
            "mode": bots_cfg.get("wall", {}).get("mode", "paper"),
            "fund_limit": bots_cfg.get("wall", {}).get("fund_limit_usdt", 10),
            "open": sum(1 for t in WHALE_COPY_TRADES if t.get("status") == "OPEN"),
            "closed": len(wc_closed), "wins": wc_wins, "losses": len(wc_closed) - wc_wins,
            "win_rate": wc_wr, "circuit": _cb_stats("wall"),
        },
        "combo": {
            "mode": bots_cfg.get("combo", {}).get("mode", "paper"),
            "fund_limit": bots_cfg.get("combo", {}).get("fund_limit_usdt", 10),
            "open": sum(1 for t in COMBO_TRADES if t.get("status") == "OPEN"),
            "closed": len(cb_closed), "wins": cb_wins, "losses": len(cb_closed) - cb_wins,
            "win_rate": cb_wr, "circuit": _cb_stats("combo"),
        },
    })


@bp.route("/admin/set_bot_config", methods=["POST"])
@_admin_required_proxy
@_sync_main_state
def admin_set_bot_config():
    """Per-bot mode (paper/real) + fund limit for v6 / wall / combo."""
    bot = request.form.get("bot", "").strip().lower()
    if bot not in ("v6", "wall", "combo"):
        return redirect("/admin")
    mode = request.form.get("mode", "paper").strip().lower()
    if mode not in ("paper", "real"):
        mode = "paper"
    try:
        limit = float(request.form.get("fund_limit", 10))
    except Exception:
        limit = 10.0
    if limit <= 0:
        return "<script>alert('Fund limit must be > 0');window.history.back()</script>"

    CONFIG.setdefault("bots", {}).setdefault(bot, {})
    # SAFETY: block switching to REAL if no Binance API key configured
    if mode == "real" and CONFIG["bots"][bot].get("mode", "paper") == "paper" and "BINANCE" not in _API_KEYS:
        audit(request.remote_addr, "SET_BOT_CONFIG", "BLOCKED", f"bot={bot} — no Binance API keys")
        return ("<script>alert('⛔ REAL MODE BLOCKED\\n\\n"
                f"Cannot switch {bot.upper()} bot to REAL — no Binance API key configured.');"
                "window.history.back()</script>")

    CONFIG["bots"][bot]["mode"] = mode
    CONFIG["bots"][bot]["fund_limit_usdt"] = limit
    try:
        with open("config.json", "w") as f:
            json.dump(CONFIG, f, indent=2)
    except Exception as e:
        log.debug(f"bot config save failed: {e}")
    audit(request.remote_addr, "SET_BOT_CONFIG", "OK", f"bot={bot} mode={mode} limit={limit}")
    return redirect("/admin")


@bp.route("/admin/set_fund_limit", methods=["POST"])
@_admin_required_proxy
@_sync_main_state
def admin_set_fund_limit():
    try:
        limit = float(request.form.get("fund_limit", 10))
        if limit <= 0:
            return "<script>alert('Fund limit must be > 0');window.history.back()</script>"
        CONFIG["bot_fund_limit_usdt"]      = limit
        GLOBAL_DATA["fund_limit_usdt"]     = limit
        with open("config.json", "w") as f: json.dump(CONFIG, f, indent=2)
        audit(request.remote_addr, "SET_FUND_LIMIT", "OK", f"limit={limit} USDT")
    except Exception as e:
        audit(request.remote_addr, "SET_FUND_LIMIT", "ERROR", str(e))
    return redirect("/admin")


@bp.route("/admin/manual_trade", methods=["POST"])
@_admin_required_proxy
@_sync_main_state
def admin_manual_trade():
    symbol   = request.form.get("symbol", "").upper().strip()
    if not symbol.endswith("USDT"):
        symbol += "USDT"
    side     = request.form.get("side", "BUY").upper()
    strategy = request.form.get("strategy", "SPOT")
    try:
        amount = float(request.form.get("amount_usdt", 0))
    except Exception:
        return "<script>alert('Invalid amount');window.history.back()</script>"
    if amount <= 0:
        return "<script>alert('Amount must be greater than 0');window.history.back()</script>"

    paper_mode = GLOBAL_DATA.get("paper_mode", True)

    # ── Build the trade rationale from live signal context (if available) ──────
    inst_s = next((s for s in GLOBAL_DATA.get("inst_signals", []) if s["symbol"] == symbol), None)
    if inst_s:
        ii     = inst_s.get("inst", {})
        reason = (f"Manual {side} | {ii.get('traffic','—')} | Score {inst_s.get('score','—')} | "
                  f"RSI {inst_s.get('rsi','—')} | WhalePow {ii.get('whale_power','—')}% | "
                  f"Inst {ii.get('inst_score','—')} | Conf {inst_s.get('confidence','—')}%")
        tp_ctx = inst_s.get("tp_zones", {})
        traffic= ii.get("traffic", "")
    else:
        reason = f"Manual admin {side} (no live signal context for {symbol})"
        tp_ctx = {}
        traffic= ""

    if paper_mode:
        result   = _execute_paper_trade(symbol, side, amount, strategy, manual=True, reason=reason)
        mode_str = "PAPER (SIMULATED)"
    elif strategy == "SPOT_GRID":
        result   = _execute_real_binance_spot_grid(symbol, amount)
        mode_str = "REAL SPOT GRID"
    else:
        result   = _execute_real_binance_spot(symbol, side, amount,
                                               expected_price=(inst_s.get("price") if inst_s else None))
        mode_str = "REAL SPOT"

    if result.get("ok"):
        audit(request.remote_addr, "MANUAL_TRADE", "OK",
              f"sym={symbol} side={side} amt={amount} mode={mode_str} strategy={strategy}")
        if (not paper_mode) and side == "BUY" and strategy == "SPOT" and _V6_OCO and "BINANCE" in _API_KEYS:
            try:
                _fill_price = fetch_ticker_price(symbol)
                _atr = calculate_atr(symbol)
                _tp_ctx2 = compute_tp_levels(_fill_price, _atr, CONFIG) if (_fill_price and _atr) else {}
                if _tp_ctx2.get("tp1") and _tp_ctx2.get("stop_loss"):
                    _fill_qty = round(amount / _fill_price, 6)
                    _oco_res = GLOBAL_DATA["oco_manager"].place_oco(
                        symbol=symbol, side="SELL", quantity=_fill_qty,
                        price=_tp_ctx2["tp1"], stop_price=_tp_ctx2["stop_loss"],
                        stop_limit_price=_tp_ctx2["stop_loss"],
                        api_key=_API_KEYS["BINANCE"]["api_key"],
                        secret_key=_API_KEYS["BINANCE"]["secret_key"],
                    )
                    audit(request.remote_addr, "MANUAL_OCO_BRACKET",
                          "OK" if _oco_res.get("ok") else "FAILED",
                          f"sym={symbol} qty={_fill_qty}")
            except Exception as _moe:
                log.warning(f"[V6 OCO] manual bracket failed: {_moe}")
        notify_trade(symbol, side, strategy, mode_str, reason,
                     amount=amount, tp_zones=tp_ctx or None, traffic=traffic)
        msg = f"Trade executed ({mode_str}):\\n{side} ${amount} of {symbol.replace('USDT','')}\\n\\nCheck Manual Trading panel for details."
    else:
        audit(request.remote_addr, "MANUAL_TRADE", "FAIL",
              f"sym={symbol} err={result.get('error','?')}")
        msg = f"Trade FAILED:\\n{result.get('error','Unknown error')}"
    return f"<script>alert('{msg}');window.location='/admin'</script>"


@bp.route("/admin/refresh_scan", methods=["POST"])
@_admin_required_proxy
@_sync_main_state
def admin_refresh_scan():
    """Kick off an immediate background scan without waiting for the timer."""
    def _force_scan():
        try:
            from logic import process_vmc_signals, process_whale_walls
            log.info("[ADMIN] Force scan triggered")
            vmc_data   = process_vmc_signals(CONFIG)
            price_map  = {c["symbol"]: c["price"] for c in vmc_data.get("ALL", [])}
            whale_data = process_whale_walls(CONFIG, price_map, _previous_walls)

            # ── WHALE COPY MODE: independent wall+OBI mirrored signals ────────
            whale_copy_signals = detect_whale_copy_signals(whale_data, CONFIG, GLOBAL_DATA.get("market_regime", "RANGING"))
            for _wcs in whale_copy_signals:
                if _wcs.get("confirmed"):
                    _wcs_atr = calculate_atr(_wcs["symbol"])
                    _wcs["eta"] = estimate_time_to_target(_wcs["price"], _wcs["target"], _wcs_atr)["label"]
                else:
                    _wcs["eta"] = "—"
            GLOBAL_DATA["whale_copy_signals"] = whale_copy_signals
            wc_min_conf = CONFIG.get("whale_copy", {}).get("min_confidence", 50) + \
                          GLOBAL_DATA.get("whale_copy_learning", {}).get("confidence_threshold_adjustment", 0)
            for sig in whale_copy_signals:
                if sig["direction"] == "COPY_BUY" and sig.get("confirmed") and sig["confidence"] >= wc_min_conf:
                    _record_whale_copy_trade(sig)
            GLOBAL_DATA["vmc"]         = vmc_data
            GLOBAL_DATA["whale"]       = whale_data
            GLOBAL_DATA["last_update"] = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 5 * 3600))
            GLOBAL_DATA["status"]      = "live"
            log.info("[ADMIN] Force scan completed — data refreshed")
        except Exception as e:
            log.error(f"[ADMIN] Force scan error: {e}")
    threading.Thread(target=_force_scan, daemon=True).start()
    audit(request.remote_addr, "FORCE_SCAN", "TRIGGERED", "")
    return "<script>alert('Force scan triggered!\\nAll signal data will refresh in ~30 seconds.');window.location='/admin'</script>"


@bp.route("/admin/paper_trades")
@_admin_required_proxy
@_sync_main_state
def admin_paper_trades_log():
    return jsonify(PAPER_TRADES[:100])


@bp.route("/admin/ptp_positions")
@_admin_required_proxy
@_sync_main_state
def admin_ptp_positions():
    """V6 UPGRADE: Partial-TP scale-out positions (TP1/TP2/TP3 progress)."""
    if not _V6_PTP or "ptp_manager" not in GLOBAL_DATA:
        return jsonify([])
    return jsonify(GLOBAL_DATA["ptp_manager"].get_positions())


@bp.route("/admin/historical_backtest")
@_admin_required_proxy
@_sync_main_state
def admin_historical_backtest():
    try:
        months = int(request.args.get("months", 3))
    except (TypeError, ValueError):
        months = 3
    try:
        report = _run_backtest(months)
        audit(request.remote_addr, "BACKTEST", "OK",
              f"months={months} trades={report.get('total_trades')}")
        return jsonify(report)
    except Exception as e:
        log.error(f"[BACKTEST] failed: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route("/admin/backtest_csv")
@_admin_required_proxy
@_sync_main_state
def admin_backtest_csv():
    try:
        months = int(request.args.get("months", 3))
    except (TypeError, ValueError):
        months = 3
    report = _run_backtest(months)
    rows = ["symbol,entry_time,exit_time,entry_price,exit_price,pnl_pct,exit_reason,trailing,bars_held,counted,equity_after"]
    for t in report.get("trades", []):
        rows.append(",".join(str(t.get(c, "")) for c in (
            "symbol", "entry_time", "exit_time", "entry_price", "exit_price",
            "pnl_pct", "exit_reason", "trailing", "bars_held", "counted",
            "equity_after")))
    summary = (f"\n# SUMMARY,trades={report.get('total_trades')},"
               f"win_rate={report.get('win_rate')}%,"
               f"profit_factor={report.get('profit_factor')},"
               f"max_drawdown={report.get('max_drawdown_pct')}%,"
               f"net_return={report.get('net_return_pct')}%,"
               f"end_equity={report.get('end_equity')}")
    return Response("\n".join(rows) + summary, mimetype="text/csv",
                    headers={"Content-Disposition":
                             f"attachment;filename=backtest_{months}mo.csv"})


@bp.route("/admin/test_telegram")
@_admin_required_proxy
@_sync_main_state
def admin_test_telegram():
# Bypassed:     ok = send_telegram(
#         "🧪 <b>V6 Master Pro — Telegram Test</b>\n"
#         "If you can read this, alerts are wired up correctly.\n"
#         f"Time: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    audit(request.remote_addr, "TEST_TELEGRAM", "OK" if ok else "FAIL", "")
    return jsonify({"ok": bool(ok),
                    "message": "Sent — check your Telegram." if ok else
                               "Failed — server could not reach Telegram (check BOT_TOKEN / proxy)."})


@bp.route("/admin/audit_log")
@_admin_required_proxy
@_sync_main_state
def admin_audit_log():
    date_from = request.args.get("date_from", time.strftime("%Y-%m-%d", time.gmtime(time.time() + 5 * 3600)))
    date_to   = request.args.get("date_to",   time.strftime("%Y-%m-%d", time.gmtime(time.time() + 5 * 3600)))
    fmt       = request.args.get("fmt", "html")
    try:
        with open("system_audit.log") as f: lines = f.readlines()
        filtered = [l for l in lines if date_from <= l[:10] <= date_to]
    except Exception:
        filtered = []
    if fmt == "csv":
        return Response("".join(filtered), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment;filename=audit.csv"})
    return f"<pre style='background:#0d1117;color:#c9d1d9;padding:20px;font-size:11px'>{''.join(filtered[-200:]) or 'No entries.'}</pre>"


@bp.route("/admin/add_client", methods=["POST"])
@_admin_required_proxy
@_sync_main_state
def admin_add_client():
    name  = request.form.get("name", "").strip()
    uid   = request.form.get("uid", "").strip()
    pwd   = request.form.get("password", "").strip()
    exp   = request.form.get("expiry", "UNLIMITED").strip() or "UNLIMITED"
    lim   = request.form.get("sig_limit", "100").strip() or "100"
    if not name or not uid or not pwd:
        return redirect("/admin")
    clients = _load_clients()
    if any(c.get("name") == name for c in clients):
        return f"<script>alert('Client \"{name}\" already exists.');window.history.back()</script>"
    clients.append({"name": name, "uid": uid, "password": generate_password_hash(pwd), "status": "ACTIVE",
                    "expiry": exp, "sig_limit": lim, "role": "CLIENT",
                    "added": time.strftime("%Y-%m-%d", time.gmtime(time.time() + 5 * 3600))})
    _save_clients(clients)
    audit(request.remote_addr, "ADD_CLIENT", "OK", f"name={name} uid={uid}")
    return redirect("/admin")


@bp.route("/admin/delete_client", methods=["POST"])
@_admin_required_proxy
@_sync_main_state
def admin_delete_client():
    name    = request.form.get("name", "").strip()
    clients = [c for c in _load_clients() if c.get("name") != name]
    _save_clients(clients)
    audit(request.remote_addr, "DELETE_CLIENT", "OK", f"name={name}")
    return redirect("/admin")


@bp.route("/admin/toggle_client", methods=["POST"])
@_admin_required_proxy
@_sync_main_state
def admin_toggle_client():
    name    = request.form.get("name", "").strip()
    clients = _load_clients()
    for c in clients:
        if c.get("name") == name:
            c["status"] = "INACTIVE" if c.get("status") == "ACTIVE" else "ACTIVE"
    _save_clients(clients)
    audit(request.remote_addr, "TOGGLE_CLIENT", "OK", f"name={name}")
    return redirect("/admin")


@bp.route("/admin/add_holding", methods=["POST"])
@_admin_required_proxy
@_sync_main_state
def admin_add_holding():
    sym = request.form.get("symbol", "").upper().strip()
    if not sym.endswith("USDT"):
        sym += "USDT"
    try:
        qty = float(request.form.get("quantity", 0))
        buy_price = float(request.form.get("buy_price", 0))
    except Exception:
        return redirect("/admin")
    try:
        target_pct = float(request.form.get("target_pct", 15))
    except Exception:
        target_pct = 15.0
    holdings = [h for h in _load_holdings() if h["symbol"] != sym]
    holdings.append({"symbol": sym, "quantity": qty, "buy_price": buy_price,
                      "target_pct": target_pct, "added": time.strftime("%Y-%m-%d", time.gmtime(time.time() + 5 * 3600))})
    _save_holdings(holdings)
    audit(request.remote_addr, "ADD_HOLDING", "OK", f"sym={sym} qty={qty}")
    return redirect("/admin")


@bp.route("/admin/delete_holding", methods=["POST"])
@_admin_required_proxy
@_sync_main_state
def admin_delete_holding():
    sym = request.form.get("symbol", "").upper().strip()
    holdings = [h for h in _load_holdings() if h["symbol"] != sym]
    _save_holdings(holdings)
    audit(request.remote_addr, "DELETE_HOLDING", "OK", f"sym={sym}")
    return redirect("/admin")


@bp.route("/admin/uptime_log")
@_admin_required_proxy
@_sync_main_state
def admin_uptime_log():
    """Returns the last N uptime_log entries plus computed gaps between
    consecutive entries — any gap over gap_threshold_min likely means the
    server was asleep/down during that window."""
    try:
        limit = int(request.args.get("limit", 100))
    except Exception:
        limit = 100
    gap_threshold_min = 20
    try:
        with open(_UPTIME_LOG_FILE) as f:
            lines = f.readlines()
    except Exception:
        lines = []
    entries = []
    for l in lines[-limit:]:
        try:
            entries.append(json.loads(l))
        except Exception:
            continue
    # newest first for display, but compute gaps in chronological order first
    out = []
    for i, e in enumerate(entries):
        gap_min = None
        if i > 0:
            gap_min = round((e["ts"] - entries[i-1]["ts"]) / 60, 1)
        out.append({**e, "gap_min_since_prev": gap_min,
                    "likely_downtime": bool(gap_min and gap_min >= gap_threshold_min)})
    out.reverse()
    return jsonify({"entries": out, "gap_threshold_min": gap_threshold_min,
                    "total_logged": len(lines)})


@bp.route("/admin/symbol_history")
@_admin_required_proxy
@_sync_main_state
def admin_symbol_history():
    """Debug tool: look up every trade (V6, Whale Copy, Combo) for one
    symbol from the LIVE in-memory trade lists — same source the Weekly
    Report uses, so results always match what the dashboard shows."""
    symbol = request.args.get("symbol", "").upper().strip()
    if not symbol:
        return jsonify({"error": "Pass ?symbol=NILUSDT (or similar) in the URL"})

    def _match(trades):
        return [t for t in trades if symbol in t.get("symbol", "").upper()]

    result = {
        "symbol": symbol,
        "v6": _match(BACKTEST_SIGNALS),
        "wall": _match(WHALE_COPY_TRADES),
        "combo": _match(COMBO_TRADES),
    }
    return jsonify(result)


@bp.route("/admin/weekly_report")
@_admin_required_proxy
@_sync_main_state
def admin_weekly_report():
    """Compile a single copy-paste-ready performance report across V6, Wall,
    and Combo bots for the last 7 days — coin breakdown, win/loss averages,
    active thresholds, and current weekly-breaker status. Built so the user
    can share ONE block of text for external analysis instead of exporting
    multiple separate CSVs."""
    now = time.time()
    cutoff = now - 7 * 86400

    def _bot_stats(trades, label):
        closed = [t for t in trades if t.get("status") == "CLOSED" and t.get("entry_ts", 0) >= cutoff]
        wins   = [t for t in closed if t.get("result") == "WIN"]
        losses = [t for t in closed if t.get("result") == "LOSS"]
        timeouts = [t for t in closed if t.get("result") == "TIMEOUT"]
        stale  = [t for t in closed if t.get("result") == "STALE_EXIT"]
        avg_win  = round(sum(t.get("pnl_pct", 0) for t in wins) / len(wins), 2) if wins else 0
        avg_loss = round(sum(t.get("pnl_pct", 0) for t in losses) / len(losses), 2) if losses else 0
        win_rate = round(len(wins) / len(closed) * 100, 1) if closed else 0

        by_coin = {}
        for t in closed:
            sym = t.get("symbol", "?")
            by_coin.setdefault(sym, []).append(t.get("pnl_pct", 0) or 0)
        coin_avg = {s: round(sum(v) / len(v), 2) for s, v in by_coin.items()}
        best  = sorted(coin_avg.items(), key=lambda x: -x[1])[:3]
        worst = sorted(coin_avg.items(), key=lambda x: x[1])[:3]

        lines = [
            f"[{label}] {len(closed)} closed trades (7d) | Win rate: {win_rate}%",
            f"  WIN={len(wins)}  LOSS={len(losses)}  TIMEOUT={len(timeouts)}  STALE_EXIT={len(stale)}",
            f"  Avg win: {avg_win}%  |  Avg loss: {avg_loss}%",
        ]
        if best:
            lines.append("  Best coins:  " + ", ".join(f"{s} ({v}%)" for s, v in best))
        if worst:
            lines.append("  Worst coins: " + ", ".join(f"{s} ({v}%)" for s, v in worst))
        return "\n".join(lines)

    v6_report    = _bot_stats(BACKTEST_SIGNALS, "V6")
    wall_report  = _bot_stats(WHALE_COPY_TRADES, "WALL")
    combo_report = _bot_stats(COMBO_TRADES, "COMBO")

    tm = CONFIG.get("trade_management", {})
    inst = CONFIG.get("institutional", {})
    thresholds = (
        f"v6_min_score={tm.get('v6_min_score', 68)}  "
        f"v6_min_confidence={tm.get('v6_min_confidence', 0)}  "
        f"mtf_min_bullish_count={tm.get('mtf_min_bullish_count', 0)}\n"
        f"  atr_stop_loss_multiplier={inst.get('atr_stop_loss_multiplier')}  "
        f"tp1_atr_multiplier={inst.get('tp1_atr_multiplier')}\n"
        f"  trade_timeout_hours={tm.get('trade_timeout_hours', 6)}  "
        f"stale_exit_max_flat_checks={tm.get('stale_exit_max_flat_checks', 3)}\n"
        f"  bot_fund_limit_usdt={CONFIG.get('bot_fund_limit_usdt', 10.0)}"
    )

    weekly_breakers = GLOBAL_DATA.get("weekly_circuit_breakers", {})
    wb_lines = []
    for bot, st in weekly_breakers.items():
        status = f"TRIPPED ({st.get('tripped_reason', '')})" if st.get("tripped") else "OK"
        wb_lines.append(f"  {bot.upper()}: {status}  |  7d PnL: {st.get('cum_pnl_7d', 0)}%  |  trades: {st.get('trades_7d', 0)}")
    weekly_breaker_report = "\n".join(wb_lines) if wb_lines else "  (no data yet)"

    regime = GLOBAL_DATA.get("market_regime", "UNKNOWN")
    btc = GLOBAL_DATA.get("btc", {})

    report = f"""=== V6 MASTER PRO — WEEKLY PERFORMANCE REPORT ===
Generated: {_pkt_ts()}
Market regime: {regime}  |  BTC: {btc.get('price', '?')} ({btc.get('change_pct', '?')}%)

--- TRADE PERFORMANCE (last 7 days) ---
{v6_report}

{wall_report}

{combo_report}

--- WEEKLY DRAWDOWN BREAKER STATUS ---
{weekly_breaker_report}

--- ACTIVE THRESHOLDS ---
{thresholds}
"""
    return jsonify({"report": report})


@bp.route("/admin/uptime_log_csv")
@_admin_required_proxy
@_sync_main_state
def admin_uptime_log_csv():
    """Full uptime_log.jsonl as a downloadable CSV — for sharing/archiving."""
    try:
        with open(_UPTIME_LOG_FILE) as f:
            lines = f.readlines()
    except Exception:
        lines = []
    entries = []
    for l in lines:
        try:
            entries.append(json.loads(l))
        except Exception:
            continue
    rows = ["pkt,type,pid,source_ip,note"]
    for e in entries:
        rows.append(",".join(str(e.get(c, "")).replace(",", ";") for c in
                    ("pkt", "type", "pid", "source_ip", "note")))
    return Response("\n".join(rows), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment;filename=uptime_log.csv"})


@bp.route("/admin/weekly_breaker_status")
@_admin_required_proxy
@_sync_main_state
def admin_weekly_breaker_status():
    out = {}
    for b in _BOT_NAMES:
        st = _weekly_stats_by_bot.get(b, _blank_weekly_stats())
        cum = round(sum(e["pnl_pct"] for e in st.get("pnl_history", [])), 3)
        out[b] = {"tripped": st.get("tripped", False), "reason": st.get("tripped_reason", ""),
                  "tripped_at": st.get("tripped_at", ""), "cum_pnl_7d": cum,
                  "trades_7d": len(st.get("pnl_history", []))}
    return jsonify(out)


@bp.route("/admin/reset_weekly_breaker", methods=["POST"])
@_admin_required_proxy
@_sync_main_state
def admin_reset_weekly_breaker():
    bot = request.form.get("bot", "").strip().lower()
    if bot not in _BOT_NAMES:
        return redirect("/admin")
    with _weekly_lock:
        _weekly_stats_by_bot[bot] = _blank_weekly_stats()
        _save_weekly_stats()
    audit(request.remote_addr, "RESET_WEEKLY_BREAKER", "OK", f"bot={bot}")
    return redirect("/admin")


@bp.route("/admin/whale_history_status")
@_admin_required_proxy
@_sync_main_state
def admin_whale_history_status():
    try:
        with open(_WHALE_HISTORY_FILE) as f:
            lines = f.readlines()
    except Exception:
        lines = []
    first_ts, last_ts = None, None
    if lines:
        try:
            first_ts = json.loads(lines[0]).get("ts")
            last_ts  = json.loads(lines[-1]).get("ts")
        except Exception:
            pass
    span_days = round((last_ts - first_ts) / 86400, 1) if (first_ts and last_ts) else 0
    import os as _os
    size_mb = round(_os.path.getsize(_WHALE_HISTORY_FILE) / 1e6, 2) if _os.path.exists(_WHALE_HISTORY_FILE) else 0
    return jsonify({"rows": len(lines), "span_days": span_days, "size_mb": size_mb,
                    "first_ts": first_ts, "last_ts": last_ts})


@bp.route("/admin/whale_history_csv")
@_admin_required_proxy
@_sync_main_state
def admin_whale_history_csv():
    """Full whale_history.jsonl converted to CSV for download/analysis."""
    try:
        with open(_WHALE_HISTORY_FILE) as f:
            lines = f.readlines()
    except Exception:
        lines = []
    cols = ["ts","cycle","sym","price","wp","obi","obi_vel","traffic","inst_score","confirms","spike","spoof","b2p"]
    rows = [",".join(cols)]
    for l in lines:
        try:
            r = json.loads(l)
            rows.append(",".join(str(r.get(c, "")) for c in cols))
        except Exception:
            continue
    return Response("\n".join(rows), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment;filename=whale_history.csv"})


@bp.route("/admin/uptime_monitor_status")
@_admin_required_proxy
@_sync_main_state
def admin_uptime_monitor_status():
    """Reports when /health was last hit by an external monitor (e.g. UptimeRobot),
    so the admin card can show a live green/red indicator instead of guessing."""
    last = _last_external_ping.get("ts")
    if last is None:
        return jsonify({"ok": False, "seconds_ago": None, "last_ping": None,
                        "note": "No external ping received yet since this server started."})
    ago = round(time.time() - last)
    # Healthy = pinged within the last 10 minutes (covers a typical 5-min UptimeRobot interval + buffer)
    ok = ago <= 600
    return jsonify({
        "ok": ok, "seconds_ago": ago,
        "last_ping": time.strftime("%Y-%m-%d %H:%M:%S PKT", time.gmtime(last + 5 * 3600)),
        "note": "Healthy — external monitor is pinging on schedule." if ok
                else f"⚠️ No ping in {ago}s — check your UptimeRobot monitor is active and pointed at /health.",
    })


@bp.route("/admin/live_binance_holdings")
@_admin_required_proxy
@_sync_main_state
def admin_live_binance_holdings():
    """Fetches REAL account balances directly from the connected Binance
    API key — read-only, no trading. Requires 'Enable Reading' permission."""
    ex = "BINANCE"
    if ex not in _API_KEYS:
        return jsonify({"error": "No Binance API key configured", "holdings": []})
    try:
        import hmac as _hmac, hashlib as _hl, urllib.parse as _up
        import requests as _rq
        key = _API_KEYS[ex]["api_key"]
        sec = _API_KEYS[ex]["secret_key"]
        ts  = int(time.time() * 1000)
        qs  = f"timestamp={ts}"
        sig = _hmac.new(sec.encode(), qs.encode(), _hl.sha256).hexdigest()
        r   = _rq.get(f"https://api.binance.com/api/v3/account?{qs}&signature={sig}",
                      headers={"X-MBX-APIKEY": key}, timeout=10)
        data = r.json()
        if r.status_code != 200:
            return jsonify({"error": data.get("msg", f"Binance HTTP {r.status_code}"), "holdings": []})

        balances = [b for b in data.get("balances", [])
                    if float(b.get("free", 0)) + float(b.get("locked", 0)) > 0]
        out = []
        for b in balances:
            asset = b["asset"]
            total = round(float(b["free"]) + float(b["locked"]), 8)
            usd_val = None
            if asset == "USDT":
                usd_val = total
            else:
                price = fetch_ticker_price(f"{asset}USDT")
                if price:
                    usd_val = round(total * price, 2)
            out.append({
                "asset": asset, "free": float(b["free"]), "locked": float(b["locked"]),
                "total": total, "usd_value": usd_val,
            })
        out.sort(key=lambda x: x.get("usd_value") or 0, reverse=True)
        audit(request.remote_addr, "LIVE_HOLDINGS_FETCH", "OK", f"assets={len(out)}")
        return jsonify({"holdings": out, "fetched_at": _pkt_ts()})
    except Exception as e:
        log.warning(f"Live Binance holdings fetch failed: {e}")
        return jsonify({"error": str(e), "holdings": []})


@bp.route("/admin/holdings_status")
@_admin_required_proxy
@_sync_main_state
def admin_holdings_status():
    out = []
    for h in _load_holdings():
        price = fetch_ticker_price(h["symbol"])
        buy_price = h.get("buy_price", 0)
        pnl = round((price - buy_price) / buy_price * 100, 2) if buy_price and price else 0
        out.append({**h, "current_price": price, "pnl_pct": pnl})
    return jsonify(out)


@bp.route("/admin/debug_etherscan")
@_admin_required_proxy
@_sync_main_state
def admin_debug_etherscan():
    """TEMPORARY diagnostic — hits Etherscan directly, bypassing app cache,
    to reveal exactly why /api/onchain returns empty. Remove once resolved."""
    import requests as _rq
    key = os.getenv("ETHERSCAN_API_KEY", "")
    if not key:
        return jsonify({"diagnosis": "ETHERSCAN_API_KEY not visible to this process"})
    addr = "0xF977814e90dA44bFA03b6295A0616a897441aceC"
    url = (f"https://api.etherscan.io/v2/api?chainid=1&module=account&action=txlist"
           f"&address={addr}&sort=desc&page=1&offset=10&apikey={key}")
    try:
        r = _rq.get(url, timeout=10)
        data = r.json()
        return jsonify({
            "key_present": True,
            "key_last4": key[-4:],
            "http_status": r.status_code,
            "etherscan_status": data.get("status"),
            "etherscan_message": data.get("message"),
            "result_count": len(data.get("result", [])) if isinstance(data.get("result"), list) else 0,
            "sample": data.get("result", [])[:2] if isinstance(data.get("result"), list) else data.get("result"),
        })
    except Exception as e:
        return jsonify({"key_present": True, "error": str(e)})


@bp.route("/admin/logs")
@_admin_required_proxy
@_sync_main_state
def admin_logs():
    """Show recent logs in browser — Render free tier log alternative."""
    log_files = ["error.log", "system_audit.log"]
    output = []
    for lf in log_files:
        output.append(f"=== {lf} ===")
        try:
            with open(lf, "r") as f:
                lines = f.readlines()
            output.extend(lines[-100:])  # last 100 lines
        except Exception as e:
            output.append(f"Could not read {lf}: {e}")
        output.append("")
    return "<pre style='background:#0d1117;color:#c9d1d9;padding:20px;font-size:11px;white-space:pre-wrap'>" + "\n".join(output) + "</pre>"

