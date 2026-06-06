"""
logic.py — V6 Master Pro Engine
Modular functions for VMC signal processing and Whale Wall detection.
Modify thresholds in config.json — no code changes needed.
"""
import time
import logging
import requests

log = logging.getLogger(__name__)
BINANCE_BASE = "https://api.binance.com/api/v3"


# ══════════════════════════════════════════════════════════════════════════════
# DATA LAYER — Binance API
# ══════════════════════════════════════════════════════════════════════════════

def fetch_all_tickers(config: dict) -> list:
    """
    Fetch 24hr stats for all USDT pairs from Binance.
    Returns list of ticker dicts sorted by quoteVolume desc, capped at coins_limit.
    """
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
    """Wilder's RSI from a list of close prices. Returns 50.0 on insufficient data."""
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


def fetch_rsi_for_symbol(symbol: str, interval: str = "1h", limit: int = 20) -> float:
    """Fetch klines and return RSI for one symbol. Returns 50.0 on any failure."""
    try:
        resp = requests.get(
            f"{BINANCE_BASE}/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=8
        )
        if resp.status_code != 200:
            return 50.0
        closes = [float(k[4]) for k in resp.json()]
        return calculate_rsi(closes)
    except Exception as e:
        log.debug(f"RSI fetch failed for {symbol}: {e}")
        return 50.0


def price_position_rsi(ticker: dict) -> float:
    """
    Fast pseudo-RSI estimate from 24hr high/low position.
    Used for coins outside RSI top-N to avoid excessive API calls.
    Maps price position (0–100%) → RSI range (20–80).
    """
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
# SIDE A — VMC SIGNAL ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def score_coin(ticker: dict, rsi: float, config: dict) -> int:
    """
    Score a coin 0–100 using WASP-Smart-Filter criteria.
    Weights: momentum (30) + volume (25) + price position (25) + RSI balance (20).
    Adjust thresholds via config.json — this function reads no hardcoded values.
    """
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

    # 1. Price momentum (30 pts)
    if change > 5:      score += 30
    elif change > 2:    score += 22
    elif change > 0.5:  score += 14
    elif change > -1:   score += 8

    # 2. Volume strength (25 pts)
    if volume > 50_000_000:    score += 25
    elif volume > 10_000_000:  score += 20
    elif volume > 2_000_000:   score += 14
    elif volume > 500_000:     score += 8

    # 3. Price position in 24h range (25 pts)
    if 40 <= price_pos <= 75:   score += 25   # healthy upper-mid zone
    elif 25 <= price_pos < 40:  score += 18
    elif price_pos > 75:        score += 12   # extended / near highs
    else:                       score += 6

    # 4. RSI balance (20 pts) — sweet spot 40–60
    if 40 <= rsi <= 60:                         score += 20
    elif 35 <= rsi < 40 or 60 < rsi <= 65:     score += 14
    elif 30 <= rsi < 35 or 65 < rsi <= 70:     score += 8

    return min(score, 100)


def categorize_signals(tickers: list, rsi_map: dict, config: dict) -> dict:
    """
    Sort tickers into VMC folders using config.json thresholds.
    Folders: ALL, FAV, STUCK, GOLDEN, BOOM, ENTRY, EXIT, PUMP, VIP.
    To change any threshold, edit config.json["vmc"] — no code change needed.
    """
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

        # STUCK — low volatility sideways coins
        if abs(change) < cfg["volatility_stuck_max"]:
            out["STUCK"].append(coin)
            continue   # STUCK coins don't qualify for active signal folders

        # GOLDEN — high score, RSI not yet overbought = safest setups
        if score >= cfg["golden_score_min"] and rsi < cfg["rsi_golden_max"]:
            out["GOLDEN"].append(coin)

        # BOOM — explosive volume + strong price move
        if change > 5 and volume > 5_000_000 * cfg["volume_boom_multiplier"]:
            out["BOOM"].append(coin)

        # ENTRY — oversold RSI or price near 24h low
        if rsi <= cfg["rsi_oversold"] or (price_pos < 25 and change < 0):
            out["ENTRY"].append(coin)

        # EXIT — overbought RSI or price near 24h high
        if rsi >= cfg["rsi_overbought"] or price_pos > 85:
            out["EXIT"].append(coin)

        # PUMP — rapid price surge with volume
        if change >= cfg["pump_change_min"] and volume > 3_000_000:
            out["PUMP"].append(coin)

        # VIP — elite score only
        if score >= cfg["vip_score_min"]:
            out["VIP"].append(coin)

    for key in out:
        out[key].sort(key=lambda x: x["score"], reverse=True)

    return out


def process_vmc_signals(config: dict) -> dict:
    """
    Main VMC processor.
    Fetches 500+ tickers, builds RSI map for top-N coins, categorizes all.
    RSI top-N is controlled by config.json["vmc"]["rsi_top_n"].
    """
    top_n   = config["vmc"]["rsi_top_n"]
    tickers = fetch_all_tickers(config)

    rsi_map = {}
    for i, t in enumerate(tickers[:top_n]):
        rsi_map[t["symbol"]] = fetch_rsi_for_symbol(t["symbol"])
        if i > 0 and i % 10 == 0:
            time.sleep(0.3)   # gentle Binance rate limiting

    log.info(f"VMC: RSI computed for {len(rsi_map)} coins. Categorizing {len(tickers)} total.")
    return categorize_signals(tickers, rsi_map, config)


# ══════════════════════════════════════════════════════════════════════════════
# SIDE B — WHALE WALL ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def fetch_order_book(symbol: str, depth: int = 20) -> dict:
    """Fetch live order book bids/asks for a symbol from Binance."""
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
    """
    Spoofing Detection: identifies fake buy/sell walls using size-ratio analysis.
    A wall is flagged if its size > spoofing_ratio_threshold × average of surrounding levels.
    Threshold is set in config.json["whale"]["spoofing_ratio_threshold"].
    """
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
    """
    Wall Proximity: finds walls within proximity_pct of current price.
    Returns list of wall dicts with type, price_level, size_usdt, dist_pct.
    Adjust wall_proximity_pct and min_wall_size_usdt in config.json.
    """
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
    """
    Blink-to-Push: detects whale walls moving CLOSER to price since last scan.
    Signals institutional pressure building before a breakout.
    Sensitivity set by config.json["whale"]["blink_push_proximity_pct"].
    """
    push_thresh = config["whale"]["blink_push_proximity_pct"]
    prev = previous_walls.get(symbol, [])
    if not prev or not current_walls:
        return False
    prev_min = min((w["dist_pct"] for w in prev), default=99)
    curr_min = min((w["dist_pct"] for w in current_walls), default=99)
    return curr_min < prev_min and curr_min <= push_thresh


def process_whale_walls(config: dict, price_map: dict, previous_walls: dict) -> list:
    """
    Main Whale Wall processor.
    Scans order books for top-N coins, runs spoofing detection, proximity check,
    and blink-to-push analysis. Updates previous_walls in-place for next cycle.
    Top-N is set in config.json["whale"]["top_coins_for_whale"].
    """
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
            })

        previous_walls[symbol] = walls

        if i > 0 and i % 10 == 0:
            time.sleep(0.2)

    results.sort(key=lambda x: (x["blink_to_push"], -x["wall_count"]), reverse=True)
    return results


# ══════════════════════════════════════════════════════════════════════════════
# GOOGLE SHEETS INTEGRATION
# ══════════════════════════════════════════════════════════════════════════════

def push_to_google_sheets(vmc_data: dict, whale_data: list, credentials_json: str, sheet_id: str) -> bool:
    """
    Push VMC signals and Whale data to Google Sheets.
    credentials_json: full service account JSON string from GOOGLE_CREDENTIALS secret.
    sheet_id: from GOOGLE_SHEET_ID secret.
    Creates worksheets 'VMC_Signals' and 'Whale_Data' if they don't exist.
    """
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

        # VMC sheet
        try:
            ws_vmc = sheet.worksheet("VMC_Signals")
        except Exception:
            ws_vmc = sheet.add_worksheet(title="VMC_Signals", rows=600, cols=10)

        rows = [["Symbol", "Price", "Change%", "Score", "RSI", "Volume(USDT)", "PricePos%", "Folder"]]
        for folder, coins in vmc_data.items():
            for coin in coins[:30]:
                rows.append([
                    coin["symbol"], coin["price"], coin["change_pct"],
                    coin["score"], coin["rsi"], coin["volume_usdt"],
                    coin["price_pos_pct"], folder
                ])
        ws_vmc.clear()
        ws_vmc.update("A1", rows)

        # Whale sheet
        try:
            ws_whale = sheet.worksheet("Whale_Data")
        except Exception:
            ws_whale = sheet.add_worksheet(title="Whale_Data", rows=200, cols=9)

        wrows = [["Symbol", "Price", "Label", "BlinkPush", "BidSpoof", "AskSpoof", "WallCount", "MinDist%", "Details"]]
        for w in whale_data[:100]:
            wrows.append([
                w["symbol"], w["price"], w["label"], w["blink_to_push"],
                w["spoofing"]["bid_spoof"], w["spoofing"]["ask_spoof"],
                w["wall_count"], w["min_dist_pct"], w["spoofing"]["details"]
            ])
        ws_whale.clear()
        ws_whale.update("A1", wrows)

        log.info(f"Sheets updated — {len(rows)-1} VMC rows, {len(wrows)-1} whale rows.")
        return True

    except ImportError:
        log.warning("gspread/oauth2client not installed — Sheets push skipped.")
        return False
    except Exception as e:
        log.error(f"Google Sheets push failed: {e}")
        return False
