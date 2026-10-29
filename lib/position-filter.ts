import type { ClosedCandle } from "./binance-top-usdt";
import { utBotSignals } from "./ut-bot";
import { powerSignals } from "./power-indicator";
import { volSignals } from "./ocs-vol";

export interface Sig {
  time: number;
  kind: "buy" | "sell";
  price: number;
}

export interface TradeStat {
  closed: number;
  wins: number;
  avgPct: number | null;
  open: boolean;
}

// Only one open position per indicator. BUY opens it (ignored if already open).
// SELL or VOL WARN closes it (ignored if flat, no shorting).
function applyPosition(raw: { time: number; kind: string; price: number }[]): { kept: Sig[]; stat: TradeStat } {
  const sorted = [...raw].sort((a, b) => a.time - b.time);
  const kept: Sig[] = [];
  let entry: Sig | null = null;
  let closed = 0;
  let wins = 0;
  let sumPct = 0;
  for (const s of sorted) {
    if (s.kind === "buy") {
      if (entry) continue;
      entry = { time: s.time, kind: "buy", price: s.price };
      kept.push(entry);
    } else {
      if (!entry) continue;
      const pct = ((s.price - entry.price) / entry.price) * 100;
      closed += 1;
      sumPct += pct;
      if (pct > 0) wins += 1;
      kept.push({ time: s.time, kind: "sell", price: s.price });
      entry = null;
    }
  }
  return {
    kept,
    stat: { closed, wins, avgPct: closed ? sumPct / closed : null, open: entry !== null },
  };
}

export function positionStatsFor(candles: ClosedCandle[]) {
  const ut = applyPosition(utBotSignals(candles).signals);
  const pwr = applyPosition(powerSignals(candles));
  const vol = applyPosition(volSignals(candles));
  return {
    kept: { ut: ut.kept, pwr: pwr.kept, vol: vol.kept },
    stat: { ut: ut.stat, pwr: pwr.stat, vol: vol.stat },
  };
}

export function fmtTrades(s: TradeStat): string {
  if (s.closed === 0) return s.open ? "0 closed · open" : "0 closed";
  const net = s.avgPct! - 0.2;
  const base = `${s.closed} closed · ${Math.round((s.wins / s.closed) * 100)}% win · avg ${s.avgPct!.toFixed(2)}% · net after fees ${net.toFixed(2)}%`;
  return s.open ? `${base} · open` : base;
}
