import { Candle, ema, rsi, rvol, dailyVwap, splitOutOfSample, BacktestResult } from "./ocs-signals";

export type StrategyMode = "Pump" | "Normal";

export type EntryOpts = {
  mode?: StrategyMode;
  pumpVolX?: number;   // Pine default 2.0
  normVolX?: number;   // Pine default 1.2
  rsiCap?: number;     // Pine default 80
  rsiLen?: number;     // Pine default 14
  rsi15Min?: number;   // Pine default 50
  rsi1hMin?: number;   // Pine default 50
};

// Build higher timeframe candles from base candles (factor 4 on 15m gives 1h).
// For each base bar, returns the index of the last COMPLETED higher-timeframe bar
// (-1 if none), which matches request.security with lookahead off.
function htfMapping(candles: Candle[], factor: number, baseMs: number) {
  const htf: Candle[] = [];
  const closedIdx: number[] = new Array(candles.length).fill(-1);
  let curKey = NaN;
  let grp: Candle[] = [];
  let last = -1;
  for (let i = 0; i < candles.length; i++) {
    const k = Math.floor(candles[i].time / (factor * baseMs));
    if (k !== curKey && grp.length > 0) {
      htf.push(mergeBars(grp));
      last = htf.length - 1;
      grp = [];
    }
    curKey = k;
    grp.push(candles[i]);
    closedIdx[i] = last;
  }
  return { htf, closedIdx };
}

function mergeBars(bars: Candle[]): Candle {
  return {
    time: bars[0].time,
    open: bars[0].open,
    high: Math.max(...bars.map((b) => b.high)),
    low: Math.min(...bars.map((b) => b.low)),
    close: bars[bars.length - 1].close,
    volume: bars.reduce((s, b) => s + b.volume, 0),
  };
}

// Pine-equivalent long entry signals, one boolean per base bar.
// Does NOT include cooldown or position handling; backtestLong handles exits.
export function buildEntrySignals(candles: Candle[], opts: EntryOpts = {}): boolean[] {
  const mode = opts.mode ?? "Pump";
  const pumpVolX = opts.pumpVolX ?? 2.0;
  const normVolX = opts.normVolX ?? 1.2;
  const rsiCap = opts.rsiCap ?? 80;
  const rsiLen = opts.rsiLen ?? 14;
  const rsi15Min = opts.rsi15Min ?? 50;
  const rsi1hMin = opts.rsi1hMin ?? 50;

  const n = candles.length;
  const signals: boolean[] = new Array(n).fill(false);
  if (n < 2) return signals;

  const closes = candles.map((c) => c.close);
  const ema21 = ema(closes, 21);
  const rsiV = rsi(closes, rsiLen);
  const vr = rvol(candles, 20);
  const vwap = dailyVwap(candles);

  const baseMs = candles[1].time - candles[0].time;
  const { htf, closedIdx } = htfMapping(candles, 4, baseMs);
  const hClose = htf.map((c) => c.close);
  const h1ema50 = ema(hClose, 50);
  const h1rsi = rsi(hClose, rsiLen);

  for (let i = 0; i < n; i++) {
    const c = candles[i];
    if (isNaN(ema21[i]) || isNaN(rsiV[i]) || isNaN(vr[i]) || isNaN(vwap[i])) continue;

    const green = c.close > c.open;
    const supportOK = c.close > vwap[i] && c.close > ema21[i];
    const pumpLong = supportOK && vr[i] >= pumpVolX && green && rsiV[i] < rsiCap;

    let normLong = false;
    const j = closedIdx[i];
    if (j >= 0 && !isNaN(h1ema50[j]) && !isNaN(h1rsi[j])) {
      normLong =
        c.close > ema21[i] &&
        rsiV[i] >= rsi15Min &&
        vr[i] >= normVolX &&
        green &&
        htf[j].close > h1ema50[j] &&
        h1rsi[j] >= rsi1hMin;
    }

    signals[i] = mode === "Pump" ? pumpLong : normLong;
  }
  return signals;
}

// One call: build signals, then run the out-of-sample split (60% train, 40% test).
export function runEntryBacktest(candles: Candle[], opts: EntryOpts = {}) {
  const signals = buildEntrySignals(candles, opts);
  const { train, test }: { train: BacktestResult; test: BacktestResult } =
    splitOutOfSample(candles, signals, 0.6);
  return {
    signalCount: signals.filter(Boolean).length,
    train,
    test,
  };
}