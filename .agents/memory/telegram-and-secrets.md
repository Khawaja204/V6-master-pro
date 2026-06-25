---
name: Telegram alerts & secret hardening
description: How Telegram alerting is wired in V6, and how to diagnose send failures (esp. HTTP 404).
---

# Telegram alerting (V6 Master Pro)

- `send_telegram()` returns `bool` (True only on HTTP 200 + `{"ok":true}`). It tries the `TELEGRAM_PROXY` (if set) first, then falls back to a direct connection. It logs API rejections at WARNING.
- `notify_trade()` is the unified per-trade/per-entry alert (side, strategy, mode, TP/SL, rationale). Fired from `alert_vip` on a real auto-entry and from `admin_manual_trade` on a successful manual trade.
- `/admin/test_telegram` calls `send_telegram` and reports the boolean back to the admin UI.

## Diagnosing send failures

- **HTTP 404 `{"ok":false,"error_code":404,"description":"Not Found"}`** = the `BOT_TOKEN` in the URL is **invalid/revoked**, NOT a code bug. Telegram returns 404 for an unknown token (a bad `chat_id` would be 400, an unauthorized-but-valid token 401).
  - **Fix is the user's:** get a fresh token from @BotFather and update the `BOT_TOKEN` secret. The code cannot fix an invalid secret.
  - Stripping whitespace from the token did NOT resolve it here, confirming the token value itself is wrong.
- `BOT_TOKEN` / `CHAT_ID` are now `.strip()`-ed at load (`(os.getenv(...) or "").strip() or None`) to defend against pasted-secret newline/space, a common cause of malformed-URL 404s.

**Why:** before returning a bool, `send_telegram` swallowed failures silently, so a dead token looked like "alerts work". Always surface API rejection so the dead-token case is visible.
