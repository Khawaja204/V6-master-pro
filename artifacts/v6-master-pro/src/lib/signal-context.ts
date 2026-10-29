import type { ClosedCandle } from "./binance-top-usdt";
import { detectFvg } from "./ocs-fvg";
import { detectOrderBlocks } from "./ob-zones";
import { positionStatsFor } from "./position-filter";
import { formatTagPrice } from "./ut-bot";

interface Zone {
  name: string;
  kind: string;
  top: number;
  bottom: number;
  from: number;
  to: number;
}

// Last `count` entry/exit tags, each with the nearest OB or FVG that was active at that bar.
export function recentContext(candles: ClosedCandle[], count = 3): string[] {
  if (candles.length < 60) return [];
  const idx = new Map<number, number>();
  candles.forEach((c, i) => idx.set(c.time, i));

  const { kept } = positionStatsFor(candles);
  const tags = [
    ...kept.ut.map((s) => ({ ...s, label: "UT" })),
    ...kept.pwr.map((s) => ({ ...s, label: "PWR" })),
    ...kept.vol.map((s) => ({ ...s, label: "VOL" })),
  ].filter((s) => idx.has(s.time));

  const zones: Zone[] = [
    ...detectFvg(candles).map((z) => ({
      name: "FVG", kind: z.kind, top: z.top, bottom: z.bottom,
      from: z.confirmIndex, to: z.fillIndex ?? Infinity,
    })),
    ...detectOrderBlocks(candles).map((z) => ({
      name: "OB", kind: z.kind, top: z.top, bottom: z.bottom,
      from: z.confirmIndex, to: z.mitigatedIndex ?? Infinity,
    })),
  ];

  return tags
    .sort((a, b) => b.time - a.time)
    .slice(0, count)
    .map((s) => {
      const i = idx.get(s.time) as number;
      let best = "no OB/FVG within 1%";
      for (const z of zones) {
        if (!(z.from <= i && i < z.to)) continue;
        const inside = s.price <= z.top && s.price >= z.bottom;
        const dist = inside
          ? 0
          : (Math.min(Math.abs(s.price - z.top), Math.abs(s.price - z.bottom)) / s.price) * 100;
        if (inside || dist <= 1) {
          best = `${inside ? "inside" : `${dist.toFixed(2)}% from`} ${z.kind} ${z.name} ${formatTagPrice(z.bottom)}–${formatTagPrice(z.top)}`;
          break;
        }
      }
      return `${s.label} ${s.kind.toUpperCase()} ${formatTagPrice(s.price)} → ${best}`;
    });
}
