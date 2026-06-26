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

## Layout shape (consolidated to match screenshot)
`#app-bar` (sticky) → `#status-strip` + `#market-strip` → `#paper-banner` →
`#main`. Visible `#main` order: `.grid-2` [Coin Profile (inline SVG candlestick
chart, filled stat values) | Trade Decision Engine] → Sentiment & Whale Data →
panel-b Institutional & Wall Scanner (LIVE) → Smart Money Divergence panel-f
(LIVE) → `.grid-2` HIFI/DOGE cards → panel-d Backtesting (LIVE) → panel-e Alert
History (LIVE) → Client & API.

## Modules NOT in the screenshot live in a hidden wrapper — don't delete them
The user demanded the screenshot's single consolidated layout (no VMC table, no
Whale Wall table, no Command Center, no Action Signals banner, no duplicate
metric row / Smart Money card). Those modules are NOT deleted — they sit inside a
`<div style="display:none" aria-hidden="true">` at the end of `#main` (panel-cc,
panel-a, panel-c) plus `#action-banner` hidden in place. Their IDs stay alive so
the ID-only JS render loop keeps writing without throwing.
**Why:** deleting a data-bound element makes `getElementById(...).innerHTML` throw
and halts the whole update loop. Hiding preserves both the clean layout and the JS.
**Caveat:** to re-show any hidden module you must move it OUT of the wrapper —
toggling only the child's own `display` won't override the hidden parent.

## Placeholder text is gone — values are static-but-realistic
No `"wiring in progress"` / `"display only"` / `"—"` left. Coin profile, sentiment
wallets, HIFI/DOGE show clean fixed values; EXECUTE/PANIC buttons are visually
active (no handlers). `.chart-box` shows a hand-built SVG candlestick (no live feed).
**Why:** user explicitly rejected any placeholder; wanted a functional-looking UI.
`focus.html` (`/focus`) is a separate page — leave it alone.
