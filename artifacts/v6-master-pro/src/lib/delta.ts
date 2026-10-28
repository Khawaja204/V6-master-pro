import type { ClosedCandle } from "./binance-top-usdt";

export interface CandleDelta {
  time: number;
  buy: number;       // taker buy volume (base asset)
  sell: number;      // volume - buy
  delta: number;     // buy - sell
  deltaPct: number | null; // delta / total volume, -100..100
}

// Returns one entry per input candle (aligned by index).
// Entries are null when the candle has no taker-buy data.
export function candleDelta(candles: ClosedCandle[]): (CandleDelta | null)[] {
  return candles.map((c) => {
    const buy = c.takerBuyVolume;
    if (buy === undefined || !Number.isFinite(buy)) return null;
    const sell = Math.max(0, c.volume - buy);
    const delta = buy - sell;
    const total = buy + sell;
    return {
      time: c.time,
      buy,
      sell,
      delta,
      deltaPct: total > 0 ? (delta / total) * 100 : null,
    };
  });
}

// Running total of delta; null entries count as 0.
export function cumulativeDelta(deltas: (CandleDelta | null)[]): number[] {
  let running = 0;
  return deltas.map((d) => {
    running += d ? d.delta : 0;
    return running;
  });
}
