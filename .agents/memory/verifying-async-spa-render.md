---
name: Verifying async-fetch SPA rendering + init-order traps
description: Why a dashboard can be stuck on "Loading...", how an early throw blocks all data, the unpinned-CDN trap, and how to verify with jsdom.
---

## The real failure mode (V6 /v6/ dashboard)
Whole dashboard stuck on "Loading..."/dashes in a REAL browser. Cause was an
ordering trap, not data: `DOMContentLoaded` called `initChart()` BEFORE
`fetchAll()`. `initChart()` threw, so `fetchAll()` never ran and no panel ever
populated. **Lesson:** never let a non-critical init step (chart, widget) run
before — and unguarded in front of — the data fetch. Wrap each init step in its
own try/catch so one failure can't block the rest.

## Why initChart threw — unpinned CDN
`index.html` loaded `unpkg.com/lightweight-charts/...` with NO version pin, so it
pulled the latest major (v5). v5 REMOVED `chart.addCandlestickSeries()` (now
`addSeries(CandlestickSeries,...)`) and `series.setMarkers()` (now
`createSeriesMarkers(series, markers)`). The v4-era code threw on load.
**Fix:** pin the CDN to a major (`lightweight-charts@4`) so the API the code
targets stays stable. **Lesson:** always pin third-party CDN libs to a major
version; an unpinned lib silently upgrades and breaks at runtime, not build time.

## Verifying — jsdom in the code-execution sandbox
Run the real `index.html` + `script.js` against the real `/dashboard_data` JSON
inside jsdom (install via `installLanguagePackages` if missing). Mock
`window.fetch`, exec script with `new window.Function(src).call(window)`,
dispatch `DOMContentLoaded`, wait ~400ms, assert on
`#scanner-tbody tr` count and field text.

PITFALLS that gave false confidence:
- Stubbing `window.LightweightCharts = undefined` makes `initChart` early-return,
  so it HIDES an initChart-throws bug. To test resilience, mock it to THROW and
  confirm data still renders.
- Functions declared in `script.js` are NOT on `window` when run via
  `new window.Function(src)`. To exercise a code path (e.g. switch the charted
  coin then re-run `fetchChart`), set inputs BEFORE dispatching `DOMContentLoaded`
  and let the natural init call chain run it.
- `screenshot type=external_url` (Firecrawl) loads the real (v5) CDN too, so it
  reproduced the real bug — but it ALSO captures before async fetch resolves and
  caches JS assets, so it can't distinguish "still loading" from "broken". Use
  jsdom for a definitive answer; use `app_preview` (returns browser logs) when an
  artifact exists.

## /v6/ route reminder
`/v6/` must serve `V6_Master_Pro_UI/index.html` (modular, references relative
script.js/style.css), NOT root `index.html` (self-contained monolith). Wrong one
makes script.js edits silently no-op.
