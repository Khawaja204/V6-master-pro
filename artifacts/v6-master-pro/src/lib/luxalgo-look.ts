import type { ClosedCandle } from "./binance-top-usdt";

// LuxAlgo-style structure overlay (apna implementation).
// Attribution: visual style ka idea LuxAlgo "Smart Money Concepts" (c) LuxAlgo se hai,
// license CC BY-NC-SA 4.0. Sirf non-commercial istemal.

export interface LxSeg {
  t1: number;
  t2: number;
  price: number;
  label: string;
  color: string;
}

export interface LxZones {
  top: number;
  eq: number;
  bottom: number;
}

function isPh(c: ClosedCandle[], p: number, w: number): boolean {
  if (p - w < 0 || p + w >= c.length) return false;
  for (let k = 1; k <= w; k += 1) {
    if (c[p].high <= c[p - k].high || c[p].high < c[p + k].high) return false;
  }
  return true;
}

function isPl(c: ClosedCandle[], p: number, w: number): boolean {
  if (p - w < 0 || p + w >= c.length) return false;
  for (let k = 1; k <= w; k += 1) {
    if (c[p].low >= c[p - k].low || c[p].low > c[p + k].low) return false;
  }
  return true;
}

// Swing ya internal structure: BOS / CHoCH segments (aakhri `keep` events) aur premium/discount zones.
export function lxOverlay(c: ClosedCandle[], swingLen = 5, keep = 3): { segs: LxSeg[]; zones: LxZones | null } {
  const segs: LxSeg[] = [];
  if (c.length < swingLen * 2 + 5) return { segs, zones: null };
  let lastH: { p: number; t: number; used: boolean } | null = null;
  let lastL: { p: number; t: number; used: boolean } | null = null;
  let trend = 0;
  for (let i = swingLen * 2; i < c.length; i += 1) {
    const pv = i - swingLen;
    if (isPh(c, pv, swingLen)) lastH = { p: c[pv].high, t: c[pv].time, used: false };
    if (isPl(c, pv, swingLen)) lastL = { p: c[pv].low, t: c[pv].time, used: false };
    if (lastH && !lastH.used && c[i].close > lastH.p && c[i - 1].close <= lastH.p) {
      segs.push({ t1: lastH.t, t2: c[i].time, price: lastH.p, label: trend === -1 ? "CHoCH" : "BOS", color: "#089981" });
      lastH.used = true;
      trend = 1;
    }
    if (lastL && !lastL.used && c[i].close < lastL.p && c[i - 1].close >= lastL.p) {
      segs.push({ t1: lastL.t, t2: c[i].time, price: lastL.p, label: trend === 1 ? "CHoCH" : "BOS", color: "#F23645" });
      lastL.used = true;
      trend = -1;
    }
  }
  const zones = lastH && lastL ? { top: lastH.p, bottom: lastL.p, eq: (lastH.p + lastL.p) / 2 } : null;
  return { segs: segs.slice(-keep), zones };
}
