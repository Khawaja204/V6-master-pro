// V6 MASTER PRO — script.js
// Fetches /dashboard_data every 30s and updates all UI sections

let countdown = 30;
let countdownTimer = null;
let chart = null;
let candleSeries = null;

// ── INIT ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initChart();
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
    if (countdown <= 0) {
      countdown = 30;
      fetchAll();
    }
  }, 1000);
}

function fetchAll() {
  fetchDashboard();
  fetchChart();
}

// ── DASHBOARD DATA ────────────────────────────────────
function fetchDashboard() {
  fetch('/dashboard_data')
    .then(r => r.json())
    .then(d => {
      updateStatusBar(d);
      updateCoinProfile(d);
      updateTradeEngine(d);
      updateSentiment(d);
      updatePaperBanner(d);
      updateScannerTable(d);
      updateSmartMoney(d);
      updateWatchCards(d);
      updateAlertHistory(d);
      updateClientAPI(d);
      updateBacktest(d);
      updateVolumeSurge(d);
    })
    .catch(e => console.error('Dashboard fetch error:', e));
}

// ── CHART ─────────────────────────────────────────────
function initChart() {
  const container = document.getElementById('chart-container');
  if (!container || typeof LightweightCharts === 'undefined') return;

  chart = LightweightCharts.createChart(container, {
    width: container.clientWidth,
    height: 200,
    layout: { background: { color: '#060610' }, textColor: '#888' },
    grid: { vertLines: { color: '#111' }, horzLines: { color: '#111' } },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    rightPriceScale: { borderColor: '#1e2030' },
    timeScale: { borderColor: '#1e2030', timeVisible: true },
  });

  candleSeries = chart.addCandlestickSeries({
    upColor: '#00cc44',
    downColor: '#cc2200',
    borderUpColor: '#00cc44',
    borderDownColor: '#cc2200',
    wickUpColor: '#00cc44',
    wickDownColor: '#cc2200',
  });

  window.addEventListener('resize', () => {
    if (chart) chart.applyOptions({ width: container.clientWidth });
  });
}

function fetchChart() {
  const sym = document.getElementById('coin-search')?.value?.trim() || 'XPLUSDT';
  fetch(`/chart_data?symbol=${sym}&interval=15m&limit=60`)
    .then(r => r.json())
    .then(d => {
      if (!candleSeries || !d.candles) return;
      const candles = d.candles.map(c => ({
        time: c.time,
        open: parseFloat(c.open),
        high: parseFloat(c.high),
        low: parseFloat(c.low),
        close: parseFloat(c.close),
      }));
      candleSeries.setData(candles);
    })
    .catch(() => {});
}

// Search button
function doSearch() {
  fetchChart();
  fetchDashboard();
}

// ── STATUS BAR ────────────────────────────────────────
function updateStatusBar(d) {
  setText('sb-cycle', d.cycle || '—');
  setText('sb-regime', d.regime || '—');
  setText('sb-btcprice', d.btc_price ? '$' + fmt2(d.btc_price) : '—');
  setText('sb-rias', d.rtc_rias || '—');
  setText('sb-exchange', d.exchange || 'Binance');
  setText('sb-winrate', (d.win_rate || 0) + '%');

  const regEl = document.getElementById('sb-regime');
  if (regEl) {
    regEl.className = 'sb-value ' + (
      (d.regime || '').toLowerCase().includes('bear') ? 'sb-bearish' :
      (d.regime || '').toLowerCase().includes('bull') ? 'sb-live' : 'sb-volatile'
    );
  }
}

// ── COIN PROFILE ──────────────────────────────────────
function updateCoinProfile(d) {
  const cp = d.selected_coin || {};
  const sig = cp.signal || d.signal || 'AVOID';
  const badge = document.getElementById('profile-badge');
  if (badge) {
    badge.textContent = sig === 'BUY' ? 'BUY – ACCUMULATION' : 'AVOID – DUMP PREP';
    badge.className = sig === 'BUY' ? 'buy-badge' : 'avoid-badge';
  }

  setText('whale-bag', fmtNum(cp.whale_bag_size || 0));
  setText('vmc-score', fmt6(cp.vmc_score || 0));
  setText('buy-price-est', fmt6(cp.buy_price_est || 0));
  setText('sell-price-est', fmt6(cp.sell_price_est || 0));
  setText('buy-price-ext', fmt6(cp.buy_price_ext || 0));
  setText('sell-price-ext', fmt6(cp.sell_price_ext || 0));

  const trend = cp.trend || 'ACCUMULATION';
  const tEl = document.getElementById('coin-trend');
  if (tEl) {
    tEl.textContent = trend;
    tEl.className = 'dg-value ' + (trend === 'ACCUMULATION' ? 'green' : 'red');
  }
}

// ── TRADE DECISION ENGINE ─────────────────────────────
function updateTradeEngine(d) {
  const sig = d.signal || 'AVOID';
  const badge = document.getElementById('action-badge');
  if (badge) {
    badge.textContent = sig;
    badge.className = 'action-badge action-' + sig;
  }

  // Traffic light
  const dot = document.getElementById('traffic-dot');
  if (dot) {
    const tl = (d.traffic_light || 'red').toLowerCase();
    dot.className = 'traffic-dot ' + (
      tl === 'green' ? 'traffic-green' :
      tl === 'yellow' ? 'traffic-yellow' : 'traffic-red'
    );
  }

  setText('inst-score', d.institutional_score || d.score || '—');
  const trap = d.whale_trap;
  const trapEl = document.getElementById('whale-trap');
  if (trapEl) {
    trapEl.innerHTML = trap ? '⚠ YES' : '0&nbsp;&nbsp;NO';
    trapEl.style.color = trap ? '#ff8800' : '#888';
  }
  setText('atr-zones', d.atr_zones || 'Scoped');

  const warnBox = document.getElementById('warning-box');
  if (warnBox) {
    if (d.warning) {
      warnBox.style.display = 'block';
      warnBox.textContent = '⚠ ' + d.warning;
    } else {
      warnBox.style.display = 'none';
    }
  }

  setText('reason-text', d.reason || 'DUMP_PREPARATION → AVOID');
}

// ── SENTIMENT & WHALE ─────────────────────────────────
function updateSentiment(d) {
  const wp = d.whale_power || 0;
  drawGauge('gauge-whale', wp, wp > 60 ? '#00cc66' : wp > 30 ? '#ffd700' : '#ff3344');
  setText('gauge-whale-label', wp + '%');

  const bsp = d.buy_pressure || 0;
  const bspText = bsp > 50 ? 'YES' : 'NO';
  drawGauge('gauge-bsp', bsp, bsp > 50 ? '#00cc66' : '#ff3344');
  setText('gauge-bsp-label', bspText);

  const w1 = d.whale_wallet_1 || {};
  setText('w1-pattern', w1.pattern || '(Pattern)');
  setText('w1-cluster', w1.cluster_status || 'Stable');
  setText('w1-moves', (w1.moves || 0) + '%');

  const w2 = d.whale_wallet_2 || {};
  setText('w2-pattern', w2.pattern || 'Pattern tag');
  setText('w2-cluster', w2.cluster_status || 'Cluster');
  setText('w2-moves', (w2.moves || 0) + '%');
}

function drawGauge(svgId, pct, color) {
  const svg = document.getElementById(svgId);
  if (!svg) return;
  const r = 44, cx = 55, cy = 55;
  const circ = 2 * Math.PI * r;
  const dash = (pct / 100) * circ;
  svg.innerHTML = `
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#1a1a2e" stroke-width="8"/>
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${color}" stroke-width="8"
      stroke-dasharray="${dash} ${circ}" stroke-dashoffset="${circ * 0.25}"
      stroke-linecap="round" style="transition:stroke-dasharray 0.5s"/>
  `;
}

// ── PAPER MODE ────────────────────────────────────────
function updatePaperBanner(d) {
  const banner = document.getElementById('paper-strip');
  if (banner) banner.style.display = d.paper_mode ? 'block' : 'none';
}

// ── SCANNER TABLE ─────────────────────────────────────
function updateScannerTable(d) {
  const coins = d.scanner_coins || d.coins || [];
  const tbody = document.getElementById('scanner-tbody');
  if (!tbody) return;

  const meta = document.getElementById('scanner-meta');
  if (meta) meta.textContent = `${coins.length} unique coins | top conf: ${d.top_conf || 0}%`;

  tbody.innerHTML = coins.slice(0, 25).map((c, i) => {
    const tl = (c.traffic_light || 'red').toLowerCase();
    const tlDot = `<span class="traffic-dot ${tl === 'green' ? 'traffic-green' : tl === 'yellow' ? 'traffic-yellow' : 'traffic-red'}" style="width:8px;height:8px;display:inline-block;border-radius:50%;margin-right:2px;"></span>`;
    const folders = (c.folders || []).map(f => `<span class="folder-badge f-${f.toLowerCase()}">${f}</span>`).join('');
    const barColor = c.conf_pct > 60 ? '#00cc66' : c.conf_pct > 30 ? '#ffd700' : '#ff3344';
    const wpColor = c.whale_power > 60 ? '#00cc66' : c.whale_power > 30 ? '#ffd700' : '#ff3344';
    const act = (c.action || 'AVOID').toUpperCase();
    const rowClass = c.whale_power > 70 ? 'hot' : act === 'AVOID' ? 'avoid-row' : '';

    return `<tr class="${rowClass}">
      <td style="color:var(--grey)">#${i+1}</td>
      <td><span class="coin-circle" style="background:${coinColor(c.symbol)}"></span>${c.symbol?.replace('USDT','') || '—'}</td>
      <td>${folders}</td>
      <td>${tlDot}${tl[0].toUpperCase()}</td>
      <td>${fmt1(c.inst_score || 0)}</td>
      <td>${c.conf_pct || 0}%
        <div class="mini-bar-wrap"><div class="mini-bar" style="width:${c.conf_pct||0}%;background:${barColor}"></div></div>
      </td>
      <td><div class="mini-bar-wrap"><div class="mini-bar" style="width:${c.whale_power||0}%;background:${wpColor}"></div></div></td>
      <td style="color:var(--grey)">${c.ofi ? fmt2(c.ofi) : '—'}</td>
      <td style="color:var(--red)">▼${fmt6(c.sl || 0)}</td>
      <td style="color:var(--green)">▲${fmt6(c.tp1 || 0)}</td>
      <td style="color:var(--green)">▲${fmt6(c.tp2 || 0)}</td>
      <td style="color:var(--green)">${c.tp3 ? '▲'+fmt6(c.tp3) : '—'}</td>
      <td><span class="action-tag at-${act.toLowerCase()}">${act}</span></td>
    </tr>`;
  }).join('');
}

// ── SMART MONEY DIVERGENCE ────────────────────────────
function updateSmartMoney(d) {
  const smd = d.smart_money || {};
  drawSMDGauge('smd-gauge', smd.score || 50);

  // Volume surge list
  const surges = d.volume_surges || [];
  const vsEl = document.getElementById('vol-surge-list');
  if (vsEl) {
    vsEl.innerHTML = surges.slice(0, 10).map(s =>
      `<div class="vol-item">
        <span class="vol-coin">${s.symbol?.replace('USDT','')}</span>
        <span class="vol-mult">🚀 ${fmt1(s.multiplier)}x</span>
        <span class="vol-amount">Vol: ${fmtVol(s.volume)}</span>
      </div>`
    ).join('') || '<div style="color:var(--grey);font-size:9px;padding:4px">No surges detected</div>';
  }
}

function drawSMDGauge(svgId, score) {
  const svg = document.getElementById(svgId);
  if (!svg) return;
  const angle = -90 + (score / 100) * 180;
  const rad = angle * Math.PI / 180;
  const cx = 70, cy = 65, r = 50;
  const nx = cx + r * Math.cos(rad);
  const ny = cy + r * Math.sin(rad);
  svg.innerHTML = `
    <defs>
      <linearGradient id="smd-grad" x1="0%" y1="0%" x2="100%" y2="0%">
        <stop offset="0%" style="stop-color:#cc0000"/>
        <stop offset="50%" style="stop-color:#ffd700"/>
        <stop offset="100%" style="stop-color:#00cc44"/>
      </linearGradient>
    </defs>
    <path d="M${cx-r},${cy} A${r},${r} 0 0,1 ${cx+r},${cy}" 
      fill="none" stroke="url(#smd-grad)" stroke-width="8" stroke-linecap="round"/>
    <line x1="${cx}" y1="${cy}" x2="${nx}" y2="${ny}" 
      stroke="#fff" stroke-width="2" stroke-linecap="round"/>
    <circle cx="${cx}" cy="${cy}" r="4" fill="#fff"/>
  `;
}

// ── WATCH CARDS ───────────────────────────────────────
function updateWatchCards(d) {
  const cards = d.watch_cards || [];
  cards.forEach((c, i) => {
    const n = i + 1;
    setText(`wc${n}-coin`, c.pair || '—');
    setText(`wc${n}-profit`, (c.expected_profit > 0 ? '+' : '') + fmt2(c.expected_profit || 0) + '%');
    setText(`wc${n}-rr`, fmt2(c.rr_ratio || 0));
    setText(`wc${n}-mode`, c.mode || 'GRID');
    const pEl = document.getElementById(`wc${n}-profit`);
    if (pEl) pEl.className = 'watch-value ' + (c.expected_profit > 0 ? 'pos' : 'red');
  });
}

// ── ALERT HISTORY ─────────────────────────────────────
function updateAlertHistory(d) {
  const alerts = d.alerts || d.alert_history || [];
  const el = document.getElementById('alert-list');
  if (!el) return;
  el.innerHTML = alerts.slice(0, 5).map(a =>
    `<div class="alert-item"><span>${a.emoji || '🟢'}</span> ${a.coin || ''} ${a.type || ''} → ${a.message || ''}</div>`
  ).join('') || '<div class="alert-item" style="color:var(--grey)">No alerts yet</div>';
}

// ── BACKTEST ──────────────────────────────────────────
function updateBacktest(d) {
  const bt = d.backtests || [];
  const tbody = document.getElementById('bt-tbody');
  if (!tbody) return;
  tbody.innerHTML = bt.slice(0, 8).map(b =>
    `<tr>
      <td>${fmt6(b.entry || 0)}</td>
      <td>${fmt6(b.tp_hit || 0)}</td>
      <td style="color:${b.win ? 'var(--green)' : 'var(--red)'}">${b.win ? 'W' : 'L'}</td>
    </tr>`
  ).join('') || '<tr><td colspan="3" style="color:var(--grey);text-align:center">No data</td></tr>';
}

// ── CLIENT & API ──────────────────────────────────────
function updateClientAPI(d) {
  const clients = d.clients || [];
  const tbody = document.getElementById('ca-tbody');
  if (!tbody) return;

  tbody.innerHTML = clients.map(c => {
    const syncStatus = c.synced
      ? `<span class="ca-synced">Synced ${c.sync_time || ''} ✓</span>`
      : c.syncing
      ? `<span class="ca-syncing">⟳ Syncing...</span>`
      : `<span class="ca-failed">Sync Failed ✗</span>`;
    return `<tr>
      <td>🔸 ${c.pair || '—'}</td>
      <td class="ca-connected">${c.connected ? 'Connected APIs' : 'Disconnected'}</td>
      <td>${c.client_name || '—'}</td>
      <td>${syncStatus}</td>
    </tr>`;
  }).join('');

  const tg = d.telegram || {};
  const tgRow = document.getElementById('tg-row');
  if (tgRow) {
    tgRow.cells[0].textContent = 'Telegram Proxy: ' + (tg.proxy_active ? 'ACTIVE (Pakistan)' : 'INACTIVE');
    tgRow.cells[3].innerHTML = tg.synced
      ? `<span class="ca-synced">Sync... ${tg.sync_time || ''}</span>`
      : `<span class="ca-failed">Offline</span>`;
  }
}

// ── VOLUME SURGE ──────────────────────────────────────
function updateVolumeSurge(d) {
  // Already handled inside updateSmartMoney
}

// ── HELPERS ───────────────────────────────────────────
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}
function fmt6(n) {
  const f = parseFloat(n);
  if (isNaN(f)) return '—';
  return f < 1 ? f.toFixed(6) : f.toFixed(2);
}
function fmt2(n) { return parseFloat(n || 0).toFixed(2); }
function fmt1(n) { return parseFloat(n || 0).toFixed(1); }
function fmtNum(n) {
  if (n >= 1e9) return (n/1e9).toFixed(1)+'B';
  if (n >= 1e6) return (n/1e6).toFixed(1)+'M';
  if (n >= 1e3) return (n/1e3).toFixed(1)+'K';
  return n;
}
function fmtVol(n) {
  if (n >= 1e9) return (n/1e9).toFixed(1)+'B USDT';
  if (n >= 1e6) return (n/1e6).toFixed(1)+'M USDT';
  return n + ' USDT';
}

const COIN_COLORS = {
  BTC:'#f7931a', ETH:'#627eea', BNB:'#f3ba2f', SOL:'#9945ff',
  XRP:'#00aae4', ADA:'#0033ad', DOGE:'#c3a634', AVAX:'#e84142',
  USDT:'#26a17b', DEFAULT:'#4488cc'
};
function coinColor(sym) {
  const s = (sym||'').replace('USDT','');
  return COIN_COLORS[s] || COIN_COLORS.DEFAULT;
}
