from dataclasses import dataclass

import pandas as pd
import pandas_ta as ta

from config import EMA_FAST, EMA_SLOW, RSI_LEN, RSI_BULL, VOL_LEN, RVOL_MIN


@dataclass(frozen=True)
class Snapshot:
    symbol: str
    interval: str
    bar_time_ms: int
    close: float
    ema_fast: float
    ema_slow: float
    rsi: float
    rvol: float

    def is_normal_buy(self):
        return (
            self.close > self.ema_fast
            and self.close > self.ema_slow
            and self.rsi >= RSI_BULL
            and self.rvol >= RVOL_MIN
        )


def compute_snapshot(symbol, interval, df):
    """Indicators on the last CLOSED bar only (df must already exclude the live candle)."""
    if len(df) < max(EMA_SLOW, RSI_LEN, VOL_LEN) + 5:
        return None

    close = df["close"]
    ema_fast = ta.ema(close, length=EMA_FAST)
    ema_slow = ta.ema(close, length=EMA_SLOW)
    rsi = ta.rsi(close, length=RSI_LEN)
    vol_ma = df["volume"].rolling(VOL_LEN).mean()
    if ema_fast is None or ema_slow is None or rsi is None:
        return None

    i = len(df) - 1
    values = [ema_fast.iloc[i], ema_slow.iloc[i], rsi.iloc[i], vol_ma.iloc[i]]
    if any(pd.isna(v) for v in values):
        return None

    vol_avg = float(vol_ma.iloc[i])
    rvol = float(df["volume"].iloc[i]) / vol_avg if vol_avg > 0 else 0.0

    return Snapshot(
        symbol=symbol,
        interval=interval,
        bar_time_ms=int(df["open_time"].iloc[i]),
        close=float(close.iloc[i]),
        ema_fast=float(ema_fast.iloc[i]),
        ema_slow=float(ema_slow.iloc[i]),
        rsi=float(rsi.iloc[i]),
        rvol=rvol,
    )
