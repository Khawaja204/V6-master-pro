/* =============================================================================
   V6 MASTER PRO — APPLICATION LOGIC
   All data fetching, rendering, and interaction. Reads window.V6_CONFIG.
   No markup or styling here; structure lives in index.html, design in style.css.
   ============================================================================= */
(function () {
  "use strict";

  const CFG = window.V6_CONFIG || {};
  const EP = (CFG.api && CFG.api.endpoints) || {};
  const BASE = (CFG.api && CFG.api.base) || "";
  const REFRESH = (CFG.refresh && CFG.refresh.intervalSec) || 30;

  /* ---- Small helpers ------------------------------------------------------ */
  const $ = (id) => document.getElementById(id);
  const api = (path) => BASE + path;
  const set = (id, val) => { const el = $(id); if (el) el.textContent = val; };
  const html = (id, val) => { const el = $(id); if (el) el.innerHTML = val; };
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function fmtPrice(p) {
    if (typeof p !== "number" || !isFinite(p)) return "—";
    if (p >= 1000) return p.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (p >= 1) return p.toFixed(4);
    return p.toFixed(8);
  }
  function fmtPct(v, withSign) {
    if (typeof v !== "number" || !isFinite(v)) return "—";
    const s = withSign && v > 0 ? "+" : "";
    return s + v.toFixed(2) + "%";
  }
  function fmtNum(v) {
    if (typeof v !== "number" || !isFinite(v)) return "—";
    if (v >= 1e9) return (v / 1e9).toFixed(2) + "B";
    if (v >= 1e6) return (v / 1e6).toFixed(2) + "M";
    if (v >= 1e3) return (v / 1e3).toFixed(1) + "K";
    return v.toFixed(0);
  }
  const cls = (v) => (v > 0 ? "up" : v < 0 ? "down" : "muted");
  const sym = (s) => String(s || "").replace("USDT", "");

  /* ---- State -------------------------------------------------------------- */
  let DATA = null;
  let countdown = REFRESH;
  let selectedSymbol = null; // user override via search; else config/auto
  let chartReqToken = 0;

  /* ===========================================================================
     FETCH
     =========================================================================== */
  async function fetchData() {
    try {
      const res = await fetch(api(EP.dashboard), { cache: "no-store" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      DATA = await res.json();
      renderAll(DATA);
      markConnection(true);
    } catch (e) {
      markConnection(false);
      set("st-status", "fetch error");
    }
  }

  function markConnection(ok) {
    const d = $("conn-dot");
    const t = $("conn-text");
    if (d) d.className = "dot" + (ok ? "" : " off");
    if (t) t.textContent = ok ? "LIVE" : "OFFLINE";
  }

  function renderAll(d) {
    renderStatusStrip(d);
    renderMarket(d);
    renderPaper(d);
    const profile = pickProfile(d);
    renderProfile(d, profile);
    renderTDE(d, profile);
    renderSentiment(d);
    renderInst(d);
    renderSmart(d);
    renderWatch(d);
    renderBacktest(d);
    renderHistory(d);
    set("foot-update", "Last data: " + (d.last_update || "—"));
  }

  /* ===========================================================================
     STATUS STRIP + MARKET
     =========================================================================== */
  function renderStatusStrip(d) {
    set("st-status", (d.status || "—").toUpperCase());
    set("st-cycle", d.cycle_count != null ? d.cycle_count : "—");
    set("st-update", d.last_update || "—");
    set("st-exchange", d.active_exchange || "—");
    set("st-regime", d.market_regime || "—");
    const wr = typeof d.win_rate === "number" ? d.win_rate.toFixed(1) + "%" : "—";
    set("st-winrate", wr);
  }

  function renderMarket(d) {
    const b = d.btc || {};
    set("mk-btc-price", "$ " + fmtPrice(b.price));
    const chg = $("mk-btc-chg");
    if (chg) { chg.textContent = fmtPct(b.change_pct, true); chg.className = "v " + cls(b.change_pct); }
    set("mk-sentiment", b.sentiment || "—");
    set("mk-vol", fmtPct(b.volatility_pct));
    set("mk-btc-regime", b.regime || "—");
    set("mk-entries", b.pause_entries ? "PAUSED" : "ALLOWED");
    const en = $("mk-entries");
    if (en) en.className = "v " + (b.pause_entries ? "down" : "up");
  }

  function renderPaper(d) {
    const banner = $("paper-banner");
    if (!banner) return;
    if (d.paper_mode === false) {
      banner.className = "paper-banner real";
      html("paper-banner",
        '<span class="pm-badge pm-real">REAL MODE</span>' +
        '<span>LIVE EXECUTION — signals are real. Trade with extreme caution.</span>');
    } else {
      banner.className = "paper-banner";
      html("paper-banner",
        '<span class="pm-badge pm-paper">PAPER MODE</span>' +
        '<span>Simulated — trades are NOT real. Safe for testing & monitoring.</span>');
    }
  }

  /* ===========================================================================
     COIN PROFILE  (+ live candlestick chart)
     =========================================================================== */
  function pickProfile(d) {
    const list = d.inst_signals || [];
    if (selectedSymbol) {
      const m = list.find((c) => c.symbol === selectedSymbol);
      if (m) return m;
    }
    const cfgSym = CFG.profileSymbol;
    if (cfgSym && cfgSym !== "auto") {
      const m = list.find((c) => c.symbol === cfgSym);
      if (m) return m;
    }
    return [...list].sort((a, b) => (b.score || 0) - (a.score || 0))[0] || null;
  }

  function renderProfile(d, c) {
    if (!c) {
      set("pf-symbol", "—"); set("pf-price", "—"); set("pf-folder", "");
      html("pf-chart", '<div class="chart-empty">Awaiting first scan cycle…</div>');
      return;
    }
    const inst = c.inst || {};
    set("pf-symbol", sym(c.symbol));
    set("pf-folder", c.folder || "");
    set("pf-price", "$ " + fmtPrice(c.price));
    const ch = $("pf-change");
    if (ch) { ch.textContent = fmtPct(c.change_pct, true); ch.className = "pf-change " + cls(c.change_pct); }
    set("pf-rsi", typeof c.rsi === "number" ? c.rsi.toFixed(1) : "—");
    set("pf-score", c.score != null ? c.score : "—");
    set("pf-high", fmtPrice(c.high_24h));
    set("pf-low", fmtPrice(c.low_24h));
    set("pf-pos", typeof c.price_pos_pct === "number" ? c.price_pos_pct.toFixed(0) + "%" : "—");
    set("pf-whale", typeof inst.whale_power === "number" ? inst.whale_power.toFixed(0) + "%" : "—");
    renderChart(c.symbol);
  }

  async function renderChart(symbol) {
    const box = $("pf-chart");
    if (!box || !EP.chart) return;
    const token = ++chartReqToken;
    const ch = (CFG.chart || {});
    const url = api(EP.chart) + "?symbol=" + encodeURIComponent(symbol) +
      "&interval=" + (ch.interval || "1h") + "&limit=" + (ch.limit || 60);
    try {
      const res = await fetch(url, { cache: "no-store" });
      const j = await res.json();
      if (token !== chartReqToken) return; // stale response
      drawCandles(box, (j && j.candles) || []);
    } catch (e) {
      if (token === chartReqToken) box.innerHTML = '<div class="chart-empty">Chart unavailable</div>';
    }
  }

  function drawCandles(box, candles) {
    if (!candles.length) { box.innerHTML = '<div class="chart-empty">No chart data for this symbol</div>'; return; }
    const W = 600, H = 170, pad = 6;
    let hi = -Infinity, lo = Infinity;
    candles.forEach((k) => { hi = Math.max(hi, k.high); lo = Math.min(lo, k.low); });
    const span = hi - lo || 1;
    const y = (p) => pad + (1 - (p - lo) / span) * (H - pad * 2);
    const n = candles.length;
    const cw = W / n;
    const bw = Math.max(1.5, cw * 0.6);
    let parts = "";
    candles.forEach((k, i) => {
      const cx = i * cw + cw / 2;
      const up = k.close >= k.open;
      const color = up ? "#3fb950" : "#ff4d4d";
      const yO = y(k.open), yC = y(k.close);
      const top = Math.min(yO, yC);
      const hgt = Math.max(1, Math.abs(yC - yO));
      parts += '<line x1="' + cx.toFixed(1) + '" y1="' + y(k.high).toFixed(1) +
        '" x2="' + cx.toFixed(1) + '" y2="' + y(k.low).toFixed(1) +
        '" stroke="' + color + '" stroke-width="1"/>';
      parts += '<rect x="' + (cx - bw / 2).toFixed(1) + '" y="' + top.toFixed(1) +
        '" width="' + bw.toFixed(1) + '" height="' + hgt.toFixed(1) +
        '" fill="' + color + '"/>';
    });
    box.innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none">' + parts + '</svg>';
  }

  /* ===========================================================================
     TRADE DECISION ENGINE
     =========================================================================== */
  function renderTDE(d, c) {
    const inst = (c && c.inst) || {};
    const traffic = inst.traffic || "RED";
    const lightEl = $("tde-light");
    const map = { GREEN: "green", YELLOW: "yellow", RED: "red" };
    const icon = { GREEN: "▲", YELLOW: "■", RED: "✕" };
    if (lightEl) { lightEl.className = "light " + (map[traffic] || "red"); lightEl.textContent = icon[traffic] || "✕"; }

    const verdict = traffic === "GREEN" ? "ENTRY READY" : traffic === "YELLOW" ? "WAIT / WATCH" : "NO ENTRY";
    set("tde-verdict", verdict);
    set("tde-symbol", c ? sym(c.symbol) + " · " + (c.trading_strategy || "—") : "—");

    set("tde-inst", typeof inst.inst_score === "number" ? inst.inst_score.toFixed(1) : "—");
    set("tde-ofi", typeof inst.ofi_score === "number" ? inst.ofi_score.toFixed(1) : "—");
    set("tde-whale", typeof inst.whale_power === "number" ? inst.whale_power.toFixed(0) + "%" : "—");
    set("tde-conf", c && typeof c.confidence === "number" ? c.confidence + "%" : "—");
    set("tde-reason", inst.reason || (c ? "Monitoring institutional flow…" : "Awaiting first scan cycle…"));

    const z = (c && c.tp_zones) || {};
    set("tde-entry", z.entry_low ? fmtPrice(z.entry_low) : "—");
    set("tde-sl", z.stop_loss ? fmtPrice(z.stop_loss) : "—");
    set("tde-tp1", z.tp1 ? fmtPrice(z.tp1) : "—");
    set("tde-tp2", z.tp2 ? fmtPrice(z.tp2) : "—");
    set("tde-tp3", z.tp3 ? fmtPrice(z.tp3) : "—");
    const sz = (c && c.sizing) || {};
    set("tde-position", sz.alloc_usdt ? "$" + sz.alloc_usdt.toFixed(2) + " (" + (sz.alloc_pct || 0).toFixed(1) + "%)" : (sz.note || "No allocation"));

    const exec = $("btn-execute");
    if (exec) {
      exec.disabled = traffic !== "GREEN";
      exec.textContent = traffic === "GREEN" ? "EXECUTE ENTRY" : "ENTRY LOCKED";
    }
  }

  /* ===========================================================================
     SENTIMENT & WHALE DATA
     =========================================================================== */
  function renderSentiment(d) {
    const whales = d.whale || [];
    const avgWhale = whales.length
      ? whales.reduce((s, w) => s + (w.whale_power || 0), 0) / whales.length : 0;
    // Buy/sell pressure from average order-book imbalance (OBI in [-1,1])
    const obis = whales.map((w) => (w.obi && typeof w.obi.obi === "number") ? w.obi.obi : 0);
    const avgObi = obis.length ? obis.reduce((s, v) => s + v, 0) / obis.length : 0;
    const buyP = Math.round((avgObi + 1) / 2 * 100);
    const sellP = 100 - buyP;

    setGauge("sn-whale", Math.round(avgWhale), "blue");
    setGauge("sn-buy", buyP, "green");
    setGauge("sn-sell", sellP, "red");
    set("sn-sentiment", (d.btc && d.btc.sentiment) || "—");
    set("sn-regime", d.market_regime || "—");

    const sorted = [...whales].sort((a, b) => (b.whale_power || 0) - (a.whale_power || 0)).slice(0, 6);
    if (!sorted.length) { html("sn-wallets", '<div class="dim center">No whale activity yet</div>'); return; }
    html("sn-wallets", sorted.map((w) => {
      const power = (w.whale_power || 0).toFixed(0);
      const col = (w.whale_power || 0) >= 70 ? "up" : (w.whale_power || 0) >= 40 ? "gold" : "muted";
      return '<div class="wallet">' +
        '<span class="w-sym">' + esc(sym(w.symbol)) + '</span>' +
        '<span class="' + col + '">' + power + '% power</span>' +
        '<span class="w-tag">' + esc(w.label || "WALL") + '</span></div>';
    }).join(""));
  }

  function setGauge(prefix, pct, color) {
    pct = Math.max(0, Math.min(100, pct || 0));
    const fill = $(prefix + "-gauge");
    if (fill) { fill.className = "gauge-fill " + color; fill.style.width = pct + "%"; }
    set(prefix + "-val", pct + "%");
  }

  /* ===========================================================================
     INSTITUTIONAL & WALL SCANNER
     =========================================================================== */
  function renderInst(d) {
    const rows = (d.inst_signals || []).slice(0, (CFG.layout && CFG.layout.tableMaxRows) || 25);
    set("inst-count", (d.inst_signals || []).length + " signals");
    if (!rows.length) {
      html("inst-body", '<tr class="empty-row"><td colspan="11">Computing institutional signals…</td></tr>');
      return;
    }
    html("inst-body", rows.map((c, i) => {
      const inst = c.inst || {};
      const z = c.tp_zones || {};
      const tr = ({ GREEN: "GREEN", YELLOW: "YELLOW", RED: "RED" }[inst.traffic]) || "RED";
      return "<tr>" +
        "<td class='dim'>" + (i + 1) + "</td>" +
        "<td class='sym'>" + esc(sym(c.symbol)) + "</td>" +
        "<td><span class='pill'>" + esc(c.folder || "—") + "</span></td>" +
        "<td><span class='tl " + tr + "'></span></td>" +
        "<td>" + (typeof inst.inst_score === "number" ? inst.inst_score.toFixed(1) : "—") + "</td>" +
        "<td>" + (c.confidence != null ? c.confidence + "%" : "—") + "</td>" +
        "<td>" + (typeof inst.whale_power === "number" ? inst.whale_power.toFixed(0) + "%" : "—") + "</td>" +
        "<td class='" + cls(c.change_pct) + "'>" + fmtPct(c.change_pct, true) + "</td>" +
        "<td>" + fmtPrice(c.price) + "</td>" +
        "<td class='down'>" + (z.stop_loss ? fmtPrice(z.stop_loss) : "—") + "</td>" +
        "<td class='up'>" + (z.tp1 ? fmtPrice(z.tp1) : "—") + "</td>" +
        "</tr>";
    }).join(""));
  }

  /* ===========================================================================
     SMART MONEY DIVERGENCE
     =========================================================================== */
  function renderSmart(d) {
    const sm = d.smart_divergence || [];
    const surge = d.volume_surge || [];
    set("smart-count", sm.length + " signals");
    let out = sm.map((s) => {
      const acc = /ACCUM/i.test(s.signal || "");
      return '<div class="sm-item ' + (acc ? "acc" : "dist") + '">' +
        '<span class="sym">' + esc(sym(s.symbol)) + '</span>' +
        '<span class="sm-sig ' + (acc ? "up" : "down") + '">' + esc(s.signal || "—") + '</span>' +
        '<span class="muted">OBI ' + (typeof s.obi === "number" ? s.obi.toFixed(3) : "—") + '</span>' +
        '<span class="' + cls(s.change_pct) + '">' + fmtPct(s.change_pct, true) + '</span></div>';
    }).join("");
    if (!sm.length) out = '<div class="dim center">No divergence signals detected</div>';
    html("smart-body", out);

    set("vol-surge", surge.length ? surge.map((v) => sym(v.symbol)).join(", ") : "None");
  }

  /* ===========================================================================
     WATCH CARDS (HIFI / DOGE style)
     =========================================================================== */
  function findCoin(d, symbol) {
    const all = [];
    Object.values(d.vmc || {}).forEach((arr) => (arr || []).forEach((c) => all.push(c)));
    let m = (d.inst_signals || []).find((c) => c.symbol === symbol);
    if (m) return m;
    return all.find((c) => c.symbol === symbol) || null;
  }

  function renderWatch(d) {
    const cards = (CFG.watchCards || []);
    html("watch-grid", cards.map((card) => {
      const c = findCoin(d, card.symbol);
      if (!c) {
        return '<div class="watch"><div class="watch-top"><span class="watch-sym">' +
          esc(card.title) + '</span><span class="dim">no data</span></div>' +
          '<div class="dim">Not in current scan universe.</div></div>';
      }
      const z = c.tp_zones || {};
      const entry = z.entry_low || c.price || 0;
      const expPct = z.tp1 && entry ? ((z.tp1 - entry) / entry * 100) : null;
      const riskPct = z.stop_loss && entry ? ((entry - z.stop_loss) / entry * 100) : null;
      const rr = expPct && riskPct && riskPct > 0 ? (expPct / riskPct).toFixed(1) : null;
      const inst = c.inst || {};
      return '<div class="watch">' +
        '<div class="watch-top"><span class="watch-sym">' + esc(card.title) + '</span>' +
        '<span class="watch-px">$ ' + fmtPrice(c.price) + '</span></div>' +
        '<div class="watch-row"><span class="muted">24h Change</span><span class="' + cls(c.change_pct) + '">' + fmtPct(c.change_pct, true) + '</span></div>' +
        '<div class="watch-row"><span class="muted">Expected → TP1</span><span class="up">' + (expPct != null ? "+" + expPct.toFixed(1) + "%" : "—") + '</span></div>' +
        '<div class="watch-row"><span class="muted">Risk / Reward</span><span class="gold">' + (rr ? "1 : " + rr : "—") + '</span></div>' +
        '<div class="watch-row"><span class="muted">Whale Power</span><span>' + (typeof inst.whale_power === "number" ? inst.whale_power.toFixed(0) + "%" : "—") + '</span></div>' +
        '<div class="watch-row"><span class="muted">Strategy</span><span class="blue">' + esc(c.trading_strategy || "—") + '</span></div>' +
        '</div>';
    }).join(""));
  }

  /* ===========================================================================
     BACKTESTING
     =========================================================================== */
  function renderBacktest(d) {
    const bt = d.backtest || [];
    const wins = d.total_wins || 0, losses = d.total_losses || 0;
    set("bt-wins", wins);
    set("bt-losses", losses);
    set("bt-total", wins + losses);
    set("bt-winrate", (typeof d.win_rate === "number" ? d.win_rate.toFixed(1) : "0.0") + "%");
    if (!bt.length) {
      html("bt-body", '<tr class="empty-row"><td colspan="6">No resolved backtest trades yet</td></tr>');
      return;
    }
    html("bt-body", bt.slice(0, (CFG.layout && CFG.layout.tableMaxRows) || 25).map((b) => {
      const win = /WIN/i.test(b.result || b.outcome || "");
      return "<tr>" +
        "<td class='sym'>" + esc(sym(b.symbol)) + "</td>" +
        "<td>" + esc(b.entry || b.entry_price || "—") + "</td>" +
        "<td>" + esc(b.exit || b.exit_price || "—") + "</td>" +
        "<td class='" + (win ? "up" : "down") + "'>" + esc(b.result || b.outcome || "—") + "</td>" +
        "<td class='" + cls(b.pnl_pct) + "'>" + (typeof b.pnl_pct === "number" ? fmtPct(b.pnl_pct, true) : "—") + "</td>" +
        "<td class='dim'>" + esc(b.time || b.closed || "—") + "</td>" +
        "</tr>";
    }).join(""));
  }

  /* ===========================================================================
     ALERT HISTORY
     =========================================================================== */
  function renderHistory(d) {
    const h = d.alert_history || [];
    set("hist-count", h.length + " alerts");
    if (!h.length) {
      html("hist-body", '<tr class="empty-row"><td colspan="6">No alerts yet</td></tr>');
      return;
    }
    html("hist-body", [...h].reverse().slice(0, (CFG.layout && CFG.layout.tableMaxRows) || 25).map((a) => {
      return "<tr>" +
        "<td class='dim'>" + esc(a.time || "—") + "</td>" +
        "<td><span class='pill'>" + esc(a.type || "—") + "</span></td>" +
        "<td class='sym'>" + esc(sym(a.symbol)) + "</td>" +
        "<td class='gold'>" + esc(a.label || "—") + "</td>" +
        "<td>" + fmtPrice(a.price) + "</td>" +
        "<td class='dim'>" + esc(a.detail || "") + "</td>" +
        "</tr>";
    }).join(""));
  }

  /* ===========================================================================
     CLIENTS (config-driven)
     =========================================================================== */
  function renderClients() {
    const clients = CFG.clients || [];
    if (!clients.length) {
      html("client-body", '<tr class="empty-row"><td colspan="4">No clients configured</td></tr>');
      return;
    }
    html("client-body", clients.map((c) => {
      return "<tr>" +
        "<td class='sym'>" + esc(c.name) + "</td>" +
        "<td>" + esc(c.api) + "</td>" +
        "<td>" + esc(c.exchange) + "</td>" +
        "<td class='up'>" + esc(c.status) + "</td>" +
        "</tr>";
    }).join(""));
  }

  /* ===========================================================================
     SEARCH (switch coin profile)
     =========================================================================== */
  function buildSearchPool() {
    if (!DATA) return [];
    const seen = new Set(), pool = [];
    Object.entries(DATA.vmc || {}).forEach(([folder, coins]) => {
      (coins || []).forEach((c) => { if (!seen.has(c.symbol)) { seen.add(c.symbol); pool.push({ ...c, folder }); } });
    });
    (DATA.inst_signals || []).forEach((c) => { if (!seen.has(c.symbol)) { seen.add(c.symbol); pool.push(c); } });
    return pool;
  }
  function onSearch(q) {
    const res = $("search-results");
    if (!res) return;
    const term = (q || "").trim().toUpperCase();
    if (!term) { res.className = "search-results"; return; }
    const hits = buildSearchPool().filter((c) =>
      (c.symbol || "").toUpperCase().includes(term)).slice(0, 8);
    if (!hits.length) { res.className = "search-results"; res.innerHTML = ""; return; }
    res.className = "search-results open";
    res.innerHTML = hits.map((c) =>
      '<div class="sr-item" data-sym="' + esc(c.symbol) + '">' +
      '<span class="sym">' + esc(sym(c.symbol)) + '</span>' +
      '<span class="muted">' + fmtPrice(c.price) + '</span>' +
      '<span class="sr-fld">' + esc(c.folder || "—") + '</span></div>').join("");
    Array.prototype.forEach.call(res.querySelectorAll(".sr-item"), (el) => {
      el.addEventListener("mousedown", () => {
        selectedSymbol = el.getAttribute("data-sym");
        res.className = "search-results";
        $("search-input").value = sym(selectedSymbol);
        if (DATA) { const p = pickProfile(DATA); renderProfile(DATA, p); renderTDE(DATA, p); }
      });
    });
  }

  /* ===========================================================================
     COUNTDOWN
     =========================================================================== */
  function tick() {
    countdown--;
    const el = $("st-countdown");
    if (el) { el.textContent = countdown + "s"; el.className = "v " + (countdown <= 5 ? "gold" : "muted"); }
    if (countdown <= 0) { countdown = REFRESH; fetchData(); }
  }

  /* ===========================================================================
     INIT
     =========================================================================== */
  function init() {
    if (CFG.layout && CFG.layout.maxWidthPx) {
      const wrap = document.querySelector(".wrap");
      if (wrap) wrap.style.maxWidth = CFG.layout.maxWidthPx + "px";
    }
    const sIn = $("search-input");
    if (sIn) {
      sIn.addEventListener("input", (e) => onSearch(e.target.value));
      sIn.addEventListener("blur", () => setTimeout(() => { const r = $("search-results"); if (r) r.className = "search-results"; }, 200));
    }
    const exec = $("btn-execute");
    if (exec) exec.addEventListener("click", () => {
      const mode = DATA && DATA.paper_mode === false ? "REAL" : "PAPER";
      alert("Entry conditions met (" + mode + " MODE).\nOrder placement is handled by the secured admin portal.");
    });
    const panic = $("btn-panic");
    if (panic) panic.addEventListener("click", () => {
      alert("PANIC requested — close all open positions via the secured admin portal.");
    });

    renderClients();
    set("st-countdown", countdown + "s");
    fetchData();
    setInterval(tick, 1000);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
