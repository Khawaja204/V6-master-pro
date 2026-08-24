"""Daily and weekly risk controls for V6 Master Pro.

The live state remains owned by main.py.
"""
import functools
import sys

_RISK_NAMES = {
    "_entries_allowed", "_record_trade_result", "_reset_daily_if_needed",
    "_weekly_entries_allowed", "_record_weekly_pnl", "_symbol_open_elsewhere",
    "_blank_bot_stats", "_blank_weekly_stats", "_load_weekly_stats",
    "_save_weekly_stats",
}
_ENGINE_NAMES = _RISK_NAMES | {
    "_execute_paper_trade", "_execute_real_binance_spot",
    "_execute_real_binance_spot_grid", "_execution_guard",
    "_save_paper_trades", "_record_backtest_signal",
    "_record_whale_copy_trade", "_save_whale_copy_trades",
    "_save_combo_trades",
}

def _with_main_state(fn):
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        main = sys.modules.get("main") or sys.modules.get("__main__")
        if main is None:
            raise RuntimeError("main module is not loaded")
        for name, value in vars(main).items():
            if name not in _ENGINE_NAMES and name not in {"wrapped", "fn"}:
                globals()[name] = value
        return fn(*args, **kwargs)
    return wrapped


@_with_main_state
def _symbol_open_elsewhere(symbol: str, exclude_bot: str) -> str:
    """Cross-bot exposure guard — returns the name of another bot that
    already has an OPEN position on `symbol`, or "" if none. Prevents
    V6 + Wall + Combo from all piling into the same coin at once, which
    would silently multiply real exposure beyond each bot's own fund limit."""
    if exclude_bot != "v6" and any(b.get("symbol") == symbol and b.get("status") == "OPEN"
                                    for b in BACKTEST_SIGNALS):
        return "v6"
    if exclude_bot != "wall" and any(t.get("symbol") == symbol and t.get("status") == "OPEN"
                                      for t in WHALE_COPY_TRADES):
        return "wall"
    if exclude_bot != "combo" and any(t.get("symbol") == symbol and t.get("status") == "OPEN"
                                       for t in COMBO_TRADES):
        return "combo"
    return ""


@_with_main_state
def _load_weekly_stats() -> dict:
    try:
        with open(_WEEKLY_TRIP_FILE) as f:
            saved = json.load(f)
        return {b: {**_blank_weekly_stats(), **saved.get(b, {})} for b in _BOT_NAMES}
    except Exception:
        return {b: _blank_weekly_stats() for b in _BOT_NAMES}


@_with_main_state
def _blank_bot_stats() -> dict:
    return {"date": "", "losses": 0, "wins": 0, "opens": 0,
            "realized_pnl_pct": 0.0, "tripped": False, "tripped_reason": ""}


@_with_main_state
def _save_weekly_stats():
    try:
        with open(_WEEKLY_TRIP_FILE, "w") as f:
            json.dump(_weekly_stats_by_bot, f, indent=2)
    except Exception as e:
        log.debug(f"weekly circuit state save failed: {e}")


@_with_main_state
def _entries_allowed(bot: str = "v6") -> bool:
    """False when that bot's daily circuit-breaker has tripped, OR when
    today's opened-trade count has already hit daily_max_trades — an
    overtrading guard independent of win/loss (caps how many NEW positions
    a bot can open per day, regardless of how they turn out).
    bot: "v6" | "wall" | "combo" — each gated independently."""
    with _daily_lock:
        _reset_daily_if_needed(bot)
        stats = _daily_stats_by_bot[bot]
        if stats["tripped"]:
            return False
        bot_cfg = CONFIG.get("bots", {}).get(bot, {})
        tm      = CONFIG.get("trade_management", {})
        max_trades = bot_cfg.get("daily_max_trades", tm.get("daily_max_trades", 0))
        if max_trades and stats.get("opens", 0) >= max_trades:
            return False
        return True


@_with_main_state
def _reset_daily_if_needed(bot: str = "v6") -> None:
    stats = _daily_stats_by_bot[bot]
    today = _today_utc()
    if stats["date"] != today:
        stats.update({"date": today, "losses": 0, "wins": 0, "opens": 0,
                      "realized_pnl_pct": 0.0, "tripped": False,
                      "tripped_reason": ""})


@_with_main_state
def _record_weekly_pnl(bot: str, pnl_pct: float) -> None:
    """Rolls a closed trade's PnL into that bot's 7-day window; trips a
    WEEKLY (not daily-reset) breaker if cumulative drawdown exceeds the
    configured limit. Stays tripped across day boundaries until an admin
    manually resets it — catches slow bleed across many small daily losses
    that never individually trip the daily breaker."""
    with _weekly_lock:
        st = _weekly_stats_by_bot.setdefault(bot, _blank_weekly_stats())
        now = time.time()
        st["pnl_history"].append({"ts": now, "pnl_pct": pnl_pct or 0.0})
        cutoff = now - 7 * 86400
        st["pnl_history"] = [e for e in st["pnl_history"] if e["ts"] >= cutoff]

        max_weekly_dd = abs(CONFIG.get("bots", {}).get(bot, {}).get(
            "weekly_max_drawdown_pct", CONFIG.get("trade_management", {}).get("weekly_max_drawdown_pct", 20.0)))
        cum_pnl = round(sum(e["pnl_pct"] for e in st["pnl_history"]), 3)
        if not st["tripped"] and cum_pnl <= -max_weekly_dd:
            st["tripped"] = True
            st["tripped_reason"] = f"7-day cumulative drawdown {cum_pnl}% ≤ -{max_weekly_dd}%"
            st["tripped_at"] = _pkt_ts()
            log.warning(f"[WEEKLY-BREAKER:{bot.upper()}] Tripped: {st['tripped_reason']}")
            audit("SYSTEM", f"WEEKLY_BREAKER_{bot.upper()}", "TRIPPED", st["tripped_reason"])
# Bypassed:             send_telegram(
#                 f"🛑 <b>{bot.upper()} BOT — WEEKLY DRAWDOWN BREAKER TRIPPED</b>\n"
#                 f"Reason: {st['tripped_reason']}\n"
#                 f"⛔ {bot.upper()} bot entries paused for the week — "
#                 f"reset manually in Admin once you've reviewed what happened."
#             )
        GLOBAL_DATA.setdefault("weekly_circuit_breakers", {})[bot] = dict(st)
        _save_weekly_stats()


@_with_main_state
def _blank_weekly_stats() -> dict:
    return {"pnl_history": [], "tripped": False, "tripped_reason": "", "tripped_at": ""}


@_with_main_state
def _record_trade_result(is_win: bool, pnl_pct: float, bot: str = "v6") -> None:
    """Feed a resolved trade into that bot's daily circuit-breaker; trip if limits hit."""
    with _daily_lock:
        _reset_daily_if_needed(bot)
        stats = _daily_stats_by_bot[bot]
        if is_win:
            stats["wins"] += 1
        else:
            stats["losses"] += 1
        stats["realized_pnl_pct"] = round(stats["realized_pnl_pct"] + (pnl_pct or 0.0), 3)

        bot_cfg  = CONFIG.get("bots", {}).get(bot, {})
        tm       = CONFIG.get("trade_management", {})
        max_loss = bot_cfg.get("daily_max_losses", tm.get("daily_max_losses", 3))
        max_dd   = abs(bot_cfg.get("daily_max_drawdown_pct", tm.get("daily_max_drawdown_pct", 10.0)))
        just_tripped = False
        if not stats["tripped"]:
            if stats["losses"] >= max_loss:
                stats["tripped"] = True
                stats["tripped_reason"] = f"{stats['losses']} losses ≥ {max_loss}"
                just_tripped = True
            elif stats["realized_pnl_pct"] <= -max_dd:
                stats["tripped"] = True
                stats["tripped_reason"] = f"drawdown {stats['realized_pnl_pct']}% ≤ -{max_dd}%"
                just_tripped = True
        GLOBAL_DATA.setdefault("circuit_breakers", {})[bot] = dict(stats)
        GLOBAL_DATA["circuit_breaker"] = dict(_daily_stats_by_bot["v6"])

    if just_tripped:
        log.warning(f"[CIRCUIT-BREAKER:{bot.upper()}] Tripped: {stats['tripped_reason']} — entries paused for the day")
        audit("SYSTEM", f"CIRCUIT_BREAKER_{bot.upper()}", "TRIPPED", stats["tripped_reason"])


@_with_main_state
def _weekly_entries_allowed(bot: str = "v6") -> bool:
    with _weekly_lock:
        return not _weekly_stats_by_bot.get(bot, {}).get("tripped", False)

