"""
Unit tests for core scoring functions in logic.py.
Run: python3 -m pytest tests/ -v
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from logic import score_coin, compute_v6_final_score


# ── score_coin() tests ──────────────────────────────────────────────
def _ticker(change=0, volume=0, high=100, low=100, last=100):
    return {
        "priceChangePercent": str(change),
        "quoteVolume": str(volume),
        "highPrice": str(high),
        "lowPrice": str(low),
        "lastPrice": str(last),
    }

def test_score_coin_strong_bullish():
    t = _ticker(change=6, volume=60_000_000, high=110, low=90, last=105)
    score = score_coin(t, rsi=50, config={})
    assert score >= 70, f"Expected high score for strong move, got {score}"

def test_score_coin_flat_low_volume():
    # last=99.02 puts price near the LOW edge of the range (price_pos ~6%),
    # combined with tiny change% and low volume -> genuinely low score
    t = _ticker(change=0.1, volume=100_000, high=100, low=99, last=99.02)
    score = score_coin(t, rsi=50, config={})
    assert score < 40, f"Expected low score for flat/low-vol coin, got {score}"

def test_score_coin_overbought_rsi_penalized():
    t = _ticker(change=3, volume=10_000_000, high=110, low=90, last=108)
    score_neutral_rsi = score_coin(t, rsi=50, config={})
    score_overbought  = score_coin(t, rsi=85, config={})
    assert score_overbought < score_neutral_rsi

def test_score_coin_bounded_0_100():
    t = _ticker(change=50, volume=999_999_999, high=200, low=1, last=199)
    score = score_coin(t, rsi=50, config={})
    assert 0 <= score <= 100

def test_score_coin_handles_bad_ticker():
    assert score_coin({}, rsi=50, config={}) == 0


# ── compute_v6_final_score() tests ──────────────────────────────────
def _signal(price=100, rsi=50, change_pct=0, inst=None, tp=None, macd_hist=0):
    return {
        "price": price, "rsi": rsi, "change_pct": change_pct,
        "macd_hist": macd_hist,
        "inst": inst or {"inst_score": 50, "whale_power": 50, "ofi_score": 50, "traffic": "YELLOW"},
        "tp_zones": tp or {"entry_low": price, "stop_loss": price*0.97, "tp1": price*1.03},
    }

def test_v6_score_bounded_0_100():
    sig = _signal()
    result = compute_v6_final_score(sig, "RANGING", btc_volatility_pct=2, divergence_signal="NONE", in_volume_surge=False)
    assert 0 <= result["score"] <= 100

def test_v6_score_strong_signal_yields_buy():
    sig = _signal(
        price=100, rsi=45, change_pct=1,
        inst={"inst_score": 90, "whale_power": 85, "ofi_score": 70, "traffic": "GREEN"},
        tp={"entry_low": 100, "stop_loss": 97, "tp1": 106},
        macd_hist=0.5,
    )
    result = compute_v6_final_score(sig, "TRENDING", btc_volatility_pct=1, divergence_signal="ACCUMULATION", in_volume_surge=True)
    assert result["label"] == "BUY", f"Expected BUY for strong signal, got {result['label']} (score={result['score']})"

def test_v6_score_weak_signal_yields_avoid():
    sig = _signal(
        price=100, rsi=80, change_pct=-2,
        inst={"inst_score": 10, "whale_power": 5, "ofi_score": 20, "traffic": "RED"},
        tp={"entry_low": 100, "stop_loss": 100, "tp1": 100},
        macd_hist=-0.5,
    )
    result = compute_v6_final_score(sig, "VOLATILE", btc_volatility_pct=8, divergence_signal="DISTRIBUTION", in_volume_surge=False)
    assert result["label"] == "AVOID", f"Expected AVOID for weak signal, got {result['label']} (score={result['score']})"

def test_v6_score_breakdown_keys_present():
    sig = _signal()
    result = compute_v6_final_score(sig, "RANGING", btc_volatility_pct=2, divergence_signal="NONE", in_volume_surge=False)
    for key in ["market_regime", "inst_whale", "technical", "smart_divergence", "trade_engine"]:
        assert key in result["breakdown"]

def test_v6_score_label_thresholds():
    sig = _signal()
    result = compute_v6_final_score(sig, "RANGING", btc_volatility_pct=2, divergence_signal="NONE", in_volume_surge=False)
    if result["score"] >= 68:
        assert result["label"] == "BUY"
    elif result["score"] >= 45:
        assert result["label"] == "WAIT"
    else:
        assert result["label"] == "AVOID"
