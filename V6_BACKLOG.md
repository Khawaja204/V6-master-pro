# V6 Master Pro — Project Backlog

> Rule: Update → Review → Fix → Finalize. Never skip the review step.
> Note: Render deployment is COMPLETE on free tier. Do NOT suggest paid Render deployment tasks.

---

## STATUS KEY
`✅ DONE` | `🔄 IN PROGRESS` | `⏳ PENDING` | `❌ BLOCKED` | `🐛 BUG`

---

## Completed Tasks

### ✅ [2026-07-31] Shell Aliases Auto-Load Fix
- Added `aj` (agent journal → AGENT_CHAT_LOG.md), `chat-log` (alias for `aj`), `backlog` (V6_BACKLOG.md) to `v6-cmd.sh`
- All 4 aliases now auto-load on every new shell: `aj`, `chat-log`, `backlog`, `sp`
- Auto-load chain: Replit Nix bashrc → `$REPL_HOME/.config/bashrc` → `.bash_aliases` → `v6-cmd.sh`
- No manual `source` needed — verified with `bash -i -c "..."` tests
- **Verified:** all 4 aliases confirmed working ✅

### ✅ [2026-07-31] Render.com Free-Tier Deployment — LIVE
- App deployed successfully by user via shell commands
- Free-tier Render deployment confirmed working
- All deployment files (`render.yaml`, `Procfile`, `.renderignore`, `ENV_CHECKLIST.md`) served their purpose
- **Status: PRODUCTION LIVE** — no further Render deployment tasks needed

### ✅ [2026-07-29] Code Review Workflow Established
- Update → Review → Fix → Finalize rule adopted
- `V6_BACKLOG.md` and `AGENT_CHAT_LOG.md` created and maintained
- gunicorn installed (v26.0.0); requirements.txt trimmed of 5 unused packages

### ✅ [2026-07-29] Backend Robustness (logic.py)
- `import random` added
- `_binance_get`: 429 exponential backoff (3 retries, `2^n × uniform(1,3)` s) + host-switch jitter
- 4× bare `requests.get` → `_SESSION.get` (10 s timeout)
- **Verified:** syntax clean, app running stable ✅

### ✅ [2026-07-29] /health Endpoint (main.py)
- `GET /health` → `{"status":"live","timestamp":"PKT","cycle_count":...,"uptime":"..."}`
- Always returns HTTP 200 (Render health check compatible)
- **Verified:** curl confirmed ✅

### ✅ [2026-07-29] Render Deployment Files Created
- `render.yaml`, `Procfile`, `.renderignore`, `ENV_CHECKLIST.md`, `requirements.txt`
- **Deployed to Render free tier successfully by user** ✅

### ✅ [2026-07-28] Shell Command System (v6-cmd.sh)
- Commands: `deploy`, `stop`, `restart`, `status`, `logs`, `save`, `push`, `full`
- Auto-load via `.config/bashrc` hook confirmed working

### ✅ [2026-07-28] saveproj.sh Bug Fixes
- Fixed `-size -1M` → `-size -1000k` (GNU find rounding bug)
- Fixed `file` binary check → MIME-type based (was excluding all .py/.sh files)
- **Verified:** 41 files / 648K output ✅

### ✅ [2026-07-28] Git Clean Backup
- Committed: `[main a073a38] V6 clean backup 2026-07-28`
- Deleted project.txt/project.zip blobs (81k lines removed)

---

## Pending / Known Issues

### ⏳ Repo Size (~490 MB)
- Almost entirely old git history blobs — no individual file violation
- `git gc --aggressive --prune=now` or `git filter-repo` can shrink it if needed
- Low priority — GitHub push is already working

### 🐛 EURUSDT Whale Copy Trade
- Trade `WC-1785263888-EURU` has `target == entry_price == 1.14`
- Will time out at 12h; cannot hit target naturally
- Low priority — affects one stale trade only

### ⏳ BOT_TOKEN Validity
- Telegram alerts may be offline (HTTP 404 = invalid/revoked token)
- Verify via @BotFather if alerts aren't arriving

---

## Ideas / Future Work

- [ ] Rate-limit `/health` endpoint (currently public, no throttle)
- [ ] Add `/metrics` endpoint (Prometheus-style for uptime monitors)
- [ ] Paper trade win-rate chart on dashboard

## DEPLOYMENT NOTE | 2026-07-31
- Render free-tier deployment: LIVE ✅
- GitHub repo: Khawaja204/V6-master-pro
- Git history cleaned: 490MB → <50MB
- Status: Auto-deploy pipeline working
- Note: Free-tier sleeps after 15min inactivity (cold starts)
