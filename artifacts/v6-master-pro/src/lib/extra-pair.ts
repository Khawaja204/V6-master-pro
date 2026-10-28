import { useEffect, useState } from "react";
import {
  calculateCandleMetrics,
  type ClosedCandle,
  type KlineInterval,
  type TopUsdtPair,
} from "./binance-top-usdt";

const BINANCE_REST = "https://api.binance.com/api/v3";
const REFRESH_MS = 45_000;
const KLINE_LIMIT = 100;

function num(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function parseKlines(rows: unknown[][]): ClosedCandle[] {
  const now = Date.now();
  const candles: ClosedCandle[] = [];
  for (const row of rows) {
    const openTime = num(row[0]);
    const closeTime = num(row[6]);
    const open = num(row[1]);
    const high = num(row[2]);
    const low = num(row[3]);
    const close = num(row[4]);
    const volume = num(row[5]);
    const quoteVolume = num(row[7]);
    if (
      openTime === null || closeTime === null || closeTime > now ||
      open === null || high === null || low === null || close === null ||
      volume === null || quoteVolume === null
    ) continue;
    candles.push({ time: Math.floor(openTime / 1000), open, high, low, close, volume, quoteVolume });
  }
  return candles;
}

export function normalizeSymbol(raw: string): string {
  const upper = raw.trim().toUpperCase();
  return upper.endsWith("USDT") ? upper : `${upper}USDT`;
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, {
    cache: "no-store",
    headers: { accept: "application/json" },
    signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) throw new Error(`Binance request failed (${response.status})`);
  return (await response.json()) as T;
}

async function loadPair(symbol: string): Promise<TopUsdtPair> {
  if (!/^[A-Z0-9]{2,20}USDT$/.test(symbol)) throw new Error("Invalid symbol");
  const [ticker, candles15m, candles1h] = await Promise.all([
    fetchJson<{ lastPrice: string; priceChangePercent: string; quoteVolume: string }>(
      `${BINANCE_REST}/ticker/24hr?symbol=${symbol}`,
    ),
    fetchJson<unknown[][]>(
      `${BINANCE_REST}/klines?symbol=${symbol}&interval=15m&limit=${KLINE_LIMIT}`,
    ).then(parseKlines),
    fetchJson<unknown[][]>(
      `${BINANCE_REST}/klines?symbol=${symbol}&interval=1h&limit=${KLINE_LIMIT}`,
    ).then(parseKlines),
  ]);
  const candles: Record<KlineInterval, ClosedCandle[]> = { "15m": candles15m, "1h": candles1h };
  const metrics = {
    "15m": calculateCandleMetrics(candles15m),
    "1h": calculateCandleMetrics(candles1h),
  };
  return {
    symbol,
    baseAsset: symbol.slice(0, -4),
    lastPrice: candles15m.at(-1)?.close ?? candles1h.at(-1)?.close ?? num(ticker.lastPrice),
    change24h: num(ticker.priceChangePercent) ?? 0,
    quoteVolume24h: num(ticker.quoteVolume) ?? 0,
    candles,
    metrics,
  };
}

export function useExtraPair(symbol: string | null): TopUsdtPair | null {
  const [pair, setPair] = useState<TopUsdtPair | null>(null);
  useEffect(() => {
    setPair(null);
    if (!symbol) return;
    let stopped = false;
    const run = () => {
      loadPair(symbol)
        .then((next) => { if (!stopped) setPair(next); })
        .catch(() => { /* chart keeps its waiting state */ });
    };
    run();
    const timer = window.setInterval(run, REFRESH_MS);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [symbol]);
  return pair;
}
