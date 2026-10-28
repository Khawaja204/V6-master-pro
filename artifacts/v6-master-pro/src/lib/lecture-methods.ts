import type { ClosedCandle } from "./binance-top-usdt";

export type MethodId = "m1" | "m2" | "m3";

export const METHODS: { id: MethodId; label: string }[] = [
  { id: "m1", label: "M1 Price Action" },
  { id: "m2", label: "M2 V1 RSI 55" },
  { id: "m3", label: "M3 ICT Consolidation" },
];

function emaLast(closes: number[], period: number): number | null {
  if (closes.length < period) return null;
  const k = 2 / (period + 1);
  let e = closes.slice(0, period).reduce((a, b) => a + b, 0) / period;
  for (let i = period; i < closes.length; i += 1) e = closes[i] * k + e * (1 - k);
  return e;
}

function rsiSeries(closes: number[], period = 14): (number | null)[] {
  const out: (number | null)[] = new Array(closes.length).fill(null);
  if (closes.length <= period) return out;
  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= period; i += 1) {
    const ch = closes[i] - closes[i - 1];
    gain += Math.max(ch, 0);
    loss += Math.max(-ch, 0);
  }
  gain /= period;
  loss /= period;
  out[period] = loss === 0 ? 100 : 100 - 100 / (1 + gain / loss);
  for (let i = period + 1; i < closes.length; i += 1) {
    const ch = closes[i] - closes[i - 1];
    gain = (gain * (period - 1) + Math.max(ch, 0)) / period;
    loss = (loss * (period - 1) + Math.max(-ch, 0)) / period;
    out[i] = loss === 0 ? 100 : 100 - 100 / (1 + gain / loss);
  }
  return out;
}

export function matchesMethod(id: MethodId, c15: ClosedCandle[], c1h: ClosedCandle[]): boolean {
  if (c15.length < 60 || c1h.length < 60) return false;
  const last15 = c15[c15.length - 1];
  const closes15 = c15.map((c) => c.close);
  const closes1h = c1h.map((c) => c.close);
  const rsi15Last = rsiSeries(closes15).at(-1) ?? null;
  const rsi1h = rsiSeries(closes1h);
  const close1hLast = closes1h[closes1h.length - 1];

  if (id === "m1") {
    const ema50 = emaLast(closes1h, 50);
    const support = Math.min(...c15.slice(-21, -1).map((c) => c.low));
    return ema50 !== null && close1hLast > ema50
      && rsi15Last !== null && rsi15Last >= 50
      && last15.close > support;
  }

  if (id === "m2") {
    const ema21 = emaLast(closes1h, 21);
    let crossedUp = false;
    for (let i = rsi1h.length - 3; i < rsi1h.length; i += 1) {
      const prev = rsi1h[i - 1];
      const cur = rsi1h[i];
      if (prev !== null && cur !== null && prev <= 55 && cur > 55) crossedUp = true;
    }
    return crossedUp && ema21 !== null && close1hLast > ema21
      && rsi15Last !== null && rsi15Last > 55;
  }

  // M3: consolidation over the 20 candles before the latest one, then a red candle.
  const range = c15.slice(-21, -1);
  const hi = Math.max(...range.map((c) => c.high));
  const lo = Math.min(...range.map((c) => c.low));
  const mid = (hi + lo) / 2;
  const consolidated = mid > 0 && ((hi - lo) / mid) * 100 <= 3;
  return consolidated && last15.close < last15.open;
}
