import type { Coin, VsaCheck } from "@workspace/api-zod";

const COINGECKO_MARKETS_URL =
  "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=250&sparkline=false&price_change_percentage=24h";
const BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/24hr";
const BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines";
const CACHE_TTL_MS = 45_000;

type CoinGeckoMarket = {
  id: string;
  symbol: string;
  name: string;
  current_price: number | null;
  market_cap: number | null;
  total_volume: number | null;
  price_change_percentage_24h: number | null;
  circulating_supply: number | null;
  total_supply: number | null;
  max_supply: number | null;
  market_cap_rank: number | null;
};

type BinanceTicker = {
  symbol: string;
  lastPrice: string;
  priceChangePercent: string;
  quoteVolume: string;
};

type LiveSnapshot = {
  coins: Coin[];
  vsaChecks: VsaCheck[];
  marketBreadth: number;
  sessionPnl: number;
  updatedAt: string;
};

export type CandleInterval = "15m" | "1h" | "4h" | "1d";

let cache: { expiresAt: number; snapshot: LiveSnapshot } | null = null;

const followerEstimates: Record<string, number> = {
  bitcoin: 12_400_000,
  ethereum: 8_100_000,
  solana: 2_900_000,
  chainlink: 1_800_000,
  arbitrum: 780_000,
  avalanche: 1_300_000,
  near: 650_000,
  optimism: 590_000,
};

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, {
    headers: { accept: "application/json", "user-agent": "V6-MASTER-PRO/1.0" },
    signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) {
    throw new Error(`Live market provider returned HTTP ${response.status} for ${url}`);
  }
  return (await response.json()) as T;
}

function finite(value: number | null | undefined, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  if (!sorted.length) return 0;
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

async function getVolumeChanges(coins: Coin[]): Promise<Map<string, number>> {
  const stableSymbols = new Set(["USDT", "USDC", "USDE", "DAI", "FDUSD"]);
  const candidates = [...coins]
    .filter((coin) => !stableSymbols.has(coin.symbol))
    .sort((a, b) => b.volume24h - a.volume24h)
    .slice(0, 8);
  const results = await Promise.allSettled(
    candidates.map(async (coin) => {
      const rows = await getJson<unknown[][]>(
        `${BINANCE_KLINES_URL}?symbol=${encodeURIComponent(coin.symbol)}USDT&interval=1h&limit=48`,
      );
      const previousWindow = rows.slice(0, 24).reduce((total, row) => total + finite(Number(row[7])), 0);
      const currentWindow = rows.slice(24).reduce((total, row) => total + finite(Number(row[7])), 0);
      const change = previousWindow > 0 ? ((currentWindow / previousWindow) - 1) * 100 : 0;
      return [coin.id, Number(change.toFixed(1))] as const;
    }),
  );
  return new Map(
    results
      .filter((result): result is PromiseFulfilledResult<readonly [string, number]> => result.status === "fulfilled")
      .map((result) => result.value),
  );
}

function buildVsaChecks(coins: Coin[], volumeChanges: Map<string, number>): VsaCheck[] {
  return [...coins]
    .filter((coin) => volumeChanges.has(coin.id))
    .sort((a, b) => b.volume24h - a.volume24h)
    .slice(0, 8)
    .map((coin, index) => {
      const volumeChange = volumeChanges.get(coin.id) ?? 0;
      const priceUp = coin.change24h >= 0;
      const volumeUp = volumeChange >= 0;
      const manipulation =
        (volumeUp && !priceUp && volumeChange >= 35) ||
        (!volumeUp && priceUp && volumeChange <= -35);
      const status = manipulation ? "manipulation" : "ok";
      const label = `${volumeUp ? "Volume Increase" : "Volume Decrease"} + ${priceUp ? "Price Increase" : "Price Decrease"}`;
      const detail = manipulation
        ? priceUp
          ? "ممکنہ distribution — Sell setup اور liquidity sweep چیک کریں۔"
          : "ممکنہ manipulation — demand zone میں Buy setup دیکھیں۔"
        : priceUp
          ? "مقدار اور قیمت کی سمت ایک جیسی ہے — رجحان کی confirmation دیکھیں۔"
          : "مقدار اور قیمت کمزور ہیں — فی الحال انتظار کریں۔";
      return {
        id: `vsa-live-${index + 1}`,
        coinId: coin.id,
        label,
        detail,
        status,
        volumeChange,
        priceChange: Number(coin.change24h.toFixed(2)),
      } satisfies VsaCheck;
    });
}

async function fetchMarketPages(): Promise<CoinGeckoMarket[]> {
  const [first, second] = await Promise.all([
    getJson<CoinGeckoMarket[]>(`${COINGECKO_MARKETS_URL}&page=1`),
    getJson<CoinGeckoMarket[]>(`${COINGECKO_MARKETS_URL}&page=2`),
  ]);
  return [...first, ...second].slice(0, 500);
}

export async function getLiveMarketSnapshot(): Promise<LiveSnapshot> {
  if (cache && cache.expiresAt > Date.now()) return cache.snapshot;

  const [markets, tickers] = await Promise.all([
    fetchMarketPages(),
    getJson<BinanceTicker[]>(BINANCE_TICKER_URL),
  ]);
  const binanceBySymbol = new Map(
    tickers
      .filter((ticker) => ticker.symbol.endsWith("USDT"))
      .map((ticker) => [ticker.symbol.slice(0, -4).toLowerCase(), ticker]),
  );

  const rawCoins = markets
    .map((market) => {
      const symbol = market.symbol.toUpperCase();
      const ticker = binanceBySymbol.get(market.symbol.toLowerCase());
      const price = ticker ? Number(ticker.lastPrice) : finite(market.current_price);
      const change24h = ticker
        ? Number(ticker.priceChangePercent)
        : finite(market.price_change_percentage_24h);
      const volume24h = ticker ? Number(ticker.quoteVolume) : finite(market.total_volume);
      const circulatingSupply = finite(market.circulating_supply);
      const maxSupply = finite(market.max_supply ?? market.total_supply);
      return {
        id: market.id,
        symbol,
        name: market.name,
        price,
        change24h,
        volume24h,
        followers: followerEstimates[market.id] ?? 0,
        circulatingSupply,
        maxSupply,
        marketCap: finite(market.market_cap),
        vsa: change24h >= 0 ? "ok_up" : "ok_down",
      } satisfies Coin;
    })
    .filter((coin) => coin.price > 0 && coin.marketCap > 0);

  const volumeChanges = await getVolumeChanges(rawCoins);
  const coins = rawCoins.map((coin) => {
    const volumeChange = volumeChanges.get(coin.id) ?? 0;
    const manipulation =
      (coin.change24h < 0 && volumeChange >= 35) ||
      (coin.change24h >= 0 && volumeChange <= -35);
    return {
      ...coin,
      vsa: manipulation
        ? coin.change24h >= 0
          ? "manipulation_sell"
          : "manipulation_buy"
        : coin.change24h >= 0
          ? "ok_up"
          : "ok_down",
    } satisfies Coin;
  });

  if (!coins.length) throw new Error("Live providers returned no usable market assets");
  const positiveCount = coins.filter((coin) => coin.change24h >= 0).length;
  const marketBreadth = Number(((positiveCount / coins.length) * 100).toFixed(1));
  const sessionPnl = Number(
    (coins.slice(0, 10).reduce((total, coin) => total + coin.change24h, 0) / Math.min(10, coins.length)).toFixed(2),
  );
  const snapshot = {
    updatedAt: new Date().toISOString(),
    coins,
    vsaChecks: buildVsaChecks(coins, volumeChanges),
    marketBreadth,
    sessionPnl,
  };
  cache = { expiresAt: Date.now() + CACHE_TTL_MS, snapshot };
  return snapshot;
}

export async function getLiveCandles(
  symbol: string,
  interval: CandleInterval,
  limit = 100,
) {
  const rows = await getJson<unknown[][]>(
    `${BINANCE_KLINES_URL}?symbol=${encodeURIComponent(symbol)}USDT&interval=${interval}&limit=${limit}`,
  );
  const candles = rows
    .map((row) => ({
      time: Math.floor(finite(Number(row[0])) / 1000),
      open: Number(row[1]),
      high: Number(row[2]),
      low: Number(row[3]),
      close: Number(row[4]),
    }))
    .filter(
      (candle) =>
        candle.time > 0 &&
        [candle.open, candle.high, candle.low, candle.close].every(
          (value) => Number.isFinite(value) && value > 0,
        ),
    );
  if (!candles.length) {
    throw new Error(`Binance returned no ${interval} candles for ${symbol}/USDT`);
  }
  return candles;
}