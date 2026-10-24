import asyncio
import time

import aiohttp
import numpy as np
import pandas as pd
import pandas_ta as ta

from config import BINANCE_BASE_URL, SYMBOLS

BATCHES = 5            # 5 x 1000 bars
COOL = 3
FEE = 0.001            # per side
SL_ATR = 1.2
TP2_R = 3.0
BE_ATR = 0.6
BE_OFF = 0.0025
TRAIL_ATR = 1.0
MODES = ["bot", "pump", "normal", "vol"]
COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
        "qv", "n", "tb", "tq", "ig"]


async def fetch_all(session, symbol, interval):
    batches, end = [], None
    for _ in range(BATCHES):
        params = {"symbol": symbol, "interval": interval, "limit": 1000}
        if end is not None:
            params["endTime"] = end
        async with session.get(BINANCE_BASE_URL + "/api/v3/klines", params=params,
                               timeout=aiohttp.ClientTimeout(total=20)) as resp:
            resp.raise_for_status()
            raw = await resp.json()
        if not raw:
            break
        batches.insert(0, raw)
        end = raw[0][0] - 1
        await asyncio.sleep(0.2)
    df = pd.DataFrame([row for b in batches for row in b], columns=COLS)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    df["open_time"] = df["open_time"].astype("int64")
    df["close_time"] = df["close_time"].astype("int64")
    now_ms = int(time.time() * 1000)
    return df[df["close_time"] < now_ms].reset_index(drop=True)


def indicators(df):
    d = df.copy()
    d["ema21"] = ta.ema(close=d["close"], length=21)
    d["ema50"] = ta.ema(close=d["close"], length=50)
    d["rsi"] = ta.rsi(close=d["close"], length=14)
    d["atr"] = ta.atr(high=d["high"], low=d["low"], close=d["close"], length=14)
    d["rvol"] = d["volume"] / d["volume"].rolling(20).mean()
    d["green"] = d["close"] > d["open"]
    day = d["open_time"] // 86_400_000
    tp = (d["high"] + d["low"] + d["close"]) / 3
    d["vwap"] = (tp * d["volume"]).groupby(day).cumsum() / d["volume"].groupby(day).cumsum()
    d["atr_ok"] = d["atr"] > d["atr"].rolling(20).mean()
    return d.reset_index(drop=True)


def signals(d, mode):
    if mode == "bot":
        s = (d["close"] > d["ema21"]) & (d["close"] > d["ema50"]) & (d["rsi"] >= 50) & (d["rvol"] >= 1.5)
    elif mode == "pump":
        s = (d["close"] > d["vwap"]) & (d["close"] > d["ema21"]) & (d["rvol"] >= 2.0) & d["green"] & (d["rsi"] < 80)
    elif mode == "normal":
        s = ((d["close"] > d["ema21"]) & (d["rsi"] >= 50) & (d["rvol"] >= 1.2) & d["green"]
             & (d["h1c"] > d["h1ema50"]) & (d["h1rsi"] >= 50))
    else:
        buy_at = np.maximum(d["vwap"], d["ema21"])
        touch = (d["low"] <= buy_at * 1.003) & (d["high"] >= buy_at * 0.997)
        s = touch & (d["rvol"] >= 1.5) & (d["close"] >= d["open"]) & d["atr_ok"]
    return s.fillna(False).astype(bool).values


def simulate(d, sig):
    close, high, low = d["close"].values, d["high"].values, d["low"].values
    atr = d["atr"].values
    n, i, last, out = len(d), 0, -10**9, []
    while i < n - 1:
        if sig[i] and i - last > COOL and np.isfinite(atr[i]) and atr[i] > 0:
            entry, a = close[i], atr[i]
            risk = SL_ATR * a
            sl, tp2 = entry - risk, entry + TP2_R * risk
            be, trail, hh, j, px = False, 0.0, high[i], i + 1, None
            while j < n:
                hh = max(hh, high[j])
                if not be and close[j] >= entry + BE_ATR * a:
                    be, trail = True, entry * (1 + BE_OFF)
                if be:
                    trail = max(trail, hh - TRAIL_ATR * atr[j])
                stop = max(sl, trail) if be else sl
                if low[j] <= stop:
                    px = stop
                    break
                if high[j] >= tp2:
                    px = tp2
                    break
                j += 1
            if px is None:
                px, j = close[n - 1], n - 1
            out.append((px - entry) / risk - 2 * FEE * entry / risk)
            last, i = j, j + 1
        else:
            i += 1
    return out


def stats(rs):
    if not rs:
        return "trades=0"
    r = np.array(rs)
    eq = np.cumsum(r)
    dd = (np.maximum.accumulate(eq) - eq).max()
    return (f"trades={len(r):4d} win={(r > 0.05).mean() * 100:5.1f}% "
            f"avgR={r.mean():+.2f} totR={r.sum():+.1f} maxDD={dd:.1f}R")


async def main():
    agg = {}
    async with aiohttp.ClientSession(headers={"User-Agent": "v6-backtest/1.0"}) as session:
        for sym in SYMBOLS:
            try:
                d15 = indicators(await fetch_all(session, sym, "15m"))
                d1h = indicators(await fetch_all(session, sym, "1h"))
            except Exception as exc:
                print(f"skip {sym}: {type(exc).__name__}", flush=True)
                continue
            h1 = d1h[["close_time", "close", "ema50", "rsi"]].rename(columns={
                "close_time": "h1_close", "close": "h1c", "ema50": "h1ema50", "rsi": "h1rsi"})
            d15m = pd.merge_asof(d15.sort_values("open_time"), h1.sort_values("h1_close"),
                                 left_on="open_time", right_on="h1_close", direction="backward")
            for mode in MODES:
                agg.setdefault(("15m", mode), []).extend(simulate(d15m, signals(d15m, mode)))
                if mode != "normal":
                    agg.setdefault(("1h", mode), []).extend(simulate(d1h, signals(d1h, mode)))
            print(f"done {sym}", flush=True)
    print("\ninterval  mode     result")
    for (iv, mode), rs in agg.items():
        print(f"{iv:<9}{mode:<9}{stats(rs)}")


if __name__ == "__main__":
    asyncio.run(main())
