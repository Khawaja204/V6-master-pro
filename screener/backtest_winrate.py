import asyncio
import itertools

import pandas as pd

from backtest_entries import prep, entries
from backtest_sweep import load, simulate, summ, SPLIT

MIN_TRADES = 100
MIN_OOS = 30
GRID = {"sl": [1.0, 1.5, 2.0], "tp2": [0.5, 0.75, 1.0, 1.5], "be": [0.5, 1.0], "trail": [1.0]}
KINDS = ["rsi30", "bb", "pb"]
COLS = ["interval", "entry", "sl", "tp2", "be", "trail", "trades", "win", "avgR", "oos_trades", "oos_avgR"]


def signal(d, kind):
    if kind == "pb":
        return entries(d, "pb")
    c = d["close"]
    if kind == "rsi30":
        s = (d["rsi"].shift(1) < 30) & (d["rsi"] >= 30)
    else:
        lower = c.rolling(20).mean() - 2 * c.rolling(20).std()
        s = (c.shift(1) < lower.shift(1)) & d["green"]
    return s.fillna(False).astype(bool).values


def main():
    data = asyncio.run(load())
    frames = {sym: prep(d15m, d1h) for sym, (d15m, d1h) in data.items()}
    rows = []
    for iv in ["15m", "1h"]:
        for kind in KINDS:
            sigs = {sym: signal(d15 if iv == "15m" else d1h, kind) for sym, (d15, d1h) in frames.items()}
            for sl, tp2, be, tr in itertools.product(GRID["sl"], GRID["tp2"], GRID["be"], GRID["trail"]):
                items = []
                for sym, (d15, d1h) in frames.items():
                    d = d15 if iv == "15m" else d1h
                    items += simulate(d, sigs[sym], sl, tp2, be, tr)
                full = summ(items)
                oos = summ([x for x in items if x[0] >= SPLIT])
                rows.append(dict(interval=iv, entry=kind, sl=sl, tp2=tp2, be=be, trail=tr,
                                 trades=full["trades"], win=full["win"], avgR=full["avgR"],
                                 oos_trades=oos["trades"], oos_avgR=oos["avgR"]))
            print(f"done {iv} {kind}", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv("winrate_results.csv", index=False)
    ok = df[(df.trades >= MIN_TRADES) & (df.oos_trades >= MIN_OOS)]
    print(f"\nValid combos (trades>=100, oos>=30): {len(ok)} of {len(df)}")
    print("\nTOP 5 BY WIN RATE:")
    print(ok.sort_values("win", ascending=False).head(5)[COLS].round(2).to_string(index=False))
    print("\nTOP 3 BY OUT-OF-SAMPLE avgR:")
    print(ok.sort_values("oos_avgR", ascending=False).head(3)[COLS].round(2).to_string(index=False))
    print(f"\nPositive oos avgR combos: {int((ok.oos_avgR > 0).sum())} of {len(ok)}")


if __name__ == "__main__":
    main()
