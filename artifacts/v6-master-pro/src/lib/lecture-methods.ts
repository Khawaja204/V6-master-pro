import type { ClosedCandle } from "./binance-top-usdt";
import type { HtfData } from "./htf-data";

export type MethodId = "m1" | "m2" | "m3" | "m4" | "m5" | "m6";

export const METHODS: { id: MethodId; label: string }[] = [
  { id: "m1", label: "M1 Price Action" },
  { id: "m2", label: "M2 V1 RSI 55" },
  { id: "m3", label: "M3 ICT Green after Red" },
  { id: "m4", label: "M4 Hidden Bullish RSI" },
  { id: "m5", label: "M5 Support + RS vs BTC" },
  { id: "m6", label: "M6 EMA9 + RSI 50 swing" },
];

function emaSeries(values: number[], period: number): number[] {
  const out = new Array<number>(values.length).fill(NaN);
  if (values.length < period) return out;
  const k = 2 / (period + 1);
  let e = values.slice(0, period).reduce((a, b) => a + b, 0) / period;
  out[period - 1] = e;
  for (let i = period; i < values.length; i += 1) {
    e = values[i] * k + e * (1 - k);
    out[i] = e;
  }
  return out;
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

// V1 proxy: smoothed Heikin Ashi candle on the last bar is green.
function v1Green(c: ClosedCandle[]): boolean {
  const n = c.length;
  if (n < 30) return false;
  const smO = emaSeries(c.map((x) => x.open), 10);
  const smH = emaSeries(c.map((x) => x.high), 10);
  const smL = emaSeries(c.map((x) => x.low), 10);
  const smC = emaSeries(c.map((x) => x.close), 10);
  const haC = new Array<number>(n);
  const haO = new Array<number>(n);
  for (let i = 0; i < n; i += 1) {
    haC[i] = (smO[i] + smH[i] + smL[i] + smC[i]) / 4;
    haO[i] = i === 0 ? (smO[i] + smC[i]) / 2 : (haO[i - 1] + haC[i - 1]) / 2;
  }
  const shaO = emaSeries(haO, 10);
  const shaC = emaSeries(haC, 10);
  return shaC[n - 1] >= shaO[n - 1];
}

// Fallback only, used when 1D exchange data is not available yet.
function dailyCloses(c: ClosedCandle[]): number[] {
  const out: number[] = [];
  for (let i = c.length - 1; i >= 0; i -= 24) out.unshift(c[i].close);
  return out;
}

// Pivot lows: the bar is lower than `w` bars on each side (confirmed by later bars).
function pivotLowIdx(c: ClosedCandle[], w = 3): number[] {
  const out: number[] = [];
  for (let i = w; i < c.length - w; i += 1) {
    let ok = true;
    for (let k = 1; k <= w; k += 1) {
      if (c[i].low >= c[i - k].low || c[i].low > c[i + k].low) {
        ok = false;
        break;
      }
    }
    if (ok) out.push(i);
  }
  return out;
}

export function matchesMethod(
  id: MethodId,
  c15: ClosedCandle[],
  c1h: ClosedCandle[],
  htf?: HtfData,
): boolean {
  if (c15.length < 60 || c1h.length < 60) return false;
  const last15 = c15[c15.length - 1];
  const closes15 = c15.map((c) => c.close);
  const closes1h = c1h.map((c) => c.close);
  const rsi15Last = rsiSeries(closes15).at(-1) ?? null;
  const rsi1h = rsiSeries(closes1h);
  const close1hLast = closes1h[closes1h.length - 1];
  const lastIdx = c1h.length - 1;

  if (id === "m1") {
    const ema50 = emaSeries(closes1h, 50).at(-1) ?? NaN;
    const support = Math.min(...c15.slice(-21, -1).map((c) => c.low));
    return close1hLast > ema50
      && rsi15Last !== null && rsi15Last >= 50
      && last15.close > support;
  }

  if (id === "m2") {
    // 1D trend from exchange daily closes (10-day EMA), 1H above EMA21,
    // 1H RSI crossed 55 in the last 3 bars, V1 proxy green, 15m RSI above 55.
    const dCl = htf && htf.d1.length >= 12 ? htf.d1.map((c) => c.close) : dailyCloses(c1h);
    const dEma = emaSeries(dCl, 10).at(-1) ?? NaN;
    const dailyUp = dCl.length >= 12 && dCl[dCl.length - 1] > dEma;
    const ema21 = emaSeries(closes1h, 21).at(-1) ?? NaN;
    let crossedUp = false;
    for (let i = rsi1h.length - 3; i < rsi1h.length; i += 1) {
      const prev = rsi1h[i - 1];
      const cur = rsi1h[i];
      if (prev !== null && cur !== null && prev <= 55 && cur > 55) crossedUp = true;
    }
    return dailyUp
      && close1hLast > ema21
      && crossedUp
      && v1Green(c1h)
      && rsi15Last !== null && rsi15Last > 55;
  }

  if (id === "m3") {
    // Consolidation or uptrend, current 15m candle green, previous red candle with a real body move >= 1%.
    const range = c15.slice(-21, -1);
    const hi = Math.max(...range.map((c) => c.high));
    const lo = Math.min(...range.map((c) => c.low));
    const mid = (hi + lo) / 2;
    const consolidated = mid > 0 && ((hi - lo) / mid) * 100 <= 3;
    const ema21 = emaSeries(closes15, 21).at(-1) ?? NaN;
    const uptrend = last15.close > ema21;
    const prev = c15[c15.length - 2];
    const prevRedWithMove = prev.close < prev.open && ((prev.open - prev.close) / prev.open) * 100 >= 1;
    return (consolidated || uptrend) && last15.close > last15.open && prevRedWithMove;
  }

  if (id === "m4") {
    // Hidden bullish: higher low in price, lower low in RSI, pivot RSI between 30 and 40,
    // and the live 1H RSI also between 30 and 40 right now.
    const piv = pivotLowIdx(c1h).filter((i) => lastIdx - i <= 80);
    if (piv.length < 2) return false;
    const p2 = piv[piv.length - 1];
    const p1 = piv[piv.length - 2];
    const r1 = rsi1h[p1];
    const r2 = rsi1h[p2];
    const liveRsi = rsi1h[lastIdx];
    return r1 !== null && r2 !== null && liveRsi !== null
      && c1h[p2].low > c1h[p1].low
      && r2 < r1 && r2 >= 30 && r2 <= 40
      && liveRsi >= 30 && liveRsi <= 40
      && lastIdx - p2 <= 6;
  }

  if (id === "m5") {
    // Major support: lowest pivot low in the last 80 bars on 1H. Price 0-2% above it.
    // Relative strength: coin's 24-bar return beats BTC's 24-bar return.
    if (!htf || htf.btc1h.length < 25 || c1h.length < 25) return false;
    const piv = pivotLowIdx(c1h).filter((i) => lastIdx - i <= 80);
    if (!piv.length) return false;
    let sup = Infinity;
    for (const i of piv) if (c1h[i].low < sup) sup = c1h[i].low;
    const nearSupport = close1hLast >= sup && close1hLast <= sup * 1.02;
    const coinRet = close1hLast / c1h[lastIdx - 24].close - 1;
    const btcCl = htf.btc1h.map((c) => c.close);
    const btcRet = btcCl[btcCl.length - 1] / btcCl[btcCl.length - 25] - 1;
    return nearSupport && coinRet > btcRet;
  }

  // M6: price above EMA9 (1H), and RSI14 crossed above 50 from the 40-50 zone in the last 3 bars.
  const ema9 = emaSeries(closes1h, 9).at(-1) ?? NaN;
  let crossed = false;
  for (let i = rsi1h.length - 3; i < rsi1h.length; i += 1) {
    const prev = rsi1h[i - 1];
    const cur = rsi1h[i];
    if (prev !== null && cur !== null && prev >= 40 && prev <= 50 && cur > 50) crossed = true;
  }
  return close1hLast > ema9 && crossed;
}
