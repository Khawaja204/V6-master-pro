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

## Simple View is the DEFAULT landing, not the main dashboard
`#simple-view` ships with `class="active"` AND `let _svActive = true`, so on load
the Simple View overlay (fixed, `inset:0`, `z-index:500`) covers the main
dashboard. Users click "← Full Dashboard" (`toggleSimpleView()`) to reach it.
`renderSimpleView()` does NOT add `active` — only `toggleSimpleView()` does.
**Why it matters:** to screenshot/verify the redesigned main dashboard you must
disable the overlay (remove `active` from the `#simple-view` div), restart,
verify, then RESTORE `class="active"` — it is pre-existing behavior, do not alter
it permanently.

## Firecrawl `external_url` screenshots cache hard
Two consecutive screenshots of the same URL returned byte-identical images.
**How to apply:** bust with a throwaway query param (`/?v=verify2`) when you need
a fresh capture after a restart.

## RTL / Urdu safety
Data may contain Urdu strings (e.g. "Trap hai — Bilkul mat khareedo abhi").
Layout is made RTL-safe with `unicode-bidi: plaintext` on `td` and text-bearing
classes (`.ab-reason`, `.hist-detail`, `.cc-top-coin`, `.s-row`). Do not invent
Urdu text — only keep the CSS safe.

## Layout shape (after consolidation)
`#app-bar` (sticky) → `#status-strip` + `#market-strip` (NOT sticky, avoids
overlap) → `#paper-banner` / `#action-banner` → `#main` (flex column, gap, max
1180px centered) holding 7 `.panel` cards: Command Center, panel-a VMC,
panel-b Institutional, panel-c Whale Wall, panel-d Live Backtesting,
panel-e Alert History, Smart Money Divergence. `focus.html` (`/focus`) is a
separate page — leave it alone.
