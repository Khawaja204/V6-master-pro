import type { ClosedCandle } from "./binance-top-usdt";

export interface VolSignal {
  time: number;
  kind: "buy" | "warn";
  price: number;
}

const VOL_LEN = 20;
const RV_BUY = 1.5;
const RV_EXPLOSIVE = 2.0;
const BUY_TOL_PCT = 0.3;
const SELL_TOL_PCT = 0.3;
const SL_ATR = 1.2;
const TP1_R = 2.0;
const TP2_R = 3.0;

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

// Simple moving average; NaN when any value in the window is NaN.
function smaSeries(values: number[], period: number): number[] {
  const out = new Array<number>(values.length).fill(NaN);
  for (let i = period - 1; i < values.length; i += 1) {
    let sum = 0;
    let bad = false;
    for (let k = 0; k < period; k += 1) {
      const v = values[i - k];
      if (!Number.isFinite(v)) { bad = true; break; }
      sum += v;
    }
    if (!bad) out[i] = sum / period;
  }
  return out;
}

// Wilder ATR (RMA), same as Pine ta.atr.
function atrSeries(candles: ClosedCandle[], period: number): number[] {
  const out = new Array<number>(candles.length).fill(NaN);
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

// Daily VWAP: resets at each UTC day.
function vwapSeries(candles: ClosedCandle[]): number[] {
  const out = new Array<number>(candles.length).fill(NaN);
  let day = -1;
  let cumPV = 0;
  let cumV = 0;
  for (let i = 0; i < candles.length; i += 1) {
    const c = candles[i];
    const d = Math.floor(c.time / 86400);
    if (d !== day) {
      day = d;
      cumPV = 0;
      cumV = 0;
    }
    cumPV += ((c.high + c.low + c.close) / 3) * c.volume;
    cumV += c.volume;
    out[i] = cumV > 0 ? cumPV / cumV : c.close;
  }
  return out;
}

export function volSignals(candles: ClosedCandle[], mode: "Pump" | "Normal" = "Pump"): VolSignal[] {
  const n = candles.length;
  const closes = candles.map((c) => c.close);
  const vols = candles.map((c) => c.volume);
  const ema21 = emaSeries(closes, 21);
  const atr = atrSeries(candles, 14);
  const atrAvg = smaSeries(atr, 20);
  const vwap = vwapSeries(candles);
  const volAvg = smaSeries(vols, VOL_LEN);
  const rv = volAvg.map((avg, i) => (Number.isFinite(avg) && avg > 0 ? vols[i] / avg : NaN));

  const out: VolSignal[] = [];
  let inTrade = false;
  let stop = NaN;
  let tp1 = NaN;
  let tp2 = NaN;

  for (let i = 25; i < n; i += 1) {
    const c = candles[i];
    const a = atr[i];
    if (!Number.isFinite(a) || !Number.isFinite(ema21[i]) || !Number.isFinite(rv[i])
      || !Number.isFinite(rv[i - 1]) || !Number.isFinite(rv[i - 2])) continue;

    const buyAt = mode === "Pump" ? Math.max(vwap[i], ema21[i]) : ema21[i];
    const buyLo = buyAt * (1 - BUY_TOL_PCT / 100);
    const buyHi = buyAt * (1 + BUY_TOL_PCT / 100);
    const touch = c.low <= buyHi && c.high >= buyLo;
    const rangeOK = Number.isFinite(atrAvg[i]) && a > atrAvg[i];
    const earlyBuy = touch && rv[i] >= RV_BUY && c.close >= c.open && rangeOK;

    if (earlyBuy && !inTrade) {
      inTrade = true;
      const risk = Math.max(SL_ATR * a, 1e-10);
      stop = c.close - risk;
      tp1 = c.close + TP1_R * risk;
      tp2 = c.close + TP2_R * risk;
      out.push({ time: c.time, kind: "buy", price: c.close });
    } else if (inTrade && (c.low <= stop || c.high >= tp2)) {
      inTrade = false;
    }

    const nearTP1 = inTrade && c.high >= tp1 * (1 - SELL_TOL_PCT / 100);
    const rvolFade = rv[i] < rv[i - 1] && rv[i - 1] < rv[i - 2];
    const sellFade = nearTP1 && rvolFade;
    const sellSpike = nearTP1 && rv[i] >= RV_EXPLOSIVE && c.close < c.open;
    if (sellFade || sellSpike) out.push({ time: c.time, kind: "warn", price: c.close });
  }
  return out;
}
