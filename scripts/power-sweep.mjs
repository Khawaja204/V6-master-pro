// Power Indicator length sweep. Descriptive research only, not a trading signal.
const SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];
const LIMIT = 1000;      // 1H candles (~6 weeks)
const FEE = 0.2;         // round trip %
const H = 12;            // horizon candles for the "tag win" check
const LENGTHS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 12];
const TRAIN_SHARE = 0.6;

async function klines(sym) {
  const r = await fetch(`https://api.binance.com/api/v3/klines?symbol=${sym}&interval=1h&limit=${LIMIT}`);
  if (!r.ok) throw new Error(`${sym}: HTTP ${r.status}`);
  return (await r.json()).map((k) => ({ t: k[0], o: +k[1], h: +k[2], l: +k[3], c: +k[4] }));
}

// Same logic as lib/power-indicator.ts
function powerSignals(cs, len) {
  const n = cs.length;
  const dsi = new Array(n).fill(0);
  for (let i = 2 * len; i < n; i++) {
    let up = 0, down = 0;
    for (let k = 0; k < len; k++) {
      const a = cs[i - k].c, b = cs[i - k - len].c;
      if (a > b) up++;
      if (a < b) down++;
    }
    dsi[i] = down === len ? 1 : up === len ? -1 : 0;
  }
  const sig = [];
  for (let i = 2 * len + 1; i < n; i++) {
    if (dsi[i] > 0 && dsi[i - 1] <= 0) sig.push({ i, kind: "buy" });
    if (dsi[i] < 0 && dsi[i - 1] >= 0) sig.push({ i, kind: "sell" });
  }
  return sig;
}

// Tag check: price H candles after each buy. Trade check: long from buy to next sell, net of fees.
function evaluate(cs, sig, from, to) {
  let hT = 0, hW = 0;
  for (const s of sig) {
    if (s.kind !== "buy" || s.i < from || s.i >= to || s.i + H >= cs.length) continue;
    hT++;
    if (cs[s.i + H].c > cs[s.i].c) hW++;
  }
  let pos = null;
  const nets = [];
  for (const s of sig) {
    if (s.i < from || s.i >= to) continue;
    if (s.kind === "buy" && pos === null) pos = s.i;
    else if (s.kind === "sell" && pos !== null) {
      nets.push((cs[s.i].c / cs[pos].c - 1) * 100 - FEE);
      pos = null;
    }
  }
  return { hT, hW, rt: nets.length, rtW: nets.filter((x) => x > 0).length, netSum: nets.reduce((a, b) => a + b, 0) };
}

function sumInto(acc, e) {
  acc.hT += e.hT; acc.hW += e.hW; acc.rt += e.rt; acc.rtW += e.rtW; acc.netSum += e.netSum;
  return acc;
}
const pct = (a, b) => (b ? `${((a / b) * 100).toFixed(0)}%` : "–");
const avg = (a, b) => (b ? `${(a / b >= 0 ? "+" : "")}${(a / b).toFixed(2)}%` : "–");

const data = {};
for (const s of SYMS) data[s] = await klines(s);

const table = [];
for (const len of LENGTHS) {
  const train = { hT: 0, hW: 0, rt: 0, rtW: 0, netSum: 0 };
  const test = { hT: 0, hW: 0, rt: 0, rtW: 0, netSum: 0 };
  for (const s of SYMS) {
    const cs = data[s];
    const split = Math.floor(cs.length * TRAIN_SHARE);
    const sig = powerSignals(cs, len);
    sumInto(train, evaluate(cs, sig, 0, split));
    sumInto(test, evaluate(cs, sig, split, cs.length));
  }
  table.push({ len, train, test });
}

console.log("len | TRAIN tag-win (n) | TRAIN net avg (trades) | TEST tag-win (n) | TEST net avg (trades)");
for (const r of table) {
  console.log(
    `${String(r.len).padStart(3)} | ${pct(r.train.hW, r.train.hT).padStart(8)} (${r.train.hT}) | ${avg(r.train.netSum, r.train.rt).padStart(8)} (${r.train.rt}) | ${pct(r.test.hW, r.test.hT).padStart(8)} (${r.test.hT}) | ${avg(r.test.netSum, r.test.rt).padStart(8)} (${r.test.rt})`,
  );
}

const best = [...table].sort((a, b) => (b.train.hW / Math.max(b.train.hT, 1)) - (a.train.hW / Math.max(a.train.hT, 1)))[0];
const def = table.find((r) => r.len === 4);
console.log("");
console.log(`Best on TRAIN: length ${best.len} -> TEST tag-win ${pct(best.test.hW, best.test.hT)} (n=${best.test.hT})`);
console.log(`Default length 4 on TEST: tag-win ${pct(def.test.hW, def.test.hT)} (n=${def.test.hT}), net ${avg(def.test.netSum, def.test.rt)}`);
console.log("Only trust a length if it also wins on TEST, with enough trades (50+).");
