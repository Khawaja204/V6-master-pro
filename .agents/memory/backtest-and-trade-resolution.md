---
name: Historical backtest & trade-resolution rules
description: Design decisions for historical_backtest() and the live trailing-stop resolution that must stay consistent.
---

# historical_backtest() (logic.py)

- Replays a **trend-pullback** strategy on Binance 1h klines: long when `close > EMA50` (uptrend) and RSI is in a pullback band around `vmc.rsi_oversold`, gated by a BTC EMA50 trend filter. ATR-based SL/TP (multipliers from `institutional.*`). Paginates klines 1000/req via `fetch_klines_range`.
- **Order-book / whale layers cannot be reconstructed historically** — Binance serves no historical depth snapshots. The backtest covers the technical + risk-management core only; this caveat is in the report's `note` and must stay surfaced to the user.
- Equity curve is compounding: each trade risks `risk.green_signal_max_pct` of current equity. Reports win rate, profit factor, max drawdown, net return.
- Applies the **same daily circuit-breaker** as live: trips on `trade_management.daily_max_losses` OR `daily_max_drawdown_pct` (per-UTC-day, measured from that day's opening equity). Skipped trades are counted in `skipped_by_circuit_breaker`.

## Conservative intrabar policy (critical)

OHLC candles give no tick ordering. Within a bar, test the candle **low against the SL as it stood entering the bar** (`sl_at_open`) BEFORE applying any TP-driven ratchet from that same bar. Otherwise you bias results optimistically (move stop up on a TP touch, then pretend the same candle's dip respected the higher stop). Changing this alone moved a sample PF 0.6→0.83.

## Live trailing-stop resolution (main.py backtest_check_loop)

- On an SL hit, **fill at the stop level** (`min(current, stop_loss)`), not the polled price, which may have gapped past it.
- **Classify WIN/LOSS by realized PnL**, not merely whether `tp1_hit` was tagged — a trailing stop can exit at breakeven or a small loss even after TP1. Tagging those as WIN corrupts win-rate, learning data, and the circuit-breaker.

**Why:** these two rules keep backtest metrics honest and live stats consistent with reality; an architect review flagged both as correctness bugs.

# Config gotcha

- `favorite_coins` lives under the `vmc` section of config.json, NOT top-level. `_backtest_symbols()` reads `CONFIG["vmc"]["favorite_coins"]` first.
