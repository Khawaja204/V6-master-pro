import asyncio
import logging
import sys
import time
from collections import deque

import aiohttp

import config
from alerter import TelegramAlerter, build_message, fmt_utc
from fetcher import BinanceFetcher
from strategy import compute_snapshot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("main")

SYMBOL_REFRESH_SECONDS = 3600


class ScanState:
    def __init__(self):
        self.recent_signals = deque(maxlen=200)
        self.last_bar = {}  # (symbol, interval) -> open_time of last processed closed bar


async def process(fetcher, alerter, state, symbol, interval):
    df = await fetcher.closed_klines(symbol, interval)
    if df.empty:
        return
    snap = compute_snapshot(symbol, interval, df)
    if snap is None:
        return

    key = (symbol, interval)
    prev = state.last_bar.get(key)
    if prev is not None and snap.bar_time_ms <= prev:
        return  # this closed bar was already handled

    state.last_bar[key] = snap.bar_time_ms
    log.info(
        "SNAP %s %s bar=%s close=%.6g ema21=%.6g ema50=%.6g rsi=%.2f rvol=%.2f",
        symbol, interval, fmt_utc(snap.bar_time_ms), snap.close,
        snap.ema_fast, snap.ema_slow, snap.rsi, snap.rvol,
    )

    if prev is None:
        log.info("Warm-up for %s %s: recorded baseline, no alert", symbol, interval)
        return

    if snap.is_normal_buy():
        state.recent_signals.append(snap)
        log.info("BUY signal %s %s", symbol, interval)
        await alerter.send(build_message(snap))


async def run_forever():
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_CHAT_ID:
        log.warning("TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not set; running without alerts")

    async with aiohttp.ClientSession(headers={"User-Agent": "v6-screener/1.0"}) as session:
        fetcher = BinanceFetcher(session, config.MAX_CONCURRENT)
        alerter = TelegramAlerter(session, config.TELEGRAM_TOKEN, config.TELEGRAM_CHAT_ID)
        state = ScanState()
        symbols = []
        last_refresh = 0.0

        while True:
            try:
                if not symbols or time.monotonic() - last_refresh > SYMBOL_REFRESH_SECONDS:
                    symbols = await fetcher.active_symbols(config.SYMBOLS)
                    last_refresh = time.monotonic()
                    log.info("Active symbols: %s", symbols)

                tasks = [
                    process(fetcher, alerter, state, sym, tf)
                    for sym in symbols
                    for tf in config.TIMEFRAMES
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, Exception):
                        log.error("Task failed: %s: %s", type(res).__name__, res)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Scan cycle failed; will retry next cycle")

            await asyncio.sleep(config.POLL_SECONDS)


if __name__ == "__main__":
    try:
        asyncio.run(run_forever())
    except KeyboardInterrupt:
        log.info("Stopped by user")
