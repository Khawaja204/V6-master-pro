"""
v6_multitimeframe.py — V6 Master Pro P1
Multi-timeframe signal confluence: 15m + 1h + 4h.
"""
import logging

log = logging.getLogger(__name__)

def _ema(values, period):
    if not values:
        return []
    k = 2.0 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out

def _rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    if avg_l == 0:
        return 100.0
    return 100.0 - (100.0 / (1 + avg_g / avg_l))

def _macd(closes, fast=12, slow=26, signal=9):
    if len(closes) < slow + signal:
        return {"macd": 0, "signal": 0, "hist": 0}
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = _ema(macd_line, signal)
    hist = macd_line[-1] - signal_line[-1]
    return {"macd": macd_line[-1], "signal": signal_line[-1], "hist": hist}

def _score_tf(klines, interval):
    if not klines or len(klines) < 30:
        return {"interval": interval, "trend": "NEUTRAL", "score": 50, "rsi": 50, "macd_hist": 0, "label": "WAIT"}

    closes = [float(k[4]) for k in klines]
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]

    rsi = _rsi(closes)
    macd_d = _macd(closes)
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    ema_bull = ema12[-1] > ema26[-1] if len(ema12) == len(ema26) and len(ema12) > 0 else False

    recent_highs = highs[-10:]
    recent_lows = lows[-10:]
    hh = max(recent_highs) == recent_highs[-1] or recent_highs[-1] > recent_highs[0]
    ll = min(recent_lows) == recent_lows[-1] or recent_lows[-1] < recent_lows[0]

    score = 50
    score += 15 if ema_bull else -15
    if macd_d["hist"] > 0:
        score += 10
    elif macd_d["hist"] < 0:
        score -= 10

    if 35 <= rsi <= 45:
        score += 15
    elif 55 <= rsi <= 65:
        score -= 5
    elif rsi > 70:
        score -= 20
    elif rsi < 30:
        score += 20

    if hh and not ll:
        score += 10
    elif ll and not hh:
        score -= 10

    score = max(0, min(100, score))

    if score >= 65:
        label = "BUY"
    elif score <= 35:
        label = "AVOID"
    else:
        label = "WAIT"

    return {
        "interval": interval,
        "trend": "BULLISH" if score > 55 else "BEARISH" if score < 45 else "NEUTRAL",
        "score": round(score, 1),
        "rsi": round(rsi, 1),
        "macd_hist": round(macd_d["hist"], 6),
        "label": label,
        "ema_bull": ema_bull,
    }

def get_mtf_signal(symbol: str, fetch_klines_func):
    try:
        k15 = fetch_klines_func(symbol, "15m", 50)
        k1h = fetch_klines_func(symbol, "1h", 50)
        k4h = fetch_klines_func(symbol, "4h", 50)
    except Exception as e:
        log.warning(f"[MTF] fetch failed {symbol}: {e}")
        return {"error": str(e)}

    s15 = _score_tf(k15, "15m")
    s1h = _score_tf(k1h, "1h")
    s4h = _score_tf(k4h, "4h")

    weights = {"15m": 0.2, "1h": 0.35, "4h": 0.45}
    wscore = (
        s15["score"] * weights["15m"] +
        s1h["score"] * weights["1h"] +
        s4h["score"] * weights["4h"]
    )

    labels = [s15["label"], s1h["label"], s4h["label"]]
    if all(l == "BUY" for l in labels):
        wscore = min(100, wscore + 10)
        confluence = "STRONG_BUY"
    elif all(l == "AVOID" for l in labels):
        wscore = max(0, wscore - 10)
        confluence = "STRONG_AVOID"
    elif labels.count("BUY") >= 2:
        confluence = "BUY"
    elif labels.count("AVOID") >= 2:
        confluence = "AVOID"
    else:
        confluence = "MIXED"

    final_score = round(wscore, 1)
    final_label = "BUY" if final_score >= 68 else "WAIT" if final_score >= 45 else "AVOID"

    return {
        "symbol": symbol,
        "confluence": confluence,
        "score": final_score,
        "label": final_label,
        "timeframes": {"15m": s15, "1h": s1h, "4h": s4h},
        "alignment": {
            "bullish_count": sum(1 for l in labels if l == "BUY"),
            "bearish_count": sum(1 for l in labels if l == "AVOID"),
            "neutral_count": sum(1 for l in labels if l == "WAIT"),
        },
    }
