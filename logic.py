"""
logic.py — V6 Master Pro Institutional Engine
VMC • Whale Wall • OBI • ATR • Traffic Light • Institutional Score
VWAP • RSI Divergence • Regime Detection • Confidence Score
All thresholds in config.json — no hardcoded values.
"""
import time
import os

def _tg_proxies():
    p = os.getenv("TELEGRAM_PROXY")
    return {"http": p, "https": p} if p else None

import logging
import threading
import requests
from requests.adapters import HTTPAdapter
try:
    from urllib3.util.retry import Retry
except Exception:
    from requests.packages.urllib3.util.retry import Retry  # type: ignore

from scoring_engine import calculate_54_point_score

log = logging.getLogger(__name__)

# ── Binance hosts — data-api.binance.vision first (not geo-blocked on Render US)
BINANCE_HOSTS = [
    "https://data-api.binance.vision",
    "https://api-gcp.binance.com",
    "https://api3.binance.com",
    "https://api4.binance.com",
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
]
BINANCE_BASE = BINANCE_HOSTS[4] + "/api/v3"   # kept for backward-compat references


def _build_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3, connect=3, read=2, backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({"User-Agent": "V6MasterPro/1.0"})
    return s


_SESSION = _build_session()
_RETRYABLE_STATUS = {429, 451, 500, 502, 503, 504}

_health_lock = threading.Lock()
_monitor_started = False
_BINANCE_HEALTH = {
    "reachable":   False,
    "last_ok":     None,
    "last_error":  "",
    "active_host": BINANCE_HOSTS[0],
}


def _mark_health(ok: bool, host: str = "", error: str = "") -> None:
    with _health_lock:
        _BINANCE_HEALTH["reachable"] = ok
        if ok:
            _BINANCE_HEALTH["last_ok"]     = time.strftime("%Y-%m-%d %H:%M:%S")
            _BINANCE_HEALTH["active_host"] = host
            _BINANCE_HEALTH["last_error"]  = ""
        else:
            _BINANCE_HEALTH["last_error"]  = error


def get_binance_health() -> dict:
    with _health_lock:
        return dict(_BINANCE_HEALTH)


def _binance_get(path: str, params: dict = None, timeout: int = 10):
    """GET with automatic host failover. 451/5xx triggers next host.
    NOTE: intentionally NOT using TELEGRAM_PROXY here — that variable is
    scoped to Telegram API calls only. Routing Binance traffic through a
    Telegram proxy (often a slow/free/dead SOCKS5) breaks market data
    entirely, which is what happened when TELEGRAM_PROXY was first set."""
    last_err = ""
    for host in BINANCE_HOSTS:
        try:
            resp = _SESSION.get(host + path, params=params, timeout=timeout)
        except requests.exceptions.RequestException as e:
            last_err = f"{type(e).__name__}: {e}"
            log.warning(f"[BINANCE] {host} unreachable ({last_err}); trying next host…")
            continue
        if resp.status_code in _RETRYABLE_STATUS:
            last_err = f"HTTP {resp.status_code} from {host}"
            log.warning(f"[BINANCE] {host} returned {resp.status_code}; trying next host…")
            continue
        _mark_health(True, host=host)
        return resp
    _mark_health(False, error=last_err)
    log.error(f"[BINANCE] All hosts unreachable. Last error: {last_err}")
    return None


def ping_binance(timeout: int = 6) -> bool:
    resp = _binance_get("/api/v3/ping", timeout=timeout)
    return bool(resp is not None and resp.status_code == 200)


def start_health_monitor(interval: int = 30) -> None:
    global _monitor_started
    with _health_lock:
        if _monitor_started:
            return
        _monitor_started = True

    def _loop():
        while True:
            try:
                ping_binance()
            except Exception as e:
                log.debug(f"health monitor ping error: {e}")
            time.sleep(interval)

    threading.Thread(target=_loop, daemon=True, name="binance-health").start()
    log.info(f"[HEALTH] Binance connectivity monitor started (every {interval}s)")


_obi_history: dict = {}


# ══════════════════════════════════════════════════════════════════════════════
# DATA LAYER
# ══════════════════════════════════════════════════════════════════════════════

def fetch_all_tickers(config: dict) -> list:
    quote   = config["scanner"]["quote_asset"]
    min_vol = config["scanner"]["min_quote_volume_24h"]
    limit   = config["scanner"]["coins_limit"]
    resp = _binance_get("/api/v3/ticker/24hr", timeout=15)
    if resp is None:
        log.error("fetch_all_tickers: all Binance hosts unreachable")
        return []
    resp.raise_for_status()
    filtered = [
        t for t in resp.json()
        if t["symbol"].endswith(quote) and float(t["quoteVolume"]) >= min_vol
    ]
    filtered.sort(key=lambda x: float(x["quoteVolume"]), reverse=True)
    log.info(f"Binance: {len(filtered)} USDT pairs above min volume.")
    return filtered[:limit]


def fetch_ticker_price(symbol: str) -> float:
    try:
        resp = _binance_get("/api/v3/ticker/price", params={"symbol": symbol}, timeout=5)
        if resp is not None and resp.status_code == 200:
            return float(resp.json()["price"])
    except Exception as e:
        log.debug(f"Price fetch failed for {symbol}: {e}")
    return 0.0


def fetch_ticker_24h(symbol: str) -> dict:
    """24hr ticker stats for one symbol — used by live on-demand scoring
    (SNIPER search box) for coins outside the pre-enriched top-20 list."""
    try:
        resp = _binance_get("/api/v3/ticker/24hr", params={"symbol": symbol}, timeout=8)
        if resp is not None and resp.status_code == 200:
            return resp.json()
    except Exception as e:
        log.debug(f"24hr ticker fetch failed for {symbol}: {e}")
    return {}


def calculate_rsi(closes: list, period: int = 14) -> float:
    """Wilder's RSI: initial simple-average seed over the first `period`
    deltas, then recursively smoothed over every remaining delta — matches
    the standard RSI formula (not a plain last-N-candle average)."""
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains  = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]
    avg_g  = sum(gains[:period]) / period
    avg_l  = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    if avg_l == 0:
        return 100.0
    return round(100.0 - (100.0 / (1 + avg_g / avg_l)), 2)


def fetch_klines(symbol: str, interval: str = "1h", limit: int = 24) -> list:
    try:
        resp = _binance_get(
            "/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=8,
        )
        return resp.json() if (resp is not None and resp.status_code == 200) else []
    except Exception as e:
        log.debug(f"Klines failed for {symbol}: {e}")
        return []


def fetch_rsi_for_symbol(symbol: str, interval: str = "1h", limit: int = 20) -> float:
    klines = fetch_klines(symbol, interval, limit)
    if not klines:
        return 50.0
    return calculate_rsi([float(k[4]) for k in klines])


def calculate_atr(symbol: str, interval: str = "1h", period: int = 14) -> float:
    """Wilder's ATR: simple-average seed over the first `period` true
    ranges, then recursively smoothed — matches the standard ATR formula.
    Fetches period*3 candles (was period+5) so the smoothing has enough
    history to actually converge instead of just averaging the last window."""
    try:
        klines = fetch_klines(symbol, interval, period * 3)
        if len(klines) < period + 1:
            return 0.0
        trs = []
        for i in range(1, len(klines)):
            high = float(klines[i][2]); low = float(klines[i][3])
            close_prev = float(klines[i - 1][4])
            trs.append(max(high - low, abs(high - close_prev), abs(low - close_prev)))
        atr = sum(trs[:period]) / period
        for i in range(period, len(trs)):
            atr = (atr * (period - 1) + trs[i]) / period
        return round(atr, 8)
    except Exception:
        return 0.0


def compute_vwap(symbol: str, interval: str = "1h", limit: int = 24) -> float:
    try:
        klines = fetch_klines(symbol, interval, limit)
        if not klines:
            return 0.0
        total_pv = sum((float(k[2]) + float(k[3]) + float(k[4])) / 3 * float(k[5]) for k in klines)
        total_v  = sum(float(k[5]) for k in klines)
        return round(total_pv / total_v, 8) if total_v else 0.0
    except Exception:
        return 0.0


def _ema(values: list, period: int) -> list:
    if not values:
        return []
    k = 2.0 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def calculate_macd(closes: list, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    if len(closes) < slow + signal:
        return {"macd": 0.0, "signal": 0.0, "hist": 0.0}
    ema_fast    = _ema(closes, fast)
    ema_slow    = _ema(closes, slow)
    macd_line   = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = _ema(macd_line, signal)
    hist        = macd_line[-1] - signal_line[-1]
    return {"macd": round(macd_line[-1], 8),
            "signal": round(signal_line[-1], 8),
            "hist": round(hist, 8)}


def fetch_macd_for_symbol(symbol: str, interval: str = "1h", limit: int = 60) -> dict:
    klines = fetch_klines(symbol, interval, limit)
    if not klines:
        return {"macd": 0.0, "signal": 0.0, "hist": 0.0}
    return calculate_macd([float(k[4]) for k in klines])


# ══════════════════════════════════════════════════════════════════════════════
# V6 FINAL SCORE — 54-POINT
# ══════════════════════════════════════════════════════════════════════════════

def compute_v6_final_score(signal: dict, regime: str, btc_volatility_pct: float,
                           divergence_signal: str, in_volume_surge: bool) -> dict:
    inst      = signal.get("inst", {}) or {}
    tp        = signal.get("tp_zones", {}) or {}
    rsi       = signal.get("rsi", 50) or 50
    chg       = signal.get("change_pct", 0) or 0
    price     = signal.get("price", 0) or 0
    macd_hist = signal.get("macd_hist", 0) or 0

    # 1 — Market Regime (10)
    reg_trend = {"TRENDING": 3, "RANGING": 2, "VOLATILE": 1}.get(regime, 2)
    reg_trend += 2 if chg > 0.5 else 1 if chg >= -0.5 else 0
    reg_trend  = min(5, reg_trend)
    v          = abs(btc_volatility_pct or 0)
    reg_vol    = 5 if v < 2 else 3 if v < 4 else 2 if v < 6 else 1
    market_regime = reg_trend + reg_vol

    # 2 — Institutional/Whale (12)
    inst_score  = inst.get("inst_score", 0) or 0
    whale_power = inst.get("whale_power", 0) or 0
    inst_whale  = (inst_score / 100 * 6) + (whale_power / 100 * 6)

    # 3 — Technical (12)
    if 40 <= rsi <= 55:             rsi_pts = 4
    elif 55 < rsi <= 62 or 35 <= rsi < 40: rsi_pts = 3
    elif 30 <= rsi < 35:            rsi_pts = 2
    elif rsi > 70 or rsi < 25:      rsi_pts = 0
    else:                           rsi_pts = 1
    macd_rel = (macd_hist / price * 100) if price else 0
    if macd_rel > 0.05:    macd_pts = 4
    elif macd_rel > 0:     macd_pts = 3
    elif macd_rel == 0:    macd_pts = 2
    elif macd_rel > -0.05: macd_pts = 1
    else:                  macd_pts = 0
    vol_pts   = 4 if in_volume_surge else 1
    technical = rsi_pts + macd_pts + vol_pts

    # 4 — Smart Money Divergence (10)
    ofi = inst.get("ofi_score", 50) or 50
    if divergence_signal == "ACCUMULATION":   div_pts = 4
    elif divergence_signal == "DISTRIBUTION": div_pts = 0
    else:                                     div_pts = 2
    smart_divergence = (ofi / 100 * 6) + div_pts

    # 5 — Trade Engine (10)
    entry  = tp.get("entry_low") or price
    sl     = tp.get("stop_loss") or 0
    tp1    = tp.get("tp1") or 0
    risk   = entry - sl
    reward = tp1 - entry
    rr     = reward / risk if risk > 0 else 0
    if rr >= 2:    rr_pts = 5
    elif rr >= 1.5: rr_pts = 4
    elif rr >= 1:  rr_pts = 3
    elif rr > 0:   rr_pts = 1
    else:          rr_pts = 0
    traffic     = inst.get("traffic", "RED")
    tr_pts      = 5 if traffic == "GREEN" else 2 if traffic == "YELLOW" else 0
    trade_engine = rr_pts + tr_pts

    raw   = market_regime + inst_whale + technical + smart_divergence + trade_engine
    score = max(0, min(100, round(raw / 54 * 100)))
    if score >= 68:   label, badge = "BUY",   "badge-buy"
    elif score >= 45: label, badge = "WAIT",  "badge-wait"
    else:             label, badge = "AVOID", "badge-avoid"

    return {
        "score": score, "raw": round(raw, 1), "rr": round(rr, 2),
        "label": label, "badge": badge,
        "breakdown": {
            "market_regime":    round(market_regime, 1),
            "inst_whale":       round(inst_whale, 1),
            "technical":        round(technical, 1),
            "smart_divergence": round(smart_divergence, 1),
            "trade_engine":     round(trade_engine, 1),
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# HISTORICAL BACKTESTER
# ══════════════════════════════════════════════════════════════════════════════

def fetch_klines_range(symbol: str, interval: str, start_ms: int, end_ms: int) -> list:
    out: list = []
    cursor = start_ms
    guard  = 0
    while cursor < end_ms and guard < 60:
        guard += 1
        resp = _binance_get("/api/v3/klines", params={
            "symbol": symbol, "interval": interval,
            "startTime": cursor, "endTime": end_ms, "limit": 1000,
        }, timeout=10)
        if resp is None or resp.status_code != 200:
            break
        batch = resp.json()
        if not batch:
            break
        out.extend(batch)
        last_open = int(batch[-1][0])
        nxt = last_open + 1
        if nxt <= cursor:
            break
        cursor = nxt
        if len(batch) < 1000:
            break
    return out


def _rsi_series(closes: list, period: int = 14) -> list:
    """Wilder's RSI computed once across the whole series (recursive
    smoothing), not by re-seeding a fresh average on every window slice."""
    n = len(closes)
    rsis = [50.0] * n
    if n <= period:
        return rsis
    deltas = [closes[i] - closes[i - 1] for i in range(1, n)]
    gains  = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    rsis[period] = 100.0 if avg_l == 0 else round(100.0 - 100.0 / (1 + avg_g / avg_l), 2)
    for i in range(period + 1, n):
        avg_g = (avg_g * (period - 1) + gains[i - 1]) / period
        avg_l = (avg_l * (period - 1) + losses[i - 1]) / period
        rsis[i] = 100.0 if avg_l == 0 else round(100.0 - 100.0 / (1 + avg_g / avg_l), 2)
    return rsis


def _atr_series(highs: list, lows: list, closes: list, period: int = 14) -> list:
    """Wilder's ATR computed once across the whole series (recursive
    smoothing), not a rolling simple average of the last `period` bars."""
    n = len(closes)
    trs = [0.0] * n
    for i in range(1, n):
        trs[i] = max(highs[i] - lows[i],
                     abs(highs[i] - closes[i - 1]),
                     abs(lows[i] - closes[i - 1]))
    atrs = [0.0] * n
    if n > period:
        atrs[period] = sum(trs[1:period + 1]) / period
        for i in range(period + 1, n):
            atrs[i] = (atrs[i - 1] * (period - 1) + trs[i]) / period
    return atrs


def _ema_series(values: list, period: int) -> list:
    if not values:
        return []
    k = 2 / (period + 1)
    ema = [values[0]]
    for v in values[1:]:
        ema.append(v * k + ema[-1] * (1 - k))
    return ema


def historical_backtest(symbols: list, months: int = 3, interval: str = "1h",
                        config: dict = None) -> dict:
    cfg      = config or {}
    tm       = cfg.get("trade_management", {})
    risk     = cfg.get("risk", {})
    vmc      = cfg.get("vmc", {})
    inst     = cfg.get("institutional", {})
    months   = max(1, min(int(months or 3), 6))
    rsi_lo   = float(vmc.get("rsi_oversold", 38))
    sl_mult  = float(inst.get("atr_stop_loss_multiplier", 1.5))
    tp1_m    = float(inst.get("tp1_atr_multiplier", 1.5))
    tp2_m    = float(inst.get("tp2_atr_multiplier", 3.0))
    tp3_m    = float(inst.get("tp3_atr_multiplier", 5.0))
    risk_pct = float(risk.get("green_signal_max_pct", 5.0))
    balance0 = float(risk.get("account_balance_usdt", 1000))
    max_dl   = int(tm.get("daily_max_losses", 5))
    trail_on = bool(tm.get("trailing_stop_enabled", True))
    be_tp1   = bool(tm.get("breakeven_on_tp1", True))
    trail_t2 = bool(tm.get("trail_to_tp1_on_tp2", True))
    now_ms   = int(time.time() * 1000)
    start_ms = now_ms - months * 30 * 24 * 3600 * 1000
    timeout_bars = 48

    btc_trend = {}
    btc_raw   = fetch_klines_range("BTCUSDT", interval, start_ms, now_ms)
    if btc_raw:
        b_close = [float(k[4]) for k in btc_raw]
        b_ema   = _ema_series(b_close, 50)
        for idx, k in enumerate(btc_raw):
            btc_trend[int(k[0])] = b_close[idx] > b_ema[idx]

    all_trades: list = []
    per_symbol: dict = {}

    for sym in symbols:
        kl = fetch_klines_range(sym, interval, start_ms, now_ms)
        if len(kl) < 60:
            per_symbol[sym] = {"trades": 0, "note": "insufficient history"}
            continue
        opens  = [int(k[0])   for k in kl]
        highs  = [float(k[2]) for k in kl]
        lows   = [float(k[3]) for k in kl]
        closes = [float(k[4]) for k in kl]
        rsi    = _rsi_series(closes, 14)
        atr    = _atr_series(highs, lows, closes, 14)
        ema50  = _ema_series(closes, 50)
        pos = None
        sym_trades = 0
        for i in range(55, len(closes)):
            if pos is None:
                trend_up = closes[i] > ema50[i]
                pullback = (rsi_lo - 8) <= rsi[i] <= (rsi_lo + 7)
                btc_ok   = btc_trend.get(opens[i], True)
                if trend_up and pullback and btc_ok and atr[i] > 0:
                    e = closes[i]; a = atr[i]
                    pos = {
                        "entry_i": i, "entry_price": e,
                        "entry_time": time.strftime("%Y-%m-%d %H:%M", time.gmtime(opens[i] / 1000)),
                        "sl":  e - sl_mult * a, "tp1": e + tp1_m * a,
                        "tp2": e + tp2_m * a,   "tp3": e + tp3_m * a,
                        "tp1_hit": False, "tp2_hit": False, "tp3_hit": False, "trailing": "",
                    }
                continue
            h, l, c = highs[i], lows[i], closes[i]
            sl_at_open = pos["sl"]
            exit_price = None; exit_reason = ""
            if l <= sl_at_open:
                exit_price = sl_at_open
                exit_reason = "TRAIL-STOP" if pos["trailing"] else "STOP-LOSS"
            else:
                if pos["tp1"] and h >= pos["tp1"]: pos["tp1_hit"] = True
                if pos["tp2"] and h >= pos["tp2"]: pos["tp2_hit"] = True
                if pos["tp3"] and h >= pos["tp3"]: pos["tp3_hit"] = True
                if trail_on:
                    if pos["tp2_hit"] and trail_t2 and pos["sl"] < pos["tp1"]:
                        pos["sl"] = pos["tp1"]; pos["trailing"] = "TP1"
                    elif pos["tp1_hit"] and be_tp1 and pos["sl"] < pos["entry_price"]:
                        pos["sl"] = pos["entry_price"]; pos["trailing"] = "BREAKEVEN"
                if pos["tp3_hit"]:
                    exit_price = pos["tp3"]; exit_reason = "TP3"
                elif (i - pos["entry_i"]) >= timeout_bars:
                    exit_price = c; exit_reason = "TIMEOUT"
            if exit_price is not None:
                pnl = (exit_price - pos["entry_price"]) / pos["entry_price"] * 100
                pnl -= 0.001 * 2 * 100   # Binance spot fee, 0.1% per side
                all_trades.append({
                    "symbol": sym,
                    "entry_time": pos["entry_time"],
                    "exit_time": time.strftime("%Y-%m-%d %H:%M", time.gmtime(opens[i] / 1000)),
                    "exit_ts": opens[i],
                    "entry_price": round(pos["entry_price"], 8),
                    "exit_price": round(exit_price, 8),
                    "pnl_pct": round(pnl, 3),
                    "exit_reason": exit_reason,
                    "trailing": pos["trailing"] or "—",
                    "bars_held": i - pos["entry_i"],
                })
                sym_trades += 1; pos = None
        per_symbol[sym] = {"trades": sym_trades}

    max_dd_pct = float(tm.get("daily_max_drawdown_pct", 10.0))
    all_trades.sort(key=lambda t: t["exit_ts"])
    equity = balance0; peak = balance0; max_dd = 0.0
    gross_p = 0.0; gross_l = 0.0; wins = 0; losses = 0; counted = 0; skipped = 0
    daily_losses: dict = {}; daily_start_eq: dict = {}
    curve = [{"t": time.strftime("%Y-%m-%d", time.gmtime(start_ms / 1000)), "equity": round(equity, 2)}]
    for tr in all_trades:
        day = tr["exit_time"][:10]
        day_open_eq = daily_start_eq.setdefault(day, equity)
        day_dd = (day_open_eq - equity) / day_open_eq * 100.0 if day_open_eq else 0.0
        if daily_losses.get(day, 0) >= max_dl or day_dd >= max_dd_pct:
            tr["counted"] = False; skipped += 1; continue
        size = equity * risk_pct / 100.0
        pnl_usdt = size * tr["pnl_pct"] / 100.0
        equity += pnl_usdt; counted += 1
        tr["counted"] = True; tr["equity_after"] = round(equity, 2)
        if tr["pnl_pct"] > 0:
            wins += 1; gross_p += pnl_usdt
        else:
            losses += 1; gross_l += abs(pnl_usdt)
            daily_losses[day] = daily_losses.get(day, 0) + 1
        peak = max(peak, equity)
        if peak > 0: max_dd = max(max_dd, (peak - equity) / peak * 100.0)
        curve.append({"t": tr["exit_time"], "equity": round(equity, 2)})

    win_rate      = round(wins / counted * 100, 1) if counted else 0.0
    profit_factor = round(gross_p / gross_l, 2) if gross_l > 0 else (float("inf") if gross_p > 0 else 0.0)
    net_return    = round((equity - balance0) / balance0 * 100, 2) if balance0 else 0.0

    return {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "symbols": symbols, "months": months, "interval": interval,
        "start": time.strftime("%Y-%m-%d", time.gmtime(start_ms / 1000)),
        "end":   time.strftime("%Y-%m-%d", time.gmtime(now_ms / 1000)),
        "total_trades": counted, "skipped_by_circuit_breaker": skipped,
        "wins": wins, "losses": losses, "win_rate": win_rate,
        "profit_factor": (round(profit_factor, 2) if profit_factor != float("inf") else 999.0),
        "max_drawdown_pct": round(max_dd, 2), "net_return_pct": net_return,
        "start_equity": round(balance0, 2), "end_equity": round(equity, 2),
        "equity_curve": curve, "per_symbol": per_symbol, "trades": all_trades,
        "note": ("Technical + risk-management core. Order-book/whale layers excluded."),
    }


def detect_rsi_divergence(klines: list) -> str:
    if len(klines) < 20:
        return "NONE"
    try:
        closes = [float(k[4]) for k in klines]
        mid    = len(closes) // 2
        rsi_e  = calculate_rsi(closes[:mid + 14])
        rsi_l  = calculate_rsi(closes)
        p_e    = closes[mid - 1]; p_l = closes[-1]
        if p_l < p_e and rsi_l > rsi_e: return "BULLISH_DIV"
        if p_l > p_e and rsi_l < rsi_e: return "BEARISH_DIV"
        return "NONE"
    except Exception:
        return "NONE"


def detect_market_regime(btc_volatility_pct: float, btc_change_pct: float) -> str:
    if abs(btc_volatility_pct) > 4.0 or abs(btc_change_pct) > 3.0: return "VOLATILE"
    if abs(btc_change_pct) > 1.5: return "TRENDING"
    return "RANGING"


def price_position_rsi(ticker: dict) -> float:
    try:
        high = float(ticker["highPrice"]); low = float(ticker["lowPrice"])
        last = float(ticker["lastPrice"])
        if high == low: return 50.0
        return round(20.0 + (last - low) / (high - low) * 100 * 0.6, 2)
    except Exception:
        return 50.0


# ══════════════════════════════════════════════════════════════════════════════
# ORDER BOOK IMBALANCE ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def calculate_obi(book: dict) -> float:
    try:
        bid_vol = sum(float(b[0]) * float(b[1]) for b in book.get("bids", []))
        ask_vol = sum(float(a[0]) * float(a[1]) for a in book.get("asks", []))
        total   = bid_vol + ask_vol
        return round((bid_vol - ask_vol) / total, 4) if total else 0.0
    except Exception:
        return 0.0


def detect_obi_spike(symbol: str, current_obi: float, config: dict) -> dict:
    hist_size = config["institutional"]["obi_history_size"]
    threshold = config["institutional"]["obi_spike_threshold"]
    history   = _obi_history.setdefault(symbol, [])
    now       = time.time()
    history.append((now, current_obi))
    _obi_history[symbol] = [(t, v) for t, v in history if now - t < 300][-hist_size:]
    if len(_obi_history[symbol]) < 3:
        return {"spike": False, "velocity": 0.0, "obi": current_obi}
    vals  = [v for _, v in _obi_history[symbol]]
    avg   = sum(vals[:-1]) / len(vals[:-1])
    std   = (sum((v - avg) ** 2 for v in vals[:-1]) / len(vals[:-1])) ** 0.5
    vel   = abs(current_obi - avg) / std if std else 0.0
    return {
        "spike": vel >= threshold, "velocity": round(vel, 3), "obi": current_obi,
        "direction": "BUY_PRESSURE" if current_obi > 0 else "SELL_PRESSURE",
    }


# ══════════════════════════════════════════════════════════════════════════════
# INSTITUTIONAL SCORE & CONFIDENCE
# ══════════════════════════════════════════════════════════════════════════════

def compute_whale_power(walls: list, spoofing: dict, blink_to_push: bool,
                        price: float, config: dict) -> float:
    score = 0.0
    bonus_thresh = config["institutional"]["wall_proximity_bonus_threshold"]
    if walls:
        min_dist = min(w["dist_pct"] for w in walls)
        score += 40 if min_dist <= bonus_thresh else 30 if min_dist <= 1.0 else 20 if min_dist <= 2.0 else 10
    if spoofing.get("bid_spoof") or spoofing.get("ask_spoof"):
        score += 30
    if blink_to_push:
        score += 30
    return min(round(score, 1), 100.0)


def compute_institutional_score(vmc_score: int, whale_power: float,
                                 ofi_result: dict, walls: list, config: dict) -> dict:
    """
    FIX: Removed the broken calculate_54_point_score() call that used
    undefined variables via 'x in dir()' — that block always passed empty
    values and caused score to be 0. The real 54-point scoring is now called
    correctly in data_refresh_loop via compute_v6_final_score().
    """
    cfg          = config["institutional"]
    bonus_thresh = cfg["wall_proximity_bonus_threshold"]
    ofi_score    = max(0.0, min(100.0, (ofi_result.get("obi", 0) + 1) * 50))
    base         = (whale_power * cfg["whale_power_weight"]) + \
                   (vmc_score   * cfg["vmc_score_weight"])   + \
                   (ofi_score   * cfg["ofi_weight"])
    wall_bonus   = base * cfg["wall_proximity_bonus_pct"] \
                   if (walls and min(w["dist_pct"] for w in walls) <= bonus_thresh) else 0.0
    final        = min(round(base + wall_bonus, 1), 100.0)

    vmc_bullish   = vmc_score >= 70
    ofi_momentum  = ofi_result.get("obi", 0) > 0.1
    wall_proximal = bool(walls and min(w["dist_pct"] for w in walls) <= bonus_thresh)
    confirms      = sum([vmc_bullish, ofi_momentum, wall_proximal])

    critical = config["whale"]["critical_whale_power_pct"]
    yellow   = cfg["yellow_light_whale_power"]

    if whale_power >= critical and confirms >= cfg["spike_confirm_threshold"]:
        light, reason, spike = "GREEN",  f"SPIKE_CONFIRMED: wp={whale_power}% confirms={confirms}/3", True
    elif whale_power >= yellow or (whale_power >= critical and confirms < cfg["spike_confirm_threshold"]):
        light, reason, spike = "YELLOW", f"OBSERVE: wp={whale_power}% confirms={confirms}/3", False
    elif final >= 70:
        light, reason, spike = "GREEN",  f"ALL_CRITERIA_MET: score={final}", False
    else:
        light, reason, spike = "RED",    f"INSUFFICIENT: score={final}", False

    return {
        "inst_score": final, "whale_power": whale_power, "ofi_score": round(ofi_score, 1),
        "vmc_score": vmc_score, "traffic": light, "spike": spike,
        "confirms": confirms, "reason": reason,
    }


def compute_confidence_score(inst_result: dict, obi_result: dict, vmc_score: int) -> int:
    score = 0
    tl    = inst_result.get("traffic", "RED")
    score += 35 if tl == "GREEN" else 17 if tl == "YELLOW" else 0
    score += min(24, inst_result.get("confirms", 0) * 8)
    if obi_result and obi_result.get("spike"): score += 15
    score += min(16, int(vmc_score / 100 * 16))
    score += min(10, int(inst_result.get("whale_power", 0) / 100 * 10))
    return min(100, max(0, score))


def estimate_time_to_target(price: float, target: float, atr: float, interval_hours: float = 1.0) -> dict:
    """
    ATR-based ESTIMATE (not a prediction) of how long price might take to
    travel from `price` to `target`, assuming it keeps moving at its recent
    average per-candle range. Always shown/labelled as an estimate.
    """
    if not atr or atr <= 0 or not price:
        return {"bars": 0, "hours": 0, "label": "—"}
    distance = abs(target - price)
    bars  = distance / atr
    hours = round(bars * interval_hours, 1)
    if hours < 1:
        label = f"~{max(5, int(hours * 60))}min (scalp)"
    elif hours < 24:
        label = f"~{round(hours, 1)}h"
    else:
        label = f"~{round(hours / 24, 1)}d"
    return {"bars": round(bars, 1), "hours": hours, "label": label}


def compute_tp_levels(price: float, atr: float, config: dict) -> dict:
    if atr == 0:
        return {"entry_low": price, "entry_high": price, "stop_loss": price,
                "tp1": price, "tp2": price, "tp3": price, "atr": 0, "risk_pct": 0, "rr": 0,
                "eta_tp1": "—"}
    cfg = config["institutional"]
    entry_low = round(price - 0.3 * atr, 8)
    stop_loss = round(price - cfg["atr_stop_loss_multiplier"] * atr, 8)
    tp1       = round(price + cfg["tp1_atr_multiplier"] * atr, 8)
    risk   = entry_low - stop_loss
    reward = tp1 - entry_low
    rr     = round(reward / risk, 2) if risk > 0 else 0
    eta    = estimate_time_to_target(price, tp1, atr)
    return {
        "atr":        round(atr, 8),
        "entry_low":  entry_low,
        "entry_high": round(price + 0.3 * atr, 8),
        "stop_loss":  stop_loss,
        "tp1":        tp1,
        "tp2":        round(price + cfg["tp2_atr_multiplier"] * atr, 8),
        "tp3":        round(price + cfg["tp3_atr_multiplier"] * atr, 8),
        "risk_pct":   round(cfg["atr_stop_loss_multiplier"] * atr / price * 100, 3),
        "rr":         rr,
        "eta_tp1":    eta["label"],
    }


def compute_position_size(inst_score_result: dict, config: dict) -> dict:
    risk_cfg = config["risk"]
    balance  = risk_cfg["account_balance_usdt"]
    light    = inst_score_result.get("traffic", "RED")
    if light == "GREEN":
        pct, usdt, note = risk_cfg["green_signal_max_pct"], \
                          round(balance * risk_cfg["green_signal_max_pct"] / 100, 2), \
                          f"GREEN — {risk_cfg['green_signal_max_pct']}% of balance"
    elif light == "YELLOW":
        pct, usdt, note = risk_cfg["yellow_signal_max_pct"], \
                          round(balance * risk_cfg["yellow_signal_max_pct"] / 100, 2), \
                          "YELLOW — minimal (25% of GREEN)"
    else:
        pct, usdt, note = 0.0, 0.0, "RED — no trade"
    return {"light": light, "alloc_pct": pct, "alloc_usdt": usdt,
            "balance": balance, "note": note}


# ══════════════════════════════════════════════════════════════════════════════
# VMC SIGNAL ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def score_coin(ticker: dict, rsi: float, config: dict) -> int:
    try:
        change    = float(ticker["priceChangePercent"])
        volume    = float(ticker["quoteVolume"])
        high      = float(ticker["highPrice"])
        low       = float(ticker["lowPrice"])
        last      = float(ticker["lastPrice"])
        price_pos = (last - low) / (high - low + 1e-9) * 100
    except Exception:
        return 0
    score = 0
    if change > 5:      score += 30
    elif change > 2:    score += 22
    elif change > 0.5:  score += 14
    elif change > -1:   score += 8
    if volume > 50_000_000:   score += 25
    elif volume > 10_000_000: score += 20
    elif volume > 2_000_000:  score += 14
    elif volume > 500_000:    score += 8
    if 40 <= price_pos <= 75:  score += 25
    elif 25 <= price_pos < 40: score += 18
    elif price_pos > 75:       score += 12
    else:                      score += 6
    if 40 <= rsi <= 60:                score += 20
    elif 35 <= rsi < 40 or 60 < rsi <= 65: score += 14
    elif 30 <= rsi < 35 or 65 < rsi <= 70: score += 8
    return min(score, 100)


def categorize_signals(tickers: list, rsi_map: dict, config: dict) -> dict:
    cfg    = config["vmc"]
    thresh = cfg["score_threshold"]
    favs   = set(cfg["favorite_coins"])
    out    = {k: [] for k in ["ALL","FAV","STUCK","GOLDEN","BOOM","ENTRY","EXIT","PUMP","VIP"]}
    for t in tickers:
        symbol = t["symbol"]
        rsi    = rsi_map.get(symbol, price_position_rsi(t))
        score  = score_coin(t, rsi, config)
        if score < thresh:
            continue
        try:
            change    = float(t["priceChangePercent"])
            volume    = float(t["quoteVolume"])
            high      = float(t["highPrice"])
            low       = float(t["lowPrice"])
            last      = float(t["lastPrice"])
            price_pos = (last - low) / (high - low + 1e-9) * 100
        except Exception:
            continue
        coin = {
            "symbol": symbol, "price": float(t["lastPrice"]),
            "change_pct": round(change, 2),
            "volume_usdt": round(float(t["quoteVolume"]), 0),
            "rsi": rsi, "score": score,
            "high_24h": float(t["highPrice"]), "low_24h": float(t["lowPrice"]),
            "price_pos_pct": round(price_pos, 1),
        }
        out["ALL"].append(coin)
        if symbol in favs: out["FAV"].append(coin)
        if abs(change) < cfg["volatility_stuck_max"]:
            out["STUCK"].append(coin); continue
        if score >= cfg["golden_score_min"] and rsi < cfg["rsi_golden_max"]:
            out["GOLDEN"].append(coin)
        if change > 5 and volume > 5_000_000 * cfg["volume_boom_multiplier"]:
            out["BOOM"].append(coin)
        if rsi <= cfg["rsi_oversold"] or (price_pos < 25 and change < 0):
            out["ENTRY"].append(coin)
        if rsi >= cfg["rsi_overbought"] or price_pos > 85:
            out["EXIT"].append(coin)
        if change >= cfg["pump_change_min"] and volume > 3_000_000:
            out["PUMP"].append(coin)
        if score >= cfg["vip_score_min"]:
            out["VIP"].append(coin)
    for key in out:
        out[key].sort(key=lambda x: x["score"], reverse=True)
    return out


def process_vmc_signals(config: dict) -> dict:
    top_n   = config["vmc"]["rsi_top_n"]
    tickers = fetch_all_tickers(config)
    rsi_map = {}
    for i, t in enumerate(tickers[:top_n]):
        rsi_map[t["symbol"]] = fetch_rsi_for_symbol(t["symbol"])
        if i > 0 and i % 10 == 0:
            time.sleep(0.3)
    log.info(f"VMC: RSI computed for {len(rsi_map)} coins. Categorizing {len(tickers)} total.")
    return categorize_signals(tickers, rsi_map, config)


# ══════════════════════════════════════════════════════════════════════════════
# WHALE WALL ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def fetch_order_book(symbol: str, depth: int = 20) -> dict:
    try:
        resp = _binance_get("/api/v3/depth", params={"symbol": symbol, "limit": depth}, timeout=8)
        if resp is None:
            return {"bids": [], "asks": []}
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.debug(f"Order book failed for {symbol}: {e}")
        return {"bids": [], "asks": []}


def detect_spoofing(bids: list, asks: list, config: dict) -> dict:
    ratio_thresh = config["whale"]["spoofing_ratio_threshold"]
    def _check(levels):
        if len(levels) < 4: return False, 0.0
        sizes = [float(l[1]) for l in levels]
        top   = sizes[0]
        avg   = sum(sizes[1:]) / len(sizes[1:])
        if avg == 0: return False, 0.0
        ratio = top / avg
        return ratio >= ratio_thresh, round(ratio, 2)
    bid_spoof, bid_ratio = _check(bids)
    ask_spoof, ask_ratio = _check(asks)
    detail = []
    if bid_spoof: detail.append(f"Fake BID wall (×{bid_ratio})")
    if ask_spoof: detail.append(f"Fake ASK wall (×{ask_ratio})")
    return {"bid_spoof": bid_spoof, "ask_spoof": ask_spoof,
            "bid_ratio": bid_ratio, "ask_ratio": ask_ratio,
            "details": " | ".join(detail) if detail else "Clean"}


def calculate_wall_proximity(price: float, book: dict, config: dict) -> list:
    prox_pct = config["whale"]["wall_proximity_pct"]
    min_size = config["whale"]["min_wall_size_usdt"]
    walls    = []
    for side, levels in [("BID", book.get("bids", [])), ("ASK", book.get("asks", []))]:
        for level in levels:
            try:
                lp = float(level[0]); lq = float(level[1]); lu = lp * lq
            except (IndexError, ValueError):
                continue
            if lu < min_size: continue
            dist = abs(lp - price) / price * 100
            if dist <= prox_pct:
                walls.append({"side": side, "price_level": round(lp, 6),
                               "size_usdt": round(lu, 0), "dist_pct": round(dist, 3)})
    walls.sort(key=lambda x: x["dist_pct"])
    return walls


def blink_to_push_check(symbol: str, current_walls: list,
                         previous_walls: dict, config: dict) -> bool:
    push_thresh = config["whale"]["blink_push_proximity_pct"]
    prev        = previous_walls.get(symbol, [])
    if not prev or not current_walls: return False
    prev_min = min((w["dist_pct"] for w in prev), default=99)
    curr_min = min((w["dist_pct"] for w in current_walls), default=99)
    return curr_min < prev_min and curr_min <= push_thresh


def process_whale_walls(config: dict, price_map: dict, previous_walls: dict) -> list:
    top_n   = config["whale"]["top_coins_for_whale"]
    depth   = config["whale"]["order_book_depth"]
    results = []
    for i, symbol in enumerate(list(price_map.keys())[:top_n]):
        price = price_map.get(symbol, 0)
        if not price: continue
        book        = fetch_order_book(symbol, depth)
        walls       = calculate_wall_proximity(price, book, config)
        spoof       = detect_spoofing(book.get("bids", []), book.get("asks", []), config)
        b2push      = blink_to_push_check(symbol, walls, previous_walls, config)
        obi         = calculate_obi(book)
        obi_r       = detect_obi_spike(symbol, obi, config)
        whale_power = compute_whale_power(walls, spoof, b2push, price, config)
        if walls or spoof["bid_spoof"] or spoof["ask_spoof"] or b2push:
            label = ("WHALE TRAP" if (spoof["bid_spoof"] or spoof["ask_spoof"])
                     else "BLINK→PUSH" if b2push else "WALL")
            results.append({
                "symbol": symbol, "price": price, "walls": walls, "spoofing": spoof,
                "blink_to_push": b2push, "label": label, "wall_count": len(walls),
                "min_dist_pct": min((w["dist_pct"] for w in walls), default=0) if walls else 0,
                "whale_power": whale_power, "obi": obi_r, "timestamp": time.time(),
            })
        previous_walls[symbol] = walls
        if i > 0 and i % 10 == 0:
            time.sleep(0.2)
    results.sort(key=lambda x: x["whale_power"], reverse=True)
    return results


# ══════════════════════════════════════════════════════════════════════════════
# ETH ON-CHAIN EXCHANGE FLOW — via Etherscan (ETH/ERC-20 only)
# ══════════════════════════════════════════════════════════════════════════════

BINANCE_ETH_HOT_WALLET = "0xF977814e90dA44bFA03b6295A0616a897441aceC"
_eth_flow_last_block: dict = {}

def fetch_eth_exchange_flows(api_key: str, min_eth: float = 50.0) -> list:
    """Detects large ETH transfers into/out of a known Binance hot wallet via
    Etherscan. Returns new flows since the last check. ETH/ERC-20 chain only —
    does NOT apply to BTC, BNB(native), SOL, XRP, ADA, DOGE, AVAX."""
    if not api_key:
        return []
    try:
        params = {
            "module": "account", "action": "txlist",
            "address": BINANCE_ETH_HOT_WALLET, "sort": "desc",
            "apikey": api_key, "offset": 20, "page": 1,
        }
        resp = requests.get("https://api.etherscan.io/api", params=params, timeout=10)
        if resp.status_code != 200:
            return []
        data = resp.json()
        if data.get("status") != "1":
            return []
        txs = data.get("result", [])
        last_block = _eth_flow_last_block.get("last", 0)
        new_txs = [t for t in txs if int(t.get("blockNumber", 0)) > last_block]
        if txs:
            _eth_flow_last_block["last"] = max(int(t["blockNumber"]) for t in txs)
        out = []
        for t in new_txs:
            eth_val = int(t.get("value", 0)) / 1e18
            if eth_val < min_eth:
                continue
            is_inflow = t.get("to", "").lower() == BINANCE_ETH_HOT_WALLET.lower()
            out.append({
                "eth": round(eth_val, 3),
                "direction": "INFLOW (deposit → sell pressure)" if is_inflow else "OUTFLOW (withdraw → accumulation)",
                "hash": t.get("hash", ""),
                "time": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(int(t.get("timeStamp", 0)) + 5 * 3600)) + " PKT",
                "source": "Etherscan",
            })
        return out
    except Exception as e:
        log.debug(f"Etherscan fetch failed: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# LARGE TRADE DETECTOR — exchange-side whale-activity proxy (no on-chain API needed)
# ══════════════════════════════════════════════════════════════════════════════

_large_trade_since: dict = {}   # symbol -> last aggTrade id checked

def fetch_large_trades(symbol: str, min_usdt: float = 50000, limit: int = 200) -> list:
    """Scans recent aggTrades for single trades >= min_usdt. Returns new large
    trades since the last check for this symbol (dedup via fromId)."""
    try:
        params = {"symbol": symbol, "limit": limit}
        last_id = _large_trade_since.get(symbol)
        if last_id:
            params["fromId"] = last_id + 1
        resp = _binance_get("/api/v3/aggTrades", params=params, timeout=8)
        if resp is None or resp.status_code != 200:
            return []
        trades = resp.json()
        if not trades:
            return []
        _large_trade_since[symbol] = trades[-1]["a"]
        out = []
        for t in trades:
            price = float(t["p"]); qty = float(t["q"])
            usdt = price * qty
            if usdt < min_usdt:
                continue
            out.append({
                "symbol": symbol, "price": price, "qty": qty,
                "usdt": round(usdt, 0),
                "side": "SELL" if t["m"] else "BUY",  # m=True: buyer is maker -> taker sold
                "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t["T"] / 1000)),
                "ts": t["T"] / 1000,
            })
        return out
    except Exception as e:
        log.debug(f"Large trade fetch failed for {symbol}: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# BTC SENTIMENT + REGIME
# ══════════════════════════════════════════════════════════════════════════════

def fetch_btc_sentiment() -> dict:
    try:
        resp = _binance_get("/api/v3/ticker/24hr", params={"symbol": "BTCUSDT"}, timeout=8)
        if resp is None:
            raise RuntimeError("all Binance hosts unreachable")
        resp.raise_for_status()
        t          = resp.json()
        change     = float(t["priceChangePercent"])
        price      = float(t["lastPrice"])
        high       = float(t["highPrice"])
        low        = float(t["lowPrice"])
        volatility = (high - low) / low * 100 if low else 0
        pause      = change <= -2.0 or volatility > 5.0
        sentiment  = "BEARISH" if pause else "BULLISH" if change >= 2.0 else "NEUTRAL"
        regime     = detect_market_regime(volatility, change)
        return {
            "price": price, "change_pct": round(change, 2),
            "volume": round(float(t["quoteVolume"]), 0),
            "volatility_pct": round(volatility, 2), "sentiment": sentiment,
            "pause_entries": pause, "regime": regime,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    except Exception as e:
        log.warning(f"BTC sentiment fetch failed: {e}")
        return {"price": 0, "change_pct": 0, "volume": 0, "volatility_pct": 0,
                "sentiment": "UNKNOWN", "pause_entries": False, "regime": "RANGING",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}


# ══════════════════════════════════════════════════════════════════════════════
# GOOGLE SHEETS INTEGRATION
# ══════════════════════════════════════════════════════════════════════════════

def _add_color_rule(spreadsheet, worksheet, col_idx: int, match_text: str, rgb: tuple):
    """One-time conditional-format rule: cells in `col_idx` (0-indexed)
    equal to `match_text` get filled with `rgb`. Called only right after a
    worksheet is newly created — surviving later ws.clear()/update() calls
    since formatting rules are attached to the sheet, not the cell values."""
    try:
        r, g, b = rgb
        body = {"requests": [{
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{
                        "sheetId": worksheet.id,
                        "startRowIndex": 1, "endRowIndex": 2000,
                        "startColumnIndex": col_idx, "endColumnIndex": col_idx + 1,
                    }],
                    "booleanRule": {
                        "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": match_text}]},
                        "format": {"backgroundColor": {"red": r, "green": g, "blue": b}},
                    },
                },
                "index": 0,
            }
        }]}
        spreadsheet.batch_update(body)
    except Exception as e:
        log.debug(f"Color rule failed for {match_text}: {e}")


def push_to_google_sheets(vmc_data: dict, whale_data: list,
                           credentials_json: str, sheet_id: str,
                           whale_copy_signals: list = None,
                           whale_copy_trades: list = None,
                           paper_trades: list = None,
                           inst_signals: list = None) -> bool:
    try:
        import json as _json, gspread
        from oauth2client.service_account import ServiceAccountCredentials
        creds_dict = _json.loads(credentials_json)
        if not creds_dict or not sheet_id: return False
        scopes = ["https://spreadsheets.google.com/feeds",
                  "https://www.googleapis.com/auth/drive"]
        creds  = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scopes)
        client = gspread.authorize(creds)
        sheet  = client.open_by_key(sheet_id)

        try:
            ws_live = sheet.worksheet("LIVE_DASHBOARD")
        except Exception:
            ws_live = sheet.add_worksheet("LIVE_DASHBOARD", rows=1100, cols=15)
            _add_color_rule(sheet, ws_live, 6, "BUY", (0.72,0.93,0.72))
            _add_color_rule(sheet, ws_live, 6, "WATCH", (1.0,0.95,0.6))

        std_headers = ["Timestamp","Asset","Status","Signal","Basis","VMC","Price",
                       "Buy/Sale","Heatmap","Slack","Chg%","RSI","Flux","Sentiment","Log"]
        ts   = time.strftime("%Y-%m-%d %H:%M:%S PKT", time.gmtime(time.time() + 5 * 3600))
        rows = [std_headers]
        for folder, coins in vmc_data.items():
            for coin in coins[:20]:
                row = {"Timestamp": ts, "Asset": coin["symbol"].replace("USDT",""), "Status": "ACTIVE",
                       "Signal": folder, "Basis": "Chg%+Vol+RSI", "VMC": coin["score"], "Price": coin["price"],
                       "Buy/Sale": "BUY" if folder in ["ENTRY","GOLDEN","VIP"] else "WATCH",
                       "Heatmap": "HOT" if coin["volume_usdt"] > 10_000_000 else "WARM",
                       "Slack": "", "Chg%": coin["change_pct"], "RSI": coin["rsi"],
                       "Flux": coin["price_pos_pct"], "Sentiment": "",
                       "Log": f"Score:{coin['score']}"}
                rows.append([row.get(h, "") for h in std_headers])

        ws_live.clear(); ws_live.update("A1", rows)

        try:
            ws_watch = sheet.worksheet("WATCH")
        except Exception:
            ws_watch = sheet.add_worksheet("WATCH", rows=200, cols=9)
            _add_color_rule(sheet, ws_watch, 2, "WHALE TRAP", (0.96,0.72,0.72))
            _add_color_rule(sheet, ws_watch, 2, "BLINK→PUSH", (1.0,0.95,0.6))
            _add_color_rule(sheet, ws_watch, 2, "WALL", (0.75,0.85,0.98))
        _now_str = time.strftime("%Y-%m-%d %H:%M:%S PKT", time.gmtime(time.time() + 5 * 3600))
        _exp_str = time.strftime("%Y-%m-%d %H:%M:%S PKT", time.gmtime(time.time() + 1800 + 5 * 3600))
        _lt_cnt  = sum(1 for w in whale_data[:100] if w["label"] == "WHALE TRAP")
        _wall_cnt= sum(1 for w in whale_data[:100] if w["label"] == "WALL")
        _bp_cnt  = sum(1 for w in whale_data[:100] if w["label"] == "BLINK→PUSH")
        wrows = [[f"Summary: {len(whale_data[:100])} active | {_lt_cnt} trapped | {_wall_cnt} walls | {_bp_cnt} blink→push",
                  "", "", "", "", "", "", "", "", "", "", ""],
                 ["Symbol","Price","Label","Light","Basis","BlinkPush","BidSpoof","AskSpoof",
                  "WallCount","MinDist%","WhalePower","GeneratedAt","ExpiresAt"]]
        for w in whale_data[:100]:
            _light = "🔴" if w["label"] == "WHALE TRAP" else "🟢" if w["label"] == "BLINK→PUSH" else "🟡"
            wrows.append([w["symbol"].replace("USDT",""), w["price"], w["label"], _light, "OBI+Walls",
                          w["blink_to_push"], w["spoofing"]["bid_spoof"], w["spoofing"]["ask_spoof"],
                          w["wall_count"], w["min_dist_pct"], w.get("whale_power", 0), _now_str, _exp_str])
        ws_watch.clear(); ws_watch.update("A1", wrows)

        # ── ARCHIVE_LOG: rolling per-cycle summary (fixes tab staying empty) ──
        try:
            ws_arch2 = sheet.worksheet("ARCHIVE_LOG")
        except Exception:
            ws_arch2 = sheet.add_worksheet("ARCHIVE_LOG", rows=5000, cols=8)
            ws_arch2.update("A1", [["Timestamp","ActiveWhaleSignals","Trapped","Walls","BlinkPush","LiveRows"]])
        try:
            ws_arch2.append_row([_now_str, len(whale_data[:100]), _lt_cnt, _wall_cnt, _bp_cnt, len(rows) - 1])
        except Exception as _ae:
            log.debug(f"ARCHIVE_LOG cycle append failed: {_ae}")

        try: ws_arch = sheet.worksheet("ARCHIVE_LOG")
        except Exception: ws_arch = sheet.add_worksheet("ARCHIVE_LOG", rows=5000, cols=15)
        try:
            all_live = ws_live.get_all_values()
            if len(all_live) > 1000:
                ws_arch.append_rows(all_live[1:len(all_live)-500])
        except Exception: pass

        try: ws_users = sheet.worksheet("USERS")
        except Exception: ws_users = sheet.add_worksheet("USERS", rows=200, cols=8)
        try:
            import json as _j2
            with open("clients.json") as _f:
                clients_local = _j2.load(_f)
        except Exception:
            clients_local = []
        urows = [["Name","UID","Password","Status","Expiry","SigLimit","Role","Added"]]
        for c in clients_local:
            urows.append([c.get("name",""), c.get("uid",""), c.get("password",""),
                          c.get("status","ACTIVE"), c.get("expiry","UNLIMITED"),
                          c.get("sig_limit","100"), c.get("role","CLIENT"), c.get("added","")])
        ws_users.clear()
        if urows: ws_users.update("A1", urows)

        # ── V6 54-POINT SIGNALS (the BUY/WAIT/AVOID score that drives
        # ── auto paper-trade entry — separate from the older VMC score) ───
        if inst_signals is not None:
            try:
                ws_v6 = sheet.worksheet("V6_SIGNALS")
            except Exception:
                ws_v6 = sheet.add_worksheet("V6_SIGNALS", rows=200, cols=16)
                _add_color_rule(sheet, ws_v6, 2, "BUY", (0.72,0.93,0.72))
                _add_color_rule(sheet, ws_v6, 2, "WAIT", (1.0,0.95,0.6))
                _add_color_rule(sheet, ws_v6, 2, "AVOID", (0.96,0.72,0.72))
            v6_rows = [["Symbol","Basis","Folder","Label","Score","MarketRegime","WhaleInst",
                        "Technical","SmartMoney","TradeEngine","RSI","Price",
                        "StopLoss","TP1","TP2","TP3","Strategy","ETA_to_TP1"]]
            seen_v6 = set()
            for s in inst_signals[:100]:
                sym = s.get("symbol")
                if sym in seen_v6:
                    continue
                seen_v6.add(sym)
                v6 = s.get("v6", {}) or {}
                bd = v6.get("breakdown", {}) or {}
                tp = s.get("tp_zones", {}) or {}
                v6_rows.append([
                    sym.replace("USDT",""), "Regime+Whale+RSI+MACD+SmartMoney+RR", s.get("folder",""), v6.get("label",""), v6.get("score",0),
                    bd.get("market_regime",0), bd.get("inst_whale",0), bd.get("technical",0),
                    bd.get("smart_divergence",0), bd.get("trade_engine",0),
                    s.get("rsi",0), s.get("price",0),
                    tp.get("stop_loss",0), tp.get("tp1",0), tp.get("tp2",0), tp.get("tp3",0),
                    s.get("trading_strategy",""), tp.get("eta_tp1","—"),
                ])
            ws_v6.clear(); ws_v6.update("A1", v6_rows)

        # ── WHALE COPY SIGNALS (current live wall+OBI signals) ────────────
        if whale_copy_signals is not None:
            try:
                ws_wc = sheet.worksheet("WHALE_COPY_SIGNALS")
            except Exception:
                ws_wc = sheet.add_worksheet("WHALE_COPY_SIGNALS", rows=200, cols=12)
                _add_color_rule(sheet, ws_wc, 2, "COPY_BUY", (0.72,0.93,0.72))
                _add_color_rule(sheet, ws_wc, 2, "COPY_AVOID", (0.96,0.72,0.72))
            wc_rows = [["Time","Symbol","Basis","Direction","WallPrice","StopLoss","Target",
                        "SizeUSDT","OBI","OBIVelocity","Confidence","Confirmed","ETA"]]
            for s in whale_copy_signals[:100]:
                wc_rows.append([
                    s.get("detected_at",""), s.get("symbol","").replace("USDT",""), "OBI+Walls", s.get("direction",""),
                    s.get("wall_price",0), s.get("stop_loss",0), s.get("target",0),
                    s.get("wall_size_usdt",0), s.get("obi",0), s.get("obi_velocity",0),
                    s.get("confidence",0), s.get("confirmed",False), s.get("eta","—"),
                ])
            ws_wc.clear(); ws_wc.update("A1", wc_rows)

        # ── WHALE COPY TRADES (paper ledger, win/loss tracked) ────────────
        if whale_copy_trades is not None:
            try:
                ws_wct = sheet.worksheet("WHALE_COPY_TRADES")
            except Exception:
                ws_wct = sheet.add_worksheet("WHALE_COPY_TRADES", rows=500, cols=12)
                _add_color_rule(sheet, ws_wct, 1, "COPY_BUY", (0.72,0.93,0.72))
                _add_color_rule(sheet, ws_wct, 1, "COPY_AVOID", (0.96,0.72,0.72))
                _add_color_rule(sheet, ws_wct, 7, "WIN", (0.72,0.93,0.72))
                _add_color_rule(sheet, ws_wct, 7, "LOSS", (0.96,0.72,0.72))
            wct_rows = [["Symbol","Basis","Direction","EntryPrice","StopLoss","Target",
                         "Confidence","Status","Result","PnL%","EntryTime","ExitTime","ETA"]]
            for t in whale_copy_trades[:200]:
                wct_rows.append([
                    t.get("symbol","").replace("USDT",""), "OBI+Walls", t.get("direction",""), t.get("entry_price",0),
                    t.get("stop_loss",0), t.get("target",0), t.get("confidence",0),
                    t.get("status",""), t.get("result") or "—", t.get("pnl_pct") or "—",
                    t.get("entry_time",""), t.get("exit_time") or "—", t.get("eta","—"),
                ])
            ws_wct.clear(); ws_wct.update("A1", wct_rows)

        # ── PAPER TRADES (manual + v6 auto-trade ledger) ──────────────────
        if paper_trades is not None:
            try:
                ws_pt = sheet.worksheet("PAPER_TRADES")
            except Exception:
                ws_pt = sheet.add_worksheet("PAPER_TRADES", rows=500, cols=10)
                _add_color_rule(sheet, ws_pt, 2, "BUY", (0.72,0.93,0.72))
                _add_color_rule(sheet, ws_pt, 2, "SELL", (0.96,0.72,0.72))
            pt_rows = [["Time","Symbol","Basis","Side","AmountUSDT","Price","Qty","Strategy","Mode","Reason"]]
            for t in paper_trades[:200]:
                pt_rows.append([
                    t.get("time",""), t.get("symbol","").replace("USDT",""), "Regime+Whale+RSI+MACD+SmartMoney+RR", t.get("side",""),
                    t.get("amount_usdt",0), t.get("price",0), t.get("qty",0),
                    t.get("strategy",""), t.get("mode",""), t.get("reason",""),
                ])
            ws_pt.clear(); ws_pt.update("A1", pt_rows)

        # ── LEGEND: one-time reference tab explaining every tab/folder's basis ──
        try:
            sheet.worksheet("LEGEND")
        except Exception:
            ws_legend = sheet.add_worksheet("LEGEND", rows=40, cols=3)
            legend_rows = [
                ["Tab / Folder", "Signal Basis", "Notes"],
                ["LIVE_DASHBOARD — all VMC folders", "Price Chg% + Volume + RSI", "No whale/order-book data"],
                ["  > VIP", "Highest overall VMC score", ""],
                ["  > GOLDEN", "High score + RSI not yet overbought", ""],
                ["  > BOOM", "5%+ price surge + volume spike", ""],
                ["  > ENTRY", "RSI oversold or price near 24h low", ""],
                ["  > EXIT", "RSI overbought or price near 24h high", ""],
                ["  > STUCK", "Low volatility, range-bound", ""],
                ["  > PUMP", "Strong price jump + volume", ""],
                ["WATCH", "Raw whale wall/spoof detection", "Detection only, no score"],
                ["V6_SIGNALS", "V6 54-point score: Regime+Whale+RSI/MACD/Volume+SmartMoney+Risk-RR", "Gates auto-trade entry"],
                ["WHALE_COPY_SIGNALS", "Order-book Wall + OBI (live, incl. unconfirmed)", "Independent of V6 score"],
                ["WHALE_COPY_TRADES", "Confirmed Wall+OBI (2 consecutive scans)", "Paper ledger, win/loss tracked"],
                ["PAPER_TRADES", "Manual entries + V6-score auto-trade triggers", ""],
                ["USERS", "Client login records", "Not a trading signal"],
                ["ARCHIVE_LOG", "Overflow rows + per-cycle summary counts", "Not a trading signal"],
            ]
            ws_legend.update("A1", legend_rows)

        log.info(f"Sheets updated — {len(rows)-1} LIVE rows, {len(wrows)-1} WATCH rows.")
        return True
    except ImportError:
        log.warning("gspread/oauth2client not installed — Sheets push skipped."); return False
    except Exception as e:
        log.error(f"Google Sheets push failed: {e}"); return False


def match_whale_pattern(obi: float, whale_power: float, trend: str,
                        blink_to_push: bool, walls: list) -> dict:
    has_bid = any(w["side"] == "BID" for w in walls)
    has_ask = any(w["side"] == "ASK" for w in walls)
    patterns = {
        "ACCUMULATION_ZONE": [(obi > 0.05, 35), (whale_power >= 40, 30),
                              (trend == "ACCUMULATION", 25), (has_bid, 10)],
        "DISTRIBUTION_ZONE": [(obi < -0.05, 35), (whale_power >= 40, 30),
                              (trend == "DISTRIBUTION", 25), (has_ask, 10)],
        "PUMP_PREPARATION":  [(blink_to_push, 40), (obi > 0.1, 35), (whale_power >= 50, 25)],
        "DUMP_PREPARATION":  [(obi < -0.1, 40), (has_ask, 35),
                              (not blink_to_push, 15), (trend == "DISTRIBUTION", 10)],
    }
    best_name, best_score = "UNCLEAR", 0
    for name, criteria in patterns.items():
        max_pts = sum(pts for _, pts in criteria)
        got_pts = sum(pts for cond, pts in criteria if cond)
        pct     = round(got_pts / max_pts * 100) if max_pts else 0
        if pct > best_score:
            best_score = pct; best_name = name
    return {"name": best_name, "similarity_pct": best_score,
            "tag": "[WHALE PATTERN MATCH]" if best_score >= 75 else ""}


_whale_copy_state: dict = {}

DEFAULT_STABLECOIN_BASES = ["USDC","USDT","BUSD","DAI","TUSD","USDP","FDUSD","PYUSD",
                            "GUSD","USDD","EURT","EURI","USD1","RLUSD","USDE"]

def is_stablecoin_pair(symbol: str, price: float, config: dict = None) -> bool:
    """
    True if `symbol` looks like a stablecoin pair — either by name (base
    asset in a known stablecoin list) or by price behavior (trading within
    1% of $1.00, catching new/unlisted stablecoins the name list hasn't
    been updated for). Used by both Whale Copy Mode and the legacy whale
    alert system so stablecoin noise is filtered consistently everywhere.
    """
    cfg      = config or {}
    wc_cfg   = cfg.get("whale_copy", {})
    excluded = set(wc_cfg.get("exclude_symbols", DEFAULT_STABLECOIN_BASES))
    base = symbol[:-4] if symbol and symbol.endswith("USDT") else symbol
    if base in excluded:
        return True
    p = price or 0
    return 0.99 <= p <= 1.01


def detect_whale_copy_signals(whale_data: list, config: dict) -> list:
    """
    WHALE COPY MODE — independent of the 54-point v6 score. Directly mirrors
    a CONFIRMED whale wall's direction:
      BID wall (real, min size) + OBI positive  -> COPY_BUY
      ASK wall (real, min size) + OBI negative  -> COPY_AVOID (spot-only, no shorting)
      Both walls present at once (ranging)       -> skipped, no clear direction
    Includes SL/TP levels and a 2-consecutive-cycle persistence check before
    a signal is marked confirmed=True (auto-trade only fires on confirmed).
    """
    wc_cfg          = config.get("whale_copy", {})
    min_wall_usdt   = wc_cfg.get("min_wall_usdt", 500000)
    sl_buffer_pct   = wc_cfg.get("sl_buffer_pct", 1.5)
    tp_fallback_pct = wc_cfg.get("tp_fallback_pct", 3.0)
    persist_window  = wc_cfg.get("persistence_window_seconds", 120)

    now = time.time()
    signals   = []
    seen_syms = set()

    for w in whale_data:
        sym    = w.get("symbol")
        price0 = w.get("price", 0) or 0
        if is_stablecoin_pair(sym, price0, config):
            continue   # stablecoin-like pair — price barely moves, whale-copy meaningless here
        seen_syms.add(sym)
        walls = w.get("walls", [])
        spoof = w.get("spoofing", {})
        obi_r = w.get("obi", {}) or {}
        obi_val = obi_r.get("obi", 0)
        obi_vel = obi_r.get("velocity", 0)
        price   = w.get("price", 0)

        bid_walls = [x for x in walls if x.get("side") == "BID" and x.get("size_usdt", 0) >= min_wall_usdt]
        ask_walls = [x for x in walls if x.get("side") == "ASK" and x.get("size_usdt", 0) >= min_wall_usdt]
        has_bid = bool(bid_walls) and not spoof.get("bid_spoof", False)
        has_ask = bool(ask_walls) and not spoof.get("ask_spoof", False)

        if has_bid and has_ask:
            _whale_copy_state.pop(sym, None)
            continue   # ranging market, no clear direction — skip
        if not has_bid and not has_ask:
            _whale_copy_state.pop(sym, None)
            continue

        if has_bid and obi_val > 0:
            wall      = max(bid_walls, key=lambda x: x["size_usdt"])
            direction = "COPY_BUY"
            opposite  = min(ask_walls, key=lambda x: x["dist_pct"]) if ask_walls else None
        elif has_ask and obi_val < 0:
            wall      = max(ask_walls, key=lambda x: x["size_usdt"])
            direction = "COPY_AVOID"
            opposite  = min(bid_walls, key=lambda x: x["dist_pct"]) if bid_walls else None
        else:
            _whale_copy_state.pop(sym, None)
            continue   # wall exists but OBI doesn't confirm the direction

        # ── Consecutive-scan-cycle confirmation (cycle-count based, not
        # wall-clock time — a time window shorter than the actual scan
        # interval meant confirmation could never trigger; this counts
        # actual consecutive scans instead, regardless of interval length).
        prev = _whale_copy_state.get(sym)
        count = (prev["count"] + 1) if (prev and prev["direction"] == direction) else 1
        _whale_copy_state[sym] = {"direction": direction, "count": count, "last_seen": now}
        confirmed = count >= 2

        wall_price     = wall.get("price_level", price)
        wall_size_usdt = wall.get("size_usdt", 0)
        wall_qty       = round(wall_size_usdt / wall_price, 4) if wall_price else 0

        # ── SL / TP levels ──────────────────────────────────────────────────
        if direction == "COPY_BUY":
            stop_loss = round(wall_price * (1 - sl_buffer_pct / 100), 8)
            target    = opposite["price_level"] if opposite else round(wall_price * (1 + tp_fallback_pct / 100), 8)
        else:
            stop_loss = round(wall_price * (1 + sl_buffer_pct / 100), 8)
            target    = opposite["price_level"] if opposite else round(wall_price * (1 - tp_fallback_pct / 100), 8)

        size_score = min(100, (wall_size_usdt / min_wall_usdt) * 50) if min_wall_usdt else 0
        obi_score  = min(100, abs(obi_val) * 200)
        confidence = round(min(100, (size_score + obi_score) / 2), 1)

        signals.append({
            "symbol":         sym,
            "direction":      direction,
            "price":          price,
            "wall_price":     wall_price,
            "wall_size_usdt": round(wall_size_usdt, 0),
            "wall_qty":       wall_qty,
            "stop_loss":      stop_loss,
            "target":         target,
            "obi":            obi_val,
            "obi_velocity":   obi_vel,
            "confidence":     confidence,
            "confirmed":      confirmed,
            "dist_pct":       wall.get("dist_pct", 0),
            "detected_at":    time.strftime("%Y-%m-%d %H:%M:%S"),
        })

    for sym in list(_whale_copy_state.keys()):
        if sym not in seen_syms:
            _whale_copy_state.pop(sym, None)

    signals.sort(key=lambda x: (x["confirmed"], x["confidence"]), reverse=True)
    return signals


def compute_whale_detail(symbol: str, price: float, ticker_24h: dict, config: dict) -> dict:
    try:
        book    = fetch_order_book(symbol, depth=20)
        bids    = book.get("bids", [])
        asks    = book.get("asks", [])
        bid_vol = sum(float(b[0]) * float(b[1]) for b in bids) if bids else 0.0
        ask_vol = sum(float(a[0]) * float(a[1]) for a in asks) if asks else 0.0
        bag_sz  = round(bid_vol, 0)

        def _vwap_side(levels):
            tot_q = sum(float(l[1]) for l in levels)
            if not tot_q: return price
            return sum(float(l[0]) * float(l[1]) for l in levels) / tot_q

        avg_buy  = round(_vwap_side(bids), 8)
        avg_sell = round(_vwap_side(asks), 8)
        total_v  = bid_vol + ask_vol
        obi      = round((bid_vol - ask_vol) / total_v, 4) if total_v else 0.0
        buy_sell = round(bid_vol / ask_vol, 2) if ask_vol else 0.0
        q_vol    = float(ticker_24h.get("quoteVolume", 0))
        buy_r    = bid_vol / total_v if total_v else 0.5
        inflow   = round(q_vol * buy_r, 0)
        outflow  = round(q_vol * (1 - buy_r), 0)
        trend    = "ACCUMULATION" if obi > 0.05 else "DISTRIBUTION" if obi < -0.05 else "NEUTRAL"

        obi_hist = _obi_history.get(symbol, [])
        if len(obi_hist) >= 2:
            vals      = [v for _, v in obi_hist]
            avg_obi   = sum(vals[:-1]) / len(vals[:-1])
            std_obi   = (sum((v - avg_obi) ** 2 for v in vals[:-1]) / len(vals[:-1])) ** 0.5
            velocity  = round(abs(obi - avg_obi) / std_obi, 3) if std_obi else 0.0
            micro_spk = velocity >= config["institutional"]["obi_spike_threshold"]
        else:
            velocity = 0.0; micro_spk = False

        walls_all = calculate_wall_proximity(price, book, config)
        spoof     = detect_spoofing(bids, asks, config)
        bid_walls = [w for w in walls_all if w["side"] == "BID"]
        ask_walls = [w for w in walls_all if w["side"] == "ASK"]

        def _best(wlist, spoof_flag):
            if not wlist: return {}
            w = wlist[0]
            return {"price": w["price_level"], "size_usdt": w["size_usdt"],
                    "dist_pct": w["dist_pct"], "real": not spoof_flag}

        bid_wall = _best(bid_walls, spoof.get("bid_spoof"))
        ask_wall = _best(ask_walls, spoof.get("ask_spoof"))
        b2push   = blink_to_push_check(symbol, walls_all, {}, config)
        wp       = compute_whale_power(walls_all, spoof, b2push, price, config)

        now = time.time()
        spike_cnt = sum(
            1 for s, h in _obi_history.items()
            if s != symbol and len(h) >= 2 and now - h[-1][0] < 300
            and abs(h[-1][1] - sum(v for _, v in h[:-1]) / len(h[:-1])) > 0.1
        )
        clustering = "COORDINATED" if spike_cnt >= 3 else "ACTIVE" if spike_cnt >= 1 else "NORMAL"
        pattern    = match_whale_pattern(obi, wp, trend, b2push, walls_all)
        critical   = wp >= config["whale"]["critical_whale_power_pct"]

        return {
            "symbol": symbol, "price": price, "whale_power": wp,
            "bag_size_usdt": bag_sz, "avg_buy_price": avg_buy, "avg_sell_price": avg_sell,
            "inflow_24h_usdt": inflow, "outflow_24h_usdt": outflow,
            "trend": trend, "buy_sell_ratio": buy_sell,
            "bid_wall": bid_wall, "ask_wall": ask_wall,
            "obi": obi, "obi_velocity": velocity,
            "micro_spike": micro_spk, "clustering": clustering,
            "pattern": pattern, "top_moves_24h": [],
            "critical": critical, "walls": walls_all, "blink_to_push": b2push,
        }
    except Exception as e:
        log.warning(f"compute_whale_detail failed {symbol}: {e}")
        return {"symbol": symbol, "price": price, "whale_power": 0, "error": str(e),
                "bid_wall": {}, "ask_wall": {}, "pattern": {}, "top_moves_24h": [],
                "trend": "NEUTRAL", "clustering": "NORMAL", "micro_spike": False}


def push_midnight_report(vmc_data: dict, whale_data: list, backtest: list,
                          credentials_json: str, sheet_id: str) -> bool:
    try:
        import json as _j, gspread
        from oauth2client.service_account import ServiceAccountCredentials
        creds_dict = _j.loads(credentials_json)
        if not creds_dict or not sheet_id: return False
        scopes = ["https://spreadsheets.google.com/feeds",
                  "https://www.googleapis.com/auth/drive"]
        creds  = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scopes)
        client = gspread.authorize(creds)
        sheet  = client.open_by_key(sheet_id)
        try: ws_arch = sheet.worksheet("ARCHIVE_LOG")
        except Exception: ws_arch = sheet.add_worksheet("ARCHIVE_LOG", rows=5000, cols=10)
        utc_ts   = time.strftime("%Y-%m-%d %H:%M:%S UTC")
        pkt_ts   = time.strftime("%Y-%m-%d %H:%M:%S PKT", time.gmtime(time.time() + 5 * 3600))
        wins     = sum(1 for b in backtest if b.get("result") == "WIN")
        losses   = sum(1 for b in backtest if b.get("result") == "LOSS")
        total    = wins + losses
        win_rate = round(wins / total * 100, 1) if total else 0
        summary  = [["MIDNIGHT REPORT", utc_ts, pkt_ts], ["Folder","Count"]]
        for k, v in vmc_data.items(): summary.append([k, len(v)])
        summary.extend([["Whale Signals", len(whale_data)],
                         ["Backtest Win%", win_rate], ["Wins", wins], ["Losses", losses]])
        ws_arch.append_rows(summary)
        log.info(f"Midnight report pushed — PKT:{pkt_ts} win_rate={win_rate}%")
        return True
    except Exception as e:
        log.error(f"Midnight report push failed: {e}"); return False
