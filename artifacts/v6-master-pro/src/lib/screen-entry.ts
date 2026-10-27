import { Candle } from "./ocs-signals";
import { buildEntrySignals } from "./ocs-entry";

export type ScreenResult = {
  symbol: string;
  pump: boolean;
  normal: boolean;
  note: string;
};

// Screening only. Returns whether the LAST closed 15m candle meets each entry rule.
// This is not a trading signal: backtests so far showed no out-of-sample edge.
export function screenSymbol(symbol: string, candles: Candle[]): ScreenResult {
  const base = { symbol, note: "Screening only, not a signal" };
  if (candles.length < 300) {
    return { ...base, pump: false, normal: false, note: "insufficient data (need 300+ candles)" };
  }
  const pumpSig = buildEntrySignals(candles, { mode: "Pump" });
  const normalSig = buildEntrySignals(candles, { mode: "Normal" });
  const last = candles.length - 1;
  return {
    ...base,
    pump: pumpSig[last] === true,
    normal: normalSig[last] === true,
  };
}

// Screen many symbols at once. Input: map of symbol -> candles.
export function screenAll(data: Record<string, Candle[]>): ScreenResult[] {
  return Object.entries(data).map(([sym, c]) => screenSymbol(sym, c));
}
