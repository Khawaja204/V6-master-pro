import type { ClosedCandle } from "./binance-top-usdt";

export interface PowerSignal {
  time: number;
  kind: "buy" | "sell";
  price: number;
}

// Power Indicator (Trading_Bites): compares each close with the close `length` bars earlier.
// State +1 when all last `length` comparisons are "lower" (buy), -1 when all are "higher" (sell).
// Signals fire on the bar the state crosses 0.
export function powerSignals(candles: ClosedCandle[], length = 6): PowerSignal[] {
  const dsi: number[] = new Array(candles.length).fill(0);
  for (let i = 2 * length; i < candles.length; i += 1) {
    let up = 0;
    let down = 0;
    for (let k = 0; k < length; k += 1) {
      const a = candles[i - k].close;
      const b = candles[i - k - length].close;
      if (a > b) up += 1;
      if (a < b) down += 1;
    }
    dsi[i] = down === length ? 1 : up === length ? -1 : 0;
  }

  const signals: PowerSignal[] = [];
  for (let i = 2 * length + 1; i < candles.length; i += 1) {
    if (dsi[i] > 0 && dsi[i - 1] <= 0) {
      signals.push({ time: candles[i].time, kind: "buy", price: candles[i].close });
    }
    if (dsi[i] < 0 && dsi[i - 1] >= 0) {
      signals.push({ time: candles[i].time, kind: "sell", price: candles[i].close });
    }
  }
  return signals;
}

// Power trades: Power BUY par entry, SL = ATR x slAtr, TP1 = tpR x risk.
// Exit: SL, TP1, ya Power SELL (jo pehle ho). Ek waqt mein ek trade.
export interface PowerTrade {
  entryTime: number;
  entry: number;
  stop: number;
  tp1: number;
  exitTime: number | null;
  exit: number | null;
  why: string;
}

export function powerTrades(
  candles: ClosedCandle[],
  length = 6,
  atrLen = 14,
  slAtr = 1.5,
  tpR = 2,
): PowerTrade[] {
  const sigAt = new Map<number, "buy" | "sell">();
  for (const s of powerSignals(candles, length)) sigAt.set(s.time, s.kind);
  const tr: number[] = candles.map((c, i) =>
    i === 0
      ? c.high - c.low
      : Math.max(c.high - c.low, Math.abs(c.high - candles[i - 1].close), Math.abs(c.low - candles[i - 1].close)));
  const trades: PowerTrade[] = [];
  let open: PowerTrade | null = null;
  for (let i = 1; i < candles.length; i += 1) {
    const c = candles[i];
    if (open) {
      if (c.low <= open.stop) {
        open.exitTime = c.time; open.exit = open.stop; open.why = "SL";
        trades.push(open); open = null; continue;
      }
      if (c.high >= open.tp1) {
        open.exitTime = c.time; open.exit = open.tp1; open.why = "TP1";
        trades.push(open); open = null; continue;
      }
      if (sigAt.get(c.time) === "sell") {
        open.exitTime = c.time; open.exit = c.close; open.why = "POWER SELL";
        trades.push(open); open = null; continue;
      }
    } else if (sigAt.get(c.time) === "buy" && i >= atrLen) {
      const atr = tr.slice(i - atrLen + 1, i + 1).reduce((a, b) => a + b, 0) / atrLen;
      const risk = Math.max(slAtr * atr, 1e-10);
      open = { entryTime: c.time, entry: c.close, stop: c.close - risk, tp1: c.close + tpR * risk, exitTime: null, exit: null, why: "open" };
    }
  }
  if (open) trades.push(open);
  return trades;
}

