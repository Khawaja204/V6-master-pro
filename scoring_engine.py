"""
V6 Master Pro — 54-Point Institutional Scoring Engine
======================================================
5 Categories (54 raw points → scaled 0-100):

1. Market Regime        10 pts
2. Whale/Institutional  12 pts
3. Technical Indicators 12 pts
4. Smart Money Divergence 10 pts
5. Trade Engine & Risk  10 pts

Signals:
  BUY  → score >= 68
  WAIT → score 45-67
  SELL → score < 45
"""

import math


# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════

def _safe(v, default=0.0):
    try:
        f = float(v)
        return f if math.isfinite(f) else default
    except Exception:
        return default


def _clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def _rsi_score(rsi):
    """RSI 4-point scoring — best zone 38-55 (momentum without overbought)."""
    rsi = _safe(rsi, 50)
    if 38 <= rsi <= 55:   return 4
    if 55 < rsi <= 62:    return 3
    if 35 <= rsi < 38:    return 3
    if 62 < rsi <= 70:    return 2
    if 28 <= rsi < 35:    return 2
    if rsi > 70:          return 0   # overbought — risky
    if rsi < 25:          return 1   # extreme oversold — possible reversal
    return 1


def _macd_score(macd_hist, price):
    """MACD histogram 4-point scoring."""
    price = _safe(price, 1)
    hist  = _safe(macd_hist, 0)
    if price == 0:
        return 2
    rel = hist / price * 100
    if rel > 0.05:    return 4
    if rel > 0.01:    return 3
    if rel >= 0:      return 2
    if rel > -0.05:   return 1
    return 0


def _volume_score(volume_usdt, in_surge):
    """Volume 4-point scoring."""
    if in_surge:
        return 4
    vol = _safe(volume_usdt, 0)
    if vol >= 50_000_000:  return 3
    if vol >= 10_000_000:  return 2
    if vol >= 1_000_000:   return 1
    return 0


# ══════════════════════════════════════════════════════════════════
# WHALE WALL ANALYSIS
# ══════════════════════════════════════════════════════════════════

def _analyze_walls(order_book):
    """
    Returns (bid_wall_usdt, ask_wall_usdt, min_dist_pct, obi)
    from raw order book dict with 'bids' and 'asks' lists.
    """
    bids = order_book.get('bids', [])
    asks = order_book.get('asks', [])

    bid_vol = sum(_safe(b[0]) * _safe(b[1]) for b in bids if len(b) >= 2)
    ask_vol = sum(_safe(a[0]) * _safe(a[1]) for a in asks if len(a) >= 2)
    total   = bid_vol + ask_vol
    obi     = (bid_vol - ask_vol) / total if total > 0 else 0.0

    # Largest single wall on each side
    bid_wall = max((_safe(b[0]) * _safe(b[1]) for b in bids if len(b) >= 2), default=0)
    ask_wall = max((_safe(a[0]) * _safe(a[1]) for a in asks if len(a) >= 2), default=0)

    return bid_wall, ask_wall, obi


def _whale_cluster_score(extra):
    """
    Whale cluster / wallet tracking depth score (0-6).
    Uses whale_power, obi, whale_trap, whale_cluster from extra dict.
    """
    whale_power   = _safe(extra.get('whale_power', 0))
    obi           = _safe(extra.get('obi', 0))
    whale_trap    = bool(extra.get('whale_trap', False))
    cluster       = str(extra.get('whale_cluster', '')).upper()

    score = 0

    # Whale power tiers
    if whale_power >= 80:   score += 3
    elif whale_power >= 60: score += 2
    elif whale_power >= 40: score += 1

    # OBI (Order Book Imbalance) — bid dominance
    if obi > 0.15:    score += 2
    elif obi > 0.05:  score += 1
    elif obi < -0.15: score -= 1   # heavy selling pressure

    # Whale trap detection — penalize
    if whale_trap:
        score -= 2

    # Cluster status
    if cluster == 'COORDINATED':  score += 1
    elif cluster == 'NORMAL':     score += 0

    return max(0, min(6, score))


def _institutional_score(extra):
    """
    Institutional score component (0-6).
    Uses vmc_score, institutional_score, traffic_light.
    """
    vmc   = _safe(extra.get('vmc_score', 0))
    inst  = _safe(extra.get('institutional_score', 0))
    light = str(extra.get('traffic_light', 'red')).upper()

    score = 0

    # VMC score (0-100 → 0-3 pts)
    if vmc >= 80:    score += 3
    elif vmc >= 65:  score += 2
    elif vmc >= 50:  score += 1

    # Institutional score (0-100 → 0-2 pts)
    if inst >= 75:   score += 2
    elif inst >= 55: score += 1

    # Traffic light
    if light == 'GREEN':    score += 1
    elif light == 'YELLOW': score += 0
    else:                   score -= 1   # RED

    return max(0, min(6, score))


# ══════════════════════════════════════════════════════════════════
# CATEGORY 1 — MARKET REGIME (10 pts)
# ══════════════════════════════════════════════════════════════════

def _score_market_regime(ticker, extra):
    """
    10 points:
      Trend direction   5 pts
      Volatility quality 5 pts
    """
    change     = _safe(ticker.get('priceChangePercent', 0))
    btc_regime = str(extra.get('btc_regime', 'RANGING')).upper()
    vol_pct    = abs(_safe(extra.get('btc_volatility_pct', 0)))

    # Trend
    if change > 3:      trend = 5
    elif change > 1:    trend = 4
    elif change > 0:    trend = 3
    elif change > -1:   trend = 2
    elif change > -3:   trend = 1
    else:               trend = 0

    # Regime bonus
    if btc_regime == 'TRENDING':   trend = min(5, trend + 1)
    elif btc_regime == 'VOLATILE': trend = max(0, trend - 1)

    # Volatility quality (low volatility = safer entries)
    if vol_pct < 1.5:   vol = 5
    elif vol_pct < 2.5: vol = 4
    elif vol_pct < 4.0: vol = 3
    elif vol_pct < 6.0: vol = 2
    elif vol_pct < 8.0: vol = 1
    else:               vol = 0

    return min(10, trend + vol)


# ══════════════════════════════════════════════════════════════════
# CATEGORY 2 — WHALE & INSTITUTIONAL (12 pts)
# ══════════════════════════════════════════════════════════════════

def _score_whale_institutional(order_book, extra):
    """
    12 points:
      Whale cluster/wallet tracking  6 pts
      Institutional score            6 pts
    """
    whale  = _whale_cluster_score(extra)
    inst   = _institutional_score(extra)
    return min(12, whale + inst)


# ══════════════════════════════════════════════════════════════════
# CATEGORY 3 — TECHNICAL INDICATORS (12 pts)
# ══════════════════════════════════════════════════════════════════

def _score_technical(klines, ticker, extra):
    """
    12 points:
      RSI    4 pts
      MACD   4 pts
      Volume 4 pts
    """
    # RSI — from klines if available, else from ticker proxy
    if klines and len(klines) >= 15:
        closes = [_safe(k[4]) for k in klines]
        rsi    = _calc_rsi(closes)
    else:
        # Proxy: price position within 24h range
        try:
            hi  = _safe(ticker['highPrice'])
            lo  = _safe(ticker['lowPrice'])
            last= _safe(ticker['lastPrice'])
            rsi = 30 + (last - lo) / (hi - lo + 1e-9) * 40 if hi > lo else 50
        except Exception:
            rsi = 50

    # MACD histogram
    macd_hist = _safe(extra.get('macd_hist', 0))
    price     = _safe(ticker.get('lastPrice', 1), 1) or 1
    vol_usdt  = _safe(ticker.get('quoteVolume', 0))
    in_surge  = bool(extra.get('in_volume_surge', False))

    rsi_pts  = _rsi_score(rsi)
    macd_pts = _macd_score(macd_hist, price)
    vol_pts  = _volume_score(vol_usdt, in_surge)

    return min(12, rsi_pts + macd_pts + vol_pts), rsi


def _calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains  = [d if d > 0 else 0.0 for d in deltas[-period:]]
    losses = [-d if d < 0 else 0.0 for d in deltas[-period:]]
    ag = sum(gains) / period
    al = sum(losses) / period
    if al == 0:
        return 100.0
    return round(100 - 100 / (1 + ag / al), 2)


# ══════════════════════════════════════════════════════════════════
# CATEGORY 4 — SMART MONEY DIVERGENCE (10 pts)
# ══════════════════════════════════════════════════════════════════

def _score_smart_money(order_book, ticker, extra):
    """
    10 points:
      OBI (Order Flow Imbalance)   6 pts
      Price/Volume divergence      4 pts
    """
    _, _, obi = _analyze_walls(order_book)

    # OBI score (6 pts)
    if obi > 0.20:    obi_pts = 6
    elif obi > 0.10:  obi_pts = 5
    elif obi > 0.05:  obi_pts = 4
    elif obi > 0:     obi_pts = 3
    elif obi > -0.05: obi_pts = 2
    elif obi > -0.15: obi_pts = 1
    else:             obi_pts = 0

    # Price/Volume divergence (4 pts)
    div_signal = str(extra.get('divergence_signal', 'NONE')).upper()
    change     = _safe(ticker.get('priceChangePercent', 0))

    if div_signal == 'ACCUMULATION':
        div_pts = 4   # price down, OBI up = smart money buying dip
    elif div_signal == 'DISTRIBUTION':
        div_pts = 0   # price up, OBI down = smart money selling into pump
    elif change > 2 and obi > 0.05:
        div_pts = 3   # price up with buying pressure = genuine move
    elif change < -2 and obi < -0.05:
        div_pts = 1   # price down with selling = trend continuation risk
    else:
        div_pts = 2   # neutral

    return min(10, obi_pts + div_pts)


# ══════════════════════════════════════════════════════════════════
# CATEGORY 5 — TRADE ENGINE & RISK (10 pts)
# ══════════════════════════════════════════════════════════════════

def _score_trade_engine(extra):
    """
    10 points:
      R/R Ratio           5 pts
      Traffic Light       3 pts
      Paper/Real safety   2 pts
    """
    # R/R
    entry  = _safe(extra.get('entry_low', 0))
    sl     = _safe(extra.get('stop_loss', 0))
    tp1    = _safe(extra.get('tp1', 0))

    risk   = entry - sl
    reward = tp1 - entry
    rr     = reward / risk if risk > 0 else 0

    if rr >= 3.0:    rr_pts = 5
    elif rr >= 2.0:  rr_pts = 4
    elif rr >= 1.5:  rr_pts = 3
    elif rr >= 1.0:  rr_pts = 2
    elif rr > 0:     rr_pts = 1
    else:            rr_pts = 0

    # Traffic light
    light = str(extra.get('traffic_light', 'red')).upper()
    if light == 'GREEN':    tl_pts = 3
    elif light == 'YELLOW': tl_pts = 1
    else:                   tl_pts = 0

    # Paper mode safety check
    paper_mode  = bool(extra.get('paper_mode', True))
    paper_wr    = _safe(extra.get('paper_win_rate', 0))
    cons_losses = _safe(extra.get('consecutive_losses', 0))
    cooldown    = bool(extra.get('cooldown_active', False))

    if cooldown or cons_losses >= 3:
        safety_pts = 0
    elif paper_mode and paper_wr >= 65:
        safety_pts = 2   # ready for real
    elif paper_mode:
        safety_pts = 1   # still learning
    else:
        safety_pts = 2 if paper_wr >= 65 else 1

    return min(10, rr_pts + tl_pts + safety_pts)


# ══════════════════════════════════════════════════════════════════
# WHALE WALLET DEPTH TRACKER
# ══════════════════════════════════════════════════════════════════

def _whale_wallet_depth(order_book):
    """
    Deep analysis of whale wallet patterns from order book.
    Returns dict with pattern classification and confidence.
    """
    bids = order_book.get('bids', [])
    asks = order_book.get('asks', [])

    bid_levels = [(float(b[0]), float(b[1])) for b in bids if len(b) >= 2]
    ask_levels = [(float(a[0]), float(a[1])) for a in asks if len(a) >= 2]

    if not bid_levels or not ask_levels:
        return {'pattern': 'UNKNOWN', 'confidence': 0, 'whale_count': 0}

    # Detect large walls (> 3x median size)
    bid_sizes  = [s for _, s in bid_levels]
    ask_sizes  = [s for _, s in ask_levels]
    med_bid    = sorted(bid_sizes)[len(bid_sizes)//2] if bid_sizes else 1
    med_ask    = sorted(ask_sizes)[len(ask_sizes)//2] if ask_sizes else 1

    large_bids = [(p, s) for p, s in bid_levels if s > med_bid * 3]
    large_asks = [(p, s) for p, s in ask_levels if s > med_ask * 3]

    whale_count = len(large_bids) + len(large_asks)

    # Pattern detection
    total_bid_wall = sum(p*s for p, s in large_bids)
    total_ask_wall = sum(p*s for p, s in large_asks)

    if total_bid_wall > total_ask_wall * 2:
        pattern    = 'ACCUMULATION'
        confidence = min(95, int(total_bid_wall / (total_ask_wall + 1) * 20))
    elif total_ask_wall > total_bid_wall * 2:
        pattern    = 'DISTRIBUTION'
        confidence = min(95, int(total_ask_wall / (total_bid_wall + 1) * 20))
    elif total_bid_wall > 0 and total_ask_wall > 0:
        pattern    = 'RANGING'
        confidence = 50
    else:
        pattern    = 'NEUTRAL'
        confidence = 30

    return {
        'pattern':     pattern,
        'confidence':  confidence,
        'whale_count': whale_count,
        'bid_wall_usdt': round(total_bid_wall, 0),
        'ask_wall_usdt': round(total_ask_wall, 0),
    }


# ══════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════

def calculate_54_point_score(symbol='', klines=None, order_book=None,
                              ticker=None, extra=None):
    """
    Full 54-point institutional scoring engine.

    Parameters
    ----------
    symbol     : str   — trading pair e.g. 'BTCUSDT'
    klines     : list  — Binance kline rows [[open_time, o, h, l, c, vol, ...]]
    order_book : dict  — {'bids': [[price,qty],...], 'asks': [[price,qty],...]}
    ticker     : dict  — Binance 24hr ticker dict
    extra      : dict  — enriched fields from logic.py:
                         whale_power, obi, institutional_score, vmc_score,
                         traffic_light, macd_hist, in_volume_surge,
                         divergence_signal, btc_regime, btc_volatility_pct,
                         whale_trap, whale_cluster, entry_low, stop_loss, tp1,
                         paper_mode, paper_win_rate, consecutive_losses,
                         cooldown_active

    Returns
    -------
    dict with keys: score, signal, badge, rsi, rr, breakdown, category_scores,
                    whale_wallet, sl, tp1, tp2, tp3, atr
    """
    if klines     is None: klines     = []
    if order_book is None: order_book = {}
    if ticker     is None: ticker     = {}
    if extra      is None: extra      = {}

    # ── Score each category ──────────────────────────────────────
    c1 = _score_market_regime(ticker, extra)
    c2 = _score_whale_institutional(order_book, extra)
    c3, rsi = _score_technical(klines, ticker, extra)
    c4 = _score_smart_money(order_book, ticker, extra)
    c5 = _score_trade_engine(extra)

    raw   = c1 + c2 + c3 + c4 + c5          # max 54
    score = round(_clamp(raw / 54) * 100)    # scale to 0-100

    # ── Signal label ─────────────────────────────────────────────
    if score >= 68:
        signal = 'BUY'
        badge  = 'badge-buy'
    elif score >= 45:
        signal = 'WAIT'
        badge  = 'badge-wait'
    else:
        signal = 'SELL'
        badge  = 'badge-sell'

    # ── R/R ratio for display ────────────────────────────────────
    entry = _safe(extra.get('entry_low', 0))
    sl    = _safe(extra.get('stop_loss', 0))
    tp1   = _safe(extra.get('tp1', 0))
    tp2   = _safe(extra.get('tp2', 0))
    tp3   = _safe(extra.get('tp3', 0))
    atr   = _safe(extra.get('atr', 0))
    risk  = entry - sl
    rr    = round((tp1 - entry) / risk, 2) if risk > 0 else 0

    # ── Whale wallet deep analysis ───────────────────────────────
    whale_wallet = _whale_wallet_depth(order_book)

    return {
        'score':  score,
        'signal': signal,
        'badge':  badge,
        'rsi':    round(rsi, 1),
        'rr':     rr,
        'sl':     sl,
        'tp1':    tp1,
        'tp2':    tp2,
        'tp3':    tp3,
        'atr':    atr,
        'breakdown': {
            'market_regime':    c1,
            'inst_whale':       c2,
            'technical':        c3,
            'smart_divergence': c4,
            'trade_engine':     c5,
        },
        'category_scores': {
            'market_regime':      f'{c1}/10',
            'whale_institutional':f'{c2}/12',
            'technical':          f'{c3}/12',
            'smart_money':        f'{c4}/10',
            'trade_engine':       f'{c5}/10',
        },
        'whale_wallet': whale_wallet,
    }
