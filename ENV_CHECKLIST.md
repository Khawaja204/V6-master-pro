# ENV_CHECKLIST — Render Dashboard Environment Variables

Set each of these manually in:
**Render Dashboard → Your Service → Environment → Add Environment Variable**

Never commit values to git. Keys only are listed here.

---

## Required — Bot & Alerts

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Telegram bot token from @BotFather |
| `CHAT_ID` | Telegram chat/channel ID for alerts |

## Required — Admin & Security

| Variable | Description |
|---|---|
| `ADMIN_PASSWORD` | Password for the /admin dashboard |
| `SECRET_KEY` | API access key for /get_data endpoint |
| `SESSION_SECRET` | Flask session secret (long random string) |

## Required — On-Chain Data

| Variable | Description |
|---|---|
| `ETHERSCAN_API_KEY` | Etherscan API key for ETH flow tracking |
| `BSCSCAN_API_KEY` | BSCscan API key for BNB whale moves |

## Optional — Google Sheets Logging

| Variable | Description |
|---|---|
| `GOOGLE_CREDENTIALS` | Service account JSON (full contents as one-line string) |
| `GOOGLE_SHEET_ID` | Target Google Sheet ID |

## Optional — Email Alerts

| Variable | Description |
|---|---|
| `EMAIL_USER` | Gmail address used to send alerts |
| `EMAIL_PASS` | Gmail app password (not your login password) |
| `EMAIL_TO` | Recipient email address |

## Optional — Binance Live Trading (leave blank for paper mode)

| Variable | Description |
|---|---|
| `API_KEY` | Binance API key (only needed for real trading) |
| `SECRET` | Binance API secret (only needed for real trading) |

## Optional — Misc

| Variable | Description |
|---|---|
| `TELEGRAM_PROXY` | SOCKS5/HTTP proxy for Telegram (e.g. socks5://host:port) |
| `PORT` | HTTP port — Render sets this automatically, do not override |

---

## Notes

- `paper_mode` is **hardcoded to True** in main.py on every startup. The bot
  will never place real orders unless you also set `API_KEY` + `SECRET` **and**
  manually toggle real mode from the admin dashboard.
- `GOOGLE_CREDENTIALS` must be the entire service-account JSON minified to a
  single line (no line breaks).
- `SESSION_SECRET` should be a random 32+ character string. Generate one with:
  `python3 -c "import secrets; print(secrets.token_hex(32))"`
