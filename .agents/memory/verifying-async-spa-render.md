---
name: Verifying async-fetch SPA rendering
description: Why external_url screenshots mislead on JS dashboards, and the jsdom sandbox technique that gives a definitive answer.
---

## Rule
Do NOT trust `screenshot type=external_url` (Firecrawl) to verify a page whose
content arrives via an async `fetch()` after load. It frequently captures BEFORE
the fetch resolves, so a working dashboard looks stuck on its "Loading..."
placeholder. It also hard-caches JS/CSS assets across a session (query strings
like `?v=N` don't reliably bust it).

**Why:** Cost real time on the V6 `/v6/` dashboard — two external screenshots
showed "Loading scanner data..." while the render logic was actually correct.

## How to verify instead
Run the real HTML + script.js against the real endpoint inside the JS
code-execution sandbox with jsdom (install via `installLanguagePackages` if
absent). Mock `window.fetch` to return the actual `/dashboard_data` JSON, exec
script.js with `new window.Function(src).call(window)`, dispatch a
`DOMContentLoaded` Event, wait ~500ms, then assert on
`document.getElementById('scanner-tbody').querySelectorAll('tr').length` and key
field text. Zero errors + populated rows = the logic works; any remaining blank
render in Firecrawl is a capture-timing artifact, not a bug.

Alternative when an artifact exists: `screenshot type=app_preview` returns
browser logs too. The V6 app is not a registered artifact, so jsdom was the path.

## Related gotcha (V6 /v6/ route)
`/v6/` must serve `V6_Master_Pro_UI/index.html` (the modular file that references
relative `script.js`/`style.css`), NOT root `index.html` (a self-contained
monolith with no external asset refs). Serving the wrong one makes all
script.js edits silently no-op while the page still appears to "work" from the
monolith's inline JS.
