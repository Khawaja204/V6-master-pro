import type { ClosedCandle } from "./binance-top-usdt";

export interface PowerSignal {
  time: number;
  kind: "buy" | "sell";
  price: number;
}

// Power Indicator (Trading_Bites): compares each close with the close `length` bars earlier.
// State +1 when all last `length` comparisons are "lower" (buy), -1 when all are "higher" (sell).
// Signals fire on the bar the state crosses 0.
export function powerSignals(candles: ClosedCandle[], length = 4): PowerSignal[] {
  const dsi: number[] = new Array(candles.length).fill(0);
  for (let i = 2 * length; i < candles.length; i += 1) {
    let up = 0;
    let down = 0;
    for (let k = 0; k < length; k += 1) {
      const a = candles[i - k].close;
      const b = candles[i - k - length].close;
      if (a > b) up += 1;
      if (a < b) down += 1;
    }
    dsi[i] = down === length ? 1 : up === length ? -1 : 0;
  }

  const signals: PowerSignal[] = [];
  for (let i = 2 * length + 1; i < candles.length; i += 1) {
    if (dsi[i] > 0 && dsi[i - 1] <= 0) {
      signals.push({ time: candles[i].time, kind: "buy", price: candles[i].close });
    }
    if (dsi[i] < 0 && dsi[i - 1] >= 0) {
      signals.push({ time: candles[i].time, kind: "sell", price: candles[i].close });
    }
  }
  return signals;
}
