import { useEffect, useRef, useState } from "react";

// Descriptive only: order-flow readings and a log of what price did after them.

export interface FlowSnapshot {
  symbol: string;
  trades: number;
  windowMin: number | null;
  buyPct: number | null;
  fundingPct: number | null;
  oiUsdt: number | null;
  fetchedAt: number;
}

export interface FlowReading {
  t: number;
  price: number;
  buyPct: number;
}

export interface FlowSummary {
  tracked: number;
  buyHeavy: { n: number; avgPct: number | null };
  sellHeavy: { n: number; avgPct: number | null };
}

const HORIZON_MS = 15 * 60 * 1000;
const LOG_EVERY_MS = 60 * 1000;
const KEEP = 720;

interface AggTrade { q: string; m: boolean; T: number }

async function getJson<T>(url: string): Promise<T | null> {
  try {
    const r = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(10000) });
    if (!r.ok) return null;
    return (await r.json()) as T;
  } catch {
    return null;
  }
}

export async function fetchFlow(symbol: string): Promise<FlowSnapshot> {
  const trades = await getJson<AggTrade[]>(
    `https://api.binance.com/api/v3/aggTrades?symbol=${symbol}&limit=1000`,
  );
  let buy = 0;
  let sell = 0;
  let n = 0;
  if (trades) {
    for (const t of trades) {
      const q = Number(t.q);
      if (!Number.isFinite(q)) continue;
      if (t.m) sell += q;
      else buy += q;
      n += 1;
    }
  }
  const first = trades?.[0]?.T;
  const last = trades?.[trades.length - 1]?.T;

  const prem = await getJson<{ lastFundingRate: string; markPrice: string }>(
    `https://fapi.binance.com/fapi/v1/premiumIndex?symbol=${symbol}`,
  );
  const oi = await getJson<{ openInterest: string }>(
    `https://fapi.binance.com/fapi/v1/openInterest?symbol=${symbol}`,
  );
  const mark = prem ? Number(prem.markPrice) : NaN;
  const funding = prem ? Number(prem.lastFundingRate) : NaN;

  return {
    symbol,
    trades: n,
    windowMin: first && last ? (last - first) / 60000 : null,
    buyPct: buy + sell > 0 ? (buy / (buy + sell)) * 100 : null,
    fundingPct: Number.isFinite(funding) ? funding * 100 : null,
    oiUsdt: oi && Number.isFinite(mark) ? Number(oi.openInterest) * mark : null,
    fetchedAt: Date.now(),
  };
}

function storageKey(symbol: string): string {
  return `flow_hist_${symbol}`;
}

function loadHistory(symbol: string): FlowReading[] {
  try {
    const raw = window.localStorage.getItem(storageKey(symbol));
    return raw ? (JSON.parse(raw) as FlowReading[]) : [];
  } catch {
    return [];
  }
}

function saveHistory(symbol: string, h: FlowReading[]): void {
  try {
    window.localStorage.setItem(storageKey(symbol), JSON.stringify(h));
  } catch {
    // storage full or blocked: the log is simply not kept
  }
}

// For each reading, take the first later reading at least 15 minutes after it.
function summarize(h: FlowReading[]): FlowSummary {
  const buyMoves: number[] = [];
  const sellMoves: number[] = [];
  let tracked = 0;
  for (let i = 0; i < h.length; i += 1) {
    const r = h[i];
    const target = r.t + HORIZON_MS;
    let later: FlowReading | undefined;
    for (let j = i + 1; j < h.length; j += 1) {
      if (h[j].t >= target) { later = h[j]; break; }
    }
    if (!later) continue;
    tracked += 1;
    const move = ((later.price - r.price) / r.price) * 100;
    if (r.buyPct >= 60) buyMoves.push(move);
    else if (r.buyPct <= 40) sellMoves.push(move);
  }
  const avg = (a: number[]) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : null);
  return {
    tracked,
    buyHeavy: { n: buyMoves.length, avgPct: avg(buyMoves) },
    sellHeavy: { n: sellMoves.length, avgPct: avg(sellMoves) },
  };
}

export function useFlow(symbol: string | null, price: number | null) {
  const [snap, setSnap] = useState<FlowSnapshot | null>(null);
  const [summary, setSummary] = useState<FlowSummary | null>(null);
  const priceRef = useRef<number | null>(price);
  priceRef.current = price;

  useEffect(() => {
    setSnap(null);
    setSummary(null);
    if (!symbol) return;
    let stopped = false;
    const run = () => {
      fetchFlow(symbol)
        .then((next) => {
          if (stopped) return;
          setSnap(next);
          const hist = loadHistory(symbol);
          const last = hist[hist.length - 1];
          const p = priceRef.current;
          if (p !== null && next.buyPct !== null && (!last || next.fetchedAt - last.t >= LOG_EVERY_MS)) {
            hist.push({ t: next.fetchedAt, price: p, buyPct: next.buyPct });
            if (hist.length > KEEP) hist.splice(0, hist.length - KEEP);
            saveHistory(symbol, hist);
          }
          setSummary(summarize(hist));
        })
        .catch(() => { /* keep last reading */ });
    };
    run();
    const timer = window.setInterval(run, 15000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [symbol]);

  return { snap, summary };
}

function compact(v: number): string {
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(2)}B`;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
  return v.toFixed(0);
}

export function formatFlow(s: FlowSnapshot | null): string {
  if (!s) return "loading";
  if (s.buyPct === null && s.fundingPct === null && s.oiUsdt === null) {
    return "unavailable (no data from Binance for this pair)";
  }
  const buy = s.buyPct === null
    ? "buy/sell n/a"
    : `buy ${s.buyPct.toFixed(0)}% / sell ${(100 - s.buyPct).toFixed(0)}% (${s.trades} trades${s.windowMin !== null ? `, ${s.windowMin.toFixed(0)}m` : ""})`;
  const fund = s.fundingPct === null ? "funding n/a" : `funding ${s.fundingPct >= 0 ? "+" : ""}${s.fundingPct.toFixed(4)}%`;
  const oi = s.oiUsdt === null ? "OI n/a" : `OI $${compact(s.oiUsdt)}`;
  return `${buy} · ${fund} · ${oi}`;
}

function pct(v: number | null): string {
  return v === null ? "–" : `${v >= 0 ? "+" : ""}${v.toFixed(3)}%`;
}

export function formatFlowTrack(s: FlowSummary | null): string {
  if (!s) return "Flow log: building (1 reading per minute)";
  if (s.tracked === 0) return "Flow log: no reading is 15 minutes old yet";
  return `Flow log, price 15m later: buy-heavy (≥60%) ${pct(s.buyHeavy.avgPct)} n=${s.buyHeavy.n} · sell-heavy (≤40%) ${pct(s.sellHeavy.avgPct)} n=${s.sellHeavy.n}`;
}
