// V6 MASTER PRO — script.js (FIELD-MATCHED)
let countdown = 30;
let countdownTimer = null;
let chart = null;
let candleSeries = null;
let lastSignals = [];

document.addEventListener('DOMContentLoaded', () => {
  try { initChart(); } catch (e) { console.error('initChart failed:', e); }
  fetchAll();
  startCountdown();
});

function startCountdown() {
  countdown = 30;
  if (countdownTimer) clearInterval(countdownTimer);
  countdownTimer = setInterval(() => {
    countdown--;
    const el = document.getElementById('next-count');
    if (el) el.textContent = countdown;
    if (countdown <= 0) { countdown = 30; fetchAll(); }
  }, 1000);
}

function fetchAll() {
  fetch('/dashboard_data')
    .then(r => r.json())
    .then(d => {
      console.log("inst_signals count:", (d.inst_signals || []).length);
      lastSignals = d.inst_signals || [];
      updateStatusBar(d);
      updateCoinProfile(d);
      updateTradeEngine(d);
      updateSentiment(d);
      updatePaperBanner(d);
      updateScannerTable(d);
      updateSmartMoney(d);
      updateAlertHistory(d);
      updateBacktest(d);
      updateClientAPI(d);
    })
    .catch(e => console.error('Fetch error:', e));
  fetchChart();
}

// ── CHART ──
function initChart() {
  const container = document.getElementById('chart-container');
  if (!container || typeof LightweightCharts === 'undefined') return;
  chart = LightweightCharts.createChart(container, {
    width: container.clientWidth,
    height: 200,
    layout: { background: { color: '#060610' }, textColor: '#888' },
    grid: { vertLines: { color: '#111' }, horzLines: { color: '#111' } },
    rightPriceScale: { borderColor: '#1e2030' },
    timeScale: { borderColor: '#1e2030', timeVisible: true },
  });
  candleSeries = chart.addCandlestickSeries({
    upColor: '#00cc44', downColor: '#cc2200',
    borderUpColor: '#00cc44', borderDownColor: '#cc2200',
    wickUpColor: '#00cc44', wickDownColor: '#cc2200',
  });
  window.addEventListener('resize', () => {
    if (chart) chart.applyOptions({ width: container.clientWidth });
  });
}

function fetchChart() {
  const raw = document.getElementById('coin-search')?.value?.trim() || 'XPLUSDT';
  const clean = raw.toUpperCase().replace(/[^A-Z0-9]/g, '');
  const sym = clean.endsWith('USDT') ? clean : clean + 'USDT';
  fetch(`/chart_data?symbol=${sym}&interval=15m&limit=60`)
    .then(r => r.json())
    .then(d => {
      if (!candleSeries || !d.candles) return;
      const candles = d.candles.map(c => ({
        time: c.time, open: parseFloat(c.open),
        high: parseFloat(c.high), low: parseFloat(c.low), close: parseFloat(c.close),
      }));
      candleSeries.setData(candles);
      updateChartMarkers(sym, candles);
    }).catch(() => {});
}

// ── CHART BUY/SELL MARKERS ──
function updateChartMarkers(sym, candles) {
  if (!candleSeries || !candles.length) return;
  const t = candles[candles.length - 1].time;
  const markers = [];
  const symU = String(sym).toUpperCase();
  lastSignals.forEach(s => {
    if (String(s.symbol || '').toUpperCase() !== symU) return;
    const label = ((s.v6 && s.v6.label) || '').toUpperCase();
    if (label === 'BUY') {
      markers.push({ time: t, position: 'belowBar', color: '#00cc66', shape: 'arrowUp', text: 'BUY' });
    } else if (label === 'SELL' || label === 'AVOID') {
      markers.push({ time: t, position: 'aboveBar', color: '#ff3344', shape: 'arrowDown', text: label });
    }
  });
  try { candleSeries.setMarkers(markers); } catch (e) { console.error('setMarkers failed:', e); }
}

function doSearch() { fetchChart(); fetchAll(); }

// ── STATUS BAR ──
function updateStatusBar(d) {
  const btc = d.btc || {};
  setText('sb-cycle', d.cycle_count || '—');
  setText('sb-regime', d.market_regime || btc.regime || '—');
  setText('sb-btcprice', btc.price ? '$' + parseFloat(btc.price).toFixed(2) : '—');
  setText('sb-rias', btc.sentiment || d.status || '—');
  setText('sb-exchange', d.active_exchange || 'Binance');

  const regEl = document.getElementById('sb-regime');
  if (regEl) {
    const r = (d.market_regime || '').toLowerCase();
    regEl.className = 'sb-value ' + (r.includes('bear') ? 'sb-bearish' : r.includes('bull') ? 'sb-live' : 'sb-volatile');
  }
}

// ── COIN PROFILE ──
function updateCoinProfile(d) {
  const signals = d.inst_signals || [];
  const top = signals[0] || {};
  const inst = top.inst || {};
  const tp = top.tp_zones || {};
  const v6 = top.v6 || {};
  const sig = (v6.label || 'AVOID').toUpperCase();

  const badge = document.getElementById('profile-badge');
  if (badge) {
    if (sig === 'BUY') {
      badge.textContent = 'BUY – ACCUMULATION';
      badge.className = 'buy-badge ml-auto';
    } else if (sig === 'WAIT') {
      badge.textContent = 'WAIT – MONITOR';
      badge.className = 'avoid-badge ml-auto';
    } else {
      badge.textContent = 'AVOID – DUMP PREP';
      badge.className = 'avoid-badge ml-auto';
    }
  }

  setText('whale-bag', fmtNum(inst.whale_power || 0));
  setText('vmc-score', inst.vmc_score != null ? inst.vmc_score : '—');
  setText('buy-price-est', fmt6(tp.entry_low || top.price || 0));
  setText('sell-price-est', fmt6(tp.tp1 || 0));
  setText('buy-price-ext', fmt6(tp.entry_low || 0));
  setText('sell-price-ext', fmt6(tp.tp2 || 0));

  const csig = document.getElementById('chart-signal');
  const csigT = document.getElementById('chart-signal-text');
  if (csig && csigT) {
    let txt, bg, icon;
    if (sig === 'BUY') { txt = 'BUY'; bg = 'rgba(0,204,102,.92)'; icon = 'fa-circle-arrow-up'; }
    else if (sig === 'WAIT' || sig === 'HOLD') { txt = 'HOLD'; bg = 'rgba(255,213,0,.92)'; icon = 'fa-circle-pause'; }
    else if (sig === 'SELL') { txt = 'SELL'; bg = 'rgba(255,51,68,.92)'; icon = 'fa-circle-arrow-down'; }
    else { txt = 'AVOID'; bg = 'rgba(255,59,48,.92)'; icon = 'fa-circle-arrow-down'; }
    csigT.textContent = txt;
    csig.style.background = bg;
    csig.style.color = (txt === 'HOLD') ? '#1a1300' : '#fff';
    const ic = csig.querySelector('i');
    if (ic) ic.className = 'fa-solid ' + icon;
  }

  const trend = sig === 'BUY' ? 'ACCUMULATION' : sig === 'WAIT' ? 'NEUTRAL' : 'DISTRIBUTION';
  const tEl = document.getElementById('coin-trend');
  if (tEl) {
    tEl.textContent = trend;
    tEl.className = 'dg-value ' + (trend === 'ACCUMULATION' ? 'green' : trend === 'NEUTRAL' ? 'orange' : 'red');
  }
}

// ── TRADE DECISION ENGINE ──
function updateTradeEngine(d) {
  const signals = d.inst_signals || [];
  const top = signals[0] || {};
  const inst = top.inst || {};
  const v6 = top.v6 || {};
  const sig = (v6.label || 'AVOID').toUpperCase();
  const score = v6.score != null ? v6.score : (inst.inst_score || 0);

  const badge = document.getElementById('action-badge');
  if (badge) {
    badge.textContent = sig;
    badge.className = 'action-badge action-' + sig;
  }

  const tl = (inst.traffic || 'red').toLowerCase();
  const dot = document.getElementById('traffic-dot');
  if (dot) dot.className = 'traffic-dot ' + (tl === 'green' ? 'traffic-green' : tl === 'yellow' ? 'traffic-yellow' : 'traffic-red');

  setText('inst-score', inst.inst_score != null ? Math.round(inst.inst_score) : '—');

  const trap = top.whale_trap || false;
  const trapEl = document.getElementById('whale-trap');
  if (trapEl) {
    trapEl.innerHTML = trap ? '⚠ YES' : '0&nbsp;&nbsp;NO';
    trapEl.style.color = trap ? '#ff8800' : '#888';
  }
  setText('atr-zones', top.atr_zones || 'Scoped');

  const warnBox = document.getElementById('warning-box');
  if (warnBox) {
    if (inst.reason) {
      warnBox.style.display = 'block';
      warnBox.textContent = '⚠ ' + inst.reason + '  (' + sig + ' · score ' + Math.round(score) + ')';
    } else { warnBox.style.display = 'none'; }
  }
  setText('reason-text', inst.reason ? inst.reason + ' → ' + sig : sig);
}

// ── SENTIMENT ──
function updateSentiment(d) {
  const whale = d.whale || {};
  const wp = parseFloat(whale.avg_power || whale.power || 0);
  drawGauge('gauge-whale', wp, wp > 60 ? '#00cc66' : wp > 30 ? '#ffd700' : '#ff3344');
  setText('gauge-whale-label', Math.round(wp) + '%');

  const bp = parseFloat(whale.buy_pressure || 0);
  drawGauge('gauge-bsp', bp, bp > 50 ? '#00cc66' : '#ff3344');
  setText('gauge-bsp-label', bp > 50 ? 'YES' : 'NO');

  const wallets = whale.top_wallets || whale.wallets || [];
  const w1 = wallets[0] || {};
  const w2 = wallets[1] || {};
  setText('w1-pattern', w1.pattern || w1.label || '(Pattern)');
  setText('w1-cluster', w1.cluster_status || w1.cluster || 'Stable');
  setText('w1-moves', (w1.moves || w1.power || 0) + '%');
  setText('w2-pattern', w2.pattern || w2.label || 'Pattern tag');
  setText('w2-cluster', w2.cluster_status || w2.cluster || 'Cluster');
  setText('w2-moves', (w2.moves || w2.power || 0) + '%');
}

function drawGauge(svgId, pct, color) {
  const svg = document.getElementById(svgId);
  if (!svg) return;
  const r = 44, cx = 55, cy = 55, circ = 2 * Math.PI * r;
  const dash = (Math.min(pct,100) / 100) * circ;
  svg.innerHTML = `
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#1a1a2e" stroke-width="8"/>
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${color}" stroke-width="8"
      stroke-dasharray="${dash} ${circ}" stroke-dashoffset="${circ*0.25}"
      stroke-linecap="round" style="transition:stroke-dasharray 0.5s"/>`;
}

// ── PAPER MODE ──
function updatePaperBanner(d) {
  const b = document.getElementById('paper-strip');
  if (b) b.style.display = d.paper_mode ? 'block' : 'none';
}

// ── SCANNER TABLE ──
function updateScannerTable(d) {
  const coins = d.inst_signals || [];
  const tbody = document.getElementById('scanner-tbody');
  if (!tbody) return;

  const meta = document.getElementById('scanner-meta');
  if (meta) {
    const topConf = coins[0] ? Math.round(coins[0].confidence || 0) : 0;
    meta.textContent = `${coins.length} unique coins | top conf: ${topConf}%`;
  }

  if (!coins.length) {
    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--grey);padding:16px">Waiting for scanner data...</td></tr>';
    return;
  }

  tbody.innerHTML = coins.slice(0, 25).map((c) => {
    const inst = c.inst || {};
    const tp = c.tp_zones || {};
    const v6 = c.v6 || {};
    const tl = (inst.traffic || 'red').toLowerCase();
    const tlDot = `<span class="tl-sq ${tl==='green'?'traffic-green':tl==='yellow'?'traffic-yellow':'traffic-red'}"></span>`;
    const instScore = parseFloat(inst.inst_score || 0);
    const conf = parseFloat(c.confidence || 0);
    const wp   = parseFloat(inst.whale_power || 0);
    const barColor = conf > 60 ? '#00cc66' : conf > 30 ? '#ffd700' : '#ff3344';
    const wpColor  = wp > 60 ? '#00cc66' : wp > 30 ? '#ffd700' : '#ff3344';
    const act = (v6.label || 'WAIT').toUpperCase();
    const strat = (c.trading_strategy || 'SPOT').toUpperCase().includes('GRID') ? 'GRID' : 'SPOT';
    const sym = (c.symbol || '').replace('USDT','');
    const rowClass = wp > 70 ? 'hot' : (act === 'AVOID' || act === 'SELL') ? 'avoid-row' : '';

    return `<tr class="${rowClass}">
      <td><span class="coin-circle" style="background:${coinColor(sym)}"></span>${sym}</td>
      <td>${tlDot}${instScore.toFixed(1)}</td>
      <td>${conf.toFixed(0)}%<div class="mini-bar-wrap"><div class="mini-bar" style="width:${Math.min(conf,100)}%;background:${barColor}"></div></div></td>
      <td><div class="mini-bar-wrap"><div class="mini-bar" style="width:${Math.min(wp,100)}%;background:${wpColor}"></div></div></td>
      <td style="color:var(--red)">▼${fmt6(tp.stop_loss||0)}</td>
      <td style="color:var(--green)">▲${fmt6(tp.tp1||0)}</td>
      <td style="color:var(--green)">▲${fmt6(tp.tp2||0)}</td>
      <td style="color:var(--green)">${tp.tp3?'▲'+fmt6(tp.tp3):'—'}</td>
      <td><span class="strat-badge">${strat}</span> <span class="action-badge action-${act}">${act}</span></td>
    </tr>`;
  }).join('');
}

// ── SMART MONEY ──
function updateSmartMoney(d) {
  const smd = d.smart_divergence || {};
  const score = parseFloat(smd.score || 50);
  drawSMDGauge('smd-gauge', score);
  drawSMDGauge('smd-gauge-2', score);

  const surges = d.volume_surge || [];
  const vsEl = document.getElementById('vol-surge-list');
  if (vsEl) {
    vsEl.innerHTML = surges.slice(0,10).map(s =>
      `<div class="vol-item">
        <span class="vol-coin">${(s.symbol||'').replace('USDT','')}</span>
        <span class="vol-mult">🚀 ${parseFloat(s.multiplier||s.ratio||1).toFixed(1)}x</span>
        <span class="vol-amount">${fmtVol(s.volume||s.vol||0)}</span>
      </div>`
    ).join('') || '<div style="color:var(--grey);font-size:9px;padding:4px">No surges</div>';
  }
}

function drawSMDGauge(svgId, score) {
  const svg = document.getElementById(svgId);
  if (!svg) return;
  const angle = -90 + (score/100)*180;
  const rad = angle * Math.PI/180;
  const cx=70, cy=65, r=50;
  const nx = cx + r*Math.cos(rad), ny = cy + r*Math.sin(rad);
  svg.innerHTML = `
    <defs><linearGradient id="sg" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" style="stop-color:#cc0000"/>
      <stop offset="50%" style="stop-color:#ffd700"/>
      <stop offset="100%" style="stop-color:#00cc44"/>
    </linearGradient></defs>
    <path d="M${cx-r},${cy} A${r},${r} 0 0,1 ${cx+r},${cy}" fill="none" stroke="url(#sg)" stroke-width="8" stroke-linecap="round"/>
    <line x1="${cx}" y1="${cy}" x2="${nx}" y2="${ny}" stroke="#fff" stroke-width="2" stroke-linecap="round"/>
    <circle cx="${cx}" cy="${cy}" r="4" fill="#fff"/>`;
}

// ── ALERT HISTORY ──
function updateAlertHistory(d) {
  const alerts = d.alert_history || [];
  const el = document.getElementById('alert-list');
  if (!el) return;
  el.innerHTML = alerts.slice(0,5).map(a => {
    const emoji = a.type==='VIP' ? '🟢' : a.label?.includes('TRAP') ? '🔴' : '🐋';
    return `<div class="alert-item"><span>${emoji}</span> ${(a.symbol||'').replace('USDT','')} ${a.label||a.type||''} → ${a.detail||a.message||''}</div>`;
  }).join('') || '<div class="alert-item" style="color:var(--grey)">No alerts yet</div>';
}

// ── BACKTEST ──
function updateBacktest(d) {
  const bt = d.backtest || d.paper_trades || [];
  const tbody = document.getElementById('bt-tbody');
  if (!tbody) return;
  tbody.innerHTML = bt.slice(0,8).map(b =>
    `<tr>
      <td>${fmt6(b.entry||0)}</td>
      <td>${fmt6(b.tp_hit||b.exit||0)}</td>
      <td style="color:${b.win||b.result==='WIN'?'var(--green)':'var(--red)'}">${b.win||b.result==='WIN'?'W':'L'}</td>
    </tr>`
  ).join('') || '<tr><td colspan="3" style="color:var(--grey);text-align:center">No trades yet</td></tr>';
}

// ── CLIENT API ──
function updateClientAPI(d) {
  const now = new Date().toTimeString().slice(0,8);
  const tbody = document.getElementById('ca-tbody');
  if (tbody) {
    tbody.innerHTML = `
      <tr>
        <td>🔸 APA / USDT</td>
        <td class="ca-connected">Connected APIs</td>
        <td>binanc@Binance</td>
        <td class="ca-synced">Synced ${now} ✓</td>
      </tr>
      <tr>
        <td>🔸 XPL / USDT</td>
        <td class="ca-connected">Connected APIs</td>
        <td>masserjae</td>
        <td class="ca-synced">Synced ${now} ✓</td>
      </tr>`;
  }
  const tgRow = document.getElementById('tg-row');
  if (tgRow && tgRow.cells[3]) {
    tgRow.cells[3].innerHTML = `<span class="ca-synced">Sync... ${now}</span>`;
  }
}

// ── HELPERS ──
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}
function fmt6(n) {
  const f = parseFloat(n);
  if (isNaN(f) || f===0) return '—';
  return f < 1 ? f.toFixed(6) : f.toFixed(2);
}
function fmtNum(n) {
  n = parseFloat(n);
  if (n >= 1e9) return (n/1e9).toFixed(1)+'B';
  if (n >= 1e6) return (n/1e6).toFixed(1)+'M';
  if (n >= 1e3) return (n/1e3).toFixed(1)+'K';
  return n || '—';
}
function fmtVol(n) {
  n = parseFloat(n);
  if (n >= 1e9) return (n/1e9).toFixed(1)+'B USDT';
  if (n >= 1e6) return (n/1e6).toFixed(1)+'M USDT';
  if (n >= 1e3) return (n/1e3).toFixed(1)+'K USDT';
  return n + ' USDT';
}
const CC = {BTC:'#f7931a',ETH:'#627eea',BNB:'#f3ba2f',SOL:'#9945ff',
  XRP:'#00aae4',ADA:'#0033ad',DOGE:'#c3a634',AVAX:'#e84142',
  USDT:'#26a17b',DEFAULT:'#4488cc'};
function coinColor(s) { return CC[s] || CC.DEFAULT; }
