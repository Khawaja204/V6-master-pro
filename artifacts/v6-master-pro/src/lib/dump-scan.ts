import type { ClosedCandle } from "./binance-top-usdt";

// Dump screening rule (15m closed candles). Sirf screening, short trade ka signal nahi.
// Pump rule ka ulta: 24-candle high se 10% neeche, EMA21 aur EMA50 se neeche, RSI14 <= 50,
// aur current candle red ho jis par RVOL >= 1.5 ho.

function emaLastOf(vals: number[], period: number): number {
  const k = 2 / (period + 1);
  let e = vals[0];
  for (let i = 1; i < vals.length; i += 1) e = vals[i] * k + e * (1 - k);
  return e;
}

function rsiLastOf(c: ClosedCandle[], period = 14): number {
  if (c.length <= period) return NaN;
  let g = 0;
  let l = 0;
  for (let i = 1; i <= period; i += 1) {
    const ch = c[i].close - c[i - 1].close;
    g += Math.max(ch, 0);
    l += Math.max(-ch, 0);
  }
  g /= period;
  l /= period;
  for (let i = period + 1; i < c.length; i += 1) {
    const ch = c[i].close - c[i - 1].close;
    g = (g * (period - 1) + Math.max(ch, 0)) / period;
    l = (l * (period - 1) + Math.max(-ch, 0)) / period;
  }
  return l === 0 ? 100 : 100 - 100 / (1 + g / l);
}

export function dumpMatch(c: ClosedCandle[]): boolean {
  if (c.length < 60) return false;
  const last = c[c.length - 1];
  const hi24 = Math.max(...c.slice(-24).map((x) => x.high));
  const drop = last.close <= hi24 * 0.9;
  const closes = c.map((x) => x.close);
  const ema21 = emaLastOf(closes, 21);
  const ema50 = emaLastOf(closes, 50);
  const belowEma = last.close < ema21 && last.close < ema50;
  const rsi = rsiLastOf(c, 14);
  const rsiOk = Number.isFinite(rsi) && rsi <= 50;
  const avgV = c.slice(-21, -1).reduce((a, x) => a + x.volume, 0) / 20;
  const rvol = avgV > 0 ? last.volume / avgV : 0;
  const redVol = last.close < last.open && rvol >= 1.5;
  return drop && belowEma && rsiOk && redVol;
}

// Diagnostic: har shart alag dikhane ke liye (dumpMatch ka hi logic)
export interface DumpParts {
  ok: boolean;
  drop: boolean;
  belowEma: boolean;
  rsiOk: boolean;
  redVol: boolean;
}

export function dumpParts(c: ClosedCandle[]): DumpParts {
  if (c.length < 60) return { ok: false, drop: false, belowEma: false, rsiOk: false, redVol: false };
  const last = c[c.length - 1];
  const hi24 = Math.max(...c.slice(-24).map((x) => x.high));
  const drop = last.close <= hi24 * 0.9;
  const closes = c.map((x) => x.close);
  const ema21 = emaLastOf(closes, 21);
  const ema50 = emaLastOf(closes, 50);
  const belowEma = last.close < ema21 && last.close < ema50;
  const rsi = rsiLastOf(c, 14);
  const rsiOk = Number.isFinite(rsi) && rsi <= 50;
  const avgV = c.slice(-21, -1).reduce((a, x) => a + x.volume, 0) / 20;
  const rvol = avgV > 0 ? last.volume / avgV : 0;
  const redVol = last.close < last.open && rvol >= 1.5;
  return { ok: drop && belowEma && rsiOk && redVol, drop, belowEma, rsiOk, redVol };
}
