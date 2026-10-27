// Fair Value Gap (FVG) detection. Pure functions, descriptive only. Not a trading signal.
import { Candle } from "./ocs-signals";

export type FvgZone = {
  kind: "bullish" | "bearish";
  middleIndex: number;        // candle 2 (the impulse candle)
  confirmIndex: number;       // candle 3 (zone is known once this bar closes)
  top: number;
  bottom: number;
  touchIndex: number | null;  // first later bar whose range enters the zone
  fillIndex: number | null;   // first later bar that trades fully through the zone
};

// Bullish FVG: candle1.high < candle3.low, zone = [candle1.high, candle3.low].
// Bearish FVG: candle1.low > candle3.high, zone = [candle3.high, candle1.low].
export function detectFvg(candles: Candle[], minSizePct = 0): FvgZone[] {
  const zones: FvgZone[] = [];
  for (let i = 2; i < candles.length; i++) {
    const c1 = candles[i - 2];
    const c3 = candles[i];
    let kind: "bullish" | "bearish" | null = null;
    let top = 0;
    let bottom = 0;
    if (c1.high < c3.low) {
      kind = "bullish";
      bottom = c1.high;
      top = c3.low;
    } else if (c1.low > c3.high) {
      kind = "bearish";
      bottom = c3.high;
      top = c1.low;
    }
    if (!kind) continue;
    const sizePct = ((top - bottom) / c3.close) * 100;
    if (sizePct < minSizePct) continue;
    zones.push({
      kind,
      middleIndex: i - 1,
      confirmIndex: i,
      top,
      bottom,
      touchIndex: null,
      fillIndex: null,
    });
  }
  for (const z of zones) {
    for (let j = z.confirmIndex + 1; j < candles.length; j++) {
      const c = candles[j];
      if (z.touchIndex === null && c.high >= z.bottom && c.low <= z.top) {
        z.touchIndex = j;
      }
      if (z.kind === "bullish" && c.low <= z.bottom) {
        z.fillIndex = j;
        break;
      }
      if (z.kind === "bearish" && c.high >= z.top) {
        z.fillIndex = j;
        break;
      }
    }
  }
  return zones;
}

// Descriptive counts only. These are NOT win rates and NOT entry signals.
export function fvgStats(zones: FvgZone[]) {
  const n = zones.length;
  const touched = zones.filter((z) => z.touchIndex !== null).length;
  const filled = zones.filter((z) => z.fillIndex !== null).length;
  return {
    n,
    bullish: zones.filter((z) => z.kind === "bullish").length,
    bearish: zones.filter((z) => z.kind === "bearish").length,
    touchedPct: n ? (touched / n) * 100 : 0,
    filledPct: n ? (filled / n) * 100 : 0,
  };
}

// Chart boxes: one per zone, from the first candle of the pattern to the fill bar
// (or the last bar if still open). Label marks it as informational only.
export function fvgBoxes(zones: FvgZone[], candles: Candle[]) {
  return zones.map((z) => ({
    kind: z.kind,
    fromTime: candles[z.confirmIndex - 2].time,
    toTime: z.fillIndex !== null ? candles[z.fillIndex].time : candles[candles.length - 1].time,
    top: z.top,
    bottom: z.bottom,
    label: "FVG zone (not a signal)",
  }));
}
