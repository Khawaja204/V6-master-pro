import asyncio
import html
import logging
from datetime import datetime, timezone

import aiohttp

from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

log = logging.getLogger("alerter")
TIMEOUT = aiohttp.ClientTimeout(total=15)


def fmt_utc(bar_time_ms):
    return datetime.fromtimestamp(bar_time_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def build_message(s):
    return (
        f"<b>BUY signal: {html.escape(s.symbol)} {html.escape(s.interval)}</b>\n"
        f"Closed bar: {fmt_utc(s.bar_time_ms)}\n"
        f"Close: {s.close:.6g}\n"
        f"EMA21: {s.ema_fast:.6g} | EMA50: {s.ema_slow:.6g}\n"
        f"RSI14: {s.rsi:.2f}\n"
        f"RVOL: {s.rvol:.2f}x"
    )


class TelegramAlerter:
    def __init__(self, session, token, chat_id, retries=5):
        self._session = session
        self._token = token
        self._chat_id = chat_id
        self._retries = retries
        self.enabled = bool(token and chat_id)

    async def send(self, text):
        if not self.enabled:
            log.warning("Telegram env vars missing; alert not sent")
            return False
        # The token lives only in this URL. Never log the URL or the exception text.
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        payload = {"chat_id": self._chat_id, "text": text, "parse_mode": "HTML"}
        for attempt in range(1, self._retries + 1):
            wait = min(2 ** attempt, 60)
            try:
                async with self._session.post(url, json=payload, timeout=TIMEOUT) as resp:
                    if resp.status == 200:
                        return True
                    if resp.status == 429:
                        wait = float(resp.headers.get("Retry-After", wait))
                    log.warning("Telegram HTTP %s (attempt %d/%d)", resp.status, attempt, self._retries)
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                log.warning("Telegram network error %s (attempt %d/%d)",
                            type(exc).__name__, attempt, self._retries)
            await asyncio.sleep(wait)
        log.error("Telegram alert failed after %d attempts", self._retries)
        return False
