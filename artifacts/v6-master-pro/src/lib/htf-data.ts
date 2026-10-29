import { useEffect, useState } from "react";
import type { ClosedCandle } from "./binance-top-usdt";

export interface HtfData {
  d1: ClosedCandle[];
  w1: ClosedCandle[];
  btc1h: ClosedCandle[];
}

const REFRESH_MS = 10 * 60 * 1000;
const BASE = "https://api.binance.com/api/v3/klines";

function num(v: unknown): number | null {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

// Closed candles only: the still-forming day or week is dropped.
async function fetchKlines(symbol: string, interval: string, limit: number): Promise<ClosedCandle[]> {
  const r = await fetch(`${BASE}?symbol=${symbol}&interval=${interval}&limit=${limit}`, {
    cache: "no-store",
    signal: AbortSignal.timeout(15000),
  });
  if (!r.ok) throw new Error(`klines ${symbol} ${interval} ${r.status}`);
  const rows = (await r.json()) as unknown[][];
  const now = Date.now();
  const out: ClosedCandle[] = [];
  for (const row of rows) {
    const t = num(row[0]);
    const closeT = num(row[6]);
    const o = num(row[1]);
    const h = num(row[2]);
    const l = num(row[3]);
    const c = num(row[4]);
    const v = num(row[5]);
    const q = num(row[7]);
    if (t === null || closeT === null || closeT > now || o === null || h === null
      || l === null || c === null || v === null || q === null) continue;
    out.push({ time: Math.floor(t / 1000), open: o, high: h, low: l, close: c, volume: v, quoteVolume: q });
  }
  return out;
}

async function loadHtf(symbol: string, btc1h: ClosedCandle[]): Promise<HtfData> {
  const [d1, w1] = await Promise.all([
    fetchKlines(symbol, "1d", 60).catch(() => [] as ClosedCandle[]),
    fetchKlines(symbol, "1w", 30).catch(() => [] as ClosedCandle[]),
  ]);
  return { d1, w1, btc1h };
}

// Daily (1D) and weekly (1W) exchange candles per symbol, plus BTC 1H for relative strength.
// Refreshed every 10 minutes.
export function useHtfMap(symbols: string[]): Record<string, HtfData> {
  const [map, setMap] = useState<Record<string, HtfData>>({});
  const key = symbols.join(",");
  useEffect(() => {
    if (!symbols.length) return;
    let stopped = false;
    const run = async () => {
      const btc = await fetchKlines("BTCUSDT", "1h", 60).catch(() => [] as ClosedCandle[]);
      const entries = await Promise.all(symbols.map(async (s) => [s, await loadHtf(s, btc)] as const));
      if (!stopped) setMap(Object.fromEntries(entries));
    };
    run();
    const timer = window.setInterval(run, REFRESH_MS);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [key]);
  return map;
}
