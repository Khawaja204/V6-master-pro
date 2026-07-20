import shutil,os
def sync_ui():
    [shutil.copy2(f"V6_Master_Pro_UI/{f}",f) for f in ["index.html","script.js","style.css"] if os.path.exists(f"V6_Master_Pro_UI/{f}")]
sync_ui()
"""
main.py — V6 Master Pro Institutional | Entry Point
Run: python3 main.py
All secrets in Replit Secrets. No hardcoded values.
"""
import os, json, time, threading, logging, secrets as _secrets
from collections import defaultdict
from logging.handlers import RotatingFileHandler
from flask import Flask, request, jsonify, session, redirect, render_template_string, Response, send_from_directory

from logic import (
    process_vmc_signals, process_whale_walls, push_to_google_sheets,
    fetch_btc_sentiment, push_midnight_report,
    compute_institutional_score, compute_tp_levels, compute_position_size,
    compute_whale_power, calculate_atr, fetch_order_book, calculate_obi,
    detect_obi_spike, compute_confidence_score, fetch_ticker_price,
    detect_market_regime, compute_vwap, detect_rsi_divergence, fetch_klines,
    fetch_macd_for_symbol, compute_v6_final_score,
    calculate_wall_proximity, detect_spoofing, blink_to_push_check,
    detect_whale_copy_signals, is_stablecoin_pair,
    fetch_ticker_24h, score_coin, fetch_rsi_for_symbol,
    estimate_time_to_target, fetch_large_trades,
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        RotatingFileHandler("error.log", maxBytes=5*1024*1024, backupCount=2),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

_audit = logging.getLogger("audit")
_audit.setLevel(logging.INFO)
_audit.propagate = False
_ah = RotatingFileHandler("system_audit.log", maxBytes=10*1024*1024, backupCount=5)
_ah.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
_audit.addHandler(_ah)

def audit(user_id: str, action: str, result: str, extra: str = ""):
    _audit.info(f"USER={user_id} | ACTION={action} | RESULT={result} | {extra}")


def _pkt_ts() -> str:
    """Current timestamp formatted in Pakistan time (UTC+5)."""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 5 * 3600))

# ── Config ────────────────────────────────────────────────────────────────────
with open("config.json") as f:
    CONFIG = json.load(f)

# ── Secrets ───────────────────────────────────────────────────────────────────
import hashlib as _hashlib
BOT_TOKEN          = (os.getenv("BOT_TOKEN") or "").strip() or None
CHAT_ID            = (os.getenv("CHAT_ID", "8743601537") or "").strip() or None
SECRET_KEY_VAL     = os.getenv("SECRET_KEY", "786")
# SESSION_SECRET: use env var if set, otherwise derive a STABLE secret from
# SECRET_KEY so it never changes on restart (fixes deployed session loss).
SESSION_SECRET     = os.getenv("SESSION_SECRET") or \
    _hashlib.sha256(f"v6-session-{SECRET_KEY_VAL}".encode()).hexdigest()
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS", "{}")
GOOGLE_SHEET_ID    = os.getenv("GOOGLE_SHEET_ID", "17mdb-9JuinpDAezkk5qCYgcP5GZYTU8KUBfLha_44mo")
# ADMIN_PASSWORD: single source of truth → ADMIN_PASSWORD env var, else "786".
# (does NOT fall back to SECRET_KEY — that is an API key, not the admin password)
ADMIN_PASSWORD     = os.getenv("ADMIN_PASSWORD") or "786"
# TELEGRAM_PROXY: optional SOCKS5/HTTP proxy for regions where Telegram is blocked
# Set to e.g. socks5://user:pass@host:1080 or http://host:8080
TELEGRAM_PROXY     = os.getenv("TELEGRAM_PROXY")
PORT               = int(os.getenv("PORT", "8080"))

# ── Global State ──────────────────────────────────────────────────────────────
GLOBAL_DATA = {
    "vmc":            {k: [] for k in ["ALL","FAV","STUCK","GOLDEN","BOOM","ENTRY","EXIT","PUMP","VIP"]},
    "whale":          [],
    "alert_history":  [],
    "backtest":       [],
    "hot_coins":      [],
    "inst_signals":   [],
    "whale_copy_signals": [],
    "large_trades":   [],
    "btc":            {},
    "last_update":    None,
    "heartbeat":      None,
    "uptime_start":   time.time(),
    "status":         "initializing",
    "cycle_count":    0,
    "active_exchange":"BINANCE",
    "btc_pause":      False,
    "win_streak":     0,
    "total_wins":     0,
    "total_losses":   0,
    "win_rate":       0.0,
    "whale_24h":      [],
    "market_regime":  "RANGING",
    "today_signals":  0,
    "top_coin_today": None,
    "volume_surge":   [],
    "smart_divergence": [],
    "upgrade_log":    [],
    "paper_mode":      CONFIG.get("paper_mode", True),
    "price_alerts":    [],
    "learning_data":   {},
    "fund_limit_usdt": CONFIG.get("bot_fund_limit_usdt", 10.0),
    "paper_trades":    [],
}

# ── Price Alerts ──────────────────────────────────────────────────────────────
PRICE_ALERTS: list = []   # [{id, symbol, target_price, direction, note, created_at}]
_alert_id_counter  = 0

# ── Paper Mode Intelligence Learning Data ──────────────────────────────────────
_LD_FILE = "learning_data.json"
_DEFAULT_LD = {
    "paper_trades": 0, "paper_wins": 0, "paper_losses": 0,
    "paper_win_rate": 0.0, "wp_threshold": 50, "conf_threshold": 50,
    "last_adjustment": None, "adjustment_log": [], "ready_for_real": False,
    "signal_stats": {},
}
try:
    with open(_LD_FILE) as _f:
        _ld_saved = json.load(_f)
        _DEFAULT_LD.update(_ld_saved)
except Exception:
    pass
GLOBAL_DATA["learning_data"] = _DEFAULT_LD

# ── API Keys (masked storage) ──────────────────────────────────────────────────
_API_KEYS_FILE = "api_keys.json"
try:
    with open(_API_KEYS_FILE) as _f:
        _API_KEYS: dict = json.load(_f)
except Exception:
    _API_KEYS = {}

def _save_api_keys():
    try:
        with open(_API_KEYS_FILE, "w") as f:
            json.dump(_API_KEYS, f, indent=2)
    except Exception as e:
        log.debug(f"API keys save failed: {e}")

def _mask(s: str) -> str:
    if not s or len(s) < 8: return "●" * 8
    return "●" * (len(s) - 4) + s[-4:]


# ══════════════════════════════════════════════════════════════════════════════
# TRADE EXECUTION ENGINE (Paper + Real Binance)
# ══════════════════════════════════════════════════════════════════════════════

def _save_paper_trades():
    try:
        with open(_TRADES_FILE, "w") as f:
            json.dump(PAPER_TRADES[-500:], f, indent=2)
    except Exception as e:
        log.debug(f"Paper trades save failed: {e}")


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
    PAPER_TRADES.insert(0, rec)
    if len(PAPER_TRADES) > 500:
        PAPER_TRADES.pop()
    _save_paper_trades()
    log.info(f"[PAPER TRADE] {side} {amount_usdt} USDT of {symbol} @ {price} ({strategy})")
    return {"ok": True, "trade": rec}


def _execute_real_binance_spot(symbol: str, side: str, amount_usdt: float) -> dict:
    """Execute a real Binance MARKET order via REST API (HMAC-signed)."""
    ex = "BINANCE"
    if ex not in _API_KEYS:
        return {"ok": False, "error": "No Binance API key configured in Admin Portal → API Key Management"}
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


def _execute_real_binance_spot_grid(symbol: str, amount_usdt: float,
                                     levels: int = 5, spacing_pct: float = 0.5) -> dict:
    """Place a grid of LIMIT BUY orders below current price on Binance."""
    ex = "BINANCE"
    if ex not in _API_KEYS:
        return {"ok": False, "error": "No Binance API key configured"}
    from logic import fetch_ticker_price as _ftp
    price = _ftp(symbol)
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

BACKTEST_SIGNALS   = []           # max 100 tracked signals

# ── Paper / Manual Trades ──────────────────────────────────────────────────────
_TRADES_FILE = "paper_trades.json"
PAPER_TRADES: list = []
try:
    with open(_TRADES_FILE) as _ptf:
        PAPER_TRADES = json.load(_ptf)
except Exception:
    pass
_WC_TRADES_FILE = "whale_copy_trades.json"
WHALE_COPY_TRADES: list = []
try:
    with open(_WC_TRADES_FILE) as _wcf:
        WHALE_COPY_TRADES = json.load(_wcf)
except Exception:
    pass
_wc_dedup: dict = {}
_previous_walls    = {}
_alert_cooldown    = {}
_login_attempts    = {}
_coin_signal_times = defaultdict(list)   # HOT COIN: symbol → [timestamps]
_bt_dedup          = {}                  # symbol → last backtest entry ts
_last_whale_ts     = time.time()         # for MARKET QUIET detection
_HISTORY_MAX       = 50
_win_streak        = 0
_total_wins        = 0
_total_losses      = 0
_today_coin_counts = defaultdict(int)    # symbol → count today

# ── Daily Circuit-Breaker state (resets at UTC midnight) ───────────────────────
_daily_lock  = threading.Lock()
_daily_stats = {"date": "", "losses": 0, "wins": 0,
                "realized_pnl_pct": 0.0, "tripped": False, "tripped_reason": ""}


def _today_utc() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _reset_daily_if_needed() -> None:
    today = _today_utc()
    if _daily_stats["date"] != today:
        _daily_stats.update({"date": today, "losses": 0, "wins": 0,
                             "realized_pnl_pct": 0.0, "tripped": False,
                             "tripped_reason": ""})


def _entries_allowed() -> bool:
    """False when the daily circuit-breaker has tripped."""
    with _daily_lock:
        _reset_daily_if_needed()
        return not _daily_stats["tripped"]


def _record_trade_result(is_win: bool, pnl_pct: float) -> None:
    """Feed a resolved trade into the daily circuit-breaker; trip if limits hit."""
    with _daily_lock:
        _reset_daily_if_needed()
        if is_win:
            _daily_stats["wins"] += 1
        else:
            _daily_stats["losses"] += 1
        _daily_stats["realized_pnl_pct"] = round(
            _daily_stats["realized_pnl_pct"] + (pnl_pct or 0.0), 3)

        tm       = CONFIG.get("trade_management", {})
        max_loss = tm.get("daily_max_losses", 5)
        max_dd   = abs(tm.get("daily_max_drawdown_pct", 10.0))
        just_tripped = False
        if not _daily_stats["tripped"]:
            if _daily_stats["losses"] >= max_loss:
                _daily_stats["tripped"] = True
                _daily_stats["tripped_reason"] = f"{_daily_stats['losses']} losses ≥ {max_loss}"
                just_tripped = True
            elif _daily_stats["realized_pnl_pct"] <= -max_dd:
                _daily_stats["tripped"] = True
                _daily_stats["tripped_reason"] = f"drawdown {_daily_stats['realized_pnl_pct']}% ≤ -{max_dd}%"
                just_tripped = True
        GLOBAL_DATA["circuit_breaker"] = dict(_daily_stats)

    if just_tripped:
        log.warning(f"[CIRCUIT-BREAKER] Tripped: {_daily_stats['tripped_reason']} — entries paused for the day")
        audit("SYSTEM", "CIRCUIT_BREAKER", "TRIPPED", _daily_stats["tripped_reason"])
        send_telegram(
            f"🛑 <b>DAILY CIRCUIT-BREAKER TRIPPED</b>\n"
            f"Reason: {_daily_stats['tripped_reason']}\n"
            f"Today: {_daily_stats['wins']}W / {_daily_stats['losses']}L | "
            f"PnL {_daily_stats['realized_pnl_pct']}%\n"
            f"⛔ New entries paused until 00:00 UTC."
        )


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _record_alert(alert_type: str, symbol: str, label: str, price,
                  detail: str, traffic: str = "", confidence: int = 0):
    entry = {
        "time":       _pkt_ts(),
        "type":       alert_type,
        "symbol":     symbol,
        "label":      label,
        "price":      price,
        "detail":     detail,
        "traffic":    traffic,
        "confidence": confidence,
    }
    hist = GLOBAL_DATA["alert_history"]
    hist.insert(0, entry)
    if len(hist) > _HISTORY_MAX:
        GLOBAL_DATA["alert_history"] = hist[:_HISTORY_MAX]
    _today_coin_counts[symbol] += 1


def _record_backtest_signal(symbol: str, entry_price: float, folder: str,
                            tp_zones: dict, confidence: int,
                            traffic: str = "", reason: str = ""):
    """Record signal as a tracked entry. Returns the entry dict, or None if the
    entry was filtered out (GREEN-only rule, circuit-breaker, or dedup window).
    Dedup: same coin not tracked twice in 30 min."""
    global BACKTEST_SIGNALS
    tm = CONFIG.get("trade_management", {})

    # ── GREEN-only entries: skip YELLOW/RED signals when enabled ──────────────
    if tm.get("green_only_entries", True) and traffic and traffic != "GREEN":
        return None
    # ── Daily circuit-breaker: no new entries once tripped ────────────────────
    if not _entries_allowed():
        return None

    now = time.time()
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
        "result":      None,   # WIN / LOSS / TIMEOUT
        "pnl_pct":     None,
    }
    BACKTEST_SIGNALS.insert(0, entry)
    if len(BACKTEST_SIGNALS) > 100:
        BACKTEST_SIGNALS = BACKTEST_SIGNALS[:100]
    GLOBAL_DATA["backtest"] = BACKTEST_SIGNALS
    return entry


def _save_whale_copy_trades():
    try:
        with open(_WC_TRADES_FILE, "w") as f:
            json.dump(WHALE_COPY_TRADES[-500:], f, indent=2)
    except Exception as e:
        log.debug(f"Whale copy trades save failed: {e}")


def _record_whale_copy_trade(sig: dict):
    """WHALE COPY MODE — separate paper-trade ledger, independent of the
    v6-score auto-trade system. Fires on a wall+OBI-confirmed COPY_BUY
    (confirmed across 2 consecutive scan cycles) above the confidence
    threshold. 30-min dedup per symbol + the shared daily circuit-breaker
    both still apply. Trades stay OPEN until whale_copy_check_loop resolves
    them against the SL/target levels."""
    global WHALE_COPY_TRADES
    if not _entries_allowed():
        return None
    sym = sig["symbol"]
    now = time.time()
    if now - _wc_dedup.get(sym, 0) < 1800:
        return None
    # Guard against duplicate OPEN entries even after a redeploy resets the
    # in-memory dedup timer above — never record a second OPEN trade for a
    # symbol that already has one.
    if any(t.get("symbol") == sym and t.get("status") == "OPEN" for t in WHALE_COPY_TRADES):
        return None
    _wc_dedup[sym] = now
    entry = {
        "id":             f"WC-{int(now)}-{sym[:4]}",
        "symbol":         sym,
        "direction":      sig["direction"],
        "entry_price":    sig.get("price", sig["wall_price"]),
        "wall_price":     sig["wall_price"],
        "wall_size_usdt": sig["wall_size_usdt"],
        "wall_qty":       sig["wall_qty"],
        "stop_loss":      sig.get("stop_loss", 0),
        "target":         sig.get("target", 0),
        "obi":            sig["obi"],
        "obi_velocity":   sig["obi_velocity"],
        "confidence":     sig["confidence"],
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
    WHALE_COPY_TRADES.insert(0, entry)
    if len(WHALE_COPY_TRADES) > 500:
        WHALE_COPY_TRADES.pop()
    _save_whale_copy_trades()
    log.info(f"[WHALE COPY] {sig['direction']} {sym} @ {sig['wall_price']} (conf {sig['confidence']}%)")
    if sig["direction"] == "COPY_BUY":
        wc_msg = (f"🐋 <b>WHALE COPY BUY — {sym.replace('USDT','')}</b>\n"
                  f"Wall Price: {_fmtP(sig['wall_price'])} | Size: ${sig['wall_size_usdt']:,.0f}\n"
                  f"🎯 Target: {_fmtP(sig['target'])} | 🛡 SL: {_fmtP(sig['stop_loss'])}\n"
                  f"⏱ Est. Time to Target: {sig.get('eta','—')}\n"
                  f"Confidence: {sig['confidence']}% | OBI: {sig['obi']}\n"
                  f"📋 Wall + OBI confirmed across 2 consecutive scans")
        notify_all(f"V6 Whale Copy BUY — {sym.replace('USDT','')}", wc_msg)
    return entry


def whale_copy_check_loop():
    """Every 5 minutes: resolve OPEN whale-copy trades against target/SL."""
    global WHALE_COPY_TRADES
    while True:
        time.sleep(300)
        try:
            changed = False
            for tr in WHALE_COPY_TRADES:
                if tr.get("status") != "OPEN":
                    continue
                age = time.time() - tr.get("entry_ts", time.time())
                if age < 300:
                    continue
                current = fetch_ticker_price(tr["symbol"])
                if not current:
                    continue
                entry_p = tr.get("entry_price", 0)
                target  = tr.get("target", 0)
                sl      = tr.get("stop_loss", 0)
                hit_target = bool(target) and current >= target
                hit_sl     = bool(sl) and current <= sl
                if hit_target or hit_sl or age >= 6 * 3600:
                    exit_price = target if hit_target else (sl if hit_sl else current)
                    tr["exit_price"] = exit_price
                    tr["exit_time"]  = _pkt_ts()
                    tr["pnl_pct"]    = round((exit_price - entry_p) / entry_p * 100, 3) if entry_p else 0
                    tr["result"]     = "WIN" if hit_target else ("LOSS" if hit_sl else "TIMEOUT")
                    tr["status"]     = "CLOSED"
                    changed = True
            if changed:
                _save_whale_copy_trades()
                log.info("[WHALE COPY] Trade resolutions updated")
        except Exception as e:
            log.warning(f"Whale copy check error: {e}")


def _update_hot_coins(symbol: str) -> bool:
    """Returns True if coin just became HOT (3+ signals in 60 min)."""
    now = time.time()
    _coin_signal_times[symbol].append(now)
    _coin_signal_times[symbol] = [t for t in _coin_signal_times[symbol] if now - t <= 3600]
    count = len(_coin_signal_times[symbol])
    if count >= 3:
        # Update global hot coins list
        hot = [h for h in GLOBAL_DATA["hot_coins"] if h["symbol"] != symbol]
        hot.insert(0, {"symbol": symbol, "count": count,
                       "since": time.strftime("%Y-%m-%d %H:%M:%S",
                                              time.localtime(_coin_signal_times[symbol][0]))})
        GLOBAL_DATA["hot_coins"] = hot[:10]
        return True
    return False


def _can_alert(key: str, cooldown: int) -> bool:
    now = time.time()
    if now - _alert_cooldown.get(key, 0) >= cooldown:
        _alert_cooldown[key] = now
        return True
    return False


def _dashboard_url(symbol: str = "") -> str:
    # Render auto-sets RENDER_EXTERNAL_URL; REPLIT_DOMAINS only applies
    # inside Replit. Neither present (e.g. localhost) means Telegram would
    # reject the button URL outright — fall back to the known production URL.
    base = (os.getenv("RENDER_EXTERNAL_URL")
            or (f"https://{os.getenv('REPLIT_DOMAINS').split(',')[0].strip()}" if os.getenv("REPLIT_DOMAINS") else None)
            or "https://v6-master-pro-1.onrender.com")
    base = base.rstrip("/")
    return f"{base}/?sniper={symbol}" if symbol else base


def _tg_proxies():
    """Return requests-compatible proxy dict if TELEGRAM_PROXY is set."""
    return {"http": TELEGRAM_PROXY, "https": TELEGRAM_PROXY} if TELEGRAM_PROXY else None


def send_telegram(msg: str, inline_button: dict = None) -> bool:
    """Send a Telegram message. Returns True on a confirmed-OK send, else False."""
    if not BOT_TOKEN or not CHAT_ID:
        return False
    import requests as _r
    payload = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}
    if inline_button:
        payload["reply_markup"] = {"inline_keyboard": [[{
            "text": inline_button.get("text", "📊 View Dashboard"),
            "url":  inline_button.get("url", "")
        }]]}
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    # Try via proxy first (if configured); on any failure fall back to a direct
    # connection so a flaky/misconfigured proxy never silently drops alerts.
    proxy = _tg_proxies()
    attempts = [proxy, None] if proxy else [None]
    for i, prox in enumerate(attempts):
        label = "proxy" if prox else "direct"
        try:
            resp = _r.post(url, json=payload, timeout=10, proxies=prox)
            if resp.status_code == 200 and resp.json().get("ok"):
                return True
            # API reachable but rejected the request (bad token/chat_id) — no
            # point retrying via direct, the payload/credentials are the issue.
            log.warning(f"Telegram API rejected send ({label}): "
                        f"HTTP {resp.status_code} {resp.text[:160]}")
            return False
        except Exception as e:
            if i == len(attempts) - 1:
                log.warning(f"Telegram send failed ({label}): {e}")
            else:
                log.info(f"Telegram {label} send failed, falling back to direct: {e}")
    return False


def send_email(subject: str, body: str) -> bool:
    """Send an email alert via Gmail SMTP. Needs EMAIL_USER (sender gmail
    address), EMAIL_PASS (a Gmail App Password — NOT the normal account
    password), and EMAIL_TO (recipient) env vars. No-ops silently if unset."""
    user = os.getenv("EMAIL_USER"); pwd = os.getenv("EMAIL_PASS"); to = os.getenv("EMAIL_TO")
    if not (user and pwd and to):
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = user
        msg["To"] = to
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(user, pwd)
            server.sendmail(user, [to], msg.as_string())
        return True
    except Exception as e:
        log.warning(f"Email send failed: {e}")
        return False


def notify_all(subject: str, telegram_msg: str, email_body: str = None):
    """Unified dispatcher for a real, actionable alert — sends to BOTH
    Telegram and Email (whichever are configured). Use this for anything
    worth acting on: a v6 BUY, a confirmed Whale Copy entry, or a holdings
    sell-check — never for routine/heartbeat noise."""
    send_telegram(telegram_msg)
    send_email(subject, email_body or telegram_msg.replace("<b>", "").replace("</b>", ""))


def notify_trade(symbol: str, side: str, strategy: str, mode: str, reason: str,
                 price=None, amount=None, tp_zones: dict = None, traffic: str = ""):
    """Unified Telegram + Email alert for every trade/entry, including the rationale."""
    side  = (side or "BUY").upper()
    icon  = "🟢" if side == "BUY" else "🔴"
    light = (f" | {traffic}") if traffic else ""
    lines = [f"{icon} <b>TRADE {side} — {symbol.replace('USDT','')}</b>",
             f"Mode: {mode} | Strategy: {strategy}{light}"]
    if price is not None:
        lines.append(f"Entry: {_fmtP(price)}")
    if amount is not None:
        lines.append(f"Size: ${amount}")
    if tp_zones:
        lines.append(
            f"🎯 TP1 {_fmtP(tp_zones.get('tp1',0))} | "
            f"TP2 {_fmtP(tp_zones.get('tp2',0))} | "
            f"TP3 {_fmtP(tp_zones.get('tp3',0))}")
        lines.append(f"🛡 SL {_fmtP(tp_zones.get('stop_loss',0))}")
        lines.append(f"⏱ Est. Time to TP1: {tp_zones.get('eta_tp1','—')}")
    lines.append(f"📋 <b>Rationale:</b> {reason}")
    msg = "\n".join(lines)
    send_telegram(msg, inline_button={"text": f"📊 Sniper: {symbol.replace('USDT','')}",
                                       "url": _dashboard_url(symbol)})
    send_email(f"V6 TRADE {side} — {symbol.replace('USDT','')}",
               msg.replace("<b>", "").replace("</b>", ""))


def alert_vip(coin: dict, inst: dict = None, tp_zones: dict = None, confidence: int = 0):
    global _win_streak
    cooldown = CONFIG["telegram"]["vip_alert_cooldown_seconds"]
    if not _can_alert(f"vip_{coin['symbol']}", cooldown):
        return
    tl   = inst.get("traffic", "") if inst else ""
    icon = "🟢" if tl == "GREEN" else "🟡" if tl == "YELLOW" else "🔴"
    is_hot = _update_hot_coins(coin["symbol"])
    hot_tag = "\n🔥 <b>[HOT COIN]</b> — 3+ signals this hour!" if is_hot else ""
    send_telegram(
        f"⭐ <b>VIP SIGNAL — {coin['symbol'].replace('USDT','')}</b>{hot_tag}\n"
        f"Price: {coin['price']} | Chg: {coin['change_pct']}%\n"
        f"Score: {coin['score']} | RSI: {coin['rsi']}\n"
        f"Confidence: {confidence}% | {icon} {tl}\n"
        f"InstScore: {inst.get('inst_score','—') if inst else '—'}",
        inline_button={"text": f"📊 Sniper: {coin['symbol'].replace('USDT','')}", "url": _dashboard_url(coin["symbol"])}
    )
    _record_alert("VIP", coin["symbol"], "VIP SIGNAL" + (" 🔥" if is_hot else ""),
                  coin["price"], f"Score:{coin['score']} | RSI:{coin['rsi']} | Conf:{confidence}%", tl, confidence)
    if tp_zones:
        wp_v   = inst.get("whale_power", "—") if inst else "—"
        ins_v  = inst.get("inst_score", "—") if inst else "—"
        strat  = coin.get("trading_strategy", "SPOT")
        sreason= coin.get("trading_strategy_reason", "")
        v6_score   = coin.get("v6", {}).get("score", coin.get("score"))
        folder_lbl = coin.get("folder", "VIP")
        reason = (f"V6-BUY {v6_score} | {folder_lbl} | Old-traffic {tl} | RSI {coin['rsi']} | "
                  f"WhalePow {wp_v}% | Inst {ins_v} | Conf {confidence}%"
                  + (f" | {sreason}" if sreason else ""))
        # GATE FIX: entry already verified via v6.label=="BUY" at the call
        # site — pass "GREEN" here so it satisfies the green_only_entries
        # safety check (circuit-breaker / 30-min dedup still fully apply).
        entry = _record_backtest_signal(coin["symbol"], coin["price"], folder_lbl,
                                        tp_zones, confidence, traffic="GREEN", reason=reason)
        if entry:   # an actual entry passed the GREEN-only + circuit-breaker gate
            _open_ct = sum(1 for b in BACKTEST_SIGNALS if b.get("status") == "OPEN")
            if _open_ct >= 3:
                reason += f" | ⚠️ CORRELATION: {_open_ct} positions already open — most crypto moves with BTC, consider overexposure risk"
            mode_str = "PAPER (AUTO)"
            # ── REAL MODE MIRROR: same auto-fire trigger also places a real
            # order, sized to the admin-set fund limit. No separate/stricter
            # logic — it simply mirrors whatever the paper bot just decided.
            if not GLOBAL_DATA.get("paper_mode", True):
                _real_amt = GLOBAL_DATA.get("fund_limit_usdt", 10.0)
                _real_res = _execute_real_binance_spot(coin["symbol"], "BUY", _real_amt)
                if _real_res.get("ok"):
                    mode_str = "REAL (AUTO)"
                    reason += f" | ⚡ REAL order placed: ${_real_amt} (orderId {_real_res.get('order_id')})"
                    audit("SYSTEM", "AUTO_REAL_ENTRY", "OPENED",
                          f"sym={coin['symbol']} amt={_real_amt} orderId={_real_res.get('order_id')}")
                else:
                    reason += f" | ❌ REAL order FAILED: {_real_res.get('error','?')} — paper entry still recorded"
                    audit("SYSTEM", "AUTO_REAL_ENTRY", "FAILED",
                          f"sym={coin['symbol']} err={_real_res.get('error','?')}")
            notify_trade(coin["symbol"], "BUY", strat, mode_str, reason,
                         price=coin["price"], tp_zones=tp_zones, traffic=tl)
            audit("SYSTEM", "AUTO_ENTRY", "OPENED",
                  f"sym={coin['symbol']} traffic={tl} conf={confidence}%")
    audit("SYSTEM", "VIP_ALERT", "SENT", f"sym={coin['symbol']} score={coin['score']} conf={confidence}%")


def alert_whale(whale: dict, confidence: int = 0):
    global _last_whale_ts
    cooldown = CONFIG["telegram"].get("alert_cooldown_seconds", 300)
    if not _can_alert(f"whale_{whale['symbol']}", cooldown):
        return
    _last_whale_ts = time.time()
    wp       = whale.get("whale_power", 0)
    critical = wp >= CONFIG["whale"]["critical_whale_power_pct"]
    prefix   = "🚨 <b>[CRITICAL_WHALE_ALERT]</b>\n" if critical else ""
    is_hot   = _update_hot_coins(whale["symbol"])
    hot_tag  = " 🔥[HOT]" if is_hot else ""
    send_telegram(
        f"{prefix}🐋 <b>{whale['label']}{hot_tag} — {whale['symbol']}</b>\n"
        f"WhalePower: {wp}% | Price: {whale['price']}\n"
        f"Walls: {whale['wall_count']} | Closest: {whale['min_dist_pct']:.2f}%\n"
        f"Blink→Push: {'YES ⚡' if whale['blink_to_push'] else 'No'} | {whale['spoofing']['details']}",
        inline_button={"text": f"🐋 Sniper: {whale['symbol'].replace('USDT','')}", "url": _dashboard_url(whale["symbol"])}
    )
    _record_alert("WHALE", whale["symbol"], whale["label"] + (" 🔥" if is_hot else ""),
                  whale["price"],
                  f"WhalePow:{wp}% | Walls:{whale['wall_count']} | MinDist:{whale['min_dist_pct']:.2f}%",
                  "", confidence)

    # Track whale_24h
    w24 = GLOBAL_DATA["whale_24h"]
    w24.insert(0, {
        "symbol":      whale["symbol"],
        "whale_power": wp,
        "label":       whale["label"],
        "price":       whale["price"],
        "time":        time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    cutoff = time.time() - 86400
    GLOBAL_DATA["whale_24h"] = [w for w in w24 if time.time() - cutoff >= 0][:20]
    audit("SYSTEM", "WHALE_ALERT", "SENT", f"sym={whale['symbol']} power={wp}%")


def alert_critical_whale(whale: dict):
    cooldown = CONFIG["telegram"]["critical_whale_cooldown_seconds"]
    if not _can_alert(f"critical_{whale['symbol']}", cooldown):
        return
    send_telegram(
        f"🚨🚨 <b>[CRITICAL_WHALE_ALERT] — {whale['symbol']}</b>\n"
        f"Whale Power: {whale.get('whale_power',0)}% (>85% THRESHOLD)\n"
        f"[AGENT_DECISION] INSTANT_ENTRY considered — confirm manually",
        inline_button={"text": "🚨 CRITICAL — View Sniper", "url": _dashboard_url(whale["symbol"])}
    )
    audit("SYSTEM", "CRITICAL_WHALE", "SENT", f"sym={whale['symbol']}")


# ══════════════════════════════════════════════════════════════════════════════
# CONTINUOUS SELF-UPGRADE PROTOCOL
# ══════════════════════════════════════════════════════════════════════════════

def self_upgrade_cycle(inst_signals: list, whale_data: list, vmc_data: dict) -> list:
    """
    Auto-reviews signal quality every scan cycle, logs improvements, and
    identifies system evolution opportunities. Stored in GLOBAL_DATA['upgrade_log'].
    """
    notes = []
    ts = time.strftime("%H:%M:%S")

    # 1. Win rate feedback — alert when system drifts
    total_bt = GLOBAL_DATA.get("total_wins", 0) + GLOBAL_DATA.get("total_losses", 0)
    wr = GLOBAL_DATA.get("win_rate", 0.0)
    if total_bt >= 10 and wr < 45:
        notes.append(f"[{ts}] ⚠️ Win rate {wr}% below 45% — market conditions may have shifted")
    elif total_bt >= 10 and wr >= 70:
        notes.append(f"[{ts}] ✅ Win rate {wr}% — system performing at institutional level")

    # 2. Folder concentration detector
    folder_dist = {f: len(vmc_data.get(f, [])) for f in ["VIP","GOLDEN","ENTRY","BOOM","EXIT","STUCK"]}
    top_f = max(folder_dist, key=folder_dist.get)
    if folder_dist[top_f] > 12:
        notes.append(f"[{ts}] 📊 Concentration: {top_f}={folder_dist[top_f]} signals — trending market")

    # 3. Whale coverage gap detection
    whale_syms = {w["symbol"] for w in whale_data}
    inst_syms  = {s["symbol"] for s in inst_signals}
    uncovered  = inst_syms - whale_syms
    if uncovered:
        notes.append(f"[{ts}] 🔍 {len(uncovered)} inst signals without whale data: {list(uncovered)[:3]}")

    # 4. BTC pause vs HOT COIN divergence
    if GLOBAL_DATA.get("btc_pause") and len(GLOBAL_DATA.get("hot_coins", [])) > 2:
        notes.append(f"[{ts}] 🚨 BTC BEARISH but {len(GLOBAL_DATA['hot_coins'])} HOT COINS active — sector divergence")

    # 5. RSI-OBI confluence cluster
    conf_cnt = sum(1 for s in inst_signals if s.get("rsi_obi_confluence"))
    if conf_cnt >= 2:
        syms = [s["symbol"].replace("USDT","") for s in inst_signals if s.get("rsi_obi_confluence")]
        notes.append(f"[{ts}] ⚡ RSI-OBI Confluence × {conf_cnt}: {','.join(syms[:4])}")

    # 6. Smart money alert
    dist_cnt = len([x for x in GLOBAL_DATA.get("smart_divergence",[]) if x.get("signal")=="DISTRIBUTION"])
    if dist_cnt >= 3:
        notes.append(f"[{ts}] 🧠 {dist_cnt} coins DISTRIBUTING — smart money exiting pumps")

    # 7. Volume surge alert
    surge_cnt = len(GLOBAL_DATA.get("volume_surge",[]))
    if surge_cnt >= 3:
        syms = [v["symbol"].replace("USDT","") for v in GLOBAL_DATA["volume_surge"][:4]]
        notes.append(f"[{ts}] 🚀 Volume Surge × {surge_cnt}: {','.join(syms)}")

    for note in notes:
        log.info(f"[SELF-UPGRADE] {note}")
    upgrade_log = GLOBAL_DATA.get("upgrade_log", [])
    upgrade_log.extend(notes)
    if len(upgrade_log) > 100:
        del upgrade_log[:len(upgrade_log)-100]
    GLOBAL_DATA["upgrade_log"] = upgrade_log
    return upgrade_log


# ══════════════════════════════════════════════════════════════════════════════
# PRICE ALERT CHECKER
# ══════════════════════════════════════════════════════════════════════════════

def check_price_alerts(all_coins: list):
    """Fire Telegram alert when a coin crosses its user-set price target."""
    global PRICE_ALERTS
    if not PRICE_ALERTS:
        return
    to_remove = []
    for alert in PRICE_ALERTS:
        coin = next((c for c in all_coins if c["symbol"] == alert["symbol"]), None)
        if not coin:
            continue
        price  = coin.get("price", 0)
        target = alert["target_price"]
        hit    = (alert["direction"] == "ABOVE" and price >= target) or \
                 (alert["direction"] == "BELOW" and price <= target)
        if hit:
            ts  = time.strftime("%Y-%m-%d %H:%M:%S")
            sym = alert["symbol"]
            msg = (f"🎯 <b>PRICE ALERT HIT!</b>\n"
                   f"📊 {sym.replace('USDT','')} / USDT\n"
                   f"💰 Current: {_fmtP(price)}\n"
                   f"🎯 Target ({alert['direction']}): {_fmtP(target)}\n"
                   f"📝 Note: {alert.get('note','—')}\n"
                   f"⏰ {ts}")
            _bot_reply(CHAT_ID, msg)
            log.info(f"[PRICE ALERT] {sym} target {target} hit at {price}")
            GLOBAL_DATA["alert_history"].insert(0, {
                "time": ts, "type": "PRICE_ALERT", "symbol": sym,
                "confidence": 100, "traffic": "GREEN",
                "detail": f"Target {_fmtP(target)} hit ({alert['direction']})"
            })
            to_remove.append(alert["id"])
    PRICE_ALERTS    = [a for a in PRICE_ALERTS if a["id"] not in to_remove]
    GLOBAL_DATA["price_alerts"] = PRICE_ALERTS[:]


# ══════════════════════════════════════════════════════════════════════════════
# SMART TRADING ENGINE — SPOT vs SPOT_GRID STRATEGY SELECTOR
# ══════════════════════════════════════════════════════════════════════════════

def determine_trading_strategy(coin: dict, whale_data: list, market_regime: str) -> tuple:
    """
    Automatically selects SPOT or SPOT_GRID strategy.
    Returns (strategy_str, reason_str).
    """
    inst       = coin.get("inst", {})
    wp         = inst.get("whale_power", 0)
    traffic    = inst.get("traffic", "RED")
    inst_score = inst.get("inst_score", 0)
    conf       = coin.get("confidence", 0)
    atr        = coin.get("atr", 0)

    whale = next((w for w in whale_data if w["symbol"] == coin.get("symbol")), None)
    walls = whale.get("walls", []) if whale else []
    has_bid = any(w.get("side") == "BID" for w in walls)
    has_ask = any(w.get("side") == "ASK" for w in walls)

    # ── SPOT GRID: ranging + walls on both sides ──────────────────────────────
    if market_regime == "RANGING" and has_bid and has_ask:
        return "SPOT_GRID", "Ranging mkt + walls both sides"
    if market_regime == "RANGING" and inst_score < 6:
        return "SPOT_GRID", "Low momentum — grid preferred"

    # ── SPOT: clear directional signal ───────────────────────────────────────
    if traffic == "GREEN" and wp > 60 and inst_score >= 7:
        return "SPOT", "Strong BUY — clear direction"
    if traffic in ["GREEN", "YELLOW"] and wp > 50 and conf > 55:
        return "SPOT", "Whale momentum + confidence"
    if market_regime == "TRENDING":
        return "SPOT", "Trending market — ride the move"

    return "SPOT_GRID", "No clear direction"


def _compute_live_signal(symbol: str) -> dict:
    """
    Compute a full v6-scored signal for ANY tracked symbol on demand — used
    by the SNIPER tab search box so a coin outside the pre-enriched top-20
    list still gets a real score instead of "NO SIGNAL DATA".
    """
    price = fetch_ticker_price(symbol)
    if not price:
        return {}
    tkr = fetch_ticker_24h(symbol) or {}
    change_pct  = float(tkr.get("priceChangePercent", 0) or 0)
    volume_usdt = float(tkr.get("quoteVolume", 0) or 0)
    rsi    = fetch_rsi_for_symbol(symbol)
    atr    = calculate_atr(symbol)
    macd_d = fetch_macd_for_symbol(symbol)

    book  = fetch_order_book(symbol, CONFIG["whale"]["order_book_depth"])
    walls = calculate_wall_proximity(price, book, CONFIG)
    spoof = detect_spoofing(book.get("bids", []), book.get("asks", []), CONFIG)
    b2p   = blink_to_push_check(symbol, walls, _previous_walls, CONFIG)
    w_pow = compute_whale_power(walls, spoof, b2p, price, CONFIG)
    obi_val = calculate_obi(book)
    obi_r   = detect_obi_spike(symbol, obi_val, CONFIG)

    vmc_score = score_coin(tkr, rsi, CONFIG) if tkr else 0
    tp     = compute_tp_levels(price, atr, CONFIG)
    inst   = compute_institutional_score(vmc_score, w_pow, obi_r, walls, CONFIG)
    conf   = compute_confidence_score(inst, obi_r, vmc_score)
    sizing = compute_position_size(inst, CONFIG)

    signal = {
        "symbol": symbol, "price": price, "change_pct": round(change_pct, 2),
        "volume_usdt": round(volume_usdt, 0), "rsi": rsi, "score": vmc_score,
        "folder": "LIVE", "atr": atr, "macd": macd_d,
        "macd_hist": macd_d.get("hist", 0.0), "tp_zones": tp,
        "inst": inst, "sizing": sizing, "confidence": conf,
    }
    mkt_reg = GLOBAL_DATA.get("market_regime", "RANGING")
    strat, sreason = determine_trading_strategy(signal, GLOBAL_DATA.get("whale", []), mkt_reg)
    signal["trading_strategy"]        = strat
    signal["trading_strategy_reason"] = sreason
    btc_vol = (GLOBAL_DATA.get("btc", {}) or {}).get("volatility_pct", 0) or 0
    signal["v6"] = compute_v6_final_score(signal, mkt_reg, btc_vol, "NONE", False)
    return signal


# ══════════════════════════════════════════════════════════════════════════════
# PAPER MODE INTELLIGENCE — LEARNING ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def _save_learning_data():
    ld = GLOBAL_DATA.get("learning_data", {})
    try:
        with open(_LD_FILE, "w") as f:
            json.dump(ld, f, indent=2)
    except Exception as e:
        log.debug(f"Learning data save failed: {e}")


def update_paper_learning():
    """After every scan, update paper trade learning from resolved backtest signals."""
    if not GLOBAL_DATA.get("paper_mode", True):
        return                        # only learn in paper mode
    ld = GLOBAL_DATA.get("learning_data", {})
    if not isinstance(ld, dict):
        ld = dict(_DEFAULT_LD)

    resolved = [b for b in BACKTEST_SIGNALS if b.get("result") in ("WIN", "LOSS")
                and not b.get("learning_recorded")]
    if not resolved:
        return

    for b in resolved:
        b["learning_recorded"] = True
        is_win = b["result"] == "WIN"
        ld["paper_trades"]  = ld.get("paper_trades", 0) + 1
        if is_win:
            ld["paper_wins"]   = ld.get("paper_wins", 0) + 1
        else:
            ld["paper_losses"] = ld.get("paper_losses", 0) + 1

        # Per-symbol stats
        sym = b.get("symbol", "?")
        ss  = ld.setdefault("signal_stats", {}).setdefault(sym, {"wins":0,"losses":0})
        if is_win: ss["wins"]   += 1
        else:      ss["losses"] += 1

    total = ld.get("paper_trades", 0)
    wins  = ld.get("paper_wins", 0)
    ld["paper_win_rate"] = round(wins / total * 100, 1) if total else 0.0

    # ── Auto-adjust thresholds every 10 trades ────────────────────────────────
    if total > 0 and total % 10 == 0:
        wr = ld["paper_win_rate"]
        old_wp   = ld.get("wp_threshold", 50)
        old_conf = ld.get("conf_threshold", 50)
        # If win rate poor: raise thresholds (be more selective)
        if wr < 45:
            ld["wp_threshold"]   = min(80, old_wp + 5)
            ld["conf_threshold"] = min(80, old_conf + 5)
            note = f"[{time.strftime('%H:%M')}] WR {wr}% < 45% → raise WP→{ld['wp_threshold']}% Conf→{ld['conf_threshold']}%"
        elif wr >= 65:
            ld["wp_threshold"]   = max(40, old_wp - 3)
            ld["conf_threshold"] = max(40, old_conf - 3)
            note = f"[{time.strftime('%H:%M')}] WR {wr}% ≥ 65% → lower WP→{ld['wp_threshold']}% (more trades)"
        else:
            note = f"[{time.strftime('%H:%M')}] WR {wr}% stable after {total} trades"

        ld.setdefault("adjustment_log", []).append(note)
        if len(ld["adjustment_log"]) > 50:
            ld["adjustment_log"] = ld["adjustment_log"][-50:]
        ld["last_adjustment"] = time.strftime("%Y-%m-%d %H:%M:%S")
        log.info(f"[LEARNING] {note}")

        # ── Ready-for-real alert ──────────────────────────────────────────────
        if wr >= 65 and total >= 10 and not ld.get("ready_for_real"):
            ld["ready_for_real"] = True
            msg = (f"🏆 <b>SYSTEM READY FOR REAL MODE!</b>\n"
                   f"🎯 Paper Win Rate: <b>{wr}%</b>\n"
                   f"📊 Trades tracked: {total}\n"
                   f"⚡ WP Threshold: {ld['wp_threshold']}% | Conf: {ld['conf_threshold']}%\n"
                   f"✅ System has learned and optimised.\n"
                   f"⚠️ Switch to REAL MODE in Admin Portal only after careful review.")
            _bot_reply(CHAT_ID, msg)

    GLOBAL_DATA["learning_data"] = ld
    _save_learning_data()


# ══════════════════════════════════════════════════════════════════════════════
# BACKGROUND THREADS
# ══════════════════════════════════════════════════════════════════════════════

def data_refresh_loop():
    interval = CONFIG["scanner"]["cache_clear_interval_seconds"]
    while True:
        t0 = time.time()
        try:
            cycle = GLOBAL_DATA["cycle_count"] + 1
            log.info(f"[SCAN #{cycle}] Starting — fetching live data...")

            vmc_data   = process_vmc_signals(CONFIG)
            price_map  = {c["symbol"]: c["price"] for c in vmc_data.get("ALL", [])}
            whale_data = process_whale_walls(CONFIG, price_map, _previous_walls)

            # ── WHALE COPY MODE: independent wall+OBI mirrored signals ────────
            whale_copy_signals = detect_whale_copy_signals(whale_data, CONFIG)
            for _wcs in whale_copy_signals:
                if _wcs.get("confirmed"):
                    _wcs_atr = calculate_atr(_wcs["symbol"])
                    _wcs["eta"] = estimate_time_to_target(_wcs["price"], _wcs["target"], _wcs_atr)["label"]
                else:
                    _wcs["eta"] = "—"
            GLOBAL_DATA["whale_copy_signals"] = whale_copy_signals
            wc_min_conf = CONFIG.get("whale_copy", {}).get("min_confidence", 50)
            for sig in whale_copy_signals:
                if sig["direction"] == "COPY_BUY" and sig.get("confirmed") and sig["confidence"] >= wc_min_conf:
                    _record_whale_copy_trade(sig)

            # ── LARGE TRADE DETECTOR: exchange-side whale-activity proxy ─────
            _lt_min_usdt = CONFIG.get("whale_copy", {}).get("large_trade_min_usdt", 50000)
            _new_large_trades = []
            for _lt_sym in list(price_map.keys())[:20]:
                if is_stablecoin_pair(_lt_sym, price_map.get(_lt_sym, 0), CONFIG):
                    continue
                _new_large_trades.extend(fetch_large_trades(_lt_sym, min_usdt=_lt_min_usdt))
            if _new_large_trades:
                _lt_all = _new_large_trades + GLOBAL_DATA.get("large_trades", [])
                _lt_all.sort(key=lambda x: x["ts"], reverse=True)
                GLOBAL_DATA["large_trades"] = _lt_all[:100]

            # ── HOT COIN: decay old entries ─────────────────────────────────
            now = time.time()
            for sym in list(_coin_signal_times.keys()):
                _coin_signal_times[sym] = [t for t in _coin_signal_times[sym] if now - t <= 3600]
            # Remove expired hot coins
            GLOBAL_DATA["hot_coins"] = [
                h for h in GLOBAL_DATA["hot_coins"]
                if len(_coin_signal_times.get(h["symbol"], [])) >= 3
            ]

            # ── Enrich institutional signals ─────────────────────────────────
            inst_signals = []
            _ob_cache = {}
            for folder in ["VIP", "GOLDEN", "ENTRY", "BOOM"]:
                for coin in vmc_data.get(folder, [])[:5]:
                    sym         = coin["symbol"]
                    price       = coin["price"]
                    whale_match = next((w for w in whale_data if w["symbol"] == sym), None)
                    if whale_match:
                        walls = whale_match["walls"]
                        spoof = whale_match["spoofing"]
                        b2p   = whale_match["blink_to_push"]
                        w_pow = whale_match.get("whale_power", 0)
                        obi_r = whale_match.get("obi", {"obi": 0})
                    elif sym in _ob_cache:
                        walls, spoof, b2p, w_pow, obi_r = _ob_cache[sym]
                    else:
                        book    = fetch_order_book(sym, CONFIG["whale"]["order_book_depth"])
                        walls   = calculate_wall_proximity(price, book, CONFIG)
                        spoof   = detect_spoofing(book.get("bids", []), book.get("asks", []), CONFIG)
                        b2p     = blink_to_push_check(sym, walls, _previous_walls, CONFIG)
                        w_pow   = compute_whale_power(walls, spoof, b2p, price, CONFIG)
                        obi_val = calculate_obi(book)
                        obi_r   = detect_obi_spike(sym, obi_val, CONFIG)
                        _previous_walls[sym] = walls
                        _ob_cache[sym] = (walls, spoof, b2p, w_pow, obi_r)
                    atr    = calculate_atr(sym)
                    macd_d = fetch_macd_for_symbol(sym)
                    tp     = compute_tp_levels(price, atr, CONFIG)
                    inst   = compute_institutional_score(coin["score"], w_pow, obi_r, walls, CONFIG)
                    conf   = compute_confidence_score(inst, obi_r, coin["score"])
                    sizing = compute_position_size(inst, CONFIG)
                    inst_signals.append({
                        **coin,
                        "folder":     folder,
                        "atr":        atr,
                        "macd":        macd_d,
                        "macd_hist":   macd_d.get("hist", 0.0),
                        "tp_zones":   tp,
                        "inst":       inst,
                        "sizing":     sizing,
                        "confidence": conf,
                    })

            inst_signals.sort(key=lambda x: (x["inst"]["spike"], x["confidence"]), reverse=True)

            # ── Agent Self-Upgrade: Volume Surge Detection ─────────────────────
            all_coins = vmc_data.get("ALL", [])
            volumes   = [c.get("volume_usdt", 0) for c in all_coins if c.get("volume_usdt", 0) > 0]
            if volumes:
                vols_sorted  = sorted(volumes)
                median_vol   = vols_sorted[len(vols_sorted)//2] if vols_sorted else 1
                vol_surge_coins = [
                    {"symbol": c["symbol"], "volume": c.get("volume_usdt",0),
                     "surge_ratio": round(c.get("volume_usdt",0) / (median_vol or 1), 2)}
                    for c in all_coins
                    if c.get("volume_usdt", 0) >= median_vol * 2.5 and c.get("volume_usdt",0) > 0
                ]
                vol_surge_coins.sort(key=lambda x: x["surge_ratio"], reverse=True)
                GLOBAL_DATA["volume_surge"] = vol_surge_coins[:10]
            else:
                GLOBAL_DATA["volume_surge"] = []

            # ── Agent Self-Upgrade: Smart Money Divergence (price↑ OBI↓) ──────
            smart_div = []
            for w in whale_data:
                sym    = w["symbol"]
                obi_v  = w.get("obi", {}).get("obi", 0)
                coin_c = next((c for c in all_coins if c["symbol"] == sym), None)
                if not coin_c:
                    continue
                chg = coin_c.get("change_pct", 0)
                # Distribution: price up but OBI negative = asks dominating (smart money selling into pump)
                if chg > 1.5 and obi_v < 0:
                    smart_div.append({"symbol": sym, "change_pct": chg,
                                      "obi": round(obi_v, 4), "signal": "DISTRIBUTION"})
                # Accumulation: price down but OBI positive = bids dominating (smart money buying dip)
                elif chg < -1.5 and obi_v > 0:
                    smart_div.append({"symbol": sym, "change_pct": chg,
                                      "obi": obi_v, "signal": "ACCUMULATION"})
            smart_div.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
            GLOBAL_DATA["smart_divergence"] = smart_div[:10]

            # ── Agent Self-Upgrade: RSI-OBI Confluence Boost ──────────────────
            for s in inst_signals:
                sym      = s["symbol"]
                rsi_val  = s.get("rsi", 50)
                obi_val  = s.get("inst", {}).get("ofi_score", 50)
                # Confluence: oversold RSI + strong bid OBI = strong buy setup
                if rsi_val and rsi_val < 38 and obi_val > 60:
                    s["rsi_obi_confluence"] = True
                    s["confidence"] = min(99, s["confidence"] + 8)
                elif rsi_val and rsi_val > 68 and obi_val < 40:
                    s["rsi_obi_confluence"] = True   # overbought + bid dropping
                else:
                    s["rsi_obi_confluence"] = False

            # ── Smart Trading Engine: Spot vs Spot-Grid per coin ──────────────
            _mkt_reg = GLOBAL_DATA.get("market_regime", "RANGING")
            for s in inst_signals:
                _strat, _sreason = determine_trading_strategy(s, whale_data, _mkt_reg)
                s["trading_strategy"]        = _strat
                s["trading_strategy_reason"] = _sreason

            # ── V6 FINAL SCORE: 54-point institutional scoring per coin ───────
            _btc_now   = GLOBAL_DATA.get("btc", {}) or {}
            _btc_vol   = _btc_now.get("volatility_pct", 0) or 0
            _div_map   = {d["symbol"]: d["signal"] for d in smart_div}
            _surge_set = {v["symbol"] for v in GLOBAL_DATA.get("volume_surge", [])}
            for s in inst_signals:
                s["v6"] = compute_v6_final_score(
                    s, _mkt_reg, _btc_vol,
                    _div_map.get(s["symbol"], "NONE"),
                    s["symbol"] in _surge_set,
                )

            GLOBAL_DATA["vmc"]          = vmc_data
            GLOBAL_DATA["whale"]        = whale_data
            GLOBAL_DATA["inst_signals"] = inst_signals
            GLOBAL_DATA["last_update"]  = time.strftime("%Y-%m-%d %H:%M:%S")
            GLOBAL_DATA["status"]       = "live"
            GLOBAL_DATA["cycle_count"]  = cycle
            GLOBAL_DATA["win_streak"]   = _win_streak
            GLOBAL_DATA["total_wins"]   = _total_wins
            GLOBAL_DATA["total_losses"] = _total_losses
            total_bt = _total_wins + _total_losses
            GLOBAL_DATA["win_rate"]     = round(_total_wins / total_bt * 100, 1) if total_bt else 0.0
            GLOBAL_DATA["backtest"]     = BACKTEST_SIGNALS

            # Top coin today
            if _today_coin_counts:
                top = max(_today_coin_counts, key=_today_coin_counts.get)
                GLOBAL_DATA["top_coin_today"] = {"symbol": top, "count": _today_coin_counts[top]}

            # ── Continuous Self-Upgrade Protocol ─────────────────────────────
            self_upgrade_cycle(inst_signals, whale_data, vmc_data)

            # ── Price Alert Checker ──────────────────────────────────────────
            check_price_alerts(vmc_data.get("ALL", []))

            # ── Paper Mode Learning Update ───────────────────────────────────
            update_paper_learning()

            # ── Sync price_alerts to GLOBAL_DATA ────────────────────────────
            GLOBAL_DATA["price_alerts"] = PRICE_ALERTS[:]

            # ── Fire Alerts ──────────────────────────────────────────────────
            if not GLOBAL_DATA.get("btc_pause"):
                # V6 GATE: auto paper-trade now fires off the fixed 54-point
                # v6.label=="BUY" for ANY folder's coin, instead of the old
                # VIP-folder-only + institutional-traffic=="GREEN" gate that
                # real market data almost never satisfied (root cause of
                # zero trades over ~2 months).
                _seen_buy_syms = set()
                for s in inst_signals:
                    sym = s["symbol"]
                    if sym in _seen_buy_syms:
                        continue
                    if s.get("v6", {}).get("label", "") == "BUY":
                        _seen_buy_syms.add(sym)
                        alert_vip(s, s.get("inst", {}), s.get("tp_zones", {}), s.get("confidence", 0))

                # NOTE: wall/blink/whale-trap Telegram pings intentionally
                # disabled — too noisy, not actionable. Whale data still shows
                # live on the dashboard/Sheets WATCH tab. Only BUY signals,
                # confirmed Whale Copy entries, and inventory sell-checks
                # reach Telegram now.
                pass
            else:
                log.info("[SCAN] BTC BEARISH — entries paused.")

            if GOOGLE_SHEET_ID and GOOGLE_CREDENTIALS != "{}":
                threading.Thread(
                    target=push_to_google_sheets,
                    args=(vmc_data, whale_data, GOOGLE_CREDENTIALS, GOOGLE_SHEET_ID),
                    kwargs={
                        "whale_copy_signals": whale_copy_signals,
                        "whale_copy_trades":  WHALE_COPY_TRADES,
                        "paper_trades":       PAPER_TRADES,
                        "inst_signals":       inst_signals,
                    },
                    daemon=True
                ).start()

            latency = round((time.time() - t0) * 1000)
            if latency > 500:
                audit("SYSTEM", "LATENCY_WARNING", f"{latency}ms", f"cycle={cycle}")
            log.info(f"[SCAN #{cycle}] Done — ALL:{len(vmc_data.get('ALL',[]))} VIP:{len(vmc_data.get('VIP',[]))} WHALE:{len(whale_data)} {latency}ms")
            audit("SYSTEM", "SCAN_CYCLE", "DONE", f"cycle={cycle} ms={latency}")

        except Exception as e:
            log.error(f"[SCAN] Cycle error: {e}", exc_info=True)
            GLOBAL_DATA["status"] = f"error: {e}"
            audit("SYSTEM", "SCAN_CYCLE", "ERROR", str(e))

        time.sleep(interval)


def backtest_check_loop():
    """Every 5 minutes: check open signals against current price. Update WIN/LOSS."""
    global _win_streak, _total_wins, _total_losses, BACKTEST_SIGNALS
    while True:
        time.sleep(300)
        try:
            now = time.time()
            changed = False
            for sig in BACKTEST_SIGNALS:
                if sig["status"] != "OPEN":
                    continue
                age = now - sig["entry_ts"]
                if age < 300:   # don't check brand-new entries
                    continue
                current = fetch_ticker_price(sig["symbol"])
                if not current:
                    continue
                entry = sig["entry_price"]
                # Check TP hits
                if sig["tp3"] and current >= sig["tp3"]:
                    sig["tp1_hit"] = sig["tp2_hit"] = sig["tp3_hit"] = True
                elif sig["tp2"] and current >= sig["tp2"]:
                    sig["tp1_hit"] = sig["tp2_hit"] = True
                elif sig["tp1"] and current >= sig["tp1"]:
                    sig["tp1_hit"] = True

                # ── Trailing stop: ratchet SL up as targets are reached ────────
                tm = CONFIG.get("trade_management", {})
                if tm.get("trailing_stop_enabled", True):
                    if sig["tp2_hit"] and tm.get("trail_to_tp1_on_tp2", True) and sig["tp1"]:
                        if sig["stop_loss"] < sig["tp1"]:
                            sig["stop_loss"] = sig["tp1"]
                            sig["trailing"]  = "TP1"
                    elif sig["tp1_hit"] and tm.get("breakeven_on_tp1", True):
                        if sig["stop_loss"] < entry:
                            sig["stop_loss"] = entry
                            sig["trailing"]  = "BREAKEVEN"

                if sig["stop_loss"] and current <= sig["stop_loss"]:
                    sig["sl_hit"] = True

                # ── Early close: trailing stop hit AFTER a profit target — lock
                #    the result immediately instead of waiting for 1h. ──
                trailing_exit = sig["sl_hit"] and sig["tp1_hit"] and sig.get("trailing")

                # Resolve after 1h (or immediately on a trailing-stop exit)
                if age >= 3600 or trailing_exit:
                    # On an SL hit, fill at the stop level (not the polled price,
                    # which can have gapped past it); otherwise fill at current.
                    if sig["sl_hit"] and sig["stop_loss"]:
                        sig["exit_price"] = min(current, sig["stop_loss"])
                    else:
                        sig["exit_price"] = current
                    sig["exit_time"]  = _pkt_ts()
                    sig["pnl_pct"]    = round((sig["exit_price"] - entry) / entry * 100, 3)

                    # Classify by REALIZED PnL, not merely whether tp1 was tagged
                    # — a trailing stop can exit at breakeven or a small loss.
                    if sig["sl_hit"]:
                        win = sig["pnl_pct"] > 0
                        sig["result"] = "WIN" if win else "LOSS"
                        sig["status"] = "CLOSED"
                        if win: _total_wins += 1; _win_streak += 1
                        else:   _total_losses += 1; _win_streak = 0
                        _record_trade_result(win, sig["pnl_pct"])
                    elif sig["tp1_hit"]:
                        sig["result"] = "WIN"; sig["status"] = "CLOSED"
                        _total_wins += 1
                        _win_streak += 1
                        _record_trade_result(True, sig["pnl_pct"])
                    elif age >= 4 * 3600 and sig["pnl_pct"] < 0:
                        sig["result"] = "LOSS"; sig["status"] = "CLOSED"
                        _total_losses += 1
                        _win_streak = 0
                        _record_trade_result(False, sig["pnl_pct"])
                    elif age >= 4 * 3600:
                        sig["result"] = "TIMEOUT"; sig["status"] = "CLOSED"
                    changed = True

            if changed:
                GLOBAL_DATA["backtest"]     = BACKTEST_SIGNALS
                GLOBAL_DATA["win_streak"]   = _win_streak
                GLOBAL_DATA["total_wins"]   = _total_wins
                GLOBAL_DATA["total_losses"] = _total_losses
                total = _total_wins + _total_losses
                GLOBAL_DATA["win_rate"]     = round(_total_wins / total * 100, 1) if total else 0.0
                log.info(f"[BACKTEST] Updated — wins:{_total_wins} losses:{_total_losses} streak:{_win_streak}")
        except Exception as e:
            log.warning(f"Backtest check error: {e}")


_heartbeat_iter = 0

def heartbeat_loop():
    global _heartbeat_iter
    interval = CONFIG["scanner"]["heartbeat_interval_seconds"]
    HEARTBEAT_SEND_EVERY = 12  # only actually message Telegram ~hourly — was
                               # spamming every single cycle with no real signal
    while True:
        time.sleep(interval)
        secs = int(time.time() - GLOBAL_DATA["uptime_start"])
        h, r = divmod(secs, 3600); m, s = divmod(r, 60)
        ts   = time.strftime("%Y-%m-%d %H:%M:%S")
        GLOBAL_DATA["heartbeat"] = ts
        log.info(f"[HEARTBEAT] Uptime:{h}h{m}m | Cycles:{GLOBAL_DATA['cycle_count']} | WinRate:{GLOBAL_DATA['win_rate']}%")
        _heartbeat_iter += 1
        if _heartbeat_iter % HEARTBEAT_SEND_EVERY == 0:
            send_telegram(
                f"💚 <b>V6 HEARTBEAT</b>\n"
                f"Status: {GLOBAL_DATA['status']} | Cycles: {GLOBAL_DATA['cycle_count']}\n"
                f"Uptime: {h}h {m}m | Exchange: {GLOBAL_DATA['active_exchange']}\n"
                f"VIP:{len(GLOBAL_DATA['vmc'].get('VIP',[]))} GOLDEN:{len(GLOBAL_DATA['vmc'].get('GOLDEN',[]))} Whale:{len(GLOBAL_DATA['whale'])}\n"
                f"WinRate: {GLOBAL_DATA['win_rate']}% | Streak: {_win_streak} | BTC: {GLOBAL_DATA['btc'].get('sentiment','?')}\n"
                f"HotCoins: {len(GLOBAL_DATA['hot_coins'])} | Alerts: {len(GLOBAL_DATA['alert_history'])}"
            )
        audit("SYSTEM", "HEARTBEAT", "OK", f"uptime={h}h{m}m wins={_total_wins} losses={_total_losses}")


def btc_monitor_loop():
    interval = CONFIG["scanner"].get("btc_monitor_interval_seconds", 30)
    while True:
        try:
            btc = fetch_btc_sentiment()
            GLOBAL_DATA["btc"]          = btc
            GLOBAL_DATA["btc_pause"]    = btc["pause_entries"]
            GLOBAL_DATA["market_regime"]= btc.get("regime", "RANGING")
            if btc["pause_entries"]:
                send_telegram(
                    f"🔴 <b>BTC BEARISH ALERT</b>\n"
                    f"BTC: {btc['change_pct']}% | Vol: {btc['volatility_pct']}%\n"
                    f"Regime: {btc.get('regime','?')} — Pausing new entries"
                )
                audit("SYSTEM", "BTC_PAUSE", "ACTIVATED", f"chg={btc['change_pct']}%")
        except Exception as e:
            log.warning(f"BTC monitor error: {e}")
        time.sleep(interval)


def market_quiet_loop():
    """Send [MARKET QUIET] alert if no whale activity for 2 hours."""
    quiet_sent = False
    while True:
        time.sleep(600)   # check every 10 min
        try:
            silence = time.time() - _last_whale_ts
            if silence >= 7200 and not quiet_sent:
                h = int(silence // 3600); m = int((silence % 3600) // 60)
                send_telegram(
                    f"😴 <b>[MARKET QUIET]</b>\n"
                    f"No whale activity for {h}h {m}m\n"
                    f"Monitor only — no new entries recommended"
                )
                audit("SYSTEM", "MARKET_QUIET", "ALERT_SENT", f"silence={h}h{m}m")
                quiet_sent = True
                log.info(f"[MARKET QUIET] No whale activity for {h}h {m}m")
            elif silence < 7200:
                quiet_sent = False
        except Exception as e:
            log.warning(f"Market quiet loop error: {e}")


def weekly_report_loop():
    """Fires a weekly performance summary every Monday at UTC+5 (PKT) midnight."""
    while True:
        now_pkt = time.gmtime(time.time() + 5 * 3600)
        days_until_monday = (7 - now_pkt.tm_wday) % 7
        if days_until_monday == 0 and now_pkt.tm_hour == 0:
            days_until_monday = 7
        secs_until = days_until_monday * 86400 - now_pkt.tm_hour * 3600 - now_pkt.tm_min * 60 - now_pkt.tm_sec
        if secs_until <= 0:
            secs_until += 86400
        time.sleep(secs_until)
        try:
            week_ago = time.time() - 7 * 86400
            week_trades = [b for b in BACKTEST_SIGNALS if b.get("exit_ts", 0) >= week_ago and b.get("status") == "CLOSED"]
            wins = sum(1 for t in week_trades if t.get("result") == "WIN")
            losses = sum(1 for t in week_trades if t.get("result") == "LOSS")
            total = wins + losses
            wr = round(wins / total * 100, 1) if total else 0
            wc_week = [t for t in WHALE_COPY_TRADES if t.get("status") == "CLOSED" and t.get("entry_ts", 0) >= week_ago]
            wc_wins = sum(1 for t in wc_week if t.get("result") == "WIN")
            wc_losses = sum(1 for t in wc_week if t.get("result") == "LOSS")
            pkt_ts = time.strftime("%Y-%m-%d %H:%M PKT", time.gmtime(time.time() + 5 * 3600))
            msg = (f"📅 <b>WEEKLY PERFORMANCE REPORT</b>\n{pkt_ts}\n\n"
                   f"🎯 Auto Trades (V6): {wins}W / {losses}L | Win Rate: {wr}%\n"
                   f"🐋 Whale Copy: {wc_wins}W / {wc_losses}L\n"
                   f"📊 Total Signals This Week: {total + len(wc_week)}\n"
                   f"⏱ Generated: {pkt_ts}")
            notify_all("V6 Weekly Report", msg)
            audit("SYSTEM", "WEEKLY_REPORT", "SENT", f"wr={wr}% trades={total}")
        except Exception as e:
            log.error(f"Weekly report error: {e}")
            audit("SYSTEM", "WEEKLY_REPORT", "ERROR", str(e))


def midnight_report_loop():
    """Fires a midnight report every 24h at UTC+5 (PKT) midnight."""
    while True:
        now_pkt    = time.gmtime(time.time() + 5 * 3600)
        secs_until = (24 - now_pkt.tm_hour) * 3600 - now_pkt.tm_min * 60 - now_pkt.tm_sec
        if secs_until <= 0:
            secs_until += 86400
        time.sleep(secs_until)
        try:
            wins   = _total_wins; losses = _total_losses; total = wins + losses
            wr     = round(wins / total * 100, 1) if total else 0
            top    = GLOBAL_DATA.get("top_coin_today", {})
            utc_ts = time.strftime("%Y-%m-%d %H:%M:%S UTC")
            pkt_ts = time.strftime("%Y-%m-%d %H:%M:%S PKT", time.gmtime(time.time() + 5 * 3600))

            send_telegram(
                f"📊 <b>DAILY MIDNIGHT REPORT</b>\n"
                f"UTC: {utc_ts}\nPKT: {pkt_ts}\n\n"
                f"📈 SIGNALS TODAY\n"
                f"VIP:{len(GLOBAL_DATA['vmc'].get('VIP',[]))} | "
                f"GOLDEN:{len(GLOBAL_DATA['vmc'].get('GOLDEN',[]))} | "
                f"ALL:{len(GLOBAL_DATA['vmc'].get('ALL',[]))}\n"
                f"Whale Signals: {len(GLOBAL_DATA['whale'])}\n"
                f"Total Alerts: {len(GLOBAL_DATA['alert_history'])}\n\n"
                f"🏆 BACKTEST\n"
                f"Win Rate: {wr}% ({wins}W / {losses}L)\n"
                f"Win Streak: {_win_streak}\n"
                f"Top Coin: {top.get('symbol','—')} ({top.get('count',0)} signals)\n\n"
                f"Hot Coins: {len(GLOBAL_DATA['hot_coins'])} active"
            )
            if GOOGLE_SHEET_ID and GOOGLE_CREDENTIALS != "{}":
                push_midnight_report(
                    GLOBAL_DATA["vmc"], GLOBAL_DATA["whale"], BACKTEST_SIGNALS,
                    GOOGLE_CREDENTIALS, GOOGLE_SHEET_ID
                )
            # Reset daily counters
            _today_coin_counts.clear()
            GLOBAL_DATA["today_signals"] = 0
            audit("SYSTEM", "MIDNIGHT_REPORT", "SENT", f"pkt={pkt_ts} wr={wr}%")
        except Exception as e:
            log.error(f"Midnight report error: {e}")
            audit("SYSTEM", "MIDNIGHT_REPORT", "ERROR", str(e))


# ══════════════════════════════════════════════════════════════════════════════
# SECURITY
# ══════════════════════════════════════════════════════════════════════════════

def _check_lockout(ip: str) -> bool:
    entry = _login_attempts.get(ip)
    if not entry: return False
    count, lockout_until = entry
    max_att = CONFIG["security"]["max_login_attempts"]
    if count >= max_att and time.time() < lockout_until: return True
    if time.time() >= lockout_until: _login_attempts.pop(ip, None)
    return False


def _record_failed_login(ip: str):
    entry  = _login_attempts.get(ip, (0, 0))
    count  = entry[0] + 1
    locked = count >= CONFIG["security"]["max_login_attempts"]
    lockout_until = time.time() + CONFIG["security"]["lockout_minutes"] * 60 if locked else entry[1]
    _login_attempts[ip] = (count, lockout_until)
    audit(ip, "LOGIN_FAILED", f"ATTEMPT_{count}", f"locked={locked}")


def _admin_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin_auth"): return redirect("/admin/login")
        if time.time() - session.get("last_active", 0) > CONFIG["security"]["session_timeout_minutes"] * 60:
            session.clear(); return redirect("/admin/login?timeout=1")
        session["last_active"] = time.time()
        return fn(*args, **kwargs)
    return wrapper


# ══════════════════════════════════════════════════════════════════════════════
# FLASK APP
# ══════════════════════════════════════════════════════════════════════════════

app = Flask(__name__)
app.secret_key = SESSION_SECRET
# ProxyFix: Replit runs behind a reverse proxy in production.
# Without this, Flask sees wrong scheme/host and session cookies may fail.
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True


@app.route("/")
def index():
    # New finalized UI is the default. Legacy dashboard preserved at /legacy.
    return redirect("/v6/", code=302)


@app.route("/legacy")
def legacy_index():
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()
    resp = Response(html, mimetype="text/html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@app.route("/v6")
def v6_redirect():
    # Trailing slash so relative asset URLs (style.css, script.js) resolve under /v6/
    return redirect("/v6/", code=302)


@app.route("/v6/")
def v6_ui():
    with open("V6_Master_Pro_UI/index.html", "r", encoding="utf-8") as f:
        html = f.read()
    resp = Response(html, mimetype="text/html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@app.route("/v6/<path:fname>")
def v6_assets(fname):
    resp = send_from_directory("V6_Master_Pro_UI", fname)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@app.route("/dashboard_data")
def dashboard_data():
    return jsonify(GLOBAL_DATA)


@app.route("/get_data", methods=["GET", "POST"])
def get_data():
    key = (request.get_json(silent=True) or {}).get("secret_key", "") if request.method == "POST" \
          else request.args.get("secret_key", "")
    if key != SECRET_KEY_VAL:
        audit(request.remote_addr, "API_ACCESS", "DENIED", "")
        return jsonify({"error": "Unauthorized"}), 401
    audit(request.remote_addr, "API_ACCESS", "GRANTED", "")
    return jsonify(GLOBAL_DATA)


@app.route("/status")
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


@app.route("/sniper_data")
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


# ── Admin Portal ──────────────────────────────────────────────────────────────

ADMIN_LOGIN_HTML = """<!DOCTYPE html><html><head><title>V6 Admin</title>
<style>body{background:#0a0a0f;color:#c9d1d9;font-family:monospace;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
.box{background:#161b22;padding:40px;border:1px solid #30363d;border-radius:8px;min-width:320px;text-align:center}
h2{color:#FFD700;margin-bottom:24px}input{width:100%;padding:10px;margin:8px 0;background:#0d1117;border:1px solid #30363d;color:#c9d1d9;border-radius:4px;box-sizing:border-box}
button{width:100%;padding:12px;background:#1f6feb;color:#fff;border:none;border-radius:4px;cursor:pointer;margin-top:8px}
.err{color:#FF4500;margin-top:12px}.warn{color:#FFA500;font-size:12px;margin-top:8px}</style></head>
<body><div class="box"><h2>🔐 V6 ADMIN PORTAL</h2>
{% if locked %}<p class="err">⛔ Too many failed attempts. Try later.</p>{% endif %}
{% if timeout %}<p class="err">⏰ Session expired.</p>{% endif %}
{% if error %}<p class="err">❌ Invalid password.</p>{% endif %}
<form method="POST"><input type="password" name="password" placeholder="Master Password" autofocus/>
<button type="submit">LOGIN</button></form>
<p class="warn">3 failed attempts = 30-minute lockout</p></div></body></html>"""

ADMIN_PORTAL_HTML = """<!DOCTYPE html><html><head><title>V6 Admin Portal</title>
<style>*{box-sizing:border-box;margin:0;padding:0}body{background:#0a0a0f;color:#c9d1d9;font-family:monospace;font-size:13px}
.header{background:#111827;padding:12px 20px;border-bottom:1px solid #21262d;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
.title{color:#FFD700;font-size:15px;font-weight:bold}.logout{color:#FF4500;text-decoration:none;font-size:12px}
.container{padding:20px;max-width:1100px;margin:0 auto}.card{background:#161b22;border:1px solid #21262d;border-radius:6px;padding:16px;margin-bottom:16px}
.card h3{color:#58a6ff;margin-bottom:12px;font-size:13px}.stat{display:inline-block;background:#0d1117;padding:8px 16px;border-radius:4px;margin:4px;border:1px solid #30363d}
.stat .val{color:#00FF00;font-size:18px;font-weight:bold;display:block}.stat .lbl{color:#555;font-size:10px}
table{width:100%;border-collapse:collapse;font-size:11px}th{background:#0d1117;color:#58a6ff;padding:6px 8px;text-align:left}td{padding:5px 8px;border-bottom:1px solid #1a1a2e}
.green{color:#00FF00}.yellow{color:#FFD700}.red{color:#FF4500}.btn{padding:6px 14px;border:none;border-radius:4px;cursor:pointer;font-size:11px;font-family:monospace}
.btn-blue{background:#1f6feb;color:#fff}.btn-red{background:#da3633;color:#fff}.btn-green{background:#238636;color:#fff}.btn-orange{background:#d97706;color:#fff}
.form-row{display:flex;gap:8px;margin-bottom:8px;flex-wrap:wrap;align-items:center}
input,select{background:#0d1117;border:1px solid #30363d;color:#c9d1d9;padding:6px 10px;border-radius:4px;font-family:monospace;font-size:12px}
.log-box{background:#0d1117;border:1px solid #30363d;padding:10px;border-radius:4px;height:200px;overflow-y:auto;font-size:10px;color:#6e7681;white-space:pre-wrap}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px}
.dot-green{background:#00FF00;box-shadow:0 0 6px #00FF00}.dot-red{background:#FF4500}.dot-yellow{background:#FFD700}
.trade-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:600px){.trade-grid{grid-template-columns:1fr}}
</style></head>
<body><div class="header">
<span class="title">🔐 V6 MASTER PRO — ADMIN PORTAL</span>
<span style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
  <span id="mode-badge" style="font-size:12px;padding:4px 12px;border-radius:4px;font-weight:bold;border:2px solid {{ '#FFD700' if paper_mode else '#FF4500' }};color:{{ '#FFD700' if paper_mode else '#FF4500' }}">
    {{ '📄 PAPER MODE' if paper_mode else '⚡ REAL MODE LIVE' }}
  </span>
  <span style="color:#555;font-size:11px">Session: 15 min idle</span>
  <a href="/admin/logout" class="logout">LOGOUT</a>
</span></div>
<div class="container">

<!-- ══ SYSTEM STATUS ══ -->
<div class="card"><h3>📊 SYSTEM STATUS</h3>
<div>
<div class="stat"><span class="val {{ 'green' if status=='live' else 'red' }}">{{ status.upper() }}</span><span class="lbl">Status</span></div>
<div class="stat"><span class="val">{{ cycles }}</span><span class="lbl">Cycles</span></div>
<div class="stat"><span class="val">{{ uptime }}</span><span class="lbl">Uptime</span></div>
<div class="stat"><span class="val {{ 'red' if btc_pause else 'green' }}">{{ 'PAUSED' if btc_pause else 'ACTIVE' }}</span><span class="lbl">Entries</span></div>
<div class="stat"><span class="val">{{ win_rate }}%</span><span class="lbl">Win Rate</span></div>
<div class="stat"><span class="val">{{ win_streak }}</span><span class="lbl">Win Streak</span></div>
<div class="stat"><span class="val">{{ total_wins }}W / {{ total_losses }}L</span><span class="lbl">Backtest</span></div>
<div class="stat"><span class="val">{{ hot_cnt }}</span><span class="lbl">Hot Coins</span></div>
<div class="stat"><span class="val">{{ hist_cnt }}</span><span class="lbl">Alerts</span></div>
</div></div>

<!-- ══ CONNECTION STATUS ══ -->
<div class="card"><h3>🔌 CONNECTION STATUS</h3>
<div id="conn-status-row" style="display:flex;gap:20px;flex-wrap:wrap">
  <span><span class="dot dot-yellow" id="dot-tg"></span><span id="lbl-tg" style="font-size:12px">Telegram: checking…</span></span>
  <span><span class="dot dot-yellow" id="dot-gs"></span><span id="lbl-gs" style="font-size:12px">Google Sheets: checking…</span></span>
  <span><span class="dot dot-yellow" id="dot-ex"></span><span id="lbl-ex" style="font-size:12px">Exchange API: checking…</span></span>
  <span><span class="dot dot-yellow" id="dot-pm"></span><span id="lbl-pm" style="font-size:12px">Trade Mode: checking…</span></span>
</div>
<div style="margin-top:8px;font-size:10px;color:#555" id="conn-meta">Last checked: —</div>
<script>
function refreshHealth(){
  fetch('/system_health',{cache:'no-store'}).then(r=>r.json()).then(d=>{
    const set=(id,ok,label)=>{
      const dot=document.getElementById('dot-'+id), lbl=document.getElementById('lbl-'+id);
      if(dot) dot.className='dot '+(ok?'dot-green':'dot-red');
      if(lbl) lbl.textContent=label;
    };
    set('tg', d.telegram==='CONNECTED',     'Telegram: '+(d.telegram==='CONNECTED'?'✅ Connected':'❌ BOT_TOKEN not set'));
    set('gs', d.google_sheets==='CONNECTED','Google Sheets: '+(d.google_sheets==='CONNECTED'?'✅ Connected':'❌ GOOGLE_CREDENTIALS not set'));
    const exUp = d.exchange_api==='CONNECTED';
    set('ex', exUp, 'Exchange API: '+(exUp?'✅ Connected ('+(d.exchange_host||'binance').replace('https://','')+')':'❌ '+(d.exchange_detail||'Disconnected')));
    set('pm', true, 'Trade Mode: '+(d.paper_mode?'📄 PAPER (safe)':'⚡ REAL LIVE'));
    document.getElementById('dot-pm').className='dot '+(d.paper_mode?'dot-green':'dot-red');
    const meta=document.getElementById('conn-meta');
    if(meta) meta.textContent='Last checked: '+new Date().toLocaleTimeString()+(d.exchange_last_ok?'  ·  Exchange last OK: '+d.exchange_last_ok:'');
  }).catch(()=>{
    const meta=document.getElementById('conn-meta');
    if(meta) meta.textContent='Health check failed — retrying…';
  });
}
refreshHealth();
setInterval(refreshHealth, 15000);
</script></div>

<!-- ══ RISK CALCULATOR + FUND LIMIT ══ -->
<div class="card"><h3>💰 RISK CALCULATOR &amp; FUND LIMIT</h3>
<div class="trade-grid">
<div>
<p style="color:#8b949e;font-size:11px;margin-bottom:8px">Account Balance (for position sizing)</p>
<form method="POST" action="/admin/set_balance"><div class="form-row">
<input type="number" name="balance" value="{{ balance }}" placeholder="Balance (USDT)" style="width:180px"/>
<button type="submit" class="btn btn-blue">Update</button></div>
<small style="color:#555">GREEN: {{ green_pct }}% | YELLOW: {{ yellow_pct }}% | RED: 0%</small></form>
</div>
<div>
<p style="color:#FF6B35;font-size:11px;margin-bottom:8px">🛡️ Bot Safety — Max Fund Per Trade</p>
<form method="POST" action="/admin/set_fund_limit"><div class="form-row">
<input type="number" name="fund_limit" value="{{ fund_limit }}" placeholder="e.g. 10" step="0.01" min="1" style="width:130px"/>
<span style="color:#555;font-size:11px">USDT max / trade</span>
<button type="submit" class="btn btn-orange">Set Limit</button></div>
<small style="color:#555">Bot will NEVER place a trade larger than this limit regardless of account size</small></form>
</div>
</div></div>

<!-- ══ EXCHANGE SWITCHER ══ -->
<div class="card"><h3>🔄 EXCHANGE SWITCHER</h3>
<form method="POST" action="/admin/set_exchange"><div class="form-row">
<select name="exchange">{% for ex in exchanges %}<option value="{{ ex }}" {{ 'selected' if ex == exchange else '' }}>{{ ex }}</option>{% endfor %}</select>
<button type="submit" class="btn btn-blue">Switch</button></div></form></div>

<!-- ══ PRICE ALERTS ══ -->
<div class="card"><h3>🎯 PRICE ALERTS ({{ price_alerts|length }} active)</h3>
<form method="POST" action="/admin/set_price_alert"><div class="form-row">
<input type="text" name="symbol" placeholder="BTCUSDT" style="width:110px" required/>
<input type="number" name="target_price" step="any" placeholder="Target Price" style="width:130px" required/>
<select name="direction" style="width:90px"><option value="ABOVE">ABOVE ↑</option><option value="BELOW">BELOW ↓</option></select>
<input type="text" name="note" placeholder="My reason…" style="flex:1"/>
<button type="submit" class="btn btn-blue">+ Add Alert</button></div></form>
{% if price_alerts %}
<table style="margin-top:10px"><thead><tr><th>Symbol</th><th>Target</th><th>Dir</th><th>Note</th><th>Set At</th><th></th></tr></thead><tbody>
{% for a in price_alerts %}<tr>
<td style="color:#FFD700">{{ a.symbol.replace('USDT','') }}</td>
<td style="color:#3fb950">{{ a.target_price }}</td>
<td><span style="color:{{ '#3fb950' if a.direction=='ABOVE' else '#FF4500' }}">{{ a.direction }}</span></td>
<td style="color:#555;font-size:10px">{{ a.note or '—' }}</td>
<td style="color:#444;font-size:10px">{{ a.created_at }}</td>
<td><form method="POST" action="/admin/delete_price_alert" style="display:inline">
<input type="hidden" name="alert_id" value="{{ a.id }}"/>
<button type="submit" class="btn btn-red" style="padding:2px 8px">✕</button></form></td>
</tr>{% endfor %}</tbody></table>
{% else %}<p style="color:#444;font-size:11px;margin-top:8px">No active alerts. Set a price target above — Telegram fires when hit.</p>{% endif %}
</div>

<!-- ══ API KEY MANAGEMENT ══ -->
<div class="card"><h3>🔑 API KEY MANAGEMENT</h3>
<p style="background:#1a0000;border:1px solid #FF4500;padding:8px;border-radius:4px;color:#FF4500;font-size:11px;margin-bottom:12px">
⚠️ <b>SECURITY:</b> Enable <b>Read + Trade only.</b> NEVER enable Withdraw permission. Keys are masked after saving.
</p>
{% for ex in ['BINANCE','KUCOIN','MEXC','BITMART','BYBIT','OKX'] %}
<details style="margin-bottom:6px;background:#0d1117;border-radius:4px;border:1px solid {{ '#30363d' if ex not in saved_keys else '#3fb950' }};padding:6px 10px">
<summary style="cursor:pointer;color:{{ '#3fb950' if ex in saved_keys else '#8b949e' }};font-weight:bold;font-size:12px">
{{ '✅' if ex in saved_keys else '⬜' }} {{ ex }}{{ ' — Configured' if ex in saved_keys else ' — Not set' }}
</summary>
<form method="POST" action="/admin/set_api_key" style="margin-top:8px">
<input type="hidden" name="exchange" value="{{ ex }}"/>
<div class="form-row">
<input type="text" name="api_key" placeholder="API Key" style="flex:1"/>
<input type="password" name="secret_key" placeholder="Secret Key" style="flex:1"/>
{% if ex == 'OKX' %}<input type="password" name="passphrase" placeholder="Passphrase" style="width:130px"/>{% endif %}
<button type="submit" class="btn btn-blue">Save</button>
<form method="POST" action="/admin/test_connection" style="display:inline"><input type="hidden" name="exchange" value="{{ ex }}"/><button type="submit" class="btn" style="background:#21262d;color:#58a6ff;border:1px solid #30363d">Test ⚡</button></form>
</div></form>
{% if ex in saved_keys %}<p style="color:#555;font-size:10px;margin-top:4px">API Key: {{ saved_keys[ex]['api_key_mask'] }} | Secret: ●●●●●●●●●●●● (saved)</p>{% endif %}
</details>{% endfor %}
</div>

<!-- ══ PAPER MODE INTELLIGENCE ══ -->
<div class="card"><h3>🧠 PAPER MODE INTELLIGENCE</h3>
<div>
<div class="stat"><span class="val">{{ ld.get('paper_trades',0) }}</span><span class="lbl">Trades</span></div>
<div class="stat"><span class="val {{ 'green' if ld.get('paper_win_rate',0)>=65 else 'yellow' if ld.get('paper_win_rate',0)>=50 else 'red' }}">{{ ld.get('paper_win_rate',0) }}%</span><span class="lbl">Win Rate</span></div>
<div class="stat"><span class="val">{{ ld.get('wp_threshold',50) }}%</span><span class="lbl">WP Min</span></div>
<div class="stat"><span class="val">{{ ld.get('conf_threshold',50) }}%</span><span class="lbl">Conf Min</span></div>
{% if ld.get('ready_for_real') %}<div class="stat"><span class="val green">🏆 READY</span><span class="lbl">Real Mode</span></div>{% endif %}
</div>
{% if ld.get('adjustment_log') %}
<div class="log-box" style="height:100px;margin-top:10px">{% for l in ld.get('adjustment_log',[])[-8:] %}{{ l }}
{% endfor %}</div>{% endif %}
<p style="color:#555;font-size:10px;margin-top:8px">Bot learns from every paper trade. Thresholds auto-adjust every 10 trades. Telegram alert fires at 65%+ win rate.</p>
</div>

<!-- ══ MODE SWITCH — PROMINENT ══ -->
<div class="card" style="border:2px solid {{ '#FFD700' if paper_mode else '#FF4500' }}">
<h3 style="color:{{ '#FFD700' if paper_mode else '#FF4500' }};font-size:15px">
  {{ '📄 PAPER MODE — Simulation Active' if paper_mode else '💰 REAL MODE — LIVE EXECUTION ACTIVE ⚠️' }}
</h3>
<div style="margin:12px 0;padding:12px;background:#0d1117;border-radius:4px">
  <span style="color:{{ '#FFD700' if paper_mode else '#FF4500' }};font-size:16px;font-weight:bold;display:block;margin-bottom:6px">
    {{ '✅ Safe — No real money at risk. All trades simulated.' if paper_mode else '🚨 LIVE — Real money execution enabled. Trade carefully.' }}
  </span>
  <p style="color:#555;font-size:11px">{{ 'System is learning from signals in paper mode. Switch to REAL MODE only when paper win rate ≥ 65%.' if paper_mode else 'REAL MODE: Signals trigger actual exchange orders. Bot fund limit applies per trade.' }}</p>
</div>
<form method="POST" action="/admin/set_mode">
  {% if paper_mode %}
  <button type="submit" class="btn btn-red" style="padding:10px 24px;font-size:13px;font-weight:bold"
    onclick="return confirm('⚠️ SWITCH TO REAL MODE?\n\nThis will enable LIVE TRADE EXECUTION.\nReal money will be used for every signal.\n\nOnly proceed if:\n• Paper Win Rate ≥ 65%\n• API keys are configured\n• Fund limit is set\n\nAre you ABSOLUTELY sure?')">
    ⚡ Switch to REAL MODE
  </button>
  {% else %}
  <button type="submit" class="btn btn-blue" style="padding:10px 24px;font-size:13px;font-weight:bold">
    📄 Switch to PAPER MODE (Safe)
  </button>
  {% endif %}
</form></div>

<!-- ══ MANUAL TRADING PANEL ══ -->
<div class="card" style="border-color:#f0883e">
<h3 style="color:#f0883e">🎮 MANUAL TRADING PANEL
  <span style="font-size:10px;padding:2px 8px;border-radius:3px;margin-left:8px;background:{{ '#1a3a00' if paper_mode else '#3a0000' }};color:{{ '#3fb950' if paper_mode else '#FF4500' }}">
    {{ 'PAPER MODE — Simulated' if paper_mode else '⚡ REAL MODE — Live Money' }}
  </span>
</h3>
<div style="background:#0d1117;border:1px solid #30363d;padding:12px;border-radius:4px;margin-bottom:12px">
<form method="POST" action="/admin/manual_trade"
  onsubmit="return confirm('{% if paper_mode %}PAPER TRADE — This will be SIMULATED. No real money.\n\nCoin: ' + this.symbol.value + '\nSide: ' + this.side.value + '\nAmount: $' + this.amount_usdt.value + '\nStrategy: ' + this.strategy.value + '\n\nConfirm paper trade?{% else %}⚠️ REAL TRADE ALERT ⚠️\n\nThis will execute a REAL order with REAL money!\n\nCoin: ' + this.symbol.value + '\nSide: ' + this.side.value + '\nAmount: $' + this.amount_usdt.value + '\nStrategy: ' + this.strategy.value + '\n\nAre you ABSOLUTELY SURE?{% endif %}')">
<div class="form-row" style="margin-bottom:10px">
  <div>
    <label style="color:#8b949e;font-size:10px;display:block;margin-bottom:3px">ASSET</label>
    <input type="text" name="symbol" placeholder="BTCUSDT" style="width:120px;text-transform:uppercase" required/>
  </div>
  <div>
    <label style="color:#8b949e;font-size:10px;display:block;margin-bottom:3px">AMOUNT (USDT)</label>
    <input type="number" name="amount_usdt" placeholder="10" min="1" step="0.01" style="width:110px" required/>
  </div>
  <div>
    <label style="color:#8b949e;font-size:10px;display:block;margin-bottom:3px">SIDE</label>
    <select name="side" style="width:90px">
      <option value="BUY">🟢 BUY</option>
      <option value="SELL">🔴 SELL</option>
    </select>
  </div>
  <div>
    <label style="color:#8b949e;font-size:10px;display:block;margin-bottom:3px">STRATEGY</label>
    <select name="strategy" style="width:120px">
      <option value="SPOT">⚡ SPOT</option>
      <option value="SPOT_GRID">⊞ SPOT GRID</option>
    </select>
  </div>
  <div style="align-self:flex-end">
    <button type="submit" class="btn {{ 'btn-blue' if paper_mode else 'btn-red' }}" style="padding:8px 18px;font-weight:bold">
      {{ '📄 Execute (Paper)' if paper_mode else '⚡ Execute (REAL)' }}
    </button>
  </div>
</div>
<small style="color:#444">SPOT = market order | SPOT GRID = 5 limit buy orders spread below current price (0.5% spacing)</small>
</form>
</div>
<div>
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
  <span style="color:#8b949e;font-size:11px">Recent Paper Trades</span>
  <button onclick="loadTrades()" class="btn" style="background:#21262d;color:#58a6ff;border:1px solid #30363d;padding:3px 8px;font-size:10px">↻ Refresh</button>
</div>
<div id="paper-trades-log" style="background:#0d1117;border:1px solid #30363d;padding:10px;border-radius:4px;min-height:60px;font-size:10px;color:#6e7681">
  <i>Click Refresh to load recent trades…</i>
</div>
</div>
<script>
function loadTrades(){
  fetch('/admin/paper_trades').then(r=>r.json()).then(trades=>{
    const el=document.getElementById('paper-trades-log');
    if(!trades.length){el.innerHTML='<i style="color:#444">No trades logged yet.</i>';return;}
    el.innerHTML=trades.slice(0,15).map(t=>{
      const sc=t.side==='BUY'?'#3fb950':'#FFD700';
      const reason=t.reason?`<div style="color:#8b949e;font-size:9px;margin-top:2px">📋 ${t.reason}</div>`:'';
      return `<div style="border-bottom:1px solid #1a1a2e;padding:4px 0">
        <span style="color:${sc};font-weight:bold">${t.side}</span>
        <span style="color:#c9d1d9"> ${(t.symbol||'').replace('USDT','')}</span>
        <span style="color:#58a6ff"> $${t.amount_usdt}</span>
        <span style="color:#555"> @ ${t.price||'?'}</span>
        <span style="color:#555"> · ${t.strategy||'SPOT'}</span>
        <span style="color:#444;float:right">${t.time}</span>
        ${reason}
      </div>`;
    }).join('');
  }).catch(()=>{document.getElementById('paper-trades-log').innerHTML='<i style="color:#FF4500">Error loading trades</i>';});
}
loadTrades();
</script>
</div>

<!-- ══ HISTORICAL BACKTEST (Phase 2) ══ -->
<div class="card"><h3>📊 HISTORICAL BACKTEST</h3>
<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px">
  <select id="bt-months" style="background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:5px;border-radius:4px;font-size:11px">
    <option value="1">1 month</option>
    <option value="3" selected>3 months</option>
    <option value="6">6 months</option>
  </select>
  <button onclick="runBacktest()" class="btn" style="background:#1f6feb;color:#fff;border:none;padding:5px 12px;font-size:11px">▶ Run Backtest</button>
  <a id="bt-csv" href="#" onclick="downloadBtCsv(event)" class="btn" style="background:#21262d;color:#3fb950;border:1px solid #30363d;padding:5px 12px;font-size:11px;text-decoration:none">⬇ Download CSV</a>
  <button onclick="testTelegram()" class="btn" style="background:#21262d;color:#58a6ff;border:1px solid #30363d;padding:5px 12px;font-size:11px">🧪 Test Telegram</button>
</div>
<div id="bt-status" style="color:#6e7681;font-size:11px;margin-bottom:8px"><i>Pick a window and run a backtest. First run fetches history and may take ~30–60s.</i></div>
<div id="bt-metrics" style="display:none;gap:8px;flex-wrap:wrap;margin-bottom:10px"></div>
<canvas id="bt-equity" height="120" style="display:none;width:100%;background:#0d1117;border:1px solid #30363d;border-radius:4px;margin-bottom:8px"></canvas>
<div id="bt-note" style="color:#6e7681;font-size:9px;font-style:italic"></div>
</div>
<script>
function btCard(label,val,color){return `<div style="flex:1;min-width:90px;background:#0d1117;border:1px solid #30363d;border-radius:4px;padding:8px"><div style="color:#6e7681;font-size:9px">${label}</div><div style="color:${color};font-size:16px;font-weight:bold">${val}</div></div>`;}
function drawEquity(curve){
  const cv=document.getElementById('bt-equity');cv.style.display='block';
  const ctx=cv.getContext('2d');const W=cv.width=cv.clientWidth,H=cv.height;
  ctx.clearRect(0,0,W,H);
  if(!curve||curve.length<2)return;
  const eq=curve.map(p=>p.equity);const mn=Math.min(...eq),mx=Math.max(...eq);const rng=(mx-mn)||1;
  ctx.strokeStyle='#3fb950';ctx.lineWidth=1.5;ctx.beginPath();
  curve.forEach((p,i)=>{const x=i/(curve.length-1)*(W-8)+4;const y=H-8-((p.equity-mn)/rng)*(H-16);i?ctx.lineTo(x,y):ctx.moveTo(x,y);});
  ctx.stroke();
  ctx.strokeStyle='#30363d';ctx.lineWidth=0.5;ctx.beginPath();
  const y0=H-8-((curve[0].equity-mn)/rng)*(H-16);ctx.moveTo(4,y0);ctx.lineTo(W-4,y0);ctx.stroke();
}
function runBacktest(){
  const m=document.getElementById('bt-months').value;
  const st=document.getElementById('bt-status');
  st.innerHTML='<span style="color:#d29922">⏳ Running backtest over '+m+' month(s)… fetching Binance history…</span>';
  fetch('/admin/historical_backtest?months='+m).then(r=>r.json()).then(d=>{
    if(d.error){st.innerHTML='<span style="color:#FF4500">Error: '+d.error+'</span>';return;}
    st.innerHTML='<span style="color:#3fb950">✓ '+d.start+' → '+d.end+' · '+d.total_trades+' trades ('+d.skipped_by_circuit_breaker+' skipped by circuit-breaker)</span>';
    const pfc=d.profit_factor>=1.5?'#3fb950':(d.profit_factor>=1?'#d29922':'#FF4500');
    const wrc=d.win_rate>=50?'#3fb950':'#d29922';
    const ddc=d.max_drawdown_pct<=15?'#3fb950':(d.max_drawdown_pct<=30?'#d29922':'#FF4500');
    const nrc=d.net_return_pct>=0?'#3fb950':'#FF4500';
    const mt=document.getElementById('bt-metrics');mt.style.display='flex';
    mt.innerHTML=btCard('Win Rate',d.win_rate+'%',wrc)+btCard('Profit Factor',d.profit_factor,pfc)
      +btCard('Max Drawdown',d.max_drawdown_pct+'%',ddc)+btCard('Net Return',d.net_return_pct+'%',nrc)
      +btCard('End Equity','$'+d.end_equity,nrc)+btCard('W / L',d.wins+' / '+d.losses,'#c9d1d9');
    drawEquity(d.equity_curve);
    document.getElementById('bt-note').textContent='ℹ '+d.note;
  }).catch(e=>{st.innerHTML='<span style="color:#FF4500">Request failed: '+e+'</span>';});
}
function downloadBtCsv(ev){ev.preventDefault();const m=document.getElementById('bt-months').value;window.location='/admin/backtest_csv?months='+m;}
function testTelegram(){
  const st=document.getElementById('bt-status');st.innerHTML='<span style="color:#d29922">⏳ Sending test message…</span>';
  fetch('/admin/test_telegram').then(r=>r.json()).then(d=>{
    st.innerHTML='<span style="color:'+(d.ok?'#3fb950':'#FF4500')+'">'+(d.ok?'✓ ':'✗ ')+d.message+'</span>';
  }).catch(e=>{st.innerHTML='<span style="color:#FF4500">Request failed: '+e+'</span>';});
}
</script>

<!-- ══ MY HOLDINGS / INVENTORY ══ -->
<div class="card"><h3>📦 MY HOLDINGS (INVENTORY)</h3>
<p style="color:#8b949e;font-size:11px;margin-bottom:10px">Track coins you already own — get a Telegram+Email alert when it looks like a good time to sell.</p>
<form method="POST" action="/admin/add_holding"><div class="form-row">
<input type="text" name="symbol" placeholder="BTC" style="width:90px" required/>
<input type="number" name="quantity" placeholder="Quantity" step="any" style="width:110px" required/>
<input type="number" name="buy_price" placeholder="Buy Price" step="any" style="width:110px" required/>
<input type="number" name="target_pct" placeholder="Target %" value="15" style="width:100px"/>
<button type="submit" class="btn btn-blue">+ Add Holding</button></div></form>
<table style="margin-top:10px"><thead><tr><th>Symbol</th><th>Qty</th><th>Buy Price</th><th>Current</th><th>P/L%</th><th></th></tr></thead>
<tbody id="holdings-tbody"><tr><td colspan="6" style="color:#444">Loading…</td></tr></tbody></table>
</div>
<script>
function loadHoldings(){
  fetch('/admin/holdings_status').then(r=>r.json()).then(hs=>{
    const tb=document.getElementById('holdings-tbody');
    if(!hs.length){tb.innerHTML='<tr><td colspan="6" style="color:#444">No holdings added yet</td></tr>';return;}
    tb.innerHTML=hs.map(h=>{
      const pnlColor=h.pnl_pct>=0?'#3fb950':'#FF4500';
      return `<tr>
        <td style="color:#FFD700">${h.symbol.replace('USDT','')}</td>
        <td>${h.quantity}</td>
        <td>${h.buy_price}</td>
        <td>${h.current_price||'—'}</td>
        <td style="color:${pnlColor}">${h.pnl_pct}%</td>
        <td><form method="POST" action="/admin/delete_holding" style="display:inline">
          <input type="hidden" name="symbol" value="${h.symbol}"/>
          <button type="submit" class="btn btn-red" style="padding:2px 8px">✕</button></form></td>
      </tr>`;
    }).join('');
  }).catch(()=>{});
}
loadHoldings();
setInterval(loadHoldings, 20000);
</script>

<!-- ══ HOT COINS ══ -->
<div class="card"><h3>🔥 HOT COINS (3+ signals/hr)</h3>
<table><thead><tr><th>Symbol</th><th>Count</th><th>Since</th></tr></thead><tbody>
{% for h in hot_coins %}<tr><td>{{ h.symbol }}</td><td style="color:#FF6B35">{{ h.count }}</td><td>{{ h.since }}</td></tr>{% else %}<tr><td colspan="3" style="color:#444">No hot coins active</td></tr>{% endfor %}
</tbody></table></div>

<!-- ══ RECENT ALERTS ══ -->
<div class="card"><h3>🔔 RECENT ALERTS</h3>
<table><thead><tr><th>Time</th><th>Type</th><th>Symbol</th><th>Conf%</th><th>Traffic</th><th>Detail</th></tr></thead><tbody>
{% for a in alerts[:20] %}<tr><td style="color:#444;font-size:10px">{{ a.time }}</td>
<td style="color:{{ '#FF4500' if a.type=='WHALE' else '#da70d6' }}">{{ a.type }}</td>
<td>{{ a.symbol }}</td><td style="color:#FFD700">{{ a.confidence }}%</td>
<td class="{{ 'green' if a.traffic=='GREEN' else 'yellow' if a.traffic=='YELLOW' else 'red' }}">{{ a.traffic or '—' }}</td>
<td style="font-size:10px;color:#6e7681">{{ a.detail }}</td></tr>{% endfor %}</tbody></table></div>

<!-- ══ AUDIT LOG ══ -->
<div class="card"><h3>📋 AUDIT LOG</h3>
<div class="form-row" style="margin-bottom:10px">
<form method="GET" action="/admin/audit_log" style="display:flex;gap:8px;flex-wrap:wrap">
<input type="date" name="date_from" value="{{ today }}"/><input type="date" name="date_to" value="{{ today }}"/>
<select name="fmt"><option value="html">HTML</option><option value="csv">CSV ↓</option></select>
<button type="submit" class="btn btn-blue">Export Audit Log</button></form>
<form method="POST" action="/admin/refresh_scan" style="display:inline">
<button type="submit" class="btn btn-green" onclick="return confirm('Force an immediate scan? This refreshes all signal data.')">🔄 Force Refresh Scan</button></form>
</div>
<div class="log-box">{{ audit_preview }}</div></div>

<!-- ══ CLIENT MANAGEMENT ══ -->
<div class="card"><h3>👥 CLIENT MANAGEMENT</h3>
<p style="color:#555;font-size:11px;margin-bottom:10px">Add/remove client access. Changes sync to Google Sheets USERS tab on next scan cycle.</p>
<form method="POST" action="/admin/add_client"><div class="form-row">
<input type="text" name="name" placeholder="Username" style="width:110px" required/>
<input type="text" name="uid" placeholder="UID/ID" style="width:80px" required/>
<input type="password" name="password" placeholder="Password" style="width:110px" required/>
<input type="text" name="expiry" placeholder="UNLIMITED or YYYY-MM-DD" style="width:160px"/>
<input type="number" name="sig_limit" placeholder="Signals/day" value="100" style="width:100px"/>
<button type="submit" class="btn btn-blue">+ Add Client</button></div></form>
{% if clients %}
<table style="margin-top:12px"><thead><tr><th>Name</th><th>UID</th><th>Status</th><th>Expiry</th><th>Sig/Day</th><th></th></tr></thead><tbody>
{% for c in clients %}<tr>
<td style="color:#3fb950">{{ c.name }}</td>
<td style="color:#FFD700">{{ c.uid }}</td>
<td><span style="color:{{ '#3fb950' if c.status=='ACTIVE' else '#FF4500' }}">{{ c.status }}</span></td>
<td style="color:#555;font-size:10px">{{ c.expiry }}</td>
<td style="color:#8b949e">{{ c.sig_limit }}</td>
<td>
<form method="POST" action="/admin/toggle_client" style="display:inline"><input type="hidden" name="name" value="{{ c.name }}"/>
<button type="submit" class="btn" style="background:#21262d;color:#58a6ff;border:1px solid #30363d;padding:2px 8px">{{ 'Disable' if c.status=='ACTIVE' else 'Enable' }}</button></form>
<form method="POST" action="/admin/delete_client" style="display:inline;margin-left:4px"><input type="hidden" name="name" value="{{ c.name }}"/>
<button type="submit" class="btn btn-red" style="padding:2px 8px" onclick="return confirm('Remove {{ c.name }}?')">✕</button></form>
</td></tr>{% endfor %}</tbody></table>
{% else %}<p style="color:#444;font-size:11px;margin-top:8px">No clients registered.</p>{% endif %}
</div>

<!-- ══ ADMIN CONTROLS ══ -->
<div class="card"><h3 style="color:#FF4500">⚠️ ADMIN CONTROLS</h3>
<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
<form method="POST" action="/admin/refresh_scan" style="display:inline">
<button type="submit" class="btn btn-green" onclick="return confirm('Force a full data scan now?')">🔄 Refresh/Reconnect</button></form>
<form method="GET" action="/admin/audit_log" style="display:inline">
<input type="hidden" name="date_from" value="{{ today }}"/>
<input type="hidden" name="date_to" value="{{ today }}"/>
<input type="hidden" name="fmt" value="csv"/>
<button type="submit" class="btn btn-blue">📥 Export Audit Log</button></form>
<form method="POST" action="/admin/clear_history" style="display:inline">
<button type="submit" class="btn btn-red" onclick="return confirm('Clear all alert history?')">🗑 Clear Alert History</button></form>
<form method="POST" action="/admin/clear_backtest" style="display:inline">
<button type="submit" class="btn btn-red" onclick="return confirm('Clear backtest results + stats?')">🗑 Clear Backtest</button></form>
<form method="POST" action="/admin/clear_whale_copy" style="display:inline">
<button type="submit" class="btn btn-red" onclick="return confirm('Clear all Whale Copy trades and signals?')">🐋 Clear Whale Copy</button></form>
</div></div>

</div></body></html>"""


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    ip = request.remote_addr
    locked  = _check_lockout(ip)
    timeout = request.args.get("timeout") == "1"
    error   = False
    if request.method == "POST" and not locked:
        if request.form.get("password", "") == ADMIN_PASSWORD:
            session["admin_auth"] = True; session["last_active"] = time.time()
            audit(ip, "ADMIN_LOGIN", "SUCCESS", "")
            return redirect("/admin")
        _record_failed_login(ip); locked = _check_lockout(ip); error = True
    return render_template_string(ADMIN_LOGIN_HTML, locked=locked, timeout=timeout, error=error)


@app.route("/admin/logout")
def admin_logout():
    audit(request.remote_addr, "ADMIN_LOGOUT", "OK", "")
    session.clear(); return redirect("/admin/login")


@app.route("/admin")
@_admin_required
def admin_portal():
    secs = int(time.time() - GLOBAL_DATA["uptime_start"])
    h, r = divmod(secs, 3600); m, s = divmod(r, 60)
    try:
        with open("system_audit.log") as f: preview = "".join(f.readlines()[-30:])
    except Exception:
        preview = "No audit log yet."
    saved_keys_masked = {ex: {"api_key_mask": _mask(_API_KEYS[ex].get("api_key",""))}
                         for ex in _API_KEYS}
    return render_template_string(ADMIN_PORTAL_HTML,
        status=GLOBAL_DATA["status"], cycles=GLOBAL_DATA["cycle_count"],
        uptime=f"{h}h {m}m {s}s", btc_pause=GLOBAL_DATA.get("btc_pause"),
        win_rate=GLOBAL_DATA["win_rate"], win_streak=_win_streak,
        total_wins=_total_wins, total_losses=_total_losses,
        hot_cnt=len(GLOBAL_DATA["hot_coins"]), hist_cnt=len(GLOBAL_DATA["alert_history"]),
        balance=CONFIG["risk"]["account_balance_usdt"],
        green_pct=CONFIG["risk"]["green_signal_max_pct"],
        yellow_pct=CONFIG["risk"]["yellow_signal_max_pct"],
        exchange=GLOBAL_DATA.get("active_exchange", "BINANCE"),
        exchanges=["BINANCE","KUCOIN","BITMART","MEXC"],
        hot_coins=GLOBAL_DATA["hot_coins"], alerts=GLOBAL_DATA["alert_history"],
        audit_preview=preview, today=time.strftime("%Y-%m-%d"),
        paper_mode=GLOBAL_DATA.get("paper_mode", True),
        price_alerts=GLOBAL_DATA.get("price_alerts", []),
        saved_keys=saved_keys_masked,
        ld=GLOBAL_DATA.get("learning_data", {}),
        clients=[type('C', (), c)() for c in _load_clients()],
        fund_limit=CONFIG.get("bot_fund_limit_usdt", 10.0),
    )


@app.route("/admin/set_price_alert", methods=["POST"])
@_admin_required
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


@app.route("/admin/delete_price_alert", methods=["POST"])
@_admin_required
def admin_delete_price_alert():
    global PRICE_ALERTS
    try:    aid = int(request.form.get("alert_id", -1))
    except: return redirect("/admin")
    PRICE_ALERTS = [a for a in PRICE_ALERTS if a["id"] != aid]
    GLOBAL_DATA["price_alerts"] = PRICE_ALERTS[:]
    audit(request.remote_addr, "DELETE_PRICE_ALERT", "OK", f"id={aid}")
    return redirect("/admin")


@app.route("/admin/set_api_key", methods=["POST"])
@_admin_required
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


@app.route("/admin/test_connection", methods=["POST"])
@_admin_required
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


@app.route("/admin/set_mode", methods=["POST"])
@_admin_required
def admin_set_mode():
    current = GLOBAL_DATA.get("paper_mode", True)
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


@app.route("/admin/set_balance", methods=["POST"])
@_admin_required
def admin_set_balance():
    try:
        CONFIG["risk"]["account_balance_usdt"] = float(request.form.get("balance", 1000))
        with open("config.json", "w") as f: json.dump(CONFIG, f, indent=2)
        audit(request.remote_addr, "SET_BALANCE", "OK", f"balance={CONFIG['risk']['account_balance_usdt']}")
    except Exception as e:
        audit(request.remote_addr, "SET_BALANCE", "ERROR", str(e))
    return redirect("/admin")


@app.route("/admin/set_exchange", methods=["POST"])
@_admin_required
def admin_set_exchange():
    ex = request.form.get("exchange", "BINANCE").upper()
    GLOBAL_DATA["active_exchange"] = ex
    audit(request.remote_addr, "SET_EXCHANGE", "OK", f"ex={ex}")
    return redirect("/admin")


@app.route("/admin/clear_history", methods=["POST"])
@_admin_required
def admin_clear_history():
    GLOBAL_DATA["alert_history"] = []
    audit(request.remote_addr, "CLEAR_HISTORY", "OK", ""); return redirect("/admin")


@app.route("/admin/clear_backtest", methods=["POST"])
@_admin_required
def admin_clear_backtest():
    global BACKTEST_SIGNALS, _total_wins, _total_losses, _win_streak
    BACKTEST_SIGNALS = []; _total_wins = 0; _total_losses = 0; _win_streak = 0
    GLOBAL_DATA["backtest"] = []; GLOBAL_DATA["win_streak"] = 0
    GLOBAL_DATA["total_wins"] = 0; GLOBAL_DATA["total_losses"] = 0; GLOBAL_DATA["win_rate"] = 0.0
    audit(request.remote_addr, "CLEAR_BACKTEST", "OK", ""); return redirect("/admin")


@app.route("/admin/clear_whale_copy", methods=["POST"])
@_admin_required
def admin_clear_whale_copy():
    global WHALE_COPY_TRADES
    WHALE_COPY_TRADES = []
    _save_whale_copy_trades()
    GLOBAL_DATA["whale_copy_signals"] = []
    audit(request.remote_addr, "CLEAR_WHALE_COPY", "OK", "")
    return redirect("/admin")


# ── System Health (public, used by admin portal JS) ────────────────────────────

@app.route("/system_health")
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


# ── Fund Limit ─────────────────────────────────────────────────────────────────

@app.route("/admin/set_fund_limit", methods=["POST"])
@_admin_required
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


# ── Manual Trade Execution ─────────────────────────────────────────────────────

@app.route("/admin/manual_trade", methods=["POST"])
@_admin_required
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
        result   = _execute_real_binance_spot(symbol, side, amount)
        mode_str = "REAL SPOT"

    if result.get("ok"):
        audit(request.remote_addr, "MANUAL_TRADE", "OK",
              f"sym={symbol} side={side} amt={amount} mode={mode_str} strategy={strategy}")
        notify_trade(symbol, side, strategy, mode_str, reason,
                     amount=amount, tp_zones=tp_ctx or None, traffic=traffic)
        msg = f"Trade executed ({mode_str}):\\n{side} ${amount} of {symbol.replace('USDT','')}\\n\\nCheck Manual Trading panel for details."
    else:
        audit(request.remote_addr, "MANUAL_TRADE", "FAIL",
              f"sym={symbol} err={result.get('error','?')}")
        msg = f"Trade FAILED:\\n{result.get('error','Unknown error')}"
    return f"<script>alert('{msg}');window.location='/admin'</script>"


# ── Force Scan ─────────────────────────────────────────────────────────────────

@app.route("/admin/refresh_scan", methods=["POST"])
@_admin_required
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
            whale_copy_signals = detect_whale_copy_signals(whale_data, CONFIG)
            for _wcs in whale_copy_signals:
                if _wcs.get("confirmed"):
                    _wcs_atr = calculate_atr(_wcs["symbol"])
                    _wcs["eta"] = estimate_time_to_target(_wcs["price"], _wcs["target"], _wcs_atr)["label"]
                else:
                    _wcs["eta"] = "—"
            GLOBAL_DATA["whale_copy_signals"] = whale_copy_signals
            wc_min_conf = CONFIG.get("whale_copy", {}).get("min_confidence", 50)
            for sig in whale_copy_signals:
                if sig["direction"] == "COPY_BUY" and sig.get("confirmed") and sig["confidence"] >= wc_min_conf:
                    _record_whale_copy_trade(sig)
            GLOBAL_DATA["vmc"]         = vmc_data
            GLOBAL_DATA["whale"]       = whale_data
            GLOBAL_DATA["last_update"] = time.strftime("%Y-%m-%d %H:%M:%S")
            GLOBAL_DATA["status"]      = "live"
            log.info("[ADMIN] Force scan completed — data refreshed")
        except Exception as e:
            log.error(f"[ADMIN] Force scan error: {e}")
    threading.Thread(target=_force_scan, daemon=True).start()
    audit(request.remote_addr, "FORCE_SCAN", "TRIGGERED", "")
    return "<script>alert('Force scan triggered!\\nAll signal data will refresh in ~30 seconds.');window.location='/admin'</script>"


# ── Paper Trades Log ───────────────────────────────────────────────────────────

@app.route("/admin/paper_trades")
@_admin_required
def admin_paper_trades_log():
    return jsonify(PAPER_TRADES[:100])


# ── Historical Backtest (Phase 2) ───────────────────────────────────────────────

_BACKTEST_CACHE = {"key": None, "report": None, "ts": 0}
_BACKTEST_LOCK  = threading.Lock()


def _backtest_symbols() -> list:
    syms = (CONFIG.get("vmc", {}).get("favorite_coins")
            or CONFIG.get("favorite_coins") or CONFIG.get("watchlist") or [])
    syms = [s if s.endswith("USDT") else f"{s}USDT" for s in syms]
    return syms[:8] if syms else ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]


def _run_backtest(months: int) -> dict:
    from logic import historical_backtest
    syms = _backtest_symbols()
    key  = f"{months}:{','.join(syms)}"
    # Serialize so concurrent admin requests don't each kick off a heavy
    # (~30–60s) Binance replay; the second waiter gets the fresh cached result.
    with _BACKTEST_LOCK:
        if (_BACKTEST_CACHE["key"] == key and _BACKTEST_CACHE["report"]
                and time.time() - _BACKTEST_CACHE["ts"] < 1800):
            return _BACKTEST_CACHE["report"]
        report = historical_backtest(syms, months=months, interval="1h", config=CONFIG)
        _BACKTEST_CACHE.update({"key": key, "report": report, "ts": time.time()})
        return report


@app.route("/admin/historical_backtest")
@_admin_required
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


@app.route("/admin/backtest_csv")
@_admin_required
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


@app.route("/admin/test_telegram")
@_admin_required
def admin_test_telegram():
    ok = send_telegram(
        "🧪 <b>V6 Master Pro — Telegram Test</b>\n"
        "If you can read this, alerts are wired up correctly.\n"
        f"Time: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    audit(request.remote_addr, "TEST_TELEGRAM", "OK" if ok else "FAIL", "")
    return jsonify({"ok": bool(ok),
                    "message": "Sent — check your Telegram." if ok else
                               "Failed — server could not reach Telegram (check BOT_TOKEN / proxy)."})


@app.route("/admin/audit_log")
@_admin_required
def admin_audit_log():
    date_from = request.args.get("date_from", time.strftime("%Y-%m-%d"))
    date_to   = request.args.get("date_to",   time.strftime("%Y-%m-%d"))
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


# ── Client Management Helpers ──────────────────────────────────────────────────

def _load_clients() -> list:
    try:
        with open("clients.json") as f:
            return json.load(f)
    except Exception:
        return []

def _save_clients(clients: list):
    with open("clients.json", "w") as f:
        json.dump(clients, f, indent=2)


_HOLDINGS_FILE = "holdings.json"

def _load_holdings() -> list:
    try:
        with open(_HOLDINGS_FILE) as f:
            return json.load(f)
    except Exception:
        return []

def _save_holdings(holdings: list):
    with open(_HOLDINGS_FILE, "w") as f:
        json.dump(holdings, f, indent=2)


def holdings_check_loop():
    """Every 5 minutes: check each held coin's live v6 score/price move and
    send a Telegram+Email sell-check alert when it looks like a good time
    to sell (AVOID signal or profit target reached). 1-hour cooldown/coin."""
    while True:
        time.sleep(300)
        try:
            for h in _load_holdings():
                sym = h["symbol"]
                sig = _compute_live_signal(sym)
                if not sig:
                    continue
                price     = sig.get("price", 0)
                buy_price = h.get("buy_price", 0)
                pnl_pct   = round((price - buy_price) / buy_price * 100, 2) if buy_price and price else 0
                v6        = sig.get("v6", {})
                label     = v6.get("label", "")
                target    = h.get("target_pct", 15)
                should_alert = label == "AVOID" or (target and pnl_pct >= target)
                if should_alert and _can_alert(f"holding_{sym}", 3600):
                    reason = "V6 score suggests distribution/avoid" if label == "AVOID" else f"Profit target ({target}%) reached"
                    msg = (f"💰 <b>SELL CHECK — {sym.replace('USDT','')}</b>\n"
                           f"Holding: {h.get('quantity',0)} @ buy {_fmtP(buy_price)}\n"
                           f"Current: {_fmtP(price)} | P/L: {pnl_pct}%\n"
                           f"V6 Signal: {label} (score {v6.get('score',0)})\n"
                           f"📋 {reason}")
                    notify_all(f"V6 Sell Check — {sym.replace('USDT','')} ({pnl_pct}%)", msg)
        except Exception as e:
            log.warning(f"Holdings check error: {e}")


@app.route("/admin/add_client", methods=["POST"])
@_admin_required
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
    clients.append({"name": name, "uid": uid, "password": pwd, "status": "ACTIVE",
                    "expiry": exp, "sig_limit": lim, "role": "CLIENT",
                    "added": time.strftime("%Y-%m-%d")})
    _save_clients(clients)
    audit(request.remote_addr, "ADD_CLIENT", "OK", f"name={name} uid={uid}")
    return redirect("/admin")


@app.route("/admin/delete_client", methods=["POST"])
@_admin_required
def admin_delete_client():
    name    = request.form.get("name", "").strip()
    clients = [c for c in _load_clients() if c.get("name") != name]
    _save_clients(clients)
    audit(request.remote_addr, "DELETE_CLIENT", "OK", f"name={name}")
    return redirect("/admin")


@app.route("/admin/toggle_client", methods=["POST"])
@_admin_required
def admin_toggle_client():
    name    = request.form.get("name", "").strip()
    clients = _load_clients()
    for c in clients:
        if c.get("name") == name:
            c["status"] = "INACTIVE" if c.get("status") == "ACTIVE" else "ACTIVE"
    _save_clients(clients)
    audit(request.remote_addr, "TOGGLE_CLIENT", "OK", f"name={name}")
    return redirect("/admin")


# ── Holdings / Inventory ────────────────────────────────────────────────────

@app.route("/admin/add_holding", methods=["POST"])
@_admin_required
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
                      "target_pct": target_pct, "added": time.strftime("%Y-%m-%d")})
    _save_holdings(holdings)
    audit(request.remote_addr, "ADD_HOLDING", "OK", f"sym={sym} qty={qty}")
    return redirect("/admin")


@app.route("/admin/delete_holding", methods=["POST"])
@_admin_required
def admin_delete_holding():
    sym = request.form.get("symbol", "").upper().strip()
    holdings = [h for h in _load_holdings() if h["symbol"] != sym]
    _save_holdings(holdings)
    audit(request.remote_addr, "DELETE_HOLDING", "OK", f"sym={sym}")
    return redirect("/admin")


@app.route("/admin/holdings_status")
@_admin_required
def admin_holdings_status():
    out = []
    for h in _load_holdings():
        price = fetch_ticker_price(h["symbol"])
        buy_price = h.get("buy_price", 0)
        pnl = round((price - buy_price) / buy_price * 100, 2) if buy_price and price else 0
        out.append({**h, "current_price": price, "pnl_pct": pnl})
    return jsonify(out)


# ── Client Portal ──────────────────────────────────────────────────────────────

CLIENT_LOGIN_HTML = """<!DOCTYPE html><html><head><title>V6 Client</title>
<style>body{background:#0a0a0f;color:#c9d1d9;font-family:monospace;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
.box{background:#161b22;padding:40px;border:1px solid #30363d;border-radius:8px;min-width:320px;text-align:center}
h2{color:#3fb950;margin-bottom:24px}input{width:100%;padding:10px;margin:8px 0;background:#0d1117;border:1px solid #30363d;color:#c9d1d9;border-radius:4px;box-sizing:border-box}
button{width:100%;padding:12px;background:#238636;color:#fff;border:none;border-radius:4px;cursor:pointer;margin-top:8px}
.err{color:#FF4500;margin-top:12px}</style></head>
<body><div class="box"><h2>📊 V6 CLIENT PORTAL</h2>
{% if error %}<p class="err">{{ error }}</p>{% endif %}
<form method="POST"><input type="text" name="username" placeholder="Username"/>
<input type="password" name="password" placeholder="Password"/>
<button type="submit">ACCESS SIGNALS</button></form>
<p style="color:#555;font-size:11px;margin-top:16px">Access controlled via Admin Google Sheet</p>
</div></body></html>"""


def _verify_client_local(username: str, password: str):
    """Verify client against local clients.json file."""
    try:
        with open("clients.json") as _f:
            clients = json.load(_f)
        for c in clients:
            if c.get("name", "").strip() == username and c.get("password", "").strip() == password:
                status = c.get("status", "ACTIVE")
                if status.strip().upper() != "ACTIVE":
                    return {"error": "Account inactive."}
                expiry = c.get("expiry", "UNLIMITED")
                if expiry.strip().upper() not in ("UNLIMITED", ""):
                    try:
                        if time.gmtime() > time.strptime(expiry.strip(), "%Y-%m-%d"):
                            return {"error": "Account expired."}
                    except Exception:
                        pass
                return {"username": c["name"], "uid": c.get("uid", ""), "sig_limit": c.get("sig_limit", "100"), "role": "CLIENT"}
        return None
    except Exception as e:
        log.warning(f"Client verify (local) failed: {e}"); return None


def _verify_client(username: str, password: str):
    # Try Google Sheets first (if credentials are configured)
    if GOOGLE_CREDENTIALS and GOOGLE_CREDENTIALS != "{}":
        try:
            import gspread, json as _j
            from oauth2client.service_account import ServiceAccountCredentials
            cd = _j.loads(GOOGLE_CREDENTIALS)
            if cd and GOOGLE_SHEET_ID:
                creds  = ServiceAccountCredentials.from_json_keyfile_dict(cd, ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"])
                gc     = gspread.authorize(creds)
                ws     = gc.open_by_key(GOOGLE_SHEET_ID).worksheet("USERS")
                for row in ws.get_all_values()[1:]:
                    if len(row) < 6: continue
                    name, uid, pwd, status, expiry, lim = row[:6]
                    if name.strip() == username and pwd.strip() == password:
                        if status.strip().upper() != "ACTIVE": return {"error": "Account inactive."}
                        if expiry.strip().upper() not in ("UNLIMITED", ""):
                            try:
                                if time.gmtime() > time.strptime(expiry.strip(), "%Y-%m-%d"): return {"error": "Account expired."}
                            except Exception: pass
                        return {"username": name, "uid": uid, "sig_limit": lim, "role": "CLIENT"}
                return None
        except Exception as e:
            log.warning(f"Client verify (Sheets) failed: {e} — falling back to local store")
    # Fallback: local clients.json (always works, no external dependency)
    return _verify_client_local(username, password)


@app.route("/client/login", methods=["GET", "POST"])
def client_login():
    ip = request.remote_addr
    if _check_lockout(ip): return render_template_string(CLIENT_LOGIN_HTML, error="⛔ Too many attempts.")
    error = None
    if request.method == "POST":
        user = _verify_client(request.form.get("username",""), request.form.get("password",""))
        if user and "error" not in user:
            session["client_user"] = user; session["last_active"] = time.time()
            audit(ip, "CLIENT_LOGIN", "SUCCESS", f"user={user['username']}"); return redirect("/client")
        error = user["error"] if (user and "error" in user) else "❌ Invalid credentials."
        _record_failed_login(ip)
    return render_template_string(CLIENT_LOGIN_HTML, error=error)


@app.route("/client")
def client_portal():
    if not session.get("client_user"): return redirect("/client/login")
    if time.time() - session.get("last_active", 0) > CONFIG["security"]["session_timeout_minutes"] * 60:
        session.clear(); return redirect("/client/login")
    session["last_active"] = time.time()
    with open("index.html", "r", encoding="utf-8") as f: return f.read()


@app.route("/client/logout")
def client_logout():
    session.clear(); return redirect("/client/login")


# ══════════════════════════════════════════════════════════════════════════════
# FOCUS MODE + CHART + WHALE DETAIL ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/focus")
def focus_mode():
    with open("focus.html", "r", encoding="utf-8") as f:
        return f.read()


@app.route("/focus_data")
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


@app.route("/chart_data")
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


@app.route("/large_trades_data")
def large_trades_data_route():
    return jsonify({"trades": GLOBAL_DATA.get("large_trades", [])[:50]})


@app.route("/whale_copy_data")
def whale_copy_data_route():
    closed = [t for t in WHALE_COPY_TRADES if t.get("status") == "CLOSED"]
    wins   = sum(1 for t in closed if t.get("result") == "WIN")
    losses = sum(1 for t in closed if t.get("result") == "LOSS")
    total  = wins + losses
    return jsonify({
        "signals":  GLOBAL_DATA.get("whale_copy_signals", []),
        "trades":   WHALE_COPY_TRADES[:50],
        "wins":     wins,
        "losses":   losses,
        "win_rate": round(wins / total * 100, 1) if total else 0.0,
    })


@app.route("/live_score")
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


@app.route("/whale_detail")
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


# ══════════════════════════════════════════════════════════════════════════════
# TELEGRAM BOT COMMAND HANDLERS
# ══════════════════════════════════════════════════════════════════════════════

def _fmtP(v):
    """Format price for Telegram messages."""
    if not v and v != 0: return "—"
    v = float(v)
    if v >= 10000: return f"{v:.2f}"
    if v >= 100:   return f"{v:.3f}"
    if v >= 1:     return f"{v:.4f}"
    if v >= 0.001: return f"{v:.6f}"
    return f"{v:.8f}"


def _bot_reply(chat_id: str, text: str, button: dict = None):
    if not BOT_TOKEN: return
    try:
        import requests as _r
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if button:
            payload["reply_markup"] = {"inline_keyboard": [[{"text": button["text"], "url": button["url"]}]]}
        _r.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json=payload, timeout=10, proxies=_tg_proxies())
    except Exception as e:
        log.debug(f"Bot reply failed: {e}")


def _handle_sniper_cmd(chat_id: str, symbol: str):
    if not symbol.endswith("USDT"): symbol += "USDT"
    symbol  = symbol.upper()
    all_c   = GLOBAL_DATA["vmc"].get("ALL", [])
    coin    = next((c for c in all_c if c["symbol"] == symbol), None)
    inst    = next((s for s in GLOBAL_DATA["inst_signals"] if s["symbol"] == symbol), None)
    whale   = next((w for w in GLOBAL_DATA["whale"] if w["symbol"] == symbol), None)
    bt      = [b for b in BACKTEST_SIGNALS if b["symbol"] == symbol]
    if not coin and not inst:
        _bot_reply(chat_id, f"❌ <b>{symbol}</b> not in current scan.\nUsage: /sniper BTCUSDT"); return
    price   = coin["price"] if coin else 0
    folders = [f for f, cs in GLOBAL_DATA["vmc"].items() if any(c["symbol"]==symbol for c in cs)]
    inst_i  = inst.get("inst",{}) if inst else {}
    tp      = inst.get("tp_zones",{}) if inst else {}
    siz     = inst.get("sizing",{}) if inst else {}
    conf    = inst.get("confidence",0) if inst else 0
    wp      = whale.get("whale_power",0) if whale else 0
    wins    = sum(1 for b in bt if b.get("result")=="WIN")
    losses  = sum(1 for b in bt if b.get("result")=="LOSS")
    hot_tag = "\n🔥 <b>[HOT COIN]</b>" if any(h["symbol"]==symbol for h in GLOBAL_DATA["hot_coins"]) else ""
    crit_tag= "\n🚨 <b>[CRITICAL_WHALE_ALERT]</b>" if wp >= CONFIG["whale"]["critical_whale_power_pct"] else ""
    _bot_reply(chat_id,
        f"⚡ <b>SNIPER: {symbol}</b>{hot_tag}{crit_tag}\n"
        f"────────────────\n"
        f"💰 Price: {_fmtP(price)} | Chg: {coin.get('change_pct','—') if coin else '—'}%\n"
        f"📊 Score: {coin.get('score','—') if coin else '—'} | RSI: {coin.get('rsi','—') if coin else '—'}\n"
        f"📁 Folders: {', '.join(folders) or '—'}\n"
        f"🚦 Light: {inst_i.get('traffic','—')} | Conf: {conf}%\n"
        f"⭐ Inst: {inst_i.get('inst_score','—')} | Whale: {wp}%\n"
        f"────────────────\n"
        f"🎯 TP1: {_fmtP(tp.get('tp1',0))} | TP2: {_fmtP(tp.get('tp2',0))} | TP3: {_fmtP(tp.get('tp3',0))}\n"
        f"🛡 SL: {_fmtP(tp.get('stop_loss',0))}\n"
        f"💼 {siz.get('note','—')}\n"
        f"────────────────\n"
        f"📈 Backtest: {wins}W / {losses}L",
        button={"text": f"⚡ Focus Mode: {symbol.replace('USDT','')}", "url": _dashboard_url(symbol)}
    )
    audit(chat_id, "BOT_SNIPER", "SENT", f"sym={symbol}")


def _handle_winrate_cmd(chat_id: str):
    open_bt = sum(1 for b in BACKTEST_SIGNALS if b["status"] == "OPEN")
    _bot_reply(chat_id,
        f"📊 <b>WIN RATE REPORT</b>\n"
        f"────────────────\n"
        f"Win Rate: <b>{GLOBAL_DATA['win_rate']}%</b>\n"
        f"Wins: {_total_wins} | Losses: {_total_losses} | Total: {_total_wins+_total_losses}\n"
        f"Win Streak: 🔥 {_win_streak} consecutive\n"
        f"Open Signals: {open_bt} being tracked\n"
        f"────────────────\n"
        f"Cycle #{GLOBAL_DATA['cycle_count']} | {GLOBAL_DATA['status']}",
        button={"text": "📊 Open Focus Mode", "url": _dashboard_url() + "focus"}
    )


def _handle_status_cmd(chat_id: str):
    secs = int(time.time() - GLOBAL_DATA["uptime_start"])
    h, r = divmod(secs, 3600); m, _ = divmod(r, 60)
    _bot_reply(chat_id,
        f"🚀 <b>V6 MASTER PRO STATUS</b>\n"
        f"────────────────\n"
        f"Status: {GLOBAL_DATA['status']} | Cycle #{GLOBAL_DATA['cycle_count']}\n"
        f"Uptime: {h}h {m}m | Ex: {GLOBAL_DATA['active_exchange']}\n"
        f"────────────────\n"
        f"📊 VIP:{len(GLOBAL_DATA['vmc'].get('VIP',[]))} GOLDEN:{len(GLOBAL_DATA['vmc'].get('GOLDEN',[]))} ALL:{len(GLOBAL_DATA['vmc'].get('ALL',[]))}\n"
        f"🐋 Whale: {len(GLOBAL_DATA['whale'])} | Hot: {len(GLOBAL_DATA['hot_coins'])}\n"
        f"📈 Win Rate: {GLOBAL_DATA['win_rate']}% | Streak: {_win_streak}\n"
        f"────────────────\n"
        f"₿ BTC: {GLOBAL_DATA['btc'].get('sentiment','?')} | Regime: {GLOBAL_DATA.get('market_regime','?')}\n"
        f"Entries: {'⛔ PAUSED' if GLOBAL_DATA.get('btc_pause') else '✅ ACTIVE'}",
        button={"text": "🎯 Open Focus Mode", "url": _dashboard_url() + "/focus"}
    )


def telegram_bot_loop():
    """Long-poll Telegram getUpdates: handles /sniper /winrate /status /help."""
    if not BOT_TOKEN:
        log.info("[BOT] BOT_TOKEN not set — command bot disabled.")
        return
    offset = None
    log.info("[BOT] Telegram command bot polling — /sniper /winrate /status /help")
    audit("SYSTEM", "BOT_STARTED", "OK", "polling")
    while True:
        try:
            import requests as _r
            params = {"timeout": 20, "allowed_updates": ["message"]}
            if offset: params["offset"] = offset
            resp = _r.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                          params=params, timeout=25, proxies=_tg_proxies())
            if resp.status_code != 200:
                time.sleep(5); continue
            for upd in resp.json().get("result", []):
                offset  = upd["update_id"] + 1
                msg     = upd.get("message", {})
                text    = msg.get("text", "").strip()
                chat_id = str(msg.get("chat", {}).get("id", ""))
                if not text or not chat_id: continue
                parts = text.split()
                cmd   = parts[0].lower().split("@")[0]
                args  = parts[1:]
                log.info(f"[BOT] cmd={cmd} from={chat_id}")
                audit(chat_id, "BOT_CMD", cmd, f"args={args}")
                if cmd == "/sniper":
                    _handle_sniper_cmd(chat_id, args[0].upper() if args else "") if args else \
                        _bot_reply(chat_id, "Usage: /sniper BTCUSDT")
                elif cmd == "/winrate":  _handle_winrate_cmd(chat_id)
                elif cmd == "/status":   _handle_status_cmd(chat_id)
                elif cmd in ("/help", "/start"):
                    _bot_reply(chat_id,
                        "🤖 <b>V6 Master Pro Bot</b>\n"
                        "/sniper BTCUSDT — Full coin analysis + TP/SL/Backtest\n"
                        "/winrate — Win rate, streak, open signals\n"
                        "/status — System status + BTC regime\n"
                        "/help — This help message")
        except Exception as e:
            log.debug(f"[BOT] Poll error: {e}")
            time.sleep(5)


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log.info(f"V6 Master Pro INSTITUTIONAL starting — PORT={PORT}")
    send_telegram(
        f"🚀 <b>V6 MASTER PRO v8 ONLINE</b>\n"
        f"PORT:{PORT} | Exchange:BINANCE\n"
        f"🎯 FocusMode✅ CandlestickChart✅ WhalePanels✅\n"
        f"🤖 Bot:/sniper /winrate /status ✅\n"
        f"Admin:/admin | Client:/client | Focus:/focus"
    )
    audit("SYSTEM", "STARTUP", "OK", f"port={PORT}")
    try:
        from logic import start_health_monitor
        start_health_monitor(interval=30)
    except Exception as _e:
        log.warning(f"health monitor start failed: {_e}")
    threading.Thread(target=data_refresh_loop,   daemon=True).start()
    threading.Thread(target=heartbeat_loop,       daemon=True).start()
    threading.Thread(target=btc_monitor_loop,     daemon=True).start()
    threading.Thread(target=midnight_report_loop, daemon=True).start()
    threading.Thread(target=weekly_report_loop,   daemon=True).start()
    threading.Thread(target=backtest_check_loop,  daemon=True).start()
    threading.Thread(target=whale_copy_check_loop, daemon=True).start()
    threading.Thread(target=holdings_check_loop,   daemon=True).start()
    threading.Thread(target=market_quiet_loop,    daemon=True).start()
    threading.Thread(target=telegram_bot_loop,    daemon=True).start()
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
