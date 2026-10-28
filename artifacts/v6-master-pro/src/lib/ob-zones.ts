export type OhlcCandle = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
};

export type OrderBlockKind = "bullish" | "bearish";

export interface OrderBlock {
  kind: OrderBlockKind;
  index: number;        // index of the order block candle
  confirmIndex: number; // first bar where this block is known (index + impulseBars)
  time: number;
  top: number;
  bottom: number;
  mitigated: boolean;
  mitigatedIndex: number | null;
  swept: boolean;       // OB or previous candle took out prior swing liquidity
  hasFvg: boolean;      // 3-candle imbalance inside the impulse
}

export interface OrderBlockOptions {
  atrPeriod?: number;     // ATR lookback, default 14
  impulseBars?: number;   // bars after the block that show the move, default 3
  impulseAtr?: number;    // required move in ATR units, default 1.5
  sweepLookback?: number; // candles used to define the prior swing, default 10
  requireSweep?: boolean; // default true
  requireFvg?: boolean;   // default true
}

function trueRanges(candles: OhlcCandle[]): number[] {
  return candles.map((c, i) => {
    if (i === 0) return c.high - c.low;
    const prevClose = candles[i - 1].close;
    return Math.max(
      c.high - c.low,
      Math.abs(c.high - prevClose),
      Math.abs(c.low - prevClose),
    );
  });
}

function atrSeries(candles: OhlcCandle[], period: number): (number | null)[] {
  const tr = trueRanges(candles);
  const out: (number | null)[] = new Array(candles.length).fill(null);
  let sum = 0;
  for (let i = 0; i < tr.length; i += 1) {
    sum += tr[i];
    if (i >= period) sum -= tr[i - period];
    if (i >= period - 1) out[i] = sum / period;
  }
  return out;
}

// Candle 1 = candles[k], candle 3 = candles[k + 2], searched inside the impulse.
function hasBullishFvg(candles: OhlcCandle[], i: number, impulseBars: number): boolean {
  for (let k = i; k <= i + impulseBars - 2; k += 1) {
    if (candles[k].high < candles[k + 2].low) return true;
  }
  return false;
}

function hasBearishFvg(candles: OhlcCandle[], i: number, impulseBars: number): boolean {
  for (let k = i; k <= i + impulseBars - 2; k += 1) {
    if (candles[k].low > candles[k + 2].high) return true;
  }
  return false;
}

export function detectOrderBlocks(
  candles: OhlcCandle[],
  options: OrderBlockOptions = {},
): OrderBlock[] {
  const atrPeriod = options.atrPeriod ?? 14;
  const impulseBars = options.impulseBars ?? 3;
  const impulseAtr = options.impulseAtr ?? 1.5;
  const sweepLookback = options.sweepLookback ?? 10;
  const requireSweep = options.requireSweep ?? true;
  const requireFvg = options.requireFvg ?? true;
  const atr = atrSeries(candles, atrPeriod);
  const blocks: OrderBlock[] = [];
  const start = Math.max(atrPeriod - 1, sweepLookback + 2);

  for (let i = start; i + impulseBars < candles.length; i += 1) {
    const a = atr[i];
    if (a === null || a <= 0) continue;

    const ob = candles[i];
    const prev = candles[i - 1];
    const next = candles.slice(i + 1, i + 1 + impulseBars);
    const confirmIndex = i + impulseBars;
    // Prior swing: the candles before the OB and its previous candle.
    const prior = candles.slice(i - 1 - sweepLookback, i - 1);
    const swingLow = Math.min(...prior.map((c) => c.low));
    const swingHigh = Math.max(...prior.map((c) => c.high));

    const bullishCandidate =
      ob.close < ob.open &&
      Math.max(...next.map((c) => c.high)) - ob.high >= impulseAtr * a;
    const bearishCandidate =
      ob.close > ob.open &&
      ob.low - Math.min(...next.map((c) => c.low)) >= impulseAtr * a;

    if (bullishCandidate) {
      const swept = Math.min(ob.low, prev.low) < swingLow;
      const hasFvg = hasBullishFvg(candles, i, impulseBars);
      if ((!requireSweep || swept) && (!requireFvg || hasFvg)) {
        blocks.push({
          kind: "bullish",
          index: i,
          confirmIndex,
          time: ob.time,
          top: ob.high,
          bottom: ob.low,
          mitigated: false,
          mitigatedIndex: null,
          swept,
          hasFvg,
        });
      }
    }

    if (bearishCandidate) {
      const swept = Math.max(ob.high, prev.high) > swingHigh;
      const hasFvg = hasBearishFvg(candles, i, impulseBars);
      if ((!requireSweep || swept) && (!requireFvg || hasFvg)) {
        blocks.push({
          kind: "bearish",
          index: i,
          confirmIndex,
          time: ob.time,
          top: ob.high,
          bottom: ob.low,
          mitigated: false,
          mitigatedIndex: null,
          swept,
          hasFvg,
        });
      }
    }
  }

  for (const block of blocks) {
    for (let j = block.confirmIndex + 1; j < candles.length; j += 1) {
      const c = candles[j];
      const touched = block.kind === "bullish"
        ? c.low <= block.top
        : c.high >= block.bottom;
      if (touched) {
        block.mitigated = true;
        block.mitigatedIndex = j;
        break;
      }
    }
  }

  return blocks;
}

export function freshOrderBlocks(blocks: OrderBlock[]): OrderBlock[] {
  return blocks.filter((block) => !block.mitigated);
}
