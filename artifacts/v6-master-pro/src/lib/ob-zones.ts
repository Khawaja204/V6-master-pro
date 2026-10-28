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
  time: number;         // time of the order block candle
  top: number;
  bottom: number;
  mitigated: boolean;
  mitigatedIndex: number | null;
}

export interface OrderBlockOptions {
  atrPeriod?: number;   // ATR lookback, default 14
  impulseBars?: number; // bars after the block that must show the move, default 3
  impulseAtr?: number;  // required move in ATR units, default 1.5
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

export function detectOrderBlocks(
  candles: OhlcCandle[],
  options: OrderBlockOptions = {},
): OrderBlock[] {
  const atrPeriod = options.atrPeriod ?? 14;
  const impulseBars = options.impulseBars ?? 3;
  const impulseAtr = options.impulseAtr ?? 1.5;
  const atr = atrSeries(candles, atrPeriod);
  const blocks: OrderBlock[] = [];

  for (let i = atrPeriod - 1; i + impulseBars < candles.length; i += 1) {
    const a = atr[i];
    if (a === null || a <= 0) continue;

    const ob = candles[i];
    const next = candles.slice(i + 1, i + 1 + impulseBars);
    const confirmIndex = i + impulseBars;

    if (ob.close < ob.open) {
      const impulseHigh = Math.max(...next.map((c) => c.high));
      if (impulseHigh - ob.high >= impulseAtr * a) {
        blocks.push({
          kind: "bullish",
          index: i,
          confirmIndex,
          time: ob.time,
          top: ob.high,
          bottom: ob.low,
          mitigated: false,
          mitigatedIndex: null,
        });
      }
    }

    if (ob.close > ob.open) {
      const impulseLow = Math.min(...next.map((c) => c.low));
      if (ob.low - impulseLow >= impulseAtr * a) {
        blocks.push({
          kind: "bearish",
          index: i,
          confirmIndex,
          time: ob.time,
          top: ob.high,
          bottom: ob.low,
          mitigated: false,
          mitigatedIndex: null,
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
