---
name: V6 Final Score (54-point engine) + coin volume key gotcha
description: How the 54-point V6 score is computed/wired, plus the volume_usdt schema gotcha that silently zeroed surge detection.
---

## Coin schema gotcha — use `volume_usdt`, never `volume`
VMC coin objects (from `categorize_signals` in logic.py) carry 24h quote volume
under the key **`volume_usdt`** (rounded `quoteVolume`). They do NOT have a
`volume` key. inst_signals built with `**coin` inherit this.
**Why it matters:** the volume-surge detector in `data_refresh_loop` originally
read `c.get("volume", 0)`, so `volume_surge` was ALWAYS empty (every value 0).
This went unnoticed until the V6 Technical subscore (which depends on
volume-surge membership) was always starved to its low path.
**How to apply:** any code reading a coin's traded volume must use
`c["volume_usdt"]`. Note the WATCH-card / `find_*` coin dicts elsewhere use a
`volume` key (built separately around logic.py:987) — schemas are NOT uniform,
so confirm the key for the specific dict you're touching.

## V6 Final Score engine (logic.py `compute_v6_final_score`)
54 raw points, scaled to 0-100, BUY/WAIT/SELL label + badge-buy/wait/sell class.
Categories: Market Regime 10 (trend+volatility), Inst/Whale 12 (inst_score 6 +
whale_power 6), Technical 12 (RSI 4 + MACD 4 + volume-surge 4), Smart Divergence
10 (ofi_score 6 + ACCUM/DIST 4), Trade Engine 10 (R/R 5 + traffic light 5).
Thresholds: score>=68 BUY, >=45 WAIT, else SELL.
MACD is real: `calculate_macd` (EMA 12/26/9) via `fetch_macd_for_symbol` (60
klines), attached per signal as `macd_hist` in the scan loop. Score is attached
as `s["v6"]` after inst_signals + smart_div + volume_surge are all built, using a
divergence map and a surge set keyed by symbol.
**Frontend:** `/v6/` dashboard binds `c.v6` to the TDE score block and the
scanner Action/V6 columns; poll cadence lives in config.js `refresh.intervalSec`.
