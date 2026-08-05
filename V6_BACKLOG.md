# V6 Master Pro — Project Backlog

> Rule: Update → Review → Fix → Finalize. Never skip the review step.
> Note: Render deployment is COMPLETE on free tier. Do NOT suggest paid Render deployment tasks.
> Note: SPOT trading only. Never suggest short-position fixes.

---

## STATUS KEY
`✅ DONE` | `🔄 IN PROGRESS` | `⏳ PENDING` | `❌ BLOCKED` | `🐛 BUG`

---

## Completed Tasks

### ✅ [2026-08-05] Architecture Review + Targeted Fixes
- Full 5-subagent read-only review: bot logic, thread safety, error handling, security, dead code
- Cross-checked all 22 findings against evolved codebase — most Criticals already resolved
- **Applied fixes:**
  - Removed duplicate `[V6 WS]` and `[V6 MTF]` log.info lines at startup (I-6)
  - Added `log.debug/warning` to 7 silent `except: pass` blocks at startup (M-3)
- **Confirmed already resolved:** `_whale_copy_state_lock`, `_ledger_lock`, client password hashing, CSRF tokens, admin password random token, persist_window, X-API-Key header
- **Verified:** syntax clean, app running at Scan #3+ ✅

### ✅ [2026-07-31] Shell Aliases Auto-Load Fix
- `aj`, `chat-log`, `backlog`, `sp` auto-load on every new shell via `.config/bashrc` hook

### ✅ [2026-07-31] Render.com Free-Tier Deployment — LIVE
- App deployed successfully by user via shell commands. Free-tier confirmed working.

### ✅ [2026-07-29] Code Review Workflow Established
- Update → Review → Fix → Finalize rule adopted permanently
- `V6_BACKLOG.md` + `AGENT_CHAT_LOG.md` maintained after every session

### ✅ [2026-07-29] Backend Robustness (logic.py)
- `_binance_get`: 429 exponential backoff + host-switch jitter
- 4× bare `requests.get` → `_SESSION.get`

### ✅ [2026-07-29] /health Endpoint (main.py)
- `GET /health` → PKT timestamp, cycle_count, uptime, paper_mode — HTTP 200 always ✅

### ✅ [2026-07-29] Render Deployment Files
- `render.yaml`, `Procfile`, `.renderignore`, `ENV_CHECKLIST.md`, `requirements.txt`

### ✅ [2026-07-28] Shell Command System
- `v6-cmd.sh`: deploy, stop, restart, status, logs, save, push, full, aj, chat-log, backlog

### ✅ [2026-07-28] saveproj.sh Bug Fixes
- `-size -1M` → `-size -1000k`; MIME-type binary check; exclusion paths added

### ✅ [2026-07-28] Git Clean Backup
- `[main a073a38]` — deleted project.txt/project.zip blobs (81k lines removed)

---

## Pending / Known Issues

### ⏳ Repo Size (~490 MB)
- Old git history blobs; `git gc --aggressive --prune=now` or `git filter-repo` can shrink it
- Low priority — GitHub push is already working

### ⏳ `scoring_engine.py` Stub
- `calculate_54_point_score()` returns literal `0`; not called anywhere (call removed in logic.py)
- Safe to leave as placeholder; replace only if a new scoring engine is needed

### ⏳ `detect_combo_signals()` Not Wired
- Fully implemented in logic.py but no `combo_check_loop` calls it
- Combo Bot produces no trades — user decision whether to activate

### 🐛 EURUSDT Whale Copy Trade
- `WC-1785263888-EURU`: target == entry_price == 1.14; will time out at 12h. Low priority.

### ⏳ BOT_TOKEN Validity
- Telegram alerts may be offline (HTTP 404 = invalid/revoked token)
- Verify via @BotFather if alerts aren't arriving

---

## Ideas / Future Work

- [ ] Wire `detect_combo_signals()` → `combo_check_loop` to activate Combo Bot
- [ ] Wire `detect_rsi_divergence()` into scan loop (currently only used at scoring layer)
- [ ] Rate-limit `/health` endpoint (currently public)
- [ ] Paper trade win-rate chart on dashboard
