import type { ClosedCandle } from "./binance-top-usdt";

export interface UtBotSignal {
  time: number;
  kind: "buy" | "sell";
  stop: number;
}

// ATR with Wilder (RMA) smoothing, same as Pine ta.atr.
function atrRma(candles: ClosedCandle[], period: number): (number | null)[] {
  const out: (number | null)[] = new Array(candles.length).fill(null);
  if (candles.length < period) return out;
  const tr = candles.map((c, i) => (i === 0
    ? c.high - c.low
    : Math.max(c.high - c.low, Math.abs(c.high - candles[i - 1].close), Math.abs(c.low - candles[i - 1].close))));
  let rma = tr.slice(0, period).reduce((a, b) => a + b, 0) / period;
  out[period - 1] = rma;
  for (let i = period; i < candles.length; i += 1) {
    rma = (rma * (period - 1) + tr[i]) / period;
    out[i] = rma;
  }
  return out;
}

// UT Bot: ATR trailing stop. Buy when price crosses above the stop, sell when it crosses below.
export function utBotSignals(
  candles: ClosedCandle[],
  keyValue = 1,
  atrPeriod = 10,
): { signals: UtBotSignal[]; stops: (number | null)[] } {
  const atr = atrRma(candles, atrPeriod);
  const stops: (number | null)[] = new Array(candles.length).fill(null);
  const signals: UtBotSignal[] = [];

  for (let i = 1; i < candles.length; i += 1) {
    const a = atr[i];
    if (a === null) continue;
    const src = candles[i].close;
    const srcPrev = candles[i - 1].close;
    const prevStop = stops[i - 1] ?? 0;
    const nLoss = keyValue * a;

    let stop: number;
    if (src > prevStop && srcPrev > prevStop) stop = Math.max(prevStop, src - nLoss);
    else if (src < prevStop && srcPrev < prevStop) stop = Math.min(prevStop, src + nLoss);
    else if (src > prevStop) stop = src - nLoss;
    else stop = src + nLoss;
    stops[i] = stop;

    const above = src > stop && srcPrev <= prevStop;
    const below = stop > src && prevStop <= srcPrev;
    if (above && src > stop) signals.push({ time: candles[i].time, kind: "buy", stop });
    if (below && src < stop) signals.push({ time: candles[i].time, kind: "sell", stop });
  }
  return { signals, stops };
}
