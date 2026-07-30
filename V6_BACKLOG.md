# V6 Master Pro — Project Backlog

> Rule: Update → Review → Fix → Finalize. Never skip the review step.

---

## STATUS KEY
`✅ DONE` | `🔄 IN PROGRESS` | `⏳ PENDING` | `❌ BLOCKED` | `🐛 BUG`

---

## Completed Tasks

### ✅ [2026-07-28] Shell Command System
- Created `v6-cmd.sh` with: `deploy`, `stop`, `restart`, `status`, `logs`, `save`, `push`, `full`
- Created `.bash_aliases` sourcing `v6-cmd.sh`
- Wired auto-load via `$REPL_HOME/.config/bashrc` → Replit Nix bashrc hook
- `sp` alias (saveproj.sh) confirmed working in fresh interactive bash session
- **Verified:** `bash -i -c "sp"` → ✅ Exported project.txt

### ✅ [2026-07-28] saveproj.sh Bug Fixes
- Fixed `-size -1M` → `-size -1000k` (GNU find mebibyte rounding bug)
- Fixed `file` binary check to use `--mime-type -b` (was excluding all Python/sh files)
- Added `! -path "./.local/*"` and `! -path "./attached_assets/*"` exclusions
- **Verified:** 41 files scanned, 648K output

### ✅ [2026-07-29] Backend Robustness (logic.py)
- Added `import random` at top of file
- `_binance_get`: full 429 exponential backoff (3 retries, `2^n × uniform(1,3)` s) + jitter `uniform(0.5, 2.0)` s between host switches
- Converted 4 bare `requests.get` calls to use global `_SESSION` (timeout 5→10 s):
  - `_get_eth_price_usd()` line 21
  - `get_bsc_whale_moves()` line 150
  - `get_funding_rate()` line 255 + removed stale `import requests` inside fn
  - `fetch_funding_rate()` line 1677
- **Reviewed:** for/else logic verified; forward-reference to `_SESSION` safe (called at runtime, not import time)
- **Verified:** `python3 -c "import ast; ast.parse(...)"` → syntax clean ✅

### ✅ [2026-07-29] /health Endpoint (main.py)
- Added `GET /health` returning: `status`, `timestamp` (PKT), `cycle_count`, `uptime`, `paper_mode`, `scan_status`
- Returns HTTP 200 always (even on internal error — Render health checks need 200)
- **Verified:** `curl http://127.0.0.1:8080/health` → `{"status":"live",...}` ✅

### ✅ [2026-07-29] Render.com Deployment Files
- `render.yaml` — Blueprint: Python runtime, gunicorn start, `/health` check, auto-deploy
- `requirements.txt` — Trimmed to only actually-used packages (removed ccxt, pandas, numpy, python-telegram-bot, websocket-client after codebase audit)
- `Procfile` — gunicorn with `--workers 1 --timeout 120 --keep-alive 5`
- `.renderignore` — excludes .env, logs, __pycache__, .replit, dev scripts
- `ENV_CHECKLIST.md` — all 15 env vars documented (keys only)
- `gunicorn` installed into workspace pythonlibs
- **Reviewed:** no secrets in any file; ccxt/pandas/numpy confirmed not imported anywhere; gspread/oauth2client confirmed lazy-imported in main.py + logic.py ✅

---

## Pending / Known Issues

### ⏳ Git Push to GitHub
- Last local commit: `[main a073a38] V6 clean backup 2026-07-28`
- Remote: `https://github.com/Khawaja204/V6-master-pro.git`
- New files not yet pushed: `render.yaml`, `Procfile`, `.renderignore`, `ENV_CHECKLIST.md`, `V6_BACKLOG.md`, `v6-cmd.sh`, `.bash_aliases`, `requirements.txt` (updated)
- **Action needed:** Run `git push origin main` or use `push` shell command

### ⏳ Repo Size (~490 MB)
- Almost entirely old git history (project.txt/project.zip blobs from prior commits)
- Can be cleaned with `git gc --aggressive --prune=now` or `git filter-repo`
- Low priority unless GitHub push is slow/rejected

### ⏳ Render First Deploy
- All deployment files ready
- Still need to: connect GitHub repo on Render, set env vars from `ENV_CHECKLIST.md`

### 🐛 EURUSDT Whale Copy Trade
- Trade `WC-1785263888-EURU` has `target == entry_price == 1.14`
- Can never hit target; will time out at 12h mark
- Low priority

### ⏳ BOT_TOKEN Validity
- Telegram alerts may be offline (HTTP 404 = invalid/revoked token)
- User should verify via @BotFather if alerts aren't arriving

---

## Ideas / Future Work

- [ ] Gunicorn production WSGI (already in Procfile — activate on Render deploy)
- [ ] Rate-limit `/health` endpoint (currently public, no throttle)
- [ ] Add `/metrics` endpoint (Prometheus-style for uptime monitors)
- [ ] Paper trade win-rate chart on dashboard
