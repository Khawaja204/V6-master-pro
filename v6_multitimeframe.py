"""
v6_multitimeframe.py — V6 Master Pro | Multi-Timeframe Confluence (P1)
15m + 1h + 4h trend alignment. Returns confluence score 0-100.
"""
import logging
from typing import Dict

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

def _analyze_tf(klines: list) -> Dict:
    """Returns trend analysis for a single timeframe's klines."""
    if len(klines) < 30:
        return {"trend": "NEUTRAL", "rsi": 50.0, "ema_fast": 0, "ema_slow": 0, "score": 0}
    closes = [float(k[4]) for k in klines]
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]
    
    ema9 = _ema(closes, 9)[-1]
    ema21 = _ema(closes, 21)[-1]
    rsi_val = _rsi(closes, 14)
    
    # Trend direction
    bullish = ema9 > ema21 and closes[-1] > ema9
    bearish = ema9 < ema21 and closes[-1] < ema9
    
    # Momentum
    last_3 = closes[-3:]
    momentum_up = last_3[-1] > last_3[0]
    
    if bullish and momentum_up:
        trend = "BULLISH"
        score = 70 + min(30, (rsi_val - 30) * 0.5)  # higher score if RSI 30-70 range
    elif bearish and not momentum_up:
        trend = "BEARISH"
        score = 70 + min(30, (70 - rsi_val) * 0.5)
    else:
        trend = "NEUTRAL"
        score = 30 + abs(50 - rsi_val)
    
    # Cap RSI contribution
    score = min(100, max(0, score))
    
    return {
        "trend": trend,
        "rsi": round(rsi_val, 2),
        "ema_fast": round(ema9, 8),
        "ema_slow": round(ema21, 8),
        "score": round(score, 1),
        "momentum_up": momentum_up
    }

def get_mtf_signal(symbol: str, klines_fetcher) -> Dict:
    """
    klines_fetcher: callable(symbol, interval, limit) -> list of klines
    Returns confluence analysis across 15m, 1h, 4h.
    """
    tf_map = {"15m": 60, "1h": 60, "4h": 60}
    results = {}
    
    for tf, limit in tf_map.items():
        try:
            kl = klines_fetcher(symbol, tf, limit)
            results[tf] = _analyze_tf(kl) if kl else {"trend": "NEUTRAL", "score": 0, "rsi": 50}
        except Exception as e:
            log.debug(f"[MTF] {symbol} {tf} failed: {e}")
            results[tf] = {"trend": "NEUTRAL", "score": 0, "rsi": 50}
    
    # Confluence scoring
    trends = [results[tf]["trend"] for tf in tf_map]
    scores = [results[tf]["score"] for tf in tf_map]
    avg_score = sum(scores) / len(scores) if scores else 0
    
    bullish_count = sum(1 for t in trends if t == "BULLISH")
    bearish_count = sum(1 for t in trends if t == "BEARISH")
    
    if bullish_count >= 2:
        confluence = "STRONG_BUY"
        confluence_score = min(100, avg_score + 15)
    elif bullish_count == 1 and bearish_count == 0:
        confluence = "WEAK_BUY"
        confluence_score = avg_score
    elif bearish_count >= 2:
        confluence = "STRONG_AVOID"
        confluence_score = min(100, avg_score + 15)
    elif bearish_count == 1 and bullish_count == 0:
        confluence = "WEAK_AVOID"
        confluence_score = avg_score
    else:
        confluence = "MIXED"
        confluence_score = avg_score * 0.7
    
    return {
        "symbol": symbol,
        "confluence": confluence,
        "confluence_score": round(confluence_score, 1),
        "timeframes": results,
        "alignment": f"{bullish_count}B/{bearish_count}A/1N" if len(trends) == 3 else "unknown"
    }
