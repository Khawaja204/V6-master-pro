"""
logic.py — V6 Master Pro Institutional Engine
VMC • Whale Wall • OBI • ATR • Traffic Light • Institutional Score
VWAP • RSI Divergence • Regime Detection • Confidence Score
All thresholds in config.json — no hardcoded values.
"""
import time
import logging
import threading
import requests
from requests.adapters import HTTPAdapter
try:
    from urllib3.util.retry import Retry
except Exception:  # pragma: no cover - fallback for older urllib3 layouts
    from requests.packages.urllib3.util.retry import Retry  # type: ignore

log = logging.getLogger(__name__)

# Binance hosts in priority order. If the primary fails (e.g. transient DNS
# "Failed to resolve api.binance.com"), requests automatically fail over to the
# next host so the data layer stays resilient to network blips.
BINANCE_HOSTS = [
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api-gcp.binance.com",
    "https://data-api.binance.vision",
]
BINANCE_BASE = BINANCE_HOSTS[0] + "/api/v3"   # kept for backward-compat references


def _build_session() -> requests.Session:
    """Shared session with automatic retries for transient connection/DNS/5xx errors."""
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

# Infrastructure-class statuses that mean "this host is unusable, try another".
_RETRYABLE_STATUS = {429, 451, 500, 502, 503, 504}

# ── Live connection-health tracking (read by /system_health) ────────────────────
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
    """Snapshot of the current Binance connectivity state."""
    with _health_lock:
        return dict(_BINANCE_HEALTH)


def _binance_get(path: str, params: dict = None, timeout: int = 10):
    """GET a Binance public endpoint with automatic host failover.

    `path` must start with `/api/v3/...`. A host counts as reachable when it
    returns any non-infrastructure status (2xx or a normal 4xx such as a bad
    symbol). Infrastructure-class statuses (429/451/5xx) and connection/DNS
    errors trigger failover to the next host. Returns the Response from a
    reachable host, or None if every host failed.
    """
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
        # Host responded with a usable status → genuinely reachable.
        _mark_health(True, host=host)
        return resp
    _mark_health(False, error=last_err)
    log.error(f"[BINANCE] All hosts unreachable. Last error: {last_err}")
    return None


def ping_binance(timeout: int = 6) -> bool:
    """Active connectivity probe. True only on a real 200 from /ping."""
    resp = _binance_get("/api/v3/ping", timeout=timeout)
    return bool(resp is not None and resp.status_code == 200)


def start_health_monitor(interval: int = 30) -> None:
    """Start a single background thread that probes Binance connectivity.

    Keeps the health snapshot fresh without doing network work inside the
    request path of /system_health (avoids request-latency / DoS amplification).
    Idempotent — repeated calls are no-ops.
    """
    global _monitor_started
    with _health_lock:
        if _monitor_started:
            return
        _monitor_started = True

    def _loop():
        while True:
            try:
                ping_binance()
            except Exception as e:  # pragma: no cover - defensive
                log.debug(f"health monitor ping error: {e}")
            time.sleep(interval)

    threading.Thread(target=_loop, daemon=True, name="binance-health").start()
    log.info(f"[HEALTH] Binance connectivity monitor started (every {interval}s)")


_obi_history: dict = {}   # symbol → [(ts, obi)]


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
    """Fetch current price for a single symbol. Used by backtest checker."""
    try:
        resp = _binance_get("/api/v3/ticker/price", params={"symbol": symbol}, timeout=5)
        if resp is not None and resp.status_code == 200:
            return float(resp.json()["price"])
    except Exception as e:
        log.debug(f"Price fetch failed for {symbol}: {e}")
    return 0.0


def calculate_rsi(closes: list, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains  = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]
    avg_g  = sum(gains[-period:]) / period
    avg_l  = sum(losses[-period:]) / period
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
    try:
        klines = fetch_klines(symbol, interval, period + 5)
        if len(klines) < 2:
            return 0.0
        trs = []
        for i in range(1, len(klines)):
            high = float(klines[i][2]); low = float(klines[i][3])
            close_prev = float(klines[i - 1][4])
            trs.append(max(high - low, abs(high - close_prev), abs(low - close_prev)))
        return round(sum(trs[-period:]) / min(len(trs), period), 8) if trs else 0.0
    except Exception:
        return 0.0


def compute_vwap(symbol: str, interval: str = "1h", limit: int = 24) -> float:
    """VWAP = Σ(typical_price × volume) / Σ(volume). Self-upgrade feature."""
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
    """Exponential moving average series."""
    if not values:
        return []
    k = 2.0 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def calculate_macd(closes: list, fast: int = 12, slow: int = 26,
                   signal: int = 9) -> dict:
    """Standard MACD(12,26,9). Returns macd line, signal line, histogram."""
    if len(closes) < slow + signal:
        return {"macd": 0.0, "signal": 0.0, "hist": 0.0}
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = _ema(macd_line, signal)
    hist = macd_line[-1] - signal_line[-1]
    return {"macd": round(macd_line[-1], 8),
            "signal": round(signal_line[-1], 8),
            "hist": round(hist, 8)}


def fetch_macd_for_symbol(symbol: str, interval: str = "1h",
                          limit: int = 60) -> dict:
    klines = fetch_klines(symbol, interval, limit)
    if not klines:
        return {"macd": 0.0, "signal": 0.0, "hist": 0.0}
    return calculate_macd([float(k[4]) for k in klines])


# ══════════════════════════════════════════════════════════════════════════════
# V6 FINAL SCORE — 54-POINT INSTITUTIONAL SCORING ENGINE
# Market Regime 10 + Institutional/Whale 12 + Technical 12 +
# Smart-Money Divergence 10 + Trade Engine 10 = 54 raw points, scaled to 0-100.
# ══════════════════════════════════════════════════════════════════════════════

def compute_v6_final_score(signal: dict, regime: str, btc_volatility_pct: float,
                           divergence_signal: str, in_volume_surge: bool) -> dict:
    inst  = signal.get("inst", {}) or {}
    tp    = signal.get("tp_zones", {}) or {}
    rsi   = signal.get("rsi", 50) or 50
    chg   = signal.get("change_pct", 0) or 0
    price = signal.get("price", 0) or 0
    macd_hist = signal.get("macd_hist", 0) or 0

    # 1 ── MARKET REGIME (10): trend (5) + volatility quality (5)
    reg_trend = {"TRENDING": 3, "RANGING": 2, "VOLATILE": 1}.get(regime, 2)
    reg_trend += 2 if chg > 0.5 else 1 if chg >= -0.5 else 0
    reg_trend = min(5, reg_trend)
    v = abs(btc_volatility_pct or 0)
    reg_vol = 5 if v < 2 else 3 if v < 4 else 2 if v < 6 else 1
    market_regime = reg_trend + reg_vol

    # 2 ── INSTITUTIONAL / WHALE (12): accumulation (6) + wall support (6)
    inst_score  = inst.get("inst_score", 0) or 0
    whale_power = inst.get("whale_power", 0) or 0
    inst_whale  = (inst_score / 100 * 6) + (whale_power / 100 * 6)

    # 3 ── TECHNICAL (12): RSI (4) + MACD (4) + Volume surge (4)
    if 40 <= rsi <= 55:
        rsi_pts = 4
    elif 55 < rsi <= 62 or 35 <= rsi < 40:
        rsi_pts = 3
    elif 30 <= rsi < 35:
        rsi_pts = 2
    elif rsi > 70 or rsi < 25:
        rsi_pts = 0
    else:
        rsi_pts = 1
    macd_rel = (macd_hist / price * 100) if price else 0
    if macd_rel > 0.05:
        macd_pts = 4
    elif macd_rel > 0:
        macd_pts = 3
    elif macd_rel == 0:
        macd_pts = 2
    elif macd_rel > -0.05:
        macd_pts = 1
    else:
        macd_pts = 0
    vol_pts   = 4 if in_volume_surge else 1
    technical = rsi_pts + macd_pts + vol_pts

    # 4 ── SMART-MONEY DIVERGENCE (10): order-flow (6) + price/volume div (4)
    ofi = inst.get("ofi_score", 50) or 50
    if divergence_signal == "ACCUMULATION":
        div_pts = 4
    elif divergence_signal == "DISTRIBUTION":
        div_pts = 0
    else:
        div_pts = 2
    smart_divergence = (ofi / 100 * 6) + div_pts

    # 5 ── TRADE ENGINE (10): R/R ratio (5) + execution traffic light (5)
    entry  = tp.get("entry_low") or price
    sl     = tp.get("stop_loss") or 0
    tp1    = tp.get("tp1") or 0
    risk   = entry - sl
    reward = tp1 - entry
    rr     = reward / risk if risk > 0 else 0
    if rr >= 2:
        rr_pts = 5
    elif rr >= 1.5:
        rr_pts = 4
    elif rr >= 1:
        rr_pts = 3
    elif rr > 0:
        rr_pts = 1
    else:
        rr_pts = 0
    traffic = inst.get("traffic", "RED")
    tr_pts  = 5 if traffic == "GREEN" else 2 if traffic == "YELLOW" else 0
    trade_engine = rr_pts + tr_pts

    raw   = market_regime + inst_whale + technical + smart_divergence + trade_engine
    score = max(0, min(100, round(raw / 54 * 100)))
    if score >= 68:
        label, badge = "BUY", "badge-buy"
    elif score >= 45:
        label, badge = "WAIT", "badge-wait"
    else:
        label, badge = "SELL", "badge-sell"
    return {
        "score": score,
        "raw":   round(raw, 1),
        "rr":    round(rr, 2),
        "label": label,
        "badge": badge,
        "breakdown": {
            "market_regime":    round(market_regime, 1),
            "inst_whale":       round(inst_whale, 1),
            "technical":        round(technical, 1),
            "smart_divergence": round(smart_divergence, 1),
            "trade_engine":     round(trade_engine, 1),
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# HISTORICAL BACKTESTER (Binance /api/v3/klines — no external data source needed)
# ══════════════════════════════════════════════════════════════════════════════

def fetch_klines_range(symbol: str, interval: str, start_ms: int,
                       end_ms: int) -> list:
    """Paginate Binance klines (max 1000/request) across an arbitrary range."""
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
    rsis = [50.0] * len(closes)
    for i in range(period, len(closes)):
        rsis[i] = calculate_rsi(closes[i - period:i + 1], period)
    return rsis


def _atr_series(highs: list, lows: list, closes: list, period: int = 14) -> list:
    n = len(closes)
    trs = [0.0] * n
    for i in range(1, n):
        trs[i] = max(highs[i] - lows[i],
                     abs(highs[i] - closes[i - 1]),
                     abs(lows[i] - closes[i - 1]))
    atrs = [0.0] * n
    for i in range(period, n):
        atrs[i] = sum(trs[i - period + 1:i + 1]) / period
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
    """Replay a trend-pullback strategy with ATR targets + trailing stop +
    daily circuit-breaker over Binance kline history. Order-book/whale layers
    cannot be reconstructed from history, so this evaluates the technical +
    risk-management core only (documented in the returned `note`)."""
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
    timeout_bars = 48  # ~2 days on 1h candles

    # ── BTC trend filter (mirrors the live BTC gate) ──────────────────────────
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
                    e = closes[i]
                    a = atr[i]
                    pos = {
                        "entry_i": i, "entry_price": e,
                        "entry_time": time.strftime("%Y-%m-%d %H:%M",
                                                    time.gmtime(opens[i] / 1000)),
                        "sl":  e - sl_mult * a,
                        "tp1": e + tp1_m * a,
                        "tp2": e + tp2_m * a,
                        "tp3": e + tp3_m * a,
                        "tp1_hit": False, "tp2_hit": False, "tp3_hit": False,
                        "trailing": "",
                    }
                continue

            h, l, c = highs[i], lows[i], closes[i]
            # Conservative intrabar policy: OHLC gives no tick order, so first
            # test the candle low against the SL *as it stood entering the bar*
            # (before any TP-driven ratchet this same bar). This avoids the
            # optimistic bias of moving the stop up on a TP touch and then
            # pretending the same candle's dip respected the higher stop.
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
                all_trades.append({
                    "symbol": sym,
                    "entry_time": pos["entry_time"],
                    "exit_time": time.strftime("%Y-%m-%d %H:%M",
                                               time.gmtime(opens[i] / 1000)),
                    "exit_ts": opens[i],
                    "entry_price": round(pos["entry_price"], 8),
                    "exit_price": round(exit_price, 8),
                    "pnl_pct": round(pnl, 3),
                    "exit_reason": exit_reason,
                    "trailing": pos["trailing"] or "—",
                    "bars_held": i - pos["entry_i"],
                })
                sym_trades += 1
                pos = None
        per_symbol[sym] = {"trades": sym_trades}

    # ── Build compounding equity curve + metrics with daily circuit-breaker ───
    max_dd_pct = float(tm.get("daily_max_drawdown_pct", 10.0))
    all_trades.sort(key=lambda t: t["exit_ts"])
    equity = balance0; peak = balance0; max_dd = 0.0
    gross_p = 0.0; gross_l = 0.0; wins = 0; losses = 0; counted = 0; skipped = 0
    daily_losses: dict = {}
    daily_start_eq: dict = {}   # equity at the first trade of each UTC day
    curve = [{"t": time.strftime("%Y-%m-%d", time.gmtime(start_ms / 1000)),
              "equity": round(equity, 2)}]

    for tr in all_trades:
        day = tr["exit_time"][:10]
        day_open_eq = daily_start_eq.setdefault(day, equity)
        # Daily circuit-breaker: trip on too many losses OR too deep a daily
        # drawdown — mirrors the live _record_trade_result logic.
        day_dd = (day_open_eq - equity) / day_open_eq * 100.0 if day_open_eq else 0.0
        if daily_losses.get(day, 0) >= max_dl or day_dd >= max_dd_pct:
            tr["counted"] = False; skipped += 1
            continue
        size = equity * risk_pct / 100.0
        pnl_usdt = size * tr["pnl_pct"] / 100.0
        equity += pnl_usdt
        counted += 1
        tr["counted"] = True
        tr["equity_after"] = round(equity, 2)
        if tr["pnl_pct"] > 0:
            wins += 1; gross_p += pnl_usdt
        else:
            losses += 1; gross_l += abs(pnl_usdt)
            daily_losses[day] = daily_losses.get(day, 0) + 1
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak * 100.0)
        curve.append({"t": tr["exit_time"], "equity": round(equity, 2)})

    win_rate = round(wins / counted * 100, 1) if counted else 0.0
    profit_factor = round(gross_p / gross_l, 2) if gross_l > 0 else (
        float("inf") if gross_p > 0 else 0.0)
    net_return = round((equity - balance0) / balance0 * 100, 2) if balance0 else 0.0

    return {
        "generated":      time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "symbols":        symbols,
        "months":         months,
        "interval":       interval,
        "start":          time.strftime("%Y-%m-%d", time.gmtime(start_ms / 1000)),
        "end":            time.strftime("%Y-%m-%d", time.gmtime(now_ms / 1000)),
        "total_trades":   counted,
        "skipped_by_circuit_breaker": skipped,
        "wins":           wins,
        "losses":         losses,
        "win_rate":       win_rate,
        "profit_factor":  (round(profit_factor, 2)
                           if profit_factor != float("inf") else 999.0),
        "max_drawdown_pct": round(max_dd, 2),
        "net_return_pct": net_return,
        "start_equity":   round(balance0, 2),
        "end_equity":     round(equity, 2),
        "equity_curve":   curve,
        "per_symbol":     per_symbol,
        "trades":         all_trades,
        "note": ("Technical + risk-management core (RSI pullback in uptrend, "
                 "ATR targets, trailing stop, daily circuit-breaker, BTC trend "
                 "filter). Order-book/whale layers are excluded — Binance does "
                 "not serve historical depth snapshots."),
    }


def detect_rsi_divergence(klines: list) -> str:
    """
    Self-upgrade feature: simple 2-point RSI divergence.
    BULLISH_DIV: price lower low but RSI higher low (reversal signal).
    BEARISH_DIV: price higher high but RSI lower high (exhaustion signal).
    """
    if len(klines) < 20:
        return "NONE"
    try:
        closes = [float(k[4]) for k in klines]
        mid    = len(closes) // 2
        rsi_e  = calculate_rsi(closes[:mid + 14])
        rsi_l  = calculate_rsi(closes)
        p_e    = closes[mid - 1]
        p_l    = closes[-1]
        if p_l < p_e and rsi_l > rsi_e:
            return "BULLISH_DIV"
        if p_l > p_e and rsi_l < rsi_e:
            return "BEARISH_DIV"
        return "NONE"
    except Exception:
        return "NONE"


def detect_market_regime(btc_volatility_pct: float, btc_change_pct: float) -> str:
    """Self-upgrade: BTC market regime — TRENDING / RANGING / VOLATILE."""
    if abs(btc_volatility_pct) > 4.0 or abs(btc_change_pct) > 3.0:
        return "VOLATILE"
    if abs(btc_change_pct) > 1.5:
        return "TRENDING"
    return "RANGING"


def price_position_rsi(ticker: dict) -> float:
    try:
        high = float(ticker["highPrice"]); low = float(ticker["lowPrice"])
        last = float(ticker["lastPrice"])
        if high == low:
            return 50.0
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
        "spike":    vel >= threshold,
        "velocity": round(vel, 3),
        "obi":      current_obi,
        "direction": "BUY_PRESSURE" if current_obi > 0 else "SELL_PRESSURE",
    }


# ══════════════════════════════════════════════════════════════════════════════
# INSTITUTIONAL SCORE & CONFIDENCE
# ══════════════════════════════════════════════════════════════════════════════

def compute_whale_power(walls: list, spoofing: dict, blink_to_push: bool, price: float, config: dict) -> float:
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


def compute_institutional_score(vmc_score: int, whale_power: float, ofi_result: dict, walls: list, config: dict) -> dict:
    cfg         = config["institutional"]
    bonus_thresh = cfg["wall_proximity_bonus_threshold"]
    ofi_score   = max(0.0, min(100.0, (ofi_result.get("obi", 0) + 1) * 50))
    base        = (whale_power * cfg["whale_power_weight"]) + (vmc_score * cfg["vmc_score_weight"]) + (ofi_score * cfg["ofi_weight"])
    wall_bonus  = base * cfg["wall_proximity_bonus_pct"] if (walls and min(w["dist_pct"] for w in walls) <= bonus_thresh) else 0.0
    final       = min(round(base + wall_bonus, 1), 100.0)
    vmc_bullish  = vmc_score >= 70
    ofi_momentum = ofi_result.get("obi", 0) > 0.1
    wall_proximal = bool(walls and min(w["dist_pct"] for w in walls) <= bonus_thresh)
    confirms     = sum([vmc_bullish, ofi_momentum, wall_proximal])
    critical     = config["whale"]["critical_whale_power_pct"]
    yellow       = cfg["yellow_light_whale_power"]
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
        "vmc_score": vmc_score, "traffic": light, "spike": spike, "confirms": confirms, "reason": reason,
    }


def compute_confidence_score(inst_result: dict, obi_result: dict, vmc_score: int) -> int:
    """
    Signal Confidence Score 0-100:
    Traffic Light (35) + Confirms (24 max) + OBI Spike (15) + VMC (16 max) + WhalePow (10 max)
    """
    score = 0
    tl = inst_result.get("traffic", "RED")
    score += 35 if tl == "GREEN" else 17 if tl == "YELLOW" else 0
    score += min(24, inst_result.get("confirms", 0) * 8)
    if obi_result and obi_result.get("spike"):
        score += 15
    score += min(16, int(vmc_score / 100 * 16))
    score += min(10, int(inst_result.get("whale_power", 0) / 100 * 10))
    return min(100, max(0, score))


def compute_tp_levels(price: float, atr: float, config: dict) -> dict:
    if atr == 0:
        return {"entry_low": price, "entry_high": price, "stop_loss": price,
                "tp1": price, "tp2": price, "tp3": price, "atr": 0, "risk_pct": 0}
    cfg = config["institutional"]
    return {
        "atr":        round(atr, 8),
        "entry_low":  round(price - 0.3 * atr, 8),
        "entry_high": round(price + 0.3 * atr, 8),
        "stop_loss":  round(price - cfg["atr_stop_loss_multiplier"] * atr, 8),
        "tp1":        round(price + cfg["tp1_atr_multiplier"] * atr, 8),
        "tp2":        round(price + cfg["tp2_atr_multiplier"] * atr, 8),
        "tp3":        round(price + cfg["tp3_atr_multiplier"] * atr, 8),
        "risk_pct":   round(cfg["atr_stop_loss_multiplier"] * atr / price * 100, 3),
    }


def compute_position_size(inst_score_result: dict, config: dict) -> dict:
    risk_cfg = config["risk"]
    balance  = risk_cfg["account_balance_usdt"]
    light    = inst_score_result.get("traffic", "RED")
    if light == "GREEN":
        pct, usdt, note = risk_cfg["green_signal_max_pct"], round(balance * risk_cfg["green_signal_max_pct"] / 100, 2), f"GREEN — {risk_cfg['green_signal_max_pct']}% of balance"
    elif light == "YELLOW":
        pct, usdt, note = risk_cfg["yellow_signal_max_pct"], round(balance * risk_cfg["yellow_signal_max_pct"] / 100, 2), "YELLOW — minimal (25% of GREEN)"
    else:
        pct, usdt, note = 0.0, 0.0, "RED — no trade"
    return {"light": light, "alloc_pct": pct, "alloc_usdt": usdt, "balance": balance, "note": note}


# ══════════════════════════════════════════════════════════════════════════════
# VMC SIGNAL ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def score_coin(ticker: dict, rsi: float, config: dict) -> int:
    try:
        change    = float(ticker["priceChangePercent"])
        volume    = float(ticker["quoteVolume"])
        high      = float(ticker["highPrice"]); low = float(ticker["lowPrice"]); last = float(ticker["lastPrice"])
        price_pos = (last - low) / (high - low + 1e-9) * 100
    except Exception:
        return 0
    score = 0
    if change > 5: score += 30
    elif change > 2: score += 22
    elif change > 0.5: score += 14
    elif change > -1: score += 8
    if volume > 50_000_000: score += 25
    elif volume > 10_000_000: score += 20
    elif volume > 2_000_000: score += 14
    elif volume > 500_000: score += 8
    if 40 <= price_pos <= 75: score += 25
    elif 25 <= price_pos < 40: score += 18
    elif price_pos > 75: score += 12
    else: score += 6
    if 40 <= rsi <= 60: score += 20
    elif 35 <= rsi < 40 or 60 < rsi <= 65: score += 14
    elif 30 <= rsi < 35 or 65 < rsi <= 70: score += 8
    return min(score, 100)


def categorize_signals(tickers: list, rsi_map: dict, config: dict) -> dict:
    cfg   = config["vmc"]; thresh = cfg["score_threshold"]; favs = set(cfg["favorite_coins"])
    out   = {k: [] for k in ["ALL","FAV","STUCK","GOLDEN","BOOM","ENTRY","EXIT","PUMP","VIP"]}
    for t in tickers:
        symbol = t["symbol"]; rsi = rsi_map.get(symbol, price_position_rsi(t)); score = score_coin(t, rsi, config)
        if score < thresh:
            continue
        try:
            change = float(t["priceChangePercent"]); volume = float(t["quoteVolume"])
            high = float(t["highPrice"]); low = float(t["lowPrice"]); last = float(t["lastPrice"])
            price_pos = (last - low) / (high - low + 1e-9) * 100
        except Exception:
            continue
        coin = {
            "symbol": symbol, "price": float(t["lastPrice"]), "change_pct": round(change, 2),
            "volume_usdt": round(float(t["quoteVolume"]), 0), "rsi": rsi, "score": score,
            "high_24h": float(t["highPrice"]), "low_24h": float(t["lowPrice"]),
            "price_pos_pct": round(price_pos, 1),
        }
        out["ALL"].append(coin)
        if symbol in favs:
            out["FAV"].append(coin)
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
        sizes = [float(l[1]) for l in levels]; top = sizes[0]; avg = sum(sizes[1:]) / len(sizes[1:])
        if avg == 0: return False, 0.0
        ratio = top / avg
        return ratio >= ratio_thresh, round(ratio, 2)
    bid_spoof, bid_ratio = _check(bids); ask_spoof, ask_ratio = _check(asks)
    detail = []
    if bid_spoof: detail.append(f"Fake BID wall (×{bid_ratio})")
    if ask_spoof: detail.append(f"Fake ASK wall (×{ask_ratio})")
    return {"bid_spoof": bid_spoof, "ask_spoof": ask_spoof, "bid_ratio": bid_ratio,
            "ask_ratio": ask_ratio, "details": " | ".join(detail) if detail else "Clean"}


def calculate_wall_proximity(price: float, book: dict, config: dict) -> list:
    prox_pct = config["whale"]["wall_proximity_pct"]; min_size = config["whale"]["min_wall_size_usdt"]; walls = []
    for side, levels in [("BID", book.get("bids", [])), ("ASK", book.get("asks", []))]:
        for level in levels:
            try:
                lp = float(level[0]); lq = float(level[1]); lu = lp * lq
            except (IndexError, ValueError): continue
            if lu < min_size: continue
            dist = abs(lp - price) / price * 100
            if dist <= prox_pct:
                walls.append({"side": side, "price_level": round(lp, 6), "size_usdt": round(lu, 0), "dist_pct": round(dist, 3)})
    walls.sort(key=lambda x: x["dist_pct"])
    return walls


def blink_to_push_check(symbol: str, current_walls: list, previous_walls: dict, config: dict) -> bool:
    push_thresh = config["whale"]["blink_push_proximity_pct"]
    prev = previous_walls.get(symbol, [])
    if not prev or not current_walls: return False
    prev_min = min((w["dist_pct"] for w in prev), default=99)
    curr_min = min((w["dist_pct"] for w in current_walls), default=99)
    return curr_min < prev_min and curr_min <= push_thresh


def process_whale_walls(config: dict, price_map: dict, previous_walls: dict) -> list:
    top_n = config["whale"]["top_coins_for_whale"]; depth = config["whale"]["order_book_depth"]; results = []
    for i, symbol in enumerate(list(price_map.keys())[:top_n]):
        price = price_map.get(symbol, 0)
        if not price: continue
        book   = fetch_order_book(symbol, depth)
        walls  = calculate_wall_proximity(price, book, config)
        spoof  = detect_spoofing(book.get("bids", []), book.get("asks", []), config)
        b2push = blink_to_push_check(symbol, walls, previous_walls, config)
        obi    = calculate_obi(book)
        obi_r  = detect_obi_spike(symbol, obi, config)
        whale_power = compute_whale_power(walls, spoof, b2push, price, config)
        if walls or spoof["bid_spoof"] or spoof["ask_spoof"] or b2push:
            label = "WHALE TRAP" if (spoof["bid_spoof"] or spoof["ask_spoof"]) else "BLINK→PUSH" if b2push else "WALL"
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
# BTC SENTIMENT + REGIME
# ══════════════════════════════════════════════════════════════════════════════

def fetch_btc_sentiment() -> dict:
    try:
        resp = _binance_get("/api/v3/ticker/24hr", params={"symbol": "BTCUSDT"}, timeout=8)
        if resp is None:
            raise RuntimeError("all Binance hosts unreachable")
        resp.raise_for_status()
        t  = resp.json()
        change     = float(t["priceChangePercent"]); price = float(t["lastPrice"])
        high       = float(t["highPrice"]); low = float(t["lowPrice"])
        volatility = (high - low) / low * 100 if low else 0
        pause      = change <= -2.0 or volatility > 5.0
        sentiment  = "BEARISH" if pause else "BULLISH" if change >= 2.0 else "NEUTRAL"
        regime     = detect_market_regime(volatility, change)
        return {
            "price": price, "change_pct": round(change, 2), "volume": round(float(t["quoteVolume"]), 0),
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

def push_to_google_sheets(vmc_data: dict, whale_data: list, credentials_json: str, sheet_id: str) -> bool:
    try:
        import json as _json, gspread
        from oauth2client.service_account import ServiceAccountCredentials
        creds_dict = _json.loads(credentials_json)
        if not creds_dict or not sheet_id: return False
        scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds  = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scopes)
        client = gspread.authorize(creds)
        sheet  = client.open_by_key(sheet_id)

        try: ws_live = sheet.worksheet("LIVE_DASHBOARD")
        except Exception: ws_live = sheet.add_worksheet("LIVE_DASHBOARD", rows=1100, cols=15)

        try: existing_headers = ws_live.row_values(1)
        except Exception: existing_headers = []
        std_headers = ["Timestamp","Asset","Status","Signal","VMC","Price","Buy/Sale","Heatmap","Slack","Chg%","RSI","Flux","Sentiment","Log"]
        for h in existing_headers:
            if h and h not in std_headers: std_headers.append(h)

        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        rows = [std_headers]
        for folder, coins in vmc_data.items():
            for coin in coins[:20]:
                row = {"Timestamp": ts, "Asset": coin["symbol"], "Status": "ACTIVE", "Signal": folder,
                       "VMC": coin["score"], "Price": coin["price"],
                       "Buy/Sale": "BUY" if folder in ["ENTRY","GOLDEN","VIP"] else "WATCH",
                       "Heatmap": "HOT" if coin["volume_usdt"] > 10_000_000 else "WARM",
                       "Slack": "", "Chg%": coin["change_pct"], "RSI": coin["rsi"],
                       "Flux": coin["price_pos_pct"], "Sentiment": "", "Log": f"Score:{coin['score']}"}
                rows.append([row.get(h, "") for h in std_headers])

        try:
            all_vals = ws_live.get_all_values()
            if len(all_vals) > 1000:
                try: ws_arch = sheet.worksheet("ARCHIVE_LOG")
                except Exception: ws_arch = sheet.add_worksheet("ARCHIVE_LOG", rows=5000, cols=15)
                ws_arch.append_rows(all_vals[1:len(all_vals)-500])
        except Exception: pass
        ws_live.clear(); ws_live.update("A1", rows)

        try: ws_watch = sheet.worksheet("WATCH")
        except Exception: ws_watch = sheet.add_worksheet("WATCH", rows=200, cols=9)
        wrows = [["Symbol","Price","Label","BlinkPush","BidSpoof","AskSpoof","WallCount","MinDist%","WhalePower"]]
        for w in whale_data[:100]:
            wrows.append([w["symbol"], w["price"], w["label"], w["blink_to_push"],
                          w["spoofing"]["bid_spoof"], w["spoofing"]["ask_spoof"],
                          w["wall_count"], w["min_dist_pct"], w.get("whale_power", 0)])
        ws_watch.clear(); ws_watch.update("A1", wrows)

        # ARCHIVE_LOG — ensure tab always exists; append rows when LIVE > 1000
        try: ws_arch = sheet.worksheet("ARCHIVE_LOG")
        except Exception: ws_arch = sheet.add_worksheet("ARCHIVE_LOG", rows=5000, cols=15)
        try:
            all_live = ws_live.get_all_values()
            if len(all_live) > 1000:
                ws_arch.append_rows(all_live[1:len(all_live)-500])
        except Exception: pass

        # USERS — sync from local clients.json so the tab always reflects registered clients
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
            urows.append([
                c.get("name",""), c.get("uid",""), c.get("password",""),
                c.get("status","ACTIVE"), c.get("expiry","UNLIMITED"),
                c.get("sig_limit","100"), c.get("role","CLIENT"), c.get("added",""),
            ])
        ws_users.clear()
        if urows: ws_users.update("A1", urows)

        log.info(f"Sheets updated — {len(rows)-1} LIVE_DASHBOARD, {len(wrows)-1} WATCH, {len(urows)-1} USERS rows.")
        return True
    except ImportError:
        log.warning("gspread/oauth2client not installed — Sheets push skipped."); return False
    except Exception as e:
        log.error(f"Google Sheets push failed: {e}"); return False


def match_whale_pattern(obi: float, whale_power: float, trend: str,
                        blink_to_push: bool, walls: list) -> dict:
    """
    Score current whale signature against 4 institutional patterns.
    Returns best match with similarity % and optional [WHALE PATTERN MATCH] tag.
    """
    has_bid = any(w["side"] == "BID" for w in walls)
    has_ask = any(w["side"] == "ASK" for w in walls)
    patterns = {
        "ACCUMULATION_ZONE": [
            (obi > 0.05,           35),
            (whale_power >= 40,    30),
            (trend == "ACCUMULATION", 25),
            (has_bid,              10),
        ],
        "DISTRIBUTION_ZONE": [
            (obi < -0.05,          35),
            (whale_power >= 40,    30),
            (trend == "DISTRIBUTION", 25),
            (has_ask,              10),
        ],
        "PUMP_PREPARATION": [
            (blink_to_push,        40),
            (obi > 0.1,            35),
            (whale_power >= 50,    25),
        ],
        "DUMP_PREPARATION": [
            (obi < -0.1,           40),
            (has_ask,              35),
            (not blink_to_push,    15),
            (trend == "DISTRIBUTION", 10),
        ],
    }
    best_name, best_score = "UNCLEAR", 0
    for name, criteria in patterns.items():
        max_pts = sum(pts for _, pts in criteria)
        got_pts = sum(pts for cond, pts in criteria if cond)
        pct     = round(got_pts / max_pts * 100) if max_pts else 0
        if pct > best_score:
            best_score = pct; best_name = name
    return {
        "name":           best_name,
        "similarity_pct": best_score,
        "tag":            "[WHALE PATTERN MATCH]" if best_score >= 75 else "",
    }


def compute_whale_detail(symbol: str, price: float, ticker_24h: dict, config: dict) -> dict:
    """
    Full institutional whale analysis for a single coin (called on-demand).
    Computes: bag size, avg buy/sell price, inflow/outflow, OBI velocity,
    micro-spike, clustering, pattern match — all from live order book.
    """
    try:
        book  = fetch_order_book(symbol, depth=20)
        bids  = book.get("bids", [])
        asks  = book.get("asks", [])

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
            velocity  = 0.0
            micro_spk = False

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

        import time as _t
        now = _t.time()
        spike_cnt = sum(
            1 for s, h in _obi_history.items()
            if s != symbol and len(h) >= 2 and now - h[-1][0] < 300
            and len(h) >= 2 and abs(h[-1][1] - sum(v for _, v in h[:-1]) / len(h[:-1])) > 0.1
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
        scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds  = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scopes)
        client = gspread.authorize(creds)
        sheet  = client.open_by_key(sheet_id)
        try: ws_arch = sheet.worksheet("ARCHIVE_LOG")
        except Exception: ws_arch = sheet.add_worksheet("ARCHIVE_LOG", rows=5000, cols=10)
        utc_ts = time.strftime("%Y-%m-%d %H:%M:%S UTC")
        pkt_ts = time.strftime("%Y-%m-%d %H:%M:%S PKT", time.gmtime(time.time() + 5 * 3600))
        wins   = sum(1 for b in backtest if b.get("result") == "WIN")
        losses = sum(1 for b in backtest if b.get("result") == "LOSS")
        total  = wins + losses
        win_rate = round(wins / total * 100, 1) if total else 0
        summary = [["MIDNIGHT REPORT", utc_ts, pkt_ts], ["Folder","Count"]]
        for k, v in vmc_data.items(): summary.append([k, len(v)])
        summary.extend([["Whale Signals", len(whale_data)],
                         ["Backtest Win%", win_rate], ["Wins", wins], ["Losses", losses]])
        ws_arch.append_rows(summary)
        log.info(f"Midnight report pushed — UTC:{utc_ts} PKT:{pkt_ts} win_rate={win_rate}%")
        return True
    except Exception as e:
        log.error(f"Midnight report push failed: {e}"); return False
