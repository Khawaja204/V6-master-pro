import type { ClosedCandle } from "./binance-top-usdt";

// Adaptive Trend Finder (log): TypeScript port.
// Original Pine indicator: (c) Julien Eche, GPL-3.0. Ye port bhi GPL-3.0 ke tahat hai.
// Sirf regression channel aur projected targets. Guarantee nahi.

export interface TrendFit {
  slope: number;
  intercept: number;
  sd: number;
  r: number;
}

export interface TrendTarget {
  h: number;
  price: number;
  side: "UP" | "DN";
}

export interface AdaptiveTrend {
  period: number;
  r: number;
  strength: string;
  dir: "UP" | "DOWN";
  startIdx: number;
  mid: (k: number) => number;
  upper: (k: number) => number;
  lower: (k: number) => number;
  targets: TrendTarget[];
}

function strengthLabel(r: number): string {
  const a = Math.abs(r);
  if (a < 0.2) return "Extremely Weak";
  if (a < 0.3) return "Very Weak";
  if (a < 0.4) return "Weak";
  if (a < 0.5) return "Mostly Weak";
  if (a < 0.6) return "Somewhat Weak";
  if (a < 0.7) return "Moderately Weak";
  if (a < 0.8) return "Moderate";
  if (a < 0.9) return "Moderately Strong";
  if (a < 0.92) return "Mostly Strong";
  if (a < 0.94) return "Strong";
  if (a < 0.96) return "Very Strong";
  if (a < 0.98) return "Exceptionally Strong";
  return "Ultra Strong";
}

// Log prices par OLS regression. x = 0 window ke sab se purane bar par.
function fit(y: number[]): TrendFit {
  const n = y.length;
  const mx = (n - 1) / 2;
  const my = y.reduce((a, b) => a + b, 0) / n;
  let sxx = 0;
  let sxy = 0;
  let syy = 0;
  for (let i = 0; i < n; i += 1) {
    const dx = i - mx;
    const dy = y[i] - my;
    sxx += dx * dx;
    sxy += dx * dy;
    syy += dy * dy;
  }
  const slope = sxx > 0 ? sxy / sxx : 0;
  const intercept = my - slope * mx;
  const r = sxx > 0 && syy > 0 ? sxy / Math.sqrt(sxx * syy) : 0;
  let ssr = 0;
  for (let i = 0; i < n; i += 1) {
    const e = y[i] - (intercept + slope * i);
    ssr += e * e;
  }
  const sd = Math.sqrt(ssr / Math.max(n - 1, 1));
  return { slope, intercept, sd, r };
}

export function adaptiveTrend(c: ClosedCandle[], dev = 2): AdaptiveTrend | null {
  if (c.length < 60) return null;
  const ln = c.map((x) => Math.log(x.close));
  let best: (TrendFit & { period: number }) | null = null;
  for (let p = 20; p <= 200; p += 10) {
    if (c.length < p) continue;
    const f = fit(ln.slice(-p));
    if (!best || Math.abs(f.r) > Math.abs(best.r)) best = { period: p, ...f };
  }
  if (!best) return null;

  const startIdx = c.length - best.period;
  const sd = best.sd;
  const dir: "UP" | "DOWN" = best.slope >= 0 ? "UP" : "DOWN";
  const lnMid = (k: number) => best!.intercept + best!.slope * (k - startIdx);
  const mid = (k: number) => Math.exp(lnMid(k));
  const upper = (k: number) => Math.exp(lnMid(k) + dev * sd);
  const lower = (k: number) => Math.exp(lnMid(k) - dev * sd);

  const last = c.length - 1;
  const targets: TrendTarget[] = [10, 20, 30].map((h) => {
    const k = last + h;
    const price = dir === "UP" ? upper(k) : lower(k);
    return { h, price, side: dir === "UP" ? "UP" : "DN" };
  });

  return {
    period: best.period,
    r: best.r,
    strength: strengthLabel(best.r),
    dir,
    startIdx,
    mid,
    upper,
    lower,
    targets,
  };
}
