import type { ClosedCandle } from "./binance-top-usdt";

// Breakout Probability (Expo): TypeScript port.
// Original Pine indicator: (c) Zeiierman, license CC BY-NC-SA 4.0
// https://creativecommons.org/licenses/by-nc-sa/4.0/
// Sirf non-commercial istemal. Yeh sirf tareekhi statistics hain, trade signal nahi.

export interface BpLevel {
  price: number;
  prob: number;
  side: "up" | "down";
  idx: number;
}

export interface BpResult {
  state: "green" | "red";
  levels: BpLevel[];
  win: number;
  loss: number;
  profit: number | null;
}

const pct = (num: number, den: number): number => (den > 0 ? (num * 100) / den : 0);

export function breakoutProb(c: ClosedCandle[], perc = 1, nbr = 5, hideZero = true): BpResult {
  const n = c.length;
  const emptyState: BpResult["state"] = "green";
  if (n < 3) return { state: emptyState, levels: [], win: 0, loss: 0, profit: null };

  // cnt[i] = [green+highs, green+lows, red+highs, red+lows] for level i
  const cnt: number[][] = Array.from({ length: nbr }, () => [0, 0, 0, 0]);
  let gtot = 0;
  let rtot = 0;
  let win = 0;
  let loss = 0;

  for (let j = 1; j < n; j += 1) {
    const prev = c[j - 1];
    const cur = c[j];
    const g = prev.close > prev.open;
    const r = prev.close < prev.open;
    if (g) gtot += 1;
    if (r) rtot += 1;
    const step = cur.close * (perc / 100);
    for (let i = 0; i < nbr; i += 1) {
      const x = step * i;
      const hh = cur.high >= prev.high + x;
      const ll = cur.low <= prev.low - x;
      if (g && hh) cnt[i][0] += 1;
      if (g && ll) cnt[i][1] += 1;
      if (r && hh) cnt[i][2] += 1;
      if (r && ll) cnt[i][3] += 1;
    }
    // Backtest: running level-0 probabilities se target chuna jata hai (Pine ke mutabiq)
    const upPick = g
      ? pct(cnt[0][0], gtot) >= pct(cnt[0][1], gtot)
      : pct(cnt[0][2], rtot) >= pct(cnt[0][3], rtot);
    const target = upPick ? prev.high : prev.low;
    const won = upPick ? cur.high >= target : cur.low <= target;
    if (won) win += 1;
    else loss += 1;
  }

  const last = c[n - 1];
  // Pine: green = c[1] > o[1]; doji red logic mein jata hai
  const isGreen = last.close > last.open;
  const state: BpResult["state"] = isGreen ? "green" : "red";
  const step = last.close * (perc / 100);
  const levels: BpLevel[] = [];
  for (let i = 0; i < nbr; i += 1) {
    const pUp = isGreen ? pct(cnt[i][0], gtot) : pct(cnt[i][2], rtot);
    const pDn = isGreen ? pct(cnt[i][1], gtot) : pct(cnt[i][3], rtot);
    levels.push({ price: last.high + step * i, prob: pUp, side: "up", idx: i });
    levels.push({ price: last.low - step * i, prob: pDn, side: "down", idx: i });
  }
  // Pine ke mutabiq: level i ek saath dikhta hai, sirf jab up aur down dono probability > 0 hon
  const shown: BpLevel[] = [];
  for (let i = 0; i < nbr; i += 1) {
    const up = levels[2 * i];
    const dn = levels[2 * i + 1];
    if (!hideZero || (up.prob > 0 && dn.prob > 0)) shown.push(up, dn);
  }
  return {
    state,
    levels: shown,
    win,
    loss,
    profit: win + loss > 0 ? pct(win, win + loss) : null,
  };
}
