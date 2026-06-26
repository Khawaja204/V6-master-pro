---
name: Dashboard UI structure & safe-restructure rules
description: Non-obvious facts for editing index.html (main dashboard) layout without breaking JS or behavior.
---

# Main dashboard (index.html, served at `/`)

## Safe to restructure the HTML freely
The page JS touches the DOM ONLY via `getElementById` + `innerHTML` — no
`querySelector`/`closest`/`parentNode` structural traversal.
**How to apply:** you may re-layout/reparent any markup as long as you preserve
(a) every element `id` the JS reads/writes and (b) any class names the JS
toggles or injects. Audit with `grep -oE 'id="[^"]+"' index.html | sort | uniq -d`
(must be empty) and confirm each JS `getElementById` target resolves once.

## Main dashboard is the DEFAULT landing (Simple View is opt-in)
The main dashboard now loads by default: `#simple-view` has NO `class="active"`
and `let _svActive = false`. Users click "⚡ SIMPLE" (`toggleSimpleView()`) to
open the Simple View overlay (fixed, `inset:0`, `z-index:500`). `renderSimpleView()`
does NOT add `active` — only `toggleSimpleView()` does.
**Why it matters:** this was an intentional, permanent change requested by the user.
Do NOT re-add `class="active"` or flip `_svActive` back to `true`. To screenshot/
verify the main dashboard, no overlay-disabling step is needed anymore.

## Firecrawl `external_url` screenshots cache hard
Two consecutive screenshots of the same URL returned byte-identical images.
**How to apply:** bust with a throwaway query param (`/?v=verify2`) when you need
a fresh capture after a restart.

## RTL / Urdu safety
Data may contain Urdu strings (e.g. "Trap hai — Bilkul mat khareedo abhi").
Layout is made RTL-safe with `unicode-bidi: plaintext` on `td` and text-bearing
classes (`.ab-reason`, `.hist-detail`, `.cc-top-coin`, `.s-row`). Do not invent
Urdu text — only keep the CSS safe.

## Layout shape (after screenshot rebuild)
`#app-bar` (sticky) → `#status-strip` + `#market-strip` → `#paper-banner` /
`#action-banner` → `#main` (flex column, max 1180px centered). `#main` now opens
with STATIC screenshot UI placeholders (display-only, no data wiring): Coin
Profile card (`.panel.open` so the relocated `#search-input`/`#search-results`
dropdown isn't clipped) + chart-box placeholder, Trade Decision Engine
(`.tde-*`, disabled `.btn-execute`/`.btn-panic`), whale-bag `.metric-row`,
`.sentiment-grid` gauges. Below those sit the LIVE data `.panel` cards (unchanged
IDs): Command Center, panel-a VMC, panel-b Institutional, panel-c Whale Wall,
panel-d Backtesting, panel-e Alert History, panel-f Smart Money Divergence, then
static HIFI/DOGE `.mini-grid` + Client & API `.capi-table`.
**Why:** user wanted the screenshot's terminal look but keep all existing data —
so new sections are placeholders and every live panel/ID was preserved.
`focus.html` (`/focus`) is a separate page — leave it alone.
