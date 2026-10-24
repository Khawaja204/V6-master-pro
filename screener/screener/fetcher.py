import asyncio
import logging
import time

import aiohttp
import pandas as pd

from config import BINANCE_BASE_URL, KLINE_LIMIT

log = logging.getLogger("fetcher")

TIMEOUT = aiohttp.ClientTimeout(total=15)
WEIGHT_WARN = 1000  # Binance IP limit is 1200 weight per minute
RAW_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trades", "taker_base", "taker_quote", "ignore",
]
FLOAT_COLUMNS = ["open", "high", "low", "close", "volume"]
KEEP_COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "close_time"]


class BinanceFetcher:
    def __init__(self, session, max_concurrent):
        self._session = session
        self._sem = asyncio.Semaphore(max_concurrent)
        self._pause_until = 0.0

    async def _respect_pause(self):
        remaining = self._pause_until - time.monotonic()
        if remaining > 0:
            await asyncio.sleep(remaining)

    async def _get(self, path, params=None, retries=4):
        url = BINANCE_BASE_URL + path
        last_error = None
        for attempt in range(1, retries + 1):
            await self._respect_pause()
            wait = 0.0
            async with self._sem:
                try:
                    async with self._session.get(url, params=params, timeout=TIMEOUT) as resp:
                        used = resp.headers.get("X-MBX-USED-WEIGHT-1M")
                        if used and int(used) >= WEIGHT_WARN:
                            log.warning("Binance weight %s/1200 this minute", used)
                        if resp.status in (418, 429):
                            wait = float(resp.headers.get("Retry-After", "60"))
                            self._pause_until = time.monotonic() + wait
                            log.warning("Rate limited (HTTP %s) on %s, pausing %.0fs",
                                        resp.status, path, wait)
                        else:
                            resp.raise_for_status()
                            return await resp.json()
                except aiohttp.ClientResponseError as exc:
                    if exc.status < 500:
                        raise  # client errors such as 400 or 451 will not fix themselves
                    last_error = exc
                    wait = min(2 ** attempt, 30)
                    log.warning("Server error %s on %s, attempt %d/%d",
                                exc.status, path, attempt, retries)
                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    last_error = exc
                    wait = min(2 ** attempt, 30)
                    log.warning("Network error %s on %s, attempt %d/%d",
                                type(exc).__name__, path, attempt, retries)
            await asyncio.sleep(wait)
        raise RuntimeError(f"Giving up on {path} ({type(last_error).__name__})")

    async def active_symbols(self, symbols):
        data = await self._get("/api/v3/exchangeInfo")
        trading = {s["symbol"] for s in data["symbols"] if s.get("status") == "TRADING"}
        active = []
        for sym in symbols:
            if sym in trading:
                active.append(sym)
            else:
                log.warning("Skipping %s: not TRADING on Binance", sym)
        return active

    async def closed_klines(self, symbol, interval):
        raw = await self._get("/api/v3/klines",
                              {"symbol": symbol, "interval": interval, "limit": KLINE_LIMIT})
        df = pd.DataFrame(raw, columns=RAW_COLUMNS)
        df[FLOAT_COLUMNS] = df[FLOAT_COLUMNS].astype(float)
        df["open_time"] = df["open_time"].astype("int64")
        df["close_time"] = df["close_time"].astype("int64")
        now_ms = int(time.time() * 1000)
        closed = df[df["close_time"] < now_ms].reset_index(drop=True)
        return closed[KEEP_COLUMNS]
