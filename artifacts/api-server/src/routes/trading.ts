import { Router, type IRouter } from "express";
import {
  GetMarketCandlesQueryParams,
  GetMarketCandlesResponse,
  GetWatchlistResponse,
  ListExecutionLogsResponse,
  ListStrategiesResponse,
  ToggleWatchlistBody,
  ToggleWatchlistParams,
  ToggleWatchlistResponse,
} from "@workspace/api-zod";
import type { ExecutionLog, Strategy } from "@workspace/api-zod";
import {
  getLiveCandles,
  getLiveMarketSnapshot,
  type CandleInterval,
} from "../services/market-data";

const router: IRouter = Router();

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
      "Map valid 1H support, resistance, order blocks, and fair value gaps.",
      "Target 1–3% and validate 12h/24h liquidity with the Coinglass heatmap.",
      "In an uptrend, RSI around 30 can confirm a Buy; in a downtrend, require RSI 15–25 plus structure shift.",
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
    coinId: "solana",
  },
  {
    id: "log-2",
    timestamp: "09:40:02",
    type: "V1",
    message: "BTC کا 1D filter bullish ہے اور RSI 55 سے اوپر ہے — 1% TP setup تیار ہے۔",
    coinId: "bitcoin",
  },
  {
    id: "log-3",
    timestamp: "09:37:48",
    type: "PA",
    message: "ETH کا 1H support hold کر رہا ہے، heatmap میں مخالف liquidity کم ہے۔",
    coinId: "ethereum",
  },
  {
    id: "log-4",
    timestamp: "09:35:11",
    type: "SMC",
    message: "LINK میں RSI 36 پر hidden bullish divergence confirm ہوئی۔",
    coinId: "chainlink",
  },
];

let watchlist = new Set(["bitcoin", "solana", "chainlink"]);

router.get("/market/snapshot", async (_req, res) => {
  try {
    const snapshot = await getLiveMarketSnapshot();
    res.json(snapshot);
  } catch (error) {
    const detail = error instanceof Error ? error.message : "Unknown live feed error";
    res.status(503).json({
      message: "Live market data is temporarily unavailable.",
      detail,
    });
  }
});

router.get("/market/candles", async (req, res) => {
  const parsedQuery = GetMarketCandlesQueryParams.safeParse(req.query);
  if (!parsedQuery.success) {
    res.status(400).json({ message: "Valid coinId, interval, and limit are required." });
    return;
  }
  const { coinId, interval, limit } = parsedQuery.data;

  try {
    const snapshot = await getLiveMarketSnapshot();
    const coin = snapshot.coins.find((item) => item.id === coinId);
    if (!coin) {
      res.status(404).json({ message: "Asset was not found in the live market snapshot." });
      return;
    }
    const candles = await getLiveCandles(coin.symbol, interval as CandleInterval, limit);
    res.json(GetMarketCandlesResponse.parse({ coinId, interval, candles }));
  } catch (error) {
    const detail = error instanceof Error ? error.message : "Unknown live exchange error";
    res.status(503).json({
      message: "Live exchange candles are temporarily unavailable for this asset.",
      detail,
    });
  }
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