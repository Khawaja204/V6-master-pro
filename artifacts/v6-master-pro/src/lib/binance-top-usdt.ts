import { useEffect, useState } from "react";

const BINANCE_REST = "https://api.binance.com/api/v3";
const BINANCE_STREAM = "wss://stream.binance.com:9443/stream";
const TICKER_REFRESH_MS = 10 * 60 * 1000;
const INITIAL_KLINE_LIMIT = 100;
const MAX_CANDLES = 100;
const INTERVALS = ["15m", "1h"] as const;
const EXCLUDED_BASE_ASSETS = new Set([
  "USDC",
  "FDUSD",
  "TUSD",
  "BUSD",
  "USDP",
  "DAI",
  "USDE",
  "USD1",
  "RLUSD",
  "USDS",
]);
const LEVERAGED_SUFFIXES = ["UP", "DOWN", "BULL", "BEAR"];

export type KlineInterval = (typeof INTERVALS)[number];

export interface ClosedCandle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  quoteVolume: number;
}

export interface CandleMetrics {
  close: number;
  ema21: number | null;
  ema50: number | null;
  rsi14: number | null;
  rvol: number | null;
  conditionMet: boolean;
}

export interface TopUsdtPair {
  symbol: string;
  baseAsset: string;
  lastPrice: number | null;
  change24h: number;
  quoteVolume24h: number;
  candles: Record<KlineInterval, ClosedCandle[]>;
  metrics: Record<KlineInterval, CandleMetrics | null>;
}

export type StreamStatus =
  | "loading"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "disconnected"
  | "error";

interface BinanceTicker {
  symbol: string;
  lastPrice: string;
  priceChangePercent: string;
  quoteVolume: string;
}

interface BinanceKline {
  t: number;
  T: number;
  s: string;
  i: string;
  o: string;
  h: string;
  l: string;
  c: string;
  v: string;
  q: string;
  x: boolean;
}

interface PairCache {
  symbol: string;
  baseAsset: string;
  change24h: number;
  quoteVolume24h: number;
  candles: Record<KlineInterval, ClosedCandle[]>;
}

function finiteNumber(value: unknown): number | null {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function eligibleTicker(ticker: BinanceTicker): boolean {
  if (!ticker.symbol.endsWith("USDT")) return false;

  const baseAsset = ticker.symbol.slice(0, -4);
  if (!baseAsset || EXCLUDED_BASE_ASSETS.has(baseAsset)) return false;
  if (LEVERAGED_SUFFIXES.some((suffix) => baseAsset.endsWith(suffix))) return false;

  return (
    finiteNumber(ticker.lastPrice) !== null &&
    finiteNumber(ticker.priceChangePercent) !== null &&
    finiteNumber(ticker.quoteVolume) !== null
  );
}

function emptyCandles(): Record<KlineInterval, ClosedCandle[]> {
  return { "15m": [], "1h": [] };
}

function mergeCandles(
  existing: ClosedCandle[],
  incoming: ClosedCandle[],
): ClosedCandle[] {
  const byTime = new Map(existing.map((candle) => [candle.time, candle]));
  for (const candle of incoming) byTime.set(candle.time, candle);
  return [...byTime.values()]
    .sort((a, b) => a.time - b.time)
    .slice(-MAX_CANDLES);
}

function parseRestCandles(rows: unknown[][]): ClosedCandle[] {
  const now = Date.now();
  return rows
    .map((row) => {
      const openTime = finiteNumber(row[0]);
      const closeTime = finiteNumber(row[6]);
      const open = finiteNumber(row[1]);
      const high = finiteNumber(row[2]);
      const low = finiteNumber(row[3]);
      const close = finiteNumber(row[4]);
      const volume = finiteNumber(row[5]);
      const quoteVolume = finiteNumber(row[7]);

      if (
        openTime === null ||
        closeTime === null ||
        closeTime > now ||
        open === null ||
        high === null ||
        low === null ||
        close === null ||
        volume === null ||
        quoteVolume === null
      ) {
        return null;
      }

      return {
        time: Math.floor(openTime / 1000),
        open,
        high,
        low,
        close,
        volume,
        quoteVolume,
      };
    })
    .filter((candle): candle is ClosedCandle => candle !== null);
}

function calculateEma(values: number[], period: number): number | null {
  if (values.length < period) return null;

  let ema = values.slice(0, period).reduce((sum, value) => sum + value, 0) / period;
  const multiplier = 2 / (period + 1);
  for (let index = period; index < values.length; index += 1) {
    ema = (values[index] - ema) * multiplier + ema;
  }
  return ema;
}

function calculateRsi(values: number[], period: number): number | null {
  if (values.length < period + 1) return null;

  let averageGain = 0;
  let averageLoss = 0;
  for (let index = 1; index <= period; index += 1) {
    const change = values[index] - values[index - 1];
    averageGain += Math.max(change, 0);
    averageLoss += Math.max(-change, 0);
  }
  averageGain /= period;
  averageLoss /= period;

  for (let index = period + 1; index < values.length; index += 1) {
    const change = values[index] - values[index - 1];
    averageGain = (averageGain * (period - 1) + Math.max(change, 0)) / period;
    averageLoss = (averageLoss * (period - 1) + Math.max(-change, 0)) / period;
  }

  if (averageGain === 0 && averageLoss === 0) return 50;
  if (averageLoss === 0) return 100;
  return 100 - 100 / (1 + averageGain / averageLoss);
}

export function calculateCandleMetrics(
  candles: ClosedCandle[],
): CandleMetrics | null {
  const latest = candles.at(-1);
  if (!latest) return null;

  const closes = candles.map((candle) => candle.close);
  const ema21 = calculateEma(closes, 21);
  const ema50 = calculateEma(closes, 50);
  const rsi14 = calculateRsi(closes, 14);
  const previousVolumes = candles.slice(-21, -1).map((candle) => candle.quoteVolume);
  const previousAverage =
    previousVolumes.length === 20
      ? previousVolumes.reduce((sum, volume) => sum + volume, 0) / 20
      : null;
  const rvol =
    previousAverage !== null && previousAverage > 0
      ? latest.quoteVolume / previousAverage
      : null;

  const conditionMet =
    ema21 !== null &&
    ema50 !== null &&
    rsi14 !== null &&
    rvol !== null &&
    latest.close > ema21 &&
    latest.close > ema50 &&
    rsi14 >= 50 &&
    rvol >= 1.5;

  return { close: latest.close, ema21, ema50, rsi14, rvol, conditionMet };
}

function makeSnapshot(
  symbols: string[],
  store: Map<string, PairCache>,
): TopUsdtPair[] {
  return symbols.flatMap((symbol) => {
    const pair = store.get(symbol);
    if (!pair) return [];
    const candles = pair.candles;
    const metrics = {
      "15m": calculateCandleMetrics(candles["15m"]),
      "1h": calculateCandleMetrics(candles["1h"]),
    };
    return [{
      ...pair,
      lastPrice:
        candles["15m"].at(-1)?.close ??
        candles["1h"].at(-1)?.close ??
        null,
      candles,
      metrics,
    }];
  });
}

export function useTopUsdtPairs() {
  const [pairs, setPairs] = useState<TopUsdtPair[]>([]);
  const [status, setStatus] = useState<StreamStatus>("loading");
  const [isLoading, setIsLoading] = useState(true);
  const [lastTickerRefresh, setLastTickerRefresh] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let stopped = false;
    let refreshInProgress = false;
    let reconnectAttempts = 0;
    let socketGeneration = 0;
    let reconnectTimer: number | undefined;
    let refreshTimer: number | undefined;
    let socket: WebSocket | null = null;
    let selectedSymbols: string[] = [];
    const pairStore = new Map<string, PairCache>();

    const publish = () => {
      if (!stopped) setPairs(makeSnapshot(selectedSymbols, pairStore));
    };

    const scheduleReconnect = () => {
      if (stopped || reconnectTimer !== undefined || !selectedSymbols.length) return;
      setStatus("reconnecting");
      const delay = Math.min(30_000, 1_000 * 2 ** Math.min(reconnectAttempts, 5));
      reconnectAttempts += 1;
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = undefined;
        connectSocket();
      }, delay);
    };

    const handleMessage = (message: MessageEvent<string>) => {
      try {
        const payload = JSON.parse(message.data) as {
          data?: { s?: string; k?: BinanceKline };
          s?: string;
          k?: BinanceKline;
        };
        const data = payload.data ?? payload;
        const kline = data.k;
        if (!kline || !kline.x || kline.T > Date.now()) return;

        const symbol = String(kline.s ?? data.s ?? "").toUpperCase();
        const interval = kline.i as KlineInterval;
        if (!selectedSymbols.includes(symbol) || !INTERVALS.includes(interval)) return;

        const candle: ClosedCandle = {
          time: Math.floor(kline.t / 1000),
          open: Number(kline.o),
          high: Number(kline.h),
          low: Number(kline.l),
          close: Number(kline.c),
          volume: Number(kline.v),
          quoteVolume: Number(kline.q),
        };
        if (
          !Number.isFinite(candle.close) ||
          !Number.isFinite(candle.quoteVolume) ||
          candle.time <= 0
        ) {
          return;
        }

        const previous = pairStore.get(symbol);
        if (!previous) return;
        pairStore.set(symbol, {
          ...previous,
          candles: {
            ...previous.candles,
            [interval]: mergeCandles(previous.candles[interval], [candle]),
          },
        });
        publish();
      } catch {
        // Ignore malformed frames; the socket remains available for later updates.
      }
    };

    function connectSocket() {
      if (stopped || !selectedSymbols.length) return;
      if (reconnectTimer !== undefined) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = undefined;
      }

      const generation = ++socketGeneration;
      if (socket) {
        socket.onclose = null;
        socket.close();
        socket = null;
      }

      const streams = selectedSymbols.flatMap((symbol) =>
        INTERVALS.map((interval) => `${symbol.toLowerCase()}@kline_${interval}`),
      );
      setStatus("connecting");

      try {
        const nextSocket = new WebSocket(
          `${BINANCE_STREAM}?streams=${streams.join("/")}`,
        );
        socket = nextSocket;
        nextSocket.onopen = () => {
          if (stopped || generation !== socketGeneration) return;
          reconnectAttempts = 0;
          setStatus("connected");
        };
        nextSocket.onmessage = handleMessage;
        nextSocket.onerror = () => nextSocket.close();
        nextSocket.onclose = () => {
          if (generation !== socketGeneration || stopped) return;
          if (socket === nextSocket) socket = null;
          scheduleReconnect();
        };
      } catch {
        socket = null;
        scheduleReconnect();
      }
    }

    async function fetchInitialCandles(
      symbol: string,
      interval: KlineInterval,
    ): Promise<ClosedCandle[]> {
      const url = `${BINANCE_REST}/klines?symbol=${encodeURIComponent(symbol)}&interval=${interval}&limit=${INITIAL_KLINE_LIMIT}`;
      const response = await fetch(url, {
        cache: "no-store",
        headers: { accept: "application/json" },
        signal: AbortSignal.timeout(15_000),
      });
      if (!response.ok) {
        throw new Error(`Binance kline request failed (${response.status}) for ${symbol} ${interval}`);
      }
      return parseRestCandles((await response.json()) as unknown[][]);
    }

    async function refreshTickerUniverse() {
      if (stopped || refreshInProgress) return;
      refreshInProgress = true;
      setError(null);

      try {
        const response = await fetch(`${BINANCE_REST}/ticker/24hr`, {
          cache: "no-store",
          headers: { accept: "application/json" },
          signal: AbortSignal.timeout(15_000),
        });
        if (!response.ok) {
          throw new Error(`Binance 24h ticker request failed (${response.status})`);
        }

        const tickers = (await response.json()) as BinanceTicker[];
        const selected = tickers
          .filter(eligibleTicker)
          .sort((a, b) => Number(b.quoteVolume) - Number(a.quoteVolume))
          .slice(0, 20);
        if (!selected.length) throw new Error("Binance returned no eligible USDT pairs");

        const nextSymbols = selected.map((ticker) => ticker.symbol);
        const previousSelection = new Set(selectedSymbols);
        const membershipChanged =
          nextSymbols.length !== selectedSymbols.length ||
          nextSymbols.some((symbol) => !previousSelection.has(symbol));
        selectedSymbols = nextSymbols;

        for (const ticker of selected) {
          const baseAsset = ticker.symbol.slice(0, -4);
          const previous = pairStore.get(ticker.symbol);
          pairStore.set(ticker.symbol, {
            symbol: ticker.symbol,
            baseAsset,
            change24h: Number(ticker.priceChangePercent),
            quoteVolume24h: Number(ticker.quoteVolume),
            candles: previous?.candles ?? emptyCandles(),
          });
        }

        setLastTickerRefresh(new Date().toISOString());
        publish();

        if (membershipChanged || !socket) connectSocket();

        const initialLoads = selected.flatMap((ticker) => {
          const cached = pairStore.get(ticker.symbol);
          if (!cached) return [];
          return INTERVALS
            .filter((interval) =>
              !previousSelection.has(ticker.symbol) ||
              cached.candles[interval].length === 0,
            )
            .map(async (interval) => {
              try {
                const candles = await fetchInitialCandles(ticker.symbol, interval);
                if (stopped) return;
                const current = pairStore.get(ticker.symbol);
                if (!current) return;
                pairStore.set(ticker.symbol, {
                  ...current,
                  candles: {
                    ...current.candles,
                    [interval]: mergeCandles(current.candles[interval], candles),
                  },
                });
              } catch (loadError) {
                const detail =
                  loadError instanceof Error ? loadError.message : "Unknown candle error";
                setError((previous) => previous ? `${previous}; ${detail}` : detail);
              }
            });
        });

        await Promise.all(initialLoads);
        publish();
        if (!stopped) setIsLoading(false);
      } catch (refreshError) {
        const detail =
          refreshError instanceof Error ? refreshError.message : "Unknown Binance ticker error";
        if (!stopped) {
          setError(detail);
          setIsLoading(false);
          if (!socket) setStatus("error");
        }
      } finally {
        refreshInProgress = false;
      }
    }

    void refreshTickerUniverse();
    refreshTimer = window.setInterval(
      () => void refreshTickerUniverse(),
      TICKER_REFRESH_MS,
    );

    return () => {
      stopped = true;
      if (refreshTimer !== undefined) window.clearInterval(refreshTimer);
      if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer);
      socketGeneration += 1;
      if (socket) {
        socket.onclose = null;
        socket.close();
      }
      socket = null;
    };
  }, []);

  return { pairs, status, isLoading, lastTickerRefresh, error };
}
