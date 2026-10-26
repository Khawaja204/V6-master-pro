// Pure indicator and backtest helpers. No UI, no network, no side effects.

export type Candle = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

// Exponential moving average. Seeded with the SMA of the first `period` values.
export function ema(values: number[], period: number): number[] {
  const out: number[] = new Array(values.length).fill(NaN);
  if (values.length < period || period < 1) return out;
  const k = 2 / (period + 1);
  let sum = 0;
  for (let i = 0; i < period; i++) sum += values[i];
  out[period - 1] = sum / period;
  for (let i = period; i < values.length; i++) {
    out[i] = values[i] * k + out[i - 1] * (1 - k);
  }
  return out;
}

// Simple moving average.
export function sma(values: number[], period: number): number[] {
  const out: number[] = new Array(values.length).fill(NaN);
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= period) sum -= values[i - period];
    if (i >= period - 1) out[i] = sum / period;
  }
  return out;
}

// Wilder RSI, same method as TradingView's ta.rsi.
export function rsi(closes: number[], period = 14): number[] {
  const out: number[] = new Array(closes.length).fill(NaN);
  if (closes.length <= period) return out;
  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= period; i++) {
    const d = closes[i] - closes[i - 1];
    if (d >= 0) gain += d;
    else loss -= d;
  }
  gain /= period;
  loss /= period;
  out[period] = loss === 0 ? 100 : 100 - 100 / (1 + gain / loss);
  for (let i = period + 1; i < closes.length; i++) {
    const d = closes[i] - closes[i - 1];
    const g = d > 0 ? d : 0;
    const l = d < 0 ? -d : 0;
    gain = (gain * (period - 1) + g) / period;
    loss = (loss * (period - 1) + l) / period;
    out[i] = loss === 0 ? 100 : 100 - 100 / (1 + gain / loss);
  }
  return out;
}

// Average True Range (Wilder smoothing), same as ta.atr.
export function atr(candles: Candle[], period = 14): number[] {
  const n = candles.length;
  const tr: number[] = new Array(n).fill(NaN);
  for (let i = 0; i < n; i++) {
    const c = candles[i];
    if (i === 0) tr[i] = c.high - c.low;
    else {
      const pc = candles[i - 1].close;
      tr[i] = Math.max(c.high - c.low, Math.abs(c.high - pc), Math.abs(c.low - pc));
    }
  }
  const out: number[] = new Array(n).fill(NaN);
  if (n < period) return out;
  let sum = 0;
  for (let i = 0; i < period; i++) sum += tr[i];
  out[period - 1] = sum / period;
  for (let i = period; i < n; i++) {
    out[i] = (out[i - 1] * (period - 1) + tr[i]) / period;
  }
  return out;
}

// Relative volume: volume divided by its 20-bar SMA.
export function rvol(candles: Candle[], period = 20): number[] {
  const volAvg = sma(candles.map((c) => c.volume), period);
  return candles.map((c, i) => (volAvg[i] > 0 ? c.volume / volAvg[i] : NaN));
}

// Session VWAP, reset when the UTC day changes (matches the Pine daily VWAP).
export function dailyVwap(candles: Candle[]): number[] {
  const out: number[] = new Array(candles.length).fill(NaN);
  let cumPV = 0;
  let cumV = 0;
  let day = -1;
  for (let i = 0; i < candles.length; i++) {
    const c = candles[i];
    const d = Math.floor(c.time / 86400000);
    if (d !== day) {
      day = d;
      cumPV = 0;
      cumV = 0;
    }
    const hlc3 = (c.high + c.low + c.close) / 3;
    cumPV += hlc3 * c.volume;
    cumV += c.volume;
    out[i] = cumV > 0 ? cumPV / cumV : c.close;
  }
  return out;
}

export type BacktestTrade = {
  entryIndex: number;
  exitIndex: number;
  entry: number;
  exit: number;
  rMultiple: number;
  reason: string;
};

export type BacktestResult = {
  trades: BacktestTrade[];
  wins: number;
  winRate: number;
  avgR: number;
  totalR: number;
};

// Minimal harness: long-only, entry on a supplied boolean signal array,
// hard stop at entry - slMult*ATR, take profit at entry + tpR*risk, time-out
// after maxBars. Fees are subtracted in R units. Used only to test whether
// a signal has any edge; it is not a trading recommendation.
export function backtestLong(
  candles: Candle[],
  signals: boolean[],
  opts: { slMult?: number; tpR?: number; maxBars?: number; feePct?: number } = {}
): BacktestResult {
  const slMult = opts.slMult ?? 1.2;
  const tpR = opts.tpR ?? 2.0;
  const maxBars = opts.maxBars ?? 48;
  const feePct = opts.feePct ?? 0.1;
  const a = atr(candles, 14);
  const trades: BacktestTrade[] = [];
  let i = 0;
  while (i < candles.length - 1) {
    if (!signals[i] || isNaN(a[i])) {
      i++;
      continue;
    }
    const entry = candles[i].close;
    const risk = Math.max(slMult * a[i], 1e-10);
    const stop = entry - risk;
    const target = entry + tpR * risk;
    let exitIdx = Math.min(i + maxBars, candles.length - 1);
    let exitPx = candles[exitIdx].close;
    let reason = "TIME";
    for (let j = i + 1; j <= Math.min(i + maxBars, candles.length - 1); j++) {
      if (candles[j].low <= stop) {
        exitIdx = j;
        exitPx = stop;
        reason = "SL";
        break;
      }
      if (candles[j].high >= target) {
        exitIdx = j;
        exitPx = target;
        reason = "TP";
        break;
      }
    }
    const feeR = (entry * feePct / 100 * 2) / risk;
    const r = (exitPx - entry) / risk - feeR;
    trades.push({ entryIndex: i, exitIndex: exitIdx, entry, exit: exitPx, rMultiple: r, reason });
    i = exitIdx + 1;
  }
  const wins = trades.filter((t) => t.rMultiple > 0.05).length;
  const totalR = trades.reduce((s, t) => s + t.rMultiple, 0);
  return {
    trades,
    wins,
    winRate: trades.length ? wins / trades.length : 0,
    avgR: trades.length ? totalR / trades.length : 0,
    totalR,
  };
}

// Out-of-sample split: run the same backtest on the first and last part of the data.
export function splitOutOfSample(
  candles: Candle[],
  signals: boolean[],
  trainFrac = 0.6
) {
  const cut = Math.floor(candles.length * trainFrac);
  const train = backtestLong(candles.slice(0, cut), signals.slice(0, cut));
  const test = backtestLong(candles.slice(cut), signals.slice(cut));
  return { train, test };
}