const BINANCE_API = "https://api.binance.com/api/v3";
const REQUEST_TIMEOUT_MS = 15_000;

export const COIN_INTERVALS = ["15m", "1h"] as const;

export type CoinInterval = (typeof COIN_INTERVALS)[number];

export interface UsdtSpotPair {
  symbol: string;
  baseAsset: string;
}

export interface CoinTicker {
  symbol: string;
  lastPrice: number;
  change24h: number;
}

export interface ClosedCoinCandle {
  openTime: number;
  closeTime: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface RecentCoinTrade {
  id: number;
  price: number;
  quantity: number;
  time: number;
}

export interface CoinCandleMetrics {
  close: number;
  ema21: number | null;
  ema50: number | null;
  rsi14: number | null;
  rvol: number | null;
  conditionMet: boolean;
}

interface ExchangeInfoSymbol {
  symbol: string;
  baseAsset: string;
  quoteAsset: string;
  status: string;
  isSpotTradingAllowed?: boolean;
}

interface ExchangeInfoResponse {
  symbols: ExchangeInfoSymbol[];
}

interface TickerResponse {
  symbol: string;
  lastPrice: string;
  priceChangePercent: string;
}

interface TradeResponse {
  id: number;
  price: string;
  qty: string;
  time: number;
}

function numberFrom(value: unknown, label: string): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    throw new Error(`Binance returned an invalid ${label}`);
  }
  return parsed;
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const forwardAbort = () => controller.abort();
  signal?.addEventListener("abort", forwardAbort, { once: true });
  if (signal?.aborted) controller.abort();

  try {
    const response = await fetch(`${BINANCE_API}${path}`, {
      cache: "no-store",
      headers: { accept: "application/json" },
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`Binance request failed (${response.status})`);
    }

    return (await response.json()) as T;
  } finally {
    window.clearTimeout(timeout);
    signal?.removeEventListener("abort", forwardAbort);
  }
}

export async function fetchUsdtSpotPairs(
  signal?: AbortSignal,
): Promise<UsdtSpotPair[]> {
  const response = await getJson<ExchangeInfoResponse>("/exchangeInfo", signal);

  return response.symbols
    .filter(
      (item) =>
        item.quoteAsset === "USDT" &&
        item.status === "TRADING" &&
        item.isSpotTradingAllowed !== false,
    )
    .map(({ symbol, baseAsset }) => ({ symbol, baseAsset }))
    .sort((a, b) => a.baseAsset.localeCompare(b.baseAsset));
}

export function searchUsdtSpotPairs(
  pairs: UsdtSpotPair[],
  query: string,
): UsdtSpotPair[] {
  const normalized = query.trim().toUpperCase().replace(/\s+/g, "");
  if (!normalized) return [];

  return pairs
    .filter(
      ({ symbol, baseAsset }) =>
        baseAsset.startsWith(normalized) || symbol.startsWith(normalized),
    )
    .slice(0, 10);
}

export async function fetchCoinTicker(
  symbol: string,
  signal?: AbortSignal,
): Promise<CoinTicker> {
  const response = await getJson<TickerResponse>(
    `/ticker/24hr?symbol=${encodeURIComponent(symbol)}`,
    signal,
  );

  return {
    symbol: response.symbol,
    lastPrice: numberFrom(response.lastPrice, "last price"),
    change24h: numberFrom(response.priceChangePercent, "24-hour change"),
  };
}

function parseClosedCandleRows(rows: unknown[][]): ClosedCoinCandle[] {
  const now = Date.now();
  const candles: ClosedCoinCandle[] = [];

  for (const row of rows) {
    if (row.length < 7) continue;
    const openTime = numberFrom(row[0], "candle open time");
    const closeTime = numberFrom(row[6], "candle close time");
    if (closeTime > now) continue;

    candles.push({
      openTime,
      closeTime,
      open: numberFrom(row[1], "candle open"),
      high: numberFrom(row[2], "candle high"),
      low: numberFrom(row[3], "candle low"),
      close: numberFrom(row[4], "candle close"),
      volume: numberFrom(row[5], "candle volume"),
    });
  }

  return candles.sort((a, b) => a.openTime - b.openTime);
}

export async function fetchClosedCoinCandles(
  symbol: string,
  interval: CoinInterval,
  signal?: AbortSignal,
): Promise<ClosedCoinCandle[]> {
  const rows = await getJson<unknown[][]>(
    `/klines?symbol=${encodeURIComponent(symbol)}&interval=${interval}&limit=100`,
    signal,
  );
  return parseClosedCandleRows(rows);
}

export async function fetchRecentCoinTrades(
  symbol: string,
  signal?: AbortSignal,
): Promise<RecentCoinTrade[]> {
  const trades = await getJson<TradeResponse[]>(
    `/trades?symbol=${encodeURIComponent(symbol)}&limit=20`,
    signal,
  );

  return trades
    .map((trade) => ({
      id: trade.id,
      price: numberFrom(trade.price, "trade price"),
      quantity: numberFrom(trade.qty, "trade quantity"),
      time: numberFrom(trade.time, "trade time"),
    }))
    .sort((a, b) => b.time - a.time);
}

function calculateEma(values: number[], period: number): number | null {
  if (values.length < period) return null;

  let ema =
    values.slice(0, period).reduce((sum, value) => sum + value, 0) / period;
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

export function calculateCoinCandleMetrics(
  candles: ClosedCoinCandle[],
): CoinCandleMetrics | null {
  const latest = candles.at(-1);
  if (!latest) return null;

  const closes = candles.map((candle) => candle.close);
  const ema21 = calculateEma(closes, 21);
  const ema50 = calculateEma(closes, 50);
  const rsi14 = calculateRsi(closes, 14);
  const previousVolumes = candles.slice(-21, -1).map((candle) => candle.volume);
  const averagePreviousVolume =
    previousVolumes.length === 20
      ? previousVolumes.reduce((sum, volume) => sum + volume, 0) / 20
      : null;
  const rvol =
    averagePreviousVolume !== null && averagePreviousVolume > 0
      ? latest.volume / averagePreviousVolume
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
