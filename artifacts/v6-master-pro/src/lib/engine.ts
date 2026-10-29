import type { ClosedCandle } from "./binance-top-usdt";
import { utBotSignals } from "./ut-bot";
import { powerSignals } from "./power-indicator";
import { volSignals } from "./ocs-vol";

export const ENGINE = {
  window: 24,      // candles an indicator's last event stays valid
  agreeMin: 2,     // votes needed to enter (of 3)
  feePct: 0.2,     // round trip
  slAtr: 1.2,
  tpR: 2,
  atrPeriod: 14,
};

export interface EngineTrade {
  entryTime: number;
  entryPrice: number;
  exitTime: number;
  exitPrice: number;
  netPct: number;
  why: "SL" | "TP" | "VOTE";
}

export interface EngineMark {
  time: number;
  kind: "buy" | "sell";
  price: number;
  why: string;
}

export interface EngineResult {
  trades: EngineTrade[];
  marks: EngineMark[];
  wins: number;
  avgNet: number | null;
  open: boolean;
}

function atrRma(candles: ClosedCandle[], period: number): number[] {
  const out = new Array<number>(candles.length).fill(NaN);
  if (candles.length < period) return out;
  const tr = candles.map((c, i) => (i === 0
    ? c.high - c.low
    : Math.max(c.high - c.low, Math.abs(c.high - candles[i - 1].close), Math.abs(c.low - candles[i - 1].close))));
  let rma = tr.slice(0, period).reduce((a, b) => a + b, 0) / period;
  out[period - 1] = rma;
  for (let i = period; i < candles.length; i += 1) {
    rma = (rma * (period - 1) + tr[i]) / period;
    out[i] = rma;
  }
  return out;
}

// Vote per bar: direction of the latest event, 0 if none within `window` bars.
function voteSeries(n: number, events: { i: number; dir: number }[], window: number): number[] {
  const out = new Array<number>(n).fill(0);
  const sorted = [...events].sort((a, b) => a.i - b.i);
  let p = 0;
  let dir = 0;
  let at = -Infinity;
  for (let i = 0; i < n; i += 1) {
    while (p < sorted.length && sorted[p].i <= i) {
      dir = sorted[p].dir;
      at = sorted[p].i;
      p += 1;
    }
    out[i] = i - at <= window ? dir : 0;
  }
  return out;
}

export function runEngine(candles: ClosedCandle[]): EngineResult {
  const n = candles.length;
  const empty: EngineResult = { trades: [], marks: [], wins: 0, avgNet: null, open: false };
  if (n < 60) return empty;

  const idx = new Map<number, number>();
  candles.forEach((c, i) => idx.set(c.time, i));
  const toEvents = (sigs: { time: number; kind: string }[]) => sigs.flatMap((s) => {
    const i = idx.get(s.time);
    if (i === undefined) return [];
    const dir = s.kind === "buy" ? 1 : s.kind === "sell" ? -1 : 0;
    return [{ i, dir }];
  });

  const ut = voteSeries(n, toEvents(utBotSignals(candles).signals), ENGINE.window);
  const pwr = voteSeries(n, toEvents(powerSignals(candles)), ENGINE.window);
  const vol = voteSeries(n, toEvents(volSignals(candles)), ENGINE.window);
  const atr = atrRma(candles, ENGINE.atrPeriod);

  const trades: EngineTrade[] = [];
  const marks: EngineMark[] = [];
  let pos: { i: number; entry: number; stop: number; tp: number } | null = null;

  for (let i = 1; i < n; i += 1) {
    const c = candles[i];
    const v = ut[i] + pwr[i] + vol[i];
    if (pos) {
      let exit: number | null = null;
      let why: EngineTrade["why"] | null = null;
      if (c.low <= pos.stop) { exit = pos.stop; why = "SL"; }
      else if (c.high >= pos.tp) { exit = pos.tp; why = "TP"; }
      else if (v <= 0) { exit = c.close; why = "VOTE"; }
      if (exit !== null && why !== null) {
        const net = ((exit - pos.entry) / pos.entry) * 100 - ENGINE.feePct;
        trades.push({
          entryTime: candles[pos.i].time,
          entryPrice: pos.entry,
          exitTime: c.time,
          exitPrice: exit,
          netPct: net,
          why,
        });
        marks.push({ time: c.time, kind: "sell", price: exit, why: `${why} ${net >= 0 ? "+" : ""}${net.toFixed(2)}%` });
        pos = null;
      }
    } else if (v >= ENGINE.agreeMin && Number.isFinite(atr[i])) {
      const risk = Math.max(ENGINE.slAtr * atr[i], 1e-10);
      pos = { i, entry: c.close, stop: c.close - risk, tp: c.close + ENGINE.tpR * risk };
      marks.push({ time: c.time, kind: "buy", price: c.close, why: `${v} of 3` });
    }
  }

  const wins = trades.filter((t) => t.netPct > 0).length;
  const avgNet = trades.length ? trades.reduce((a, t) => a + t.netPct, 0) / trades.length : null;
  return { trades, marks, wins, avgNet, open: pos !== null };
}

export function formatEngine(r: EngineResult): string {
  const avg = r.avgNet === null ? "–" : `${r.avgNet >= 0 ? "+" : ""}${r.avgNet.toFixed(2)}%`;
  const state = r.open ? "open" : "flat";
  return `${r.trades.length} closed · ${r.wins} win · net avg ${avg} · ${state}`;
}
