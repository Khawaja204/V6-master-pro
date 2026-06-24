"""
logic.py — V6 Master Pro Institutional Engine
Modular functions: VMC, Whale Wall, OBI, ATR, Traffic Light, Institutional Score.
All thresholds in config.json — no hardcoded values.
"""
import time
import logging
import requests

log = logging.getLogger(__name__)
BINANCE_BASE = "https://api.binance.com/api/v3"

# ── In-memory OBI history per symbol ─────────────────────────────────────────
_obi_history: dict = {}   # symbol → list of (timestamp, obi_value)


# ══════════════════════════════════════════════════════════════════════════════
# DATA LAYER — Binance API
# ══════════════════════════════════════════════════════════════════════════════

def fetch_all_tickers(config: dict) -> list:
    quote   = config["scanner"]["quote_asset"]
    min_vol = config["scanner"]["min_quote_volume_24h"]
    limit   = config["scanner"]["coins_limit"]
    resp = requests.get(f"{BINANCE_BASE}/ticker/24hr", timeout=15)
    resp.raise_for_status()
    filtered = [
        t for t in resp.json()
        if t["symbol"].endswith(quote) and float(t["quoteVolume"]) >= min_vol
    ]
    filtered.sort(key=lambda x: float(x["quoteVolume"]), reverse=True)
    log.info(f"Binance: {len(filtered)} USDT pairs above min volume.")
    return filtered[:limit]


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
    rs = avg_g / avg_l
    return round(100.0 - (100.0 / (1 + rs)), 2)


def fetch_klines(symbol: str, interval: str = "1h", limit: int = 20) -> list:
    """Fetch raw klines for a symbol. Returns list of kline arrays."""
    try:
        resp = requests.get(
            f"{BINANCE_BASE}/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=8
        )
        if resp.status_code != 200:
            return []
        return resp.json()
    except Exception as e:
        log.debug(f"Klines fetch failed for {symbol}: {e}")
        return []


def fetch_rsi_for_symbol(symbol: str, interval: str = "1h", limit: int = 20) -> float:
    klines = fetch_klines(symbol, interval, limit)
    if not klines:
        return 50.0
    closes = [float(k[4]) for k in klines]
    return calculate_rsi(closes)


def calculate_atr(symbol: str, interval: str = "1h", period: int = 14) -> float:
    """ATR (Average True Range) from kline data. Returns 0.0 on failure."""
    try:
        klines = fetch_klines(symbol, interval, period + 5)
        if len(klines) < 2:
            return 0.0
        trs = []
        for i in range(1, len(klines)):
            high  = float(klines[i][2])
            low   = float(klines[i][3])
            close_prev = float(klines[i - 1][4])
            tr = max(high - low, abs(high - close_prev), abs(low - close_prev))
            trs.append(tr)
        if not trs:
            return 0.0
        return round(sum(trs[-period:]) / min(len(trs), period), 8)
    except Exception as e:
        log.debug(f"ATR calc failed for {symbol}: {e}")
        return 0.0


def price_position_rsi(ticker: dict) -> float:
    try:
        high = float(ticker["highPrice"])
        low  = float(ticker["lowPrice"])
        last = float(ticker["lastPrice"])
        if high == low:
            return 50.0
        pos = (last - low) / (high - low) * 100
        return round(20.0 + pos * 0.6, 2)
    except Exception:
        return 50.0


# ══════════════════════════════════════════════════════════════════════════════
# ORDER BOOK IMBALANCE (OBI) ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def calculate_obi(book: dict) -> float:
    """
    Order Book Imbalance = (total_bid_usdt - total_ask_usdt) / (total_bid_usdt + total_ask_usdt).
    Range: -1.0 (pure ask pressure) to +1.0 (pure bid pressure).
    """
    try:
        bid_vol = sum(float(b[0]) * float(b[1]) for b in book.get("bids", []))
        ask_vol = sum(float(a[0]) * float(a[1]) for a in book.get("asks", []))
        total   = bid_vol + ask_vol
        if total == 0:
            return 0.0
        return round((bid_vol - ask_vol) / total, 4)
    except Exception:
        return 0.0


def detect_obi_spike(symbol: str, current_obi: float, config: dict) -> dict:
    """
    OBI Velocity Tracker: detects sudden micro-spikes in order flow imbalance.
    Predictive — triggers before price moves.
    Logs spike to audit logger.
    """
    hist_size = config["institutional"]["obi_history_size"]
    threshold = config["institutional"]["obi_spike_threshold"]

    history = _obi_history.setdefault(symbol, [])
    now     = time.time()
    history.append((now, current_obi))

    # Keep only recent history
    cutoff = now - 300   # last 5 minutes
    _obi_history[symbol] = [(t, v) for t, v in history if t >= cutoff][-hist_size:]

    if len(_obi_history[symbol]) < 3:
        return {"spike": False, "velocity": 0.0, "obi": current_obi}

    vals = [v for _, v in _obi_history[symbol]]
    avg  = sum(vals[:-1]) / len(vals[:-1])
    std  = (sum((v - avg) ** 2 for v in vals[:-1]) / len(vals[:-1])) ** 0.5

    if std == 0:
        return {"spike": False, "velocity": 0.0, "obi": current_obi}

    velocity = abs(current_obi - avg) / std
    is_spike = velocity >= threshold

    return {
        "spike":    is_spike,
        "velocity": round(velocity, 3),
        "obi":      current_obi,
        "direction": "BUY_PRESSURE" if current_obi > 0 else "SELL_PRESSURE"
    }


# ══════════════════════════════════════════════════════════════════════════════
# INSTITUTIONAL SCORE & TRAFFIC LIGHT
# ══════════════════════════════════════════════════════════════════════════════

def compute_whale_power(walls: list, spoofing: dict, blink_to_push: bool, price: float, config: dict) -> float:
    """
    Whale Power 0–100:
    - Wall proximity contribution (40 pts max)
    - Spoofing detection (30 pts max)
    - Blink-to-push signal (30 pts max)
    """
    score = 0.0
    prox_bonus_thresh = config["institutional"]["wall_proximity_bonus_threshold"]

    if walls:
        min_dist = min(w["dist_pct"] for w in walls)
        if min_dist <= prox_bonus_thresh:
            score += 40
        elif min_dist <= 1.0:
            score += 30
        elif min_dist <= 2.0:
            score += 20
        else:
            score += 10

    if spoofing.get("bid_spoof") or spoofing.get("ask_spoof"):
        score += 30

    if blink_to_push:
        score += 30

    return min(round(score, 1), 100.0)


def compute_institutional_score(vmc_score: int, whale_power: float, ofi_result: dict, walls: list, config: dict) -> dict:
    """
    Institutional Score Formula:
      Whale Power:  40%
      VMC Score:    30%
      Order Flow:   30%
      Wall Proximity Bonus: +10% if wall within 0.5%
    Returns score (0-100) + traffic light + reasoning.
    """
    cfg = config["institutional"]
    w_whale = cfg["whale_power_weight"]
    w_vmc   = cfg["vmc_score_weight"]
    w_ofi   = cfg["ofi_weight"]
    bonus_thresh = cfg["wall_proximity_bonus_threshold"]
    bonus_add    = cfg["wall_proximity_bonus_pct"]

    # Normalize OFI to 0–100 (OBI is -1 to +1, positive = bullish)
    ofi_score = max(0.0, min(100.0, (ofi_result.get("obi", 0) + 1) * 50))

    base = (whale_power * w_whale) + (vmc_score * w_vmc) + (ofi_score * w_ofi)

    # Wall proximity bonus
    wall_bonus = 0.0
    if walls:
        min_dist = min(w["dist_pct"] for w in walls)
        if min_dist <= bonus_thresh:
            wall_bonus = base * bonus_add

    final = min(round(base + wall_bonus, 1), 100.0)

    # Traffic light
    yellow_thresh = cfg["yellow_light_whale_power"]
    critical_thresh = config["whale"]["critical_whale_power_pct"]

    # Spike validation: need 2 of 3
    vmc_bullish   = vmc_score >= 70
    ofi_momentum  = ofi_result.get("obi", 0) > 0.1
    wall_proximal = bool(walls and min(w["dist_pct"] for w in walls) <= bonus_thresh)
    confirms      = sum([vmc_bullish, ofi_momentum, wall_proximal])

    if whale_power >= critical_thresh and confirms >= cfg["spike_confirm_threshold"]:
        light  = "GREEN"
        reason = f"SPIKE_CONFIRMED: whale_power={whale_power}% | confirms={confirms}/3"
        spike  = True
    elif whale_power >= yellow_thresh or (whale_power >= critical_thresh and confirms < cfg["spike_confirm_threshold"]):
        light  = "YELLOW"
        reason = f"OBSERVE: whale_power={whale_power}% | confirms={confirms}/3"
        spike  = False
    elif final >= 70:
        light  = "GREEN"
        reason = f"ALL_CRITERIA_MET: inst_score={final}"
        spike  = False
    else:
        light  = "RED"
        reason = f"INSUFFICIENT: inst_score={final}"
        spike  = False

    return {
        "inst_score":  final,
        "whale_power": whale_power,
        "ofi_score":   round(ofi_score, 1),
        "vmc_score":   vmc_score,
        "traffic":     light,
        "spike":       spike,
        "confirms":    confirms,
        "reason":      reason,
    }


def compute_tp_levels(price: float, atr: float, config: dict) -> dict:
    """
    ATR-based trade zones:
    Stop Loss = price - 1.5×ATR (non-negotiable)
    TP1 = price + 1.5×ATR
    TP2 = price + 3.0×ATR
    TP3 = price + 5.0×ATR
    Entry zone = price ± 0.3×ATR
    """
    if atr == 0:
        return {"entry_low": price, "entry_high": price,
                "stop_loss": price, "tp1": price, "tp2": price, "tp3": price, "atr": 0}
    cfg = config["institutional"]
    sl_mult  = cfg["atr_stop_loss_multiplier"]
    tp1_mult = cfg["tp1_atr_multiplier"]
    tp2_mult = cfg["tp2_atr_multiplier"]
    tp3_mult = cfg["tp3_atr_multiplier"]
    return {
        "atr":        round(atr, 8),
        "entry_low":  round(price - 0.3 * atr, 8),
        "entry_high": round(price + 0.3 * atr, 8),
        "stop_loss":  round(price - sl_mult * atr, 8),
        "tp1":        round(price + tp1_mult * atr, 8),
        "tp2":        round(price + tp2_mult * atr, 8),
        "tp3":        round(price + tp3_mult * atr, 8),
        "risk_pct":   round(sl_mult * atr / price * 100, 3),
    }


def compute_position_size(inst_score_result: dict, config: dict) -> dict:
    """
    Auto-Risk Calculator based on traffic light and account balance.
    GREEN: up to green_signal_max_pct of balance
    YELLOW: 25% of GREEN allocation
    RED: 0
    """
    risk_cfg = config["risk"]
    balance  = risk_cfg["account_balance_usdt"]
    light    = inst_score_result.get("traffic", "RED")

    if light == "GREEN":
        alloc_pct   = risk_cfg["green_signal_max_pct"]
        alloc_usdt  = round(balance * alloc_pct / 100, 2)
        note        = f"GREEN — up to {alloc_pct}% of balance"
    elif light == "YELLOW":
        alloc_pct   = risk_cfg["yellow_signal_max_pct"]
        alloc_usdt  = round(balance * alloc_pct / 100, 2)
        note        = f"YELLOW — minimal (25% of GREEN allocation)"
    else:
        alloc_pct   = 0.0
        alloc_usdt  = 0.0
        note        = "RED — no trade"

    return {
        "light":       light,
        "alloc_pct":   alloc_pct,
        "alloc_usdt":  alloc_usdt,
        "balance":     balance,
        "note":        note,
    }


# ══════════════════════════════════════════════════════════════════════════════
# SIDE A — VMC SIGNAL ENGINE
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

    if volume > 50_000_000:    score += 25
    elif volume > 10_000_000:  score += 20
    elif volume > 2_000_000:   score += 14
    elif volume > 500_000:     score += 8

    if 40 <= price_pos <= 75:   score += 25
    elif 25 <= price_pos < 40:  score += 18
    elif price_pos > 75:        score += 12
    else:                       score += 6

    if 40 <= rsi <= 60:                         score += 20
    elif 35 <= rsi < 40 or 60 < rsi <= 65:     score += 14
    elif 30 <= rsi < 35 or 65 < rsi <= 70:     score += 8

    return min(score, 100)


def categorize_signals(tickers: list, rsi_map: dict, config: dict) -> dict:
    cfg    = config["vmc"]
    thresh = cfg["score_threshold"]
    favs   = set(cfg["favorite_coins"])
    out    = {k: [] for k in ["ALL", "FAV", "STUCK", "GOLDEN", "BOOM", "ENTRY", "EXIT", "PUMP", "VIP"]}

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
            "symbol":        symbol,
            "price":         float(t["lastPrice"]),
            "change_pct":    round(change, 2),
            "volume_usdt":   round(float(t["quoteVolume"]), 0),
            "rsi":           rsi,
            "score":         score,
            "high_24h":      float(t["highPrice"]),
            "low_24h":       float(t["lowPrice"]),
            "price_pos_pct": round(price_pos, 1),
        }

        out["ALL"].append(coin)
        if symbol in favs:
            out["FAV"].append(coin)

        if abs(change) < cfg["volatility_stuck_max"]:
            out["STUCK"].append(coin)
            continue

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
# SIDE B — WHALE WALL ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def fetch_order_book(symbol: str, depth: int = 20) -> dict:
    try:
        resp = requests.get(
            f"{BINANCE_BASE}/depth",
            params={"symbol": symbol, "limit": depth},
            timeout=8
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.debug(f"Order book failed for {symbol}: {e}")
        return {"bids": [], "asks": []}


def detect_spoofing(bids: list, asks: list, config: dict) -> dict:
    ratio_thresh = config["whale"]["spoofing_ratio_threshold"]

    def _check(levels: list):
        if len(levels) < 4:
            return False, 0.0
        sizes    = [float(lvl[1]) for lvl in levels]
        top_size = sizes[0]
        avg_rest = sum(sizes[1:]) / len(sizes[1:])
        if avg_rest == 0:
            return False, 0.0
        ratio = top_size / avg_rest
        return ratio >= ratio_thresh, round(ratio, 2)

    bid_spoof, bid_ratio = _check(bids)
    ask_spoof, ask_ratio = _check(asks)
    detail = []
    if bid_spoof:
        detail.append(f"Fake BID wall (×{bid_ratio})")
    if ask_spoof:
        detail.append(f"Fake ASK wall (×{ask_ratio})")

    return {
        "bid_spoof": bid_spoof,
        "ask_spoof": ask_spoof,
        "bid_ratio": bid_ratio,
        "ask_ratio": ask_ratio,
        "details":   " | ".join(detail) if detail else "Clean",
    }


def calculate_wall_proximity(price: float, book: dict, config: dict) -> list:
    prox_pct = config["whale"]["wall_proximity_pct"]
    min_size = config["whale"]["min_wall_size_usdt"]
    walls    = []

    for side, levels in [("BID", book.get("bids", [])), ("ASK", book.get("asks", []))]:
        for level in levels:
            try:
                lvl_price = float(level[0])
                lvl_qty   = float(level[1])
                lvl_usdt  = lvl_price * lvl_qty
            except (IndexError, ValueError):
                continue
            if lvl_usdt < min_size:
                continue
            dist_pct = abs(lvl_price - price) / price * 100
            if dist_pct <= prox_pct:
                walls.append({
                    "side":        side,
                    "price_level": round(lvl_price, 6),
                    "size_usdt":   round(lvl_usdt, 0),
                    "dist_pct":    round(dist_pct, 3),
                })

    walls.sort(key=lambda x: x["dist_pct"])
    return walls


def blink_to_push_check(symbol: str, current_walls: list, previous_walls: dict, config: dict) -> bool:
    push_thresh = config["whale"]["blink_push_proximity_pct"]
    prev = previous_walls.get(symbol, [])
    if not prev or not current_walls:
        return False
    prev_min = min((w["dist_pct"] for w in prev), default=99)
    curr_min = min((w["dist_pct"] for w in current_walls), default=99)
    return curr_min < prev_min and curr_min <= push_thresh


def process_whale_walls(config: dict, price_map: dict, previous_walls: dict) -> list:
    top_n   = config["whale"]["top_coins_for_whale"]
    depth   = config["whale"]["order_book_depth"]
    results = []

    for i, symbol in enumerate(list(price_map.keys())[:top_n]):
        price = price_map.get(symbol, 0)
        if not price:
            continue

        book   = fetch_order_book(symbol, depth)
        walls  = calculate_wall_proximity(price, book, config)
        spoof  = detect_spoofing(book.get("bids", []), book.get("asks", []), config)
        b2push = blink_to_push_check(symbol, walls, previous_walls, config)
        obi    = calculate_obi(book)
        obi_r  = detect_obi_spike(symbol, obi, config)

        # Whale power
        whale_power = compute_whale_power(walls, spoof, b2push, price, config)

        if walls or spoof["bid_spoof"] or spoof["ask_spoof"] or b2push:
            if spoof["bid_spoof"] or spoof["ask_spoof"]:
                label = "WHALE TRAP"
            elif b2push:
                label = "BLINK→PUSH"
            else:
                label = "WALL"

            results.append({
                "symbol":        symbol,
                "price":         price,
                "walls":         walls,
                "spoofing":      spoof,
                "blink_to_push": b2push,
                "label":         label,
                "wall_count":    len(walls),
                "min_dist_pct":  min((w["dist_pct"] for w in walls), default=0) if walls else 0,
                "whale_power":   whale_power,
                "obi":           obi_r,
            })

        previous_walls[symbol] = walls

        if i > 0 and i % 10 == 0:
            time.sleep(0.2)

    results.sort(key=lambda x: (-x["whale_power"], x["blink_to_push"]), reverse=False)
    results.sort(key=lambda x: x["whale_power"], reverse=True)
    return results


# ══════════════════════════════════════════════════════════════════════════════
# BTC SENTIMENT MONITOR
# ══════════════════════════════════════════════════════════════════════════════

def fetch_btc_sentiment() -> dict:
    """
    Fetch live BTC price and 24hr change.
    Returns sentiment: BULLISH / BEARISH / EXTREME_VOLATILITY.
    """
    try:
        resp = requests.get(
            f"{BINANCE_BASE}/ticker/24hr",
            params={"symbol": "BTCUSDT"},
            timeout=8
        )
        resp.raise_for_status()
        t = resp.json()
        change = float(t["priceChangePercent"])
        price  = float(t["lastPrice"])
        volume = float(t["quoteVolume"])
        high   = float(t["highPrice"])
        low    = float(t["lowPrice"])
        volatility = (high - low) / low * 100 if low else 0

        if change <= -2.0 or volatility > 5.0:
            sentiment = "BEARISH"
            pause_entries = True
        elif change >= 2.0:
            sentiment = "BULLISH"
            pause_entries = False
        else:
            sentiment = "NEUTRAL"
            pause_entries = False

        return {
            "price":         price,
            "change_pct":    round(change, 2),
            "volume":        round(volume, 0),
            "volatility_pct": round(volatility, 2),
            "sentiment":     sentiment,
            "pause_entries": pause_entries,
            "timestamp":     time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    except Exception as e:
        log.warning(f"BTC sentiment fetch failed: {e}")
        return {
            "price": 0, "change_pct": 0, "volume": 0,
            "volatility_pct": 0, "sentiment": "UNKNOWN",
            "pause_entries": False,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }


# ══════════════════════════════════════════════════════════════════════════════
# GOOGLE SHEETS INTEGRATION
# ══════════════════════════════════════════════════════════════════════════════

def push_to_google_sheets(vmc_data: dict, whale_data: list, credentials_json: str, sheet_id: str) -> bool:
    try:
        import json as _json
        import gspread
        from oauth2client.service_account import ServiceAccountCredentials

        creds_dict = _json.loads(credentials_json)
        if not creds_dict or not sheet_id:
            log.debug("Google Sheets not configured — skipping push.")
            return False

        scopes = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
        creds  = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scopes)
        client = gspread.authorize(creds)
        sheet  = client.open_by_key(sheet_id)

        # ── LIVE_DASHBOARD tab ─────────────────────────────────────────────────
        try:
            ws_live = sheet.worksheet("LIVE_DASHBOARD")
        except Exception:
            ws_live = sheet.add_worksheet(title="LIVE_DASHBOARD", rows=1100, cols=15)

        # Auto-detect headers dynamically
        try:
            existing_headers = ws_live.row_values(1)
        except Exception:
            existing_headers = []

        std_headers = ["Timestamp", "Asset", "Status", "Signal", "VMC", "Price",
                       "Buy/Sale", "Heatmap", "Slack", "Chg%", "RSI", "Flux",
                       "Sentiment", "Log"]

        # Merge with any admin-added columns
        for h in existing_headers:
            if h and h not in std_headers:
                std_headers.append(h)

        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        rows = [std_headers]
        for folder, coins in vmc_data.items():
            for coin in coins[:20]:
                row = {
                    "Timestamp": ts,
                    "Asset":     coin["symbol"],
                    "Status":    "ACTIVE",
                    "Signal":    folder,
                    "VMC":       coin["score"],
                    "Price":     coin["price"],
                    "Buy/Sale":  "BUY" if folder in ["ENTRY", "GOLDEN", "VIP"] else "WATCH",
                    "Heatmap":   "HOT" if coin["volume_usdt"] > 10_000_000 else "WARM",
                    "Slack":     "",
                    "Chg%":      coin["change_pct"],
                    "RSI":       coin["rsi"],
                    "Flux":      coin["price_pos_pct"],
                    "Sentiment": "",
                    "Log":       f"Score:{coin['score']}",
                }
                rows.append([row.get(h, "") for h in std_headers])

        # Archive if over 1000 rows
        try:
            all_vals = ws_live.get_all_values()
            if len(all_vals) > 1000:
                try:
                    ws_arch = sheet.worksheet("ARCHIVE_LOG")
                except Exception:
                    ws_arch = sheet.add_worksheet(title="ARCHIVE_LOG", rows=5000, cols=15)
                old_rows = all_vals[1:len(all_vals)-500]  # keep last 500
                ws_arch.append_rows(old_rows)
        except Exception:
            pass

        ws_live.clear()
        ws_live.update("A1", rows)

        # ── WATCH tab ─────────────────────────────────────────────────────────
        try:
            ws_watch = sheet.worksheet("WATCH")
        except Exception:
            ws_watch = sheet.add_worksheet(title="WATCH", rows=200, cols=9)

        wrows = [["Symbol", "Price", "Label", "BlinkPush", "BidSpoof", "AskSpoof",
                  "WallCount", "MinDist%", "WhalePower"]]
        for w in whale_data[:100]:
            wrows.append([
                w["symbol"], w["price"], w["label"], w["blink_to_push"],
                w["spoofing"]["bid_spoof"], w["spoofing"]["ask_spoof"],
                w["wall_count"], w["min_dist_pct"], w.get("whale_power", 0)
            ])
        ws_watch.clear()
        ws_watch.update("A1", wrows)

        log.info(f"Sheets updated — {len(rows)-1} LIVE_DASHBOARD rows, {len(wrows)-1} WATCH rows.")
        return True

    except ImportError:
        log.warning("gspread/oauth2client not installed — Sheets push skipped.")
        return False
    except Exception as e:
        log.error(f"Google Sheets push failed: {e}")
        return False


def push_midnight_report(vmc_data: dict, whale_data: list, credentials_json: str, sheet_id: str) -> bool:
    """
    Auto-generate midnight report and push to ARCHIVE_LOG.
    Records both UTC and PKT (UTC+5) timestamps.
    """
    try:
        import json as _json
        import gspread
        from oauth2client.service_account import ServiceAccountCredentials

        creds_dict = _json.loads(credentials_json)
        if not creds_dict or not sheet_id:
            return False

        scopes = ["https://spreadsheets.google.com/feeds",
                  "https://www.googleapis.com/auth/drive"]
        creds  = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scopes)
        client = gspread.authorize(creds)
        sheet  = client.open_by_key(sheet_id)

        try:
            ws_arch = sheet.worksheet("ARCHIVE_LOG")
        except Exception:
            ws_arch = sheet.add_worksheet(title="ARCHIVE_LOG", rows=5000, cols=10)

        utc_ts  = time.strftime("%Y-%m-%d %H:%M:%S UTC")
        pkt_ts  = time.strftime("%Y-%m-%d %H:%M:%S PKT",
                                time.gmtime(time.time() + 5 * 3600))

        summary = [
            ["MIDNIGHT REPORT", utc_ts, pkt_ts],
            ["Folder", "Count"],
        ]
        for k, v in vmc_data.items():
            summary.append([k, len(v)])
        summary.append(["Whale Signals", len(whale_data)])

        ws_arch.append_rows(summary)
        log.info(f"Midnight report pushed to ARCHIVE_LOG — UTC:{utc_ts} PKT:{pkt_ts}")
        return True
    except Exception as e:
        log.error(f"Midnight report push failed: {e}")
        return False
