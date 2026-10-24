import asyncio
import itertools
import os
import pickle

import aiohttp
import numpy as np
import pandas as pd

from config import BINANCE_BASE_URL, SYMBOLS
from backtest import COOL, FEE, MODES, fetch_all, indicators, signals

CACHE = "bt_cache.pkl"
BE_OFF = 0.0025
SPLIT = 0.6
MIN_TRADES = 100
MIN_OOS = 30
GRID = {
    "sl": [1.2, 1.5, 2.0, 2.5],
    "tp2": [2.0, 3.0, 4.0],
    "be": [0.6, 1.0],
    "trail": [1.0, 1.5],
}
COMBOS = [("15m", m) for m in MODES] + [("1h", m) for m in MODES if m != "normal"]


async def load():
    if os.path.exists(CACHE):
        with open(CACHE, "rb") as f:
            return pickle.load(f)
    data = {}
    async with aiohttp.ClientSession(headers={"User-Agent": "v6-sweep/1.0"}) as session:
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
            data[sym] = (d15m, d1h)
            print(f"loaded {sym}", flush=True)
    with open(CACHE, "wb") as f:
        pickle.dump(data, f)
    return data


def simulate(d, sig, sl_m, tp2_r, be_m, tr_m):
    close, high, low, atr = d["close"].values, d["high"].values, d["low"].values, d["atr"].values
    n, i, last, out = len(d), 0, -10**9, []
    while i < n - 1:
        if sig[i] and i - last > COOL and np.isfinite(atr[i]) and atr[i] > 0:
            entry, a = close[i], atr[i]
            risk = sl_m * a
            sl, tp2 = entry - risk, entry + tp2_r * risk
            be, trail, hh, j, px = False, 0.0, high[i], i + 1, None
            while j < n:
                hh = max(hh, high[j])
                if not be and close[j] >= entry + be_m * a:
                    be, trail = True, entry * (1 + BE_OFF)
                if be:
                    trail = max(trail, hh - tr_m * atr[j])
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
            r = (px - entry) / risk - 2 * FEE * entry / risk
            out.append((i / n, r))
            last, i = j, j + 1
        else:
            i += 1
    return out


def summ(items):
    if not items:
        return dict(trades=0, win=np.nan, avgR=np.nan, totR=0.0, maxDD=np.nan)
    items = sorted(items)
    r = np.array([x[1] for x in items])
    eq = np.cumsum(r)
    return dict(trades=len(r), win=float((r > 0.05).mean() * 100), avgR=float(r.mean()),
                totR=float(r.sum()), maxDD=float((np.maximum.accumulate(eq) - eq).max()))


def main():
    data = asyncio.run(load())
    sigs = {}
    for sym, (d15m, d1h) in data.items():
        for mode in MODES:
            sigs[(sym, "15m", mode)] = signals(d15m, mode)
            if mode != "normal":
                sigs[(sym, "1h", mode)] = signals(d1h, mode)
    rows = []
    for sl, tp2, be, tr in itertools.product(GRID["sl"], GRID["tp2"], GRID["be"], GRID["trail"]):
        for iv, mode in COMBOS:
            items = []
            for sym, (d15m, d1h) in data.items():
                d = d15m if iv == "15m" else d1h
                items += simulate(d, sigs[(sym, iv, mode)], sl, tp2, be, tr)
            full = summ(items)
            ins = summ([x for x in items if x[0] < SPLIT])
            oos = summ([x for x in items if x[0] >= SPLIT])
            rows.append(dict(interval=iv, mode=mode, sl=sl, tp2=tp2, be=be, trail=tr,
                             trades=full["trades"], win=full["win"], avgR=full["avgR"],
                             totR=full["totR"], maxDD=full["maxDD"],
                             is_avgR=ins["avgR"], oos_trades=oos["trades"], oos_avgR=oos["avgR"]))
            print(f"sl={sl} tp2={tp2} be={be} tr={tr} {iv} {mode} done", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv("sweep_results.csv", index=False)
    cols = ["sl", "tp2", "be", "trail", "trades", "win", "avgR", "totR", "maxDD", "is_avgR", "oos_avgR"]
    print("\nTop 3 per mode (trades>=100, oos trades>=30, sorted by oos avgR)")
    for iv, mode in COMBOS:
        sub = df[(df.interval == iv) & (df["mode"] == mode) & (df.trades >= MIN_TRADES) & (df.oos_trades >= MIN_OOS)]
        print(f"\n== {iv} {mode} ==")
        if sub.empty:
            print("no combination met the minimum trade counts")
            continue
        print(sub.sort_values("oos_avgR", ascending=False)[cols].head(3).round(2).to_string(index=False))
    pos = df[(df.trades >= MIN_TRADES) & (df.oos_trades >= MIN_OOS) & (df.oos_avgR > 0)]
    print(f"\ncombinations with positive out-of-sample avgR: {len(pos)} of {len(df)}")


if __name__ == "__main__":
    main()
