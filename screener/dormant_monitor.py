import asyncio
import csv
import logging
import statistics
import time
from datetime import datetime, timezone

import aiohttp

BASE = "https://api.binance.com"
EXCLUDE = ("UP", "DOWN", "BULL", "BEAR")
STABLES = {"USDC", "FDUSD", "TUSD", "BUSD", "USD1", "RLUSD", "DAI", "USDP", "EUR", "AEUR"}
MIN_QVOL_NOW = 50_000      # current 24h quote volume (USD) must be at least this
MAX_BASE_MEDIAN = 20_000   # 30-day median daily quote volume must be below this
SPIKE_RATIO = 10           # current 24h volume / 30-day median
CHECK_EVERY = 3600         # seconds between scans
OUT = "dormant_list.csv"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dormant")


async def get(session, path, params=None):
    for attempt in range(1, 5):
        try:
            async with session.get(BASE + path, params=params,
                                   timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status in (418, 429):
                    wait = float(r.headers.get("Retry-After", "60"))
                    log.warning("rate limited, sleeping %.0fs", wait)
                    await asyncio.sleep(wait)
                    continue
                r.raise_for_status()
                return await r.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            log.warning("%s attempt %d failed: %s", path, attempt, type(exc).__name__)
            await asyncio.sleep(2 ** attempt)
    raise RuntimeError(f"giving up on {path}")


def is_candidate(sym):
    if not sym.endswith("USDT"):
        return False
    base = sym[:-4]
    if base.endswith(EXCLUDE) or base in STABLES:
        return False
    return True


async def scan(session):
    tickers = await get(session, "/api/v3/ticker/24hr")
    cands = []
    for t in tickers:
        sym = t["symbol"]
        if not is_candidate(sym):
            continue
        qv = float(t["quoteVolume"])
        if qv >= MIN_QVOL_NOW:
            cands.append((sym, qv, float(t["priceChangePercent"])))
    log.info("checking %d candidates", len(cands))

    rows = []
    for sym, qv, chg in cands:
        k = await get(session, "/api/v3/klines", {"symbol": sym, "interval": "1d", "limit": 31})
        now_ms = int(time.time() * 1000)
        closed = [c for c in k if int(c[6]) < now_ms]
        hist = [float(c[7]) for c in closed][-30:]
        if len(hist) < 20:
            continue
        med = statistics.median(hist)
        if med > MAX_BASE_MEDIAN:
            continue
        ratio = qv / max(med, 1.0)
        if ratio >= SPIKE_RATIO:
            rows.append({"symbol": sym, "qvol_24h": round(qv), "median_30d": round(med),
                         "ratio": round(ratio, 1), "change_24h_pct": round(chg, 2)})
        await asyncio.sleep(0.15)
    rows.sort(key=lambda r: r["ratio"], reverse=True)
    return rows


def save(rows):
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["scan_time", "symbol", "qvol_24h", "median_30d", "ratio", "change_24h_pct"])
        for r in rows:
            w.writerow([stamp, r["symbol"], r["qvol_24h"], r["median_30d"], r["ratio"], r["change_24h_pct"]])


async def main():
    log.info("dormant monitor started. Informational only. Possible manipulation risk. Not financial advice.")
    async with aiohttp.ClientSession(headers={"User-Agent": "v6-dormant/1.0"}) as session:
        while True:
            try:
                rows = await scan(session)
                save(rows)
                log.info("found %d coins with volume spike (saved to %s)", len(rows), OUT)
                for r in rows[:10]:
                    log.info("%s ratio=%s qvol=%s median=%s chg=%s%%", r["symbol"], r["ratio"],
                             r["qvol_24h"], r["median_30d"], r["change_24h_pct"])
            except Exception:
                log.exception("scan failed, will retry next cycle")
            await asyncio.sleep(CHECK_EVERY)


if __name__ == "__main__":
    asyncio.run(main())
