import asyncio
import itertools

import numpy as np
import pandas as pd

from backtest import signals
from backtest_sweep import load, simulate, summ, SPLIT

MIN_TRADES = 100
MIN_OOS = 30
SWING = 5
GRID = {"sl": [1.2, 1.5, 2.0, 2.5], "tp2": [2.0, 3.0, 4.0], "be": [0.6, 1.0], "trail": [1.0, 1.5]}
COMBOS = [("15m", k) for k in ["bot", "pb", "sb", "htf", "pb_htf"]] + \
         [("1h", k) for k in ["bot", "pb", "sb"]]


def pivot_level(d):
    h = d["high"]
    is_ph = h == h.rolling(2 * SWING + 1, center=True).max()
    return h.where(is_ph).shift(SWING).ffill()


def prep(d15m, d1h):
    h1_cols = ["h1c", "h1ema21", "h1ema50", "h1rsi", "h1_close", "piv"]
    base = d15m.drop(columns=h1_cols, errors="ignore").copy()
    h1 = d1h[["close_time", "close", "ema21", "ema50", "rsi"]].rename(columns={
        "close_time": "h1_close", "close": "h1c", "ema21": "h1ema21",
        "ema50": "h1ema50", "rsi": "h1rsi"})
    d = pd.merge_asof(base.sort_values("open_time"), h1.sort_values("h1_close"),
                      left_on="open_time", right_on="h1_close", direction="backward")
    d = d.reset_index(drop=True)
    d["piv"] = pivot_level(d)
    d1 = d1h.copy().reset_index(drop=True)
    d1["piv"] = pivot_level(d1)
    return d, d1


def entries(d, kind):
    c, e21, e50 = d["close"], d["ema21"], d["ema50"]
    green = d["green"]
    if kind == "pb":
        trend = (e21 > e50) & (c > e50)
        touch = (d["low"] <= e21 * 1.002) & (c > e21)
        s = trend & touch & green
    elif kind == "sb":
        lvl = d["piv"]
        s = (c > lvl.shift(1)) & (c.shift(1) <= lvl.shift(1)) & green & (e21 > e50)
    elif kind == "htf":
        htf = (d["h1c"] > d["h1ema21"]) & (d["h1ema21"] > d["h1ema50"])
        s = htf & (c > e21) & green & (d["rvol"] >= 1.2)
    elif kind == "pb_htf":
        htf = (d["h1c"] > d["h1ema21"]) & (d["h1ema21"] > d["h1ema50"])
        trend = (e21 > e50) & (c > e50)
        touch = (d["low"] <= e21 * 1.002) & (c > e21)
        s = htf & trend & touch & green
    return s.fillna(False).astype(bool).values


def sig_for(d, kind):
    if kind == "bot":
        return signals(d, "bot")
    return entries(d, kind)


def main():
    data = asyncio.run(load())
    frames = {sym: prep(d15m, d1h) for sym, (d15m, d1h) in data.items()}
    print(f"symbols: {len(frames)}", flush=True)
    rows = []
    for iv, kind in COMBOS:
        sigs = {}
        for sym, (d15, d1h) in frames.items():
            d = d15 if iv == "15m" else d1h
            sigs[sym] = sig_for(d, kind)
        for sl, tp2, be, tr in itertools.product(GRID["sl"], GRID["tp2"], GRID["be"], GRID["trail"]):
            per = {}
            for sym, (d15, d1h) in frames.items():
                d = d15 if iv == "15m" else d1h
                per[sym] = simulate(d, sigs[sym], sl, tp2, be, tr)
            items = [x for v in per.values() for x in v]
            full = summ(items)
            ins = summ([x for x in items if x[0] < SPLIT])
            oos = summ([x for x in items if x[0] >= SPLIT])
            sym_pos = sum(1 for v in per.values() if v and np.mean([x[1] for x in v]) > 0)
            rows.append(dict(interval=iv, entry=kind, sl=sl, tp2=tp2, be=be, trail=tr,
                             trades=full["trades"], win=full["win"], avgR=full["avgR"],
                             totR=full["totR"], maxDD=full["maxDD"], is_avgR=ins["avgR"],
                             oos_trades=oos["trades"], oos_avgR=oos["avgR"], sym_pos=sym_pos))
        print(f"done {iv} {kind}", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv("entry_results.csv", index=False)
    cols = ["sl", "tp2", "be", "trail", "trades", "win", "avgR", "totR", "maxDD",
            "is_avgR", "oos_trades", "oos_avgR", "sym_pos"]
    print(f"\nBest per entry (trades>=100, oos>=30, sorted by oos_avgR, sym_pos out of {len(frames)})")
    for iv, kind in COMBOS:
        sub = df[(df["interval"] == iv) & (df["entry"] == kind) &
                 (df["trades"] >= MIN_TRADES) & (df["oos_trades"] >= MIN_OOS)]
        pos = int((sub["oos_avgR"] > 0).sum())
        print(f"\n== {iv} {kind} == positive oos combos: {pos}/{len(sub)}")
        if sub.empty:
            print("not enough trades")
            continue
        print(sub.sort_values("oos_avgR", ascending=False)[cols].head(2).round(2).to_string(index=False))
    print("\nTotal positive oos combos:", int(((df["oos_avgR"] > 0) & (df["trades"] >= MIN_TRADES)).sum()))


if __name__ == "__main__":
    main()
