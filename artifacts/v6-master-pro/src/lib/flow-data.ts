import { useEffect, useState } from "react";

// Descriptive only: these are order-flow readings, not trade signals.

export interface FlowSnapshot {
  symbol: string;
  trades: number;          // spot trades used (max 1000)
  windowMin: number | null; // minutes covered by those trades
  buyPct: number | null;   // taker buy volume share
  fundingPct: number | null; // latest funding rate, % (futures only)
  oiUsdt: number | null;   // open interest in USDT (futures only)
  fetchedAt: number;
}

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
      // m = true means the buyer was the maker, so the aggressor was a seller.
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

export function useFlow(symbol: string | null): FlowSnapshot | null {
  const [snap, setSnap] = useState<FlowSnapshot | null>(null);
  useEffect(() => {
    setSnap(null);
    if (!symbol) return;
    let stopped = false;
    const run = () => {
      fetchFlow(symbol)
        .then((next) => { if (!stopped) setSnap(next); })
        .catch(() => { /* keep last reading */ });
    };
    run();
    const timer = window.setInterval(run, 15000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [symbol]);
  return snap;
}

function compact(v: number): string {
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(2)}B`;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
  return v.toFixed(0);
}

export function formatFlow(s: FlowSnapshot | null): string {
  if (!s) return "loading";
  const buy = s.buyPct === null ? "n/a" : `buy ${s.buyPct.toFixed(0)}% / sell ${(100 - s.buyPct).toFixed(0)}% (${s.trades} trades${s.windowMin !== null ? `, ${s.windowMin.toFixed(0)}m` : ""})`;
  const fund = s.fundingPct === null ? "funding n/a" : `funding ${s.fundingPct >= 0 ? "+" : ""}${s.fundingPct.toFixed(4)}%`;
  const oi = s.oiUsdt === null ? "OI n/a" : `OI $${compact(s.oiUsdt)}`;
  return `${buy} · ${fund} · ${oi}`;
}
