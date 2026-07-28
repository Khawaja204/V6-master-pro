---
name: V6 Paper Trading Safety
description: Paper mode enforcement, kill switch, and backtest persistence rules.
---

## Paper Mode Enforcement
- `GLOBAL_DATA["paper_mode"]` is **hardcoded to `True`** at startup (not read from config).
- Toggling to REAL MODE via `/admin/set_mode` is **blocked** unless `"BINANCE"` key exists in `_API_KEYS`.
- `config.json` does NOT have a `paper_mode` key by design — absence means always True on restart.

## Kill Switch
- `/admin/kill_switch` (POST, admin-only): cancels all OPEN backtest + whale-copy trades, forces paper mode ON, trips the daily circuit-breaker.
- Button is in the admin UI next to "Clear Backtest" / "Clear Whale Copy".

## Backtest Signals Persistence
- File: `backtest_signals.json` (created on first resolved trade).
- Loaded at startup; only OPEN signals < 6h old are restored (stale OPEN signals dropped).
- Saved by `_save_backtest_signals()` called from `backtest_check_loop` on every change.

## Backtest Closure Timing
- Trades now close at 1h (not 4h) if no SL or TP hit.
- pnl < -0.5% → LOSS; otherwise → TIMEOUT.

## YELLOW signals in paper mode
- `_record_backtest_signal` skips RED always; skips YELLOW only in real mode.
- In paper mode YELLOW signals ARE recorded so LIVE BACKTESTING tab populates.

**Why:** Original code only allowed GREEN traffic through — with STUCK market conditions producing mostly YELLOW signals, the backtest tab was always empty. Real mode stays strict (GREEN-only).
