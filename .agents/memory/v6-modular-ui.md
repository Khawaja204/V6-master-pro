---
name: V6 modular UI (V6_Master_Pro_UI)
description: The clean modular dashboard rebuild — where it lives, how it is served, and why it is separate from the legacy index.html.
---

## What it is
`V6_Master_Pro_UI/` is the dashboard: `index.html`, `script.js` (all fetch/render),
`config.js` (editable endpoints / refresh / layout / watch coins / clients),
`deployment.txt`. `style.css` is now UNUSED — superseded by a Tailwind redesign.

## Styling: Tailwind redesign (supersedes the old "no embedded style" rule)
The user explicitly requested a full Tailwind redesign of `/v6/` to match an
attached mockup, as a single cohesive `index.html`. So index.html now loads the
Tailwind CDN + FontAwesome + lightweight-charts@4, and carries an embedded
`<style>` block. That `<style>` defines `:root` CSS vars (`--green/--red/--orange/
--yellow/--grey`) AND every component class that `script.js` injects via innerHTML
(`action-*`, `traffic-*`, `mini-bar*`, `coin-circle`, `vol-*`, `alert-item`,
`ca-*`, `sb-*` color classes, `buy-badge`/`avoid-badge`, `dg-value`/`.green/.red/
.orange`, row `hot`/`avoid-row`, `dtable` table styling).
**Why:** redesign request beats the older modular "NO embedded `<style>`" rule —
do NOT re-split CSS back out or strip the inline styles. `script.js` stays
external (it is the data engine).
**How to apply:** when rebuilding index.html, you MUST preserve all ~43 IDs
script.js reads/writes AND keep every injected component class defined in the
`<style>` block, or dynamic content renders unstyled. Scanner table is now 9
columns (Coin, Inst, Conf%, WhalePow, SL, TP1, TP2, TP3, Action) — thead,
empty-state colspan, and `updateScannerTable` row template must all stay at 9.
`fetchChart` normalizes the search input with `replace(/[^A-Z0-9]/g,'')` (strips
ALL slashes/spaces) before appending USDT — a single-`.replace` left a space and
blanked the chart.

## How it is served — `/v6`, NOT `/`
Flask (`main.py`) serves it NON-destructively at `/v6` via `send_from_directory`
(routes: `/v6` 302→`/v6/`, `/v6/` → index.html, `/v6/<path>` → assets, both
no-store). The legacy monolithic `index.html` is untouched at `/`.
**Why:** the new UI needs the Python backend for live data, and a static-only
deploy can't run it. Same-origin serving avoids CORS. `config.api.base=""` keeps
fetches root-relative (`/dashboard_data`, `/chart_data`) so it works behind the
Replit proxy and in production without edits.
**Caveat:** index.html uses RELATIVE asset hrefs, so it MUST be reached with the
trailing slash `/v6/` (hence the 302). At bare `/v6`, `style.css` would resolve
to `/style.css` and 404.

## Data contract it renders (from /dashboard_data)
Top inst_signals[] (symbol, folder, confidence, price, change_pct, score, rsi,
price_pos_pct, inst{traffic GREEN/YELLOW/RED, inst_score, ofi_score, whale_power,
reason}, sizing{alloc_usdt, note}, tp_zones{entry_low, stop_loss, tp1/2/3},
trading_strategy). Also btc{}, whale[]{whale_power,label,obi.obi}, smart_divergence[],
volume_surge[], alert_history[], backtest[]+total_wins/losses/win_rate, vmc{}.
Coin profile chart pulls `/chart_data?symbol=&interval=&limit=` → candles[] drawn
as a hand-built SVG candlestick (stale responses guarded by a request token).
**Backend strings interpolated into HTML are escaped** (`esc`) and `traffic` is
whitelisted before class interpolation.

## Deploy
Reserved VM / Autoscale (not Static). Start `python3 main.py`, entry `main.py`,
env BOT_TOKEN/SECRET_KEY/SESSION_SECRET. Documented in the folder's deployment.txt.
