export interface VolumeProfile {
  poc: number; // price with the most traded volume
  vah: number; // value area high
  val: number; // value area low
}

// Volume at each price bin, binned by candle close. Value area = the bins
// around POC that hold valueAreaPct of total volume.
export function volumeProfile(
  candles: { high: number; low: number; close: number; quoteVolume: number }[],
  bins = 24,
  valueAreaPct = 0.7,
): VolumeProfile | null {
  if (candles.length < 2) return null;
  let lo = Infinity;
  let hi = -Infinity;
  for (const c of candles) {
    if (c.low < lo) lo = c.low;
    if (c.high > hi) hi = c.high;
  }
  if (!(hi > lo)) return null;

  const step = (hi - lo) / bins;
  const vol = new Array<number>(bins).fill(0);
  for (const c of candles) {
    const idx = Math.min(bins - 1, Math.max(0, Math.floor((c.close - lo) / step)));
    vol[idx] += c.quoteVolume;
  }
  const total = vol.reduce((a, b) => a + b, 0);
  if (total <= 0) return null;

  let pocIdx = 0;
  for (let i = 1; i < bins; i += 1) {
    if (vol[i] > vol[pocIdx]) pocIdx = i;
  }

  let low = pocIdx;
  let high = pocIdx;
  let acc = vol[pocIdx];
  while (acc / total < valueAreaPct && (low > 0 || high < bins - 1)) {
    const below = low > 0 ? vol[low - 1] : -1;
    const above = high < bins - 1 ? vol[high + 1] : -1;
    if (above >= below) {
      high += 1;
      acc += vol[high];
    } else {
      low -= 1;
      acc += vol[low];
    }
  }

  return {
    poc: lo + (pocIdx + 0.5) * step,
    vah: lo + (high + 1) * step,
    val: lo + low * step,
  };
}
