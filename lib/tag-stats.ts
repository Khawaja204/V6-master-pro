import type { ClosedCandle } from "./binance-top-usdt";
import { utBotSignals } from "./ut-bot";
import { powerSignals } from "./power-indicator";
import { volSignals } from "./ocs-vol";

export interface TagStat {
  total: number;
  wins: number;
}

export interface TagStats {
  ut: TagStat;
  pwr: TagStat;
  vol: TagStat;
}

interface Sig {
  time: number;
  kind: string;
  price: number;
}

// Win = price moved in the signal direction `horizon` candles after the tag.
// VOL WARN (exit warnings) are not counted, only BUY/SELL tags.
function score(candles: ClosedCandle[], sigs: Sig[], horizon: number): TagStat {
  const index = new Map<number, number>();
  candles.forEach((c, i) => index.set(c.time, i));
  let total = 0;
  let wins = 0;
  for (const s of sigs) {
    if (s.kind === "warn") continue;
    const i = index.get(s.time);
    if (i === undefined || i + horizon >= candles.length) continue;
    const future = candles[i + horizon].close;
    total += 1;
    if (s.kind === "buy" ? future > s.price : future < s.price) wins += 1;
  }
  return { total, wins };
}

export function tagStatsFor(candles: ClosedCandle[], horizon = 12): TagStats {
  return {
    ut: score(candles, utBotSignals(candles).signals, horizon),
    pwr: score(candles, powerSignals(candles), horizon),
    vol: score(candles, volSignals(candles), horizon),
  };
}

export function fmtStat(s: TagStat): string {
  if (s.total === 0) return "–";
  return `${s.wins}/${s.total} ${Math.round((s.wins / s.total) * 100)}%`;
}
