import type { ClosedCandle } from "./binance-top-usdt";

// Dynamic S/R (pivot based, touch count), candlestick patterns, aur apne pivots se BOS/CHoCH.

export interface SrLevel { price: number; touches: number; strong: boolean; side: "R" | "S"; }
export interface PatternBar { time: number; kind: "bull" | "bear"; name: string; }
export interface StructureBar { time: number; kind: "bull" | "bear"; name: string; }

function isPivotHigh(c: ClosedCandle[], p: number, w: number): boolean {
  if (p - w < 0 || p + w >= c.length) return false;
  for (let k = 1; k <= w; k += 1) {
    if (c[p].high <= c[p - k].high || c[p].high < c[p + k].high) return false;
  }
  return true;
}

function isPivotLow(c: ClosedCandle[], p: number, w: number): boolean {
  if (p - w < 0 || p + w >= c.length) return false;
  for (let k = 1; k <= w; k += 1) {
    if (c[p].low >= c[p - k].low || c[p].low > c[p + k].low) return false;
  }
  return true;
}

// Sabse qareeb n R (upar) aur n S (neeche) levels, touch count ke saath.
export function srLevels(c: ClosedCandle[], pivLen = 5, tolPct = 0.15, n = 3): SrLevel[] {
  if (c.length < pivLen * 2 + 5) return [];
  const last = c[c.length - 1].close;
  const highs: number[] = [];
  const lows: number[] = [];
  for (let p = pivLen; p < c.length - pivLen; p += 1) {
    if (isPivotHigh(c, p, pivLen)) highs.push(c[p].high);
    if (isPivotLow(c, p, pivLen)) lows.push(c[p].low);
  }
  const touchesOf = (lv: number, useHigh: boolean): number => {
    let t = 0;
    for (const k of c) {
      const v = useHigh ? k.high : k.low;
      if (Math.abs(v - lv) / lv * 100 <= tolPct) t += 1;
    }
    return t;
  };
  const res: SrLevel[] = [];
  const rs = highs.filter((v) => v > last).sort((a, b) => a - b).slice(0, n);
  for (const lv of rs) {
    const t = touchesOf(lv, true);
    res.push({ price: lv, touches: t, strong: t >= 3, side: "R" });
  }
  const ss = lows.filter((v) => v < last).sort((a, b) => b - a).slice(0, n);
  for (const lv of ss) {
    const t = touchesOf(lv, false);
    res.push({ price: lv, touches: t, strong: t >= 3, side: "S" });
  }
  return res;
}

// Candlestick patterns: Hammer, Shooting Star, Bull/Bear Engulfing (trend ke saath).
export function candlePatterns(c: ClosedCandle[]): PatternBar[] {
  const out: PatternBar[] = [];
  for (let i = 6; i < c.length; i += 1) {
    const x = c[i];
    const p = c[i - 1];
    const body = Math.abs(x.close - x.open);
    const range = Math.max(x.high - x.low, 1e-12);
    const upW = x.high - Math.max(x.open, x.close);
    const loW = Math.min(x.open, x.close) - x.low;
    const down = p.close < c[i - 6].close;
    const up = p.close > c[i - 6].close;
    if (loW >= 2 * body && upW <= 0.3 * range && down) {
      out.push({ time: x.time, kind: "bull", name: "HAMMER" });
    } else if (upW >= 2 * body && loW <= 0.3 * range && up) {
      out.push({ time: x.time, kind: "bear", name: "SHOOTING STAR" });
    } else if (p.close < p.open && x.close > x.open && x.close >= p.open && x.open <= p.close) {
      out.push({ time: x.time, kind: "bull", name: "BULL ENGULF" });
    } else if (p.close > p.open && x.close < x.open && x.close <= p.open && x.open >= p.close) {
      out.push({ time: x.time, kind: "bear", name: "BEAR ENGULF" });
    }
  }
  return out;
}

// BOS / CHoCH: apne pivots ke upar ya neeche close hone par (confirmed pivots).
export function structureMarks(c: ClosedCandle[], pivLen = 5): StructureBar[] {
  const out: StructureBar[] = [];
  let lastH: number | null = null;
  let lastL: number | null = null;
  let trend = 0;
  for (let i = pivLen * 2 + 1; i < c.length; i += 1) {
    const p = i - pivLen;
    if (isPivotHigh(c, p, pivLen)) lastH = c[p].high;
    if (isPivotLow(c, p, pivLen)) lastL = c[p].low;
    if (lastH !== null && c[i - 1].close <= lastH && c[i].close > lastH) {
      out.push({ time: c[i].time, kind: "bull", name: trend === -1 ? "CHoCH UP" : "BOS UP" });
      trend = 1;
      lastH = null;
    }
    if (lastL !== null && c[i - 1].close >= lastL && c[i].close < lastL) {
      out.push({ time: c[i].time, kind: "bear", name: trend === 1 ? "CHoCH DOWN" : "BOS DOWN" });
      trend = -1;
      lastL = null;
    }
  }
  return out;
}
