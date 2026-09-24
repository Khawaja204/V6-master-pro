import { Router, type IRouter } from "express";
import {
  GetMarketSnapshotResponse,
  GetWatchlistResponse,
  ListExecutionLogsResponse,
  ListStrategiesResponse,
  ToggleWatchlistBody,
  ToggleWatchlistParams,
  ToggleWatchlistResponse,
} from "@workspace/api-zod";
import type { Coin, ExecutionLog, Strategy, VsaCheck } from "@workspace/api-zod";

const router: IRouter = Router();

const coins: Coin[] = [
  {
    id: "btc",
    symbol: "BTC",
    name: "Bitcoin",
    price: 106482.12,
    change24h: 2.84,
    volume24h: 28400000000,
    followers: 12400000,
    circulatingSupply: 19.85,
    maxSupply: 21,
    marketCap: 2113000000000,
    vsa: "ok_up",
  },
  {
    id: "eth",
    symbol: "ETH",
    name: "Ethereum",
    price: 3864.73,
    change24h: 1.62,
    volume24h: 12600000000,
    followers: 8100000,
    circulatingSupply: 120.4,
    maxSupply: 120.4,
    marketCap: 465300000000,
    vsa: "ok_up",
  },
  {
    id: "sol",
    symbol: "SOL",
    name: "Solana",
    price: 228.64,
    change24h: -1.18,
    volume24h: 4800000000,
    followers: 2900000,
    circulatingSupply: 476.9,
    maxSupply: 592.6,
    marketCap: 109000000000,
    vsa: "manipulation_buy",
  },
  {
    id: "link",
    symbol: "LINK",
    name: "Chainlink",
    price: 24.81,
    change24h: -2.46,
    volume24h: 910000000,
    followers: 1800000,
    circulatingSupply: 587.1,
    maxSupply: 1000,
    marketCap: 14570000000,
    vsa: "manipulation_buy",
  },
  {
    id: "arb",
    symbol: "ARB",
    name: "Arbitrum",
    price: 0.742,
    change24h: 3.91,
    volume24h: 680000000,
    followers: 780000,
    circulatingSupply: 3862.2,
    maxSupply: 10000,
    marketCap: 2866000000,
    vsa: "manipulation_sell",
  },
  {
    id: "avax",
    symbol: "AVAX",
    name: "Avalanche",
    price: 38.12,
    change24h: -0.72,
    volume24h: 410000000,
    followers: 1300000,
    circulatingSupply: 409.1,
    maxSupply: 715.7,
    marketCap: 15590000000,
    vsa: "ok_down",
  },
  {
    id: "near",
    symbol: "NEAR",
    name: "NEAR Protocol",
    price: 5.18,
    change24h: 4.12,
    volume24h: 320000000,
    followers: 650000,
    circulatingSupply: 1190.4,
    maxSupply: 1210.2,
    marketCap: 6160000000,
    vsa: "ok_up",
  },
  {
    id: "op",
    symbol: "OP",
    name: "Optimism",
    price: 1.91,
    change24h: -3.14,
    volume24h: 270000000,
    followers: 590000,
    circulatingSupply: 1500.1,
    maxSupply: 4294.9,
    marketCap: 2865000000,
    vsa: "ok_down",
  },
];

const vsaChecks: VsaCheck[] = [
  {
    id: "vsa-1",
    coinId: "btc",
    label: "Volume Increase + Price Increase",
    detail: "مقدار اور قیمت دونوں بڑھ رہے ہیں — رجحان صحت مند ہے۔",
    status: "ok",
    volumeChange: 18.4,
    priceChange: 2.84,
  },
  {
    id: "vsa-2",
    coinId: "eth",
    label: "Volume Increase + Price Increase",
    detail: "خریداری کی طاقت موجود ہے، confirmation کا انتظار کریں۔",
    status: "ok",
    volumeChange: 11.8,
    priceChange: 1.62,
  },
  {
    id: "vsa-3",
    coinId: "sol",
    label: "Volume Increase + Price Decrease",
    detail: "ممکنہ manipulation — demand zone میں Buy setup دیکھیں۔",
    status: "manipulation",
    volumeChange: 31.6,
    priceChange: -1.18,
  },
  {
    id: "vsa-4",
    coinId: "arb",
    label: "Volume Decrease + Price Increase",
    detail: "ممکنہ distribution — Sell setup اور liquidity sweep چیک کریں۔",
    status: "manipulation",
    volumeChange: -14.2,
    priceChange: 3.91,
  },
  {
    id: "vsa-5",
    coinId: "avax",
    label: "Volume Decrease + Price Decrease",
    detail: "مقدار اور قیمت دونوں کم ہیں — فی الحال انتظار کریں۔",
    status: "ok",
    volumeChange: -8.7,
    priceChange: -0.72,
  },
];

const strategies: Strategy[] = [
  {
    id: "v1",
    name: "V1 Smoothed Heikin Ashi",
    shortName: "V1",
    category: "Trend",
    timeframe: "30m / 1D",
    bias: "Long bias",
    rules: [
      "Smoothed Heikin Ashi candle must close in trend direction.",
      "RSI 55 acts as the primary momentum gate.",
      "30m entry requires 1D structure to agree.",
      "Wick invalidation protects the setup; target is a 1% TP.",
    ],
    winRate: 68.4,
    trades: 142,
  },
  {
    id: "price-action",
    name: "Price Action",
    shortName: "PA",
    category: "Scalp / Intraday",
    timeframe: "4H OC / 1H S&R",
    bias: "Reactive",
    rules: [
      "Use 4H open-close direction as the session anchor.",
      "Map 1H support and resistance before taking a trade.",
      "Target 1–3% and validate liquidity with the Coinglass heatmap.",
      "Skip entries when liquidation clusters sit against the setup.",
    ],
    winRate: 63.1,
    trades: 89,
  },
  {
    id: "ict",
    name: "ICT Method 2",
    shortName: "ICT",
    category: "Liquidity",
    timeframe: "15m / 1H",
    bias: "Session based",
    rules: [
      "Mark consolidation and the dealing range before expansion.",
      "Analyze the final minutes of the active session.",
      "Require a displacement candle and a clean liquidity sweep.",
      "Enter on the return to the fair value area.",
    ],
    winRate: 61.8,
    trades: 74,
  },
  {
    id: "institutional",
    name: "Institutional OB + FVG",
    shortName: "OB / FVG",
    category: "Order flow",
    timeframe: "1W / 1D",
    bias: "Structure first",
    rules: [
      "Classify body, wick, and trend-base candles.",
      "Validate the order block across 1W and 1D structure.",
      "Confirm a multi-drop reaction before marking the level active.",
      "Pair the block with an unfilled fair value gap.",
    ],
    winRate: 59.7,
    trades: 61,
  },
  {
    id: "rsi-smc",
    name: "RSI Divergence + SMC Scalp 4",
    shortName: "SMC 4",
    category: "Divergence",
    timeframe: "5m / 15m",
    bias: "Reversal",
    rules: [
      "Hidden bullish divergence between RSI 30–40 is a Buy condition.",
      "Hidden bearish divergence above RSI 50 is a Sell condition.",
      "Require a market structure shift before entry.",
      "Keep the scalp tight and invalidate on a fresh swing break.",
    ],
    winRate: 64.9,
    trades: 118,
  },
];

const executionLogs: ExecutionLog[] = [
  {
    id: "log-1",
    timestamp: "09:42:16",
    type: "VSA",
    message: "SOL پر Volume Increase + Price Decrease ملا — Manipulation Buy zone فعال ہے۔",
    coinId: "sol",
  },
  {
    id: "log-2",
    timestamp: "09:40:02",
    type: "V1",
    message: "BTC کا 1D filter bullish ہے اور RSI 55 سے اوپر ہے — 1% TP setup تیار ہے۔",
    coinId: "btc",
  },
  {
    id: "log-3",
    timestamp: "09:37:48",
    type: "PA",
    message: "ETH کا 1H support hold کر رہا ہے، heatmap میں مخالف liquidity کم ہے۔",
    coinId: "eth",
  },
  {
    id: "log-4",
    timestamp: "09:35:11",
    type: "SMC",
    message: "LINK میں RSI 36 پر hidden bullish divergence confirm ہوئی۔",
    coinId: "link",
  },
];

let watchlist = new Set(["btc", "sol", "link"]);

router.get("/market/snapshot", (_req, res) => {
  const data = GetMarketSnapshotResponse.parse({
    updatedAt: "2026-09-24T09:42:16+05:00",
    coins,
    vsaChecks,
    marketBreadth: 61.8,
    sessionPnl: 3.42,
  });
  res.json(data);
});

router.get("/strategies", (_req, res) => {
  res.json(ListStrategiesResponse.parse(strategies));
});

router.get("/watchlist", (_req, res) => {
  res.json(GetWatchlistResponse.parse({ coinIds: Array.from(watchlist) }));
});

router.put("/watchlist/:coinId", (req, res) => {
  const { coinId } = ToggleWatchlistParams.parse(req.params);
  const { favorite } = ToggleWatchlistBody.parse(req.body);
  if (favorite) watchlist.add(coinId);
  else watchlist.delete(coinId);
  res.json(
    ToggleWatchlistResponse.parse({ coinIds: Array.from(watchlist) }),
  );
});

router.get("/execution-logs", (_req, res) => {
  res.json(ListExecutionLogsResponse.parse(executionLogs));
});

export default router;