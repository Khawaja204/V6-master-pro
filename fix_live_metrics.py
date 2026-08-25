import sys, ast

# ══════════════════════════════════════════════════════════════
# Live Scalping Metrics + Candle Countdown + Flash Alerts
# Adds to the Command tab: Volume Surge status, Order Book
# Imbalance (bias), Open Interest 5-min change (Binance Futures,
# lightweight per-selected-coin fetch), a live 1m/5m candle-close
# countdown timer, and a flash-alert glow on the verdict box when
# a high-probability BUY setup triggers.
# ══════════════════════════════════════════════════════════════

# ── routes/api.py ──
API_PATH = 'routes/api.py'
with open(API_PATH, 'r', encoding='utf-8') as f:
    API_content = f.read()

API_EDITS = [
    (
        "_LOCAL_NAMES = {'chart_data', 'rsi_scan', 'get_data', 'status', 'whale_copy_data_route', 'live_score_route', 'large_trades_summary_route', 'api_wc_learning', 'dashboard_data', 'large_trades_data_route', 'sniper_data', 'focus_mode', 'health_check', 'focus_data', 'large_trades_list_route', 'combo_bot_data_route', 'v6_bot_data_route', 'whale_detail_route', 'api_onchain', 'eth_onchain_data_route', 'system_health', 'market_overview_route'}\n",
        "_LOCAL_NAMES = {'chart_data', 'rsi_scan', 'get_data', 'status', 'whale_copy_data_route', 'live_score_route', 'large_trades_summary_route', 'api_wc_learning', 'dashboard_data', 'large_trades_data_route', 'sniper_data', 'focus_mode', 'health_check', 'focus_data', 'large_trades_list_route', 'combo_bot_data_route', 'v6_bot_data_route', 'whale_detail_route', 'api_onchain', 'eth_onchain_data_route', 'system_health', 'market_overview_route', 'oi_data_route'}\n",
    ),
    (
        'def market_overview_route():\n    return jsonify(GLOBAL_DATA.get("market_overview", {}))\n',
        'def market_overview_route():\n    return jsonify(GLOBAL_DATA.get("market_overview", {}))\n\n\n@bp.route("/oi_data")\n@_sync_main_state\ndef oi_data_route():\n    """Lightweight Open Interest fetch for whichever coin the Command\n    Center currently has selected — Binance Futures\' public endpoint,\n    no API key needed, fetched on demand for just the one active symbol\n    (not every scanned coin) to stay cheap. Keeps a short in-memory\n    rolling history per symbol so a 5-minute % change can be reported\n    without needing a paid historical-OI data source."""\n    import requests as _rq\n    symbol = request.args.get("symbol", "").upper()\n    if not symbol:\n        return jsonify({"error": "symbol required"}), 400\n    try:\n        r = _rq.get("https://fapi.binance.com/fapi/v1/openInterest",\n                     params={"symbol": symbol}, timeout=8)\n        if r.status_code != 200:\n            return jsonify({"symbol": symbol, "available": False})\n        oi_now = float(r.json().get("openInterest", 0))\n    except Exception as e:\n        return jsonify({"symbol": symbol, "available": False, "error": str(e)})\n\n    hist = GLOBAL_DATA.setdefault("oi_history", {})\n    now = time.time()\n    entries = hist.setdefault(symbol, [])\n    entries.append({"t": now, "oi": oi_now})\n    entries[:] = [e for e in entries if now - e["t"] <= 1800]  # keep last 30 min\n    hist[symbol] = entries[-60:]\n\n    baseline = next((e for e in entries if now - e["t"] >= 280), entries[0])\n    change_pct = round((oi_now - baseline["oi"]) / baseline["oi"] * 100, 2) if baseline["oi"] else 0.0\n\n    return jsonify({\n        "symbol": symbol, "available": True,\n        "open_interest": oi_now,\n        "change_pct_5m": change_pct,\n    })\n',
    ),
]

if 'oi_data_route' in API_content:
    print('routes/api.py: already patched — skipping')
else:
    for i, (old, new) in enumerate(API_EDITS, 1):
        cnt = API_content.count(old)
        if cnt != 1:
            print(f'routes/api.py EDIT {i}: FAILED - expected 1 match, found {cnt}. Aborting, no changes written to this file.')
            sys.exit(1)
        API_content = API_content.replace(old, new, 1)
        print(f'routes/api.py EDIT {i}: applied OK')
    ast.parse(API_content)
    with open(API_PATH, 'w', encoding='utf-8') as f:
        f.write(API_content)
    print('routes/api.py: all edits applied OK')

# ── V6_Master_Pro_UI/index.html ──
HTML_PATH = 'V6_Master_Pro_UI/index.html'
with open(HTML_PATH, 'r', encoding='utf-8') as f:
    HTML_content = f.read()

HTML_EDITS = [
    (
        '.mo-value{font-size:14px;font-weight:bold;color:var(--white);margin-top:3px}\n.mo-sub{font-size:8px;color:var(--grey);margin-top:2px}\n',
        '.mo-value{font-size:14px;font-weight:bold;color:var(--white);margin-top:3px}\n.mo-sub{font-size:8px;color:var(--grey);margin-top:2px}\n\n/* COMMAND CENTER — high-probability setup flash alert */\n@keyframes cmdFlash{0%{box-shadow:0 0 0 rgba(0,255,136,0)}50%{box-shadow:0 0 22px rgba(0,255,136,0.85)}100%{box-shadow:0 0 0 rgba(0,255,136,0)}}\n.cmd-flash{animation:cmdFlash 1.1s ease-in-out 3}\n',
    ),
    (
        '    <div id="cmd-verdict-label" style="font-size:32px;font-weight:bold;color:var(--grey);letter-spacing:1px">—</div>\n    <div id="cmd-verdict-sub" style="font-size:12px;color:var(--grey);margin-top:4px">Score — / 100 &nbsp;|&nbsp; Confidence —%</div>\n',
        '    <div id="cmd-verdict-label" style="font-size:32px;font-weight:bold;color:var(--grey);letter-spacing:1px">—</div>\n    <div id="cmd-verdict-sub" style="font-size:12px;color:var(--grey);margin-top:4px">Score — / 100 &nbsp;|&nbsp; Confidence —%</div>\n  </div>\n\n  <!-- LIVE SCALPING METRICS -->\n  <div class="card" id="cmd-metrics-card" style="margin-bottom:8px">\n    <div class="ch" style="font-size:10px">📡 Live Scalping Metrics</div>\n    <div class="cb" style="display:grid;grid-template-columns:1fr 1fr;gap:8px">\n      <div>\n        <div style="font-size:8px;color:var(--grey)">VOLUME SURGE</div>\n        <div id="cmd-vol-surge" style="font-size:12px;font-weight:bold;margin-top:2px">—</div>\n      </div>\n      <div>\n        <div style="font-size:8px;color:var(--grey)">ORDER BOOK IMBALANCE</div>\n        <div id="cmd-obi" style="font-size:12px;font-weight:bold;margin-top:2px">—</div>\n      </div>\n      <div>\n        <div style="font-size:8px;color:var(--grey)">OPEN INTEREST (5m)</div>\n        <div id="cmd-oi" style="font-size:12px;font-weight:bold;margin-top:2px">—</div>\n      </div>\n      <div>\n        <div style="font-size:8px;color:var(--grey)">CANDLE CLOSES IN</div>\n        <div style="font-size:12px;font-weight:bold;margin-top:2px">\n          <span id="cmd-candle-1m" style="color:var(--gold)">—</span><span style="color:var(--grey);font-size:8px"> 1m</span>\n          &nbsp;·&nbsp;\n          <span id="cmd-candle-5m" style="color:var(--gold)">—</span><span style="color:var(--grey);font-size:8px"> 5m</span>\n        </div>\n      </div>\n    </div>\n',
    ),
    (
        '  fetchMarketOverview();\n  setInterval(fetchMarketOverview, 90000);\n',
        '  fetchMarketOverview();\n  setInterval(fetchMarketOverview, 90000);\n  startCandleCountdown();\n',
    ),
    (
        'window._cmdCandleSeries = null;\n\n',
        "window._cmdCandleSeries = null;\n\n/* ── Live Scalping Metrics: Volume Surge / OBI / Open Interest / Flash Alert ── */\nwindow._cmdOiFetchedFor = null;\nwindow._cmdLastFlashKey = null;\n\nfunction updateCmdMetrics(best, d, label, conf){\n  const surgeEl=document.getElementById('cmd-vol-surge');\n  const obiEl=document.getElementById('cmd-obi');\n  const oiEl=document.getElementById('cmd-oi');\n  const box=document.getElementById('cmd-verdict-box');\n  if(!surgeEl) return;\n\n  const inSurge = (d.volume_surge||[]).some(s=>s.symbol===best.symbol);\n  surgeEl.textContent = inSurge ? '🚀 ACTIVE' : 'No surge';\n  surgeEl.style.color = inSurge ? 'var(--green)' : 'var(--grey)';\n\n  const whaleMatch = (d.whale||[]).find(w=>w.symbol===best.symbol);\n  const obiVal = whaleMatch && whaleMatch.obi ? Number(whaleMatch.obi.obi||0) : null;\n  if(obiEl){\n    if(obiVal===null){ obiEl.textContent='—'; obiEl.style.color='var(--grey)'; }\n    else{\n      const bias = obiVal>0.15?'Bullish':obiVal<-0.15?'Bearish':'Neutral';\n      obiEl.textContent = `${obiVal.toFixed(2)} (${bias})`;\n      obiEl.style.color = obiVal>0.15?'var(--green)':obiVal<-0.15?'var(--red)':'var(--gold)';\n    }\n  }\n\n  // Open Interest — fetched once per coin change (not every 8s poll) to stay cheap\n  if(oiEl && window._cmdOiFetchedFor!==best.symbol){\n    window._cmdOiFetchedFor = best.symbol;\n    oiEl.textContent='Loading…'; oiEl.style.color='var(--grey)';\n    fetch(`/oi_data?symbol=${encodeURIComponent(best.symbol)}`).then(r=>r.json()).then(od=>{\n      if(window._cmdOiFetchedFor!==best.symbol) return; // coin changed while in flight\n      if(!od.available){ oiEl.textContent='N/A'; oiEl.style.color='var(--grey)'; return; }\n      const chg=od.change_pct_5m||0;\n      oiEl.textContent=(chg>=0?'+':'')+chg+'%';\n      oiEl.style.color = chg>0.5?'var(--green)':chg<-0.5?'var(--red)':'var(--gold)';\n    }).catch(()=>{ oiEl.textContent='N/A'; oiEl.style.color='var(--grey)'; });\n  }\n\n  // Flash alert: fires once per distinct (coin + BUY + surge/high-confidence) trigger\n  if(box){\n    const highProb = label==='BUY' && (inSurge || conf>=70);\n    const flashKey = highProb ? (best.symbol+'|'+label+'|'+inSurge) : null;\n    if(flashKey && flashKey!==window._cmdLastFlashKey){\n      window._cmdLastFlashKey = flashKey;\n      box.classList.remove('cmd-flash');\n      void box.offsetWidth; // restart animation\n      box.classList.add('cmd-flash');\n    } else if(!highProb){\n      window._cmdLastFlashKey = null;\n    }\n  }\n}\n\nfunction startCandleCountdown(){\n  function tick(){\n    const now=Date.now();\n    const oneEl=document.getElementById('cmd-candle-1m');\n    const fiveEl=document.getElementById('cmd-candle-5m');\n    if(oneEl){\n      const secs=60-Math.floor((now/1000)%60);\n      oneEl.textContent=String(secs).padStart(2,'0')+'s';\n    }\n    if(fiveEl){\n      const secs=300-Math.floor((now/1000)%300);\n      const m=Math.floor(secs/60), s=secs%60;\n      fiveEl.textContent=m+':'+String(s).padStart(2,'0');\n    }\n  }\n  tick();\n  setInterval(tick, 1000);\n}\n\n",
    ),
    (
        "  const conf=Math.round(best.confidence||0);\n  const sym=(best.symbol||'').replace('USDT','');\n",
        "  const conf=Math.round(best.confidence||0);\n  const sym=(best.symbol||'').replace('USDT','');\n  updateCmdMetrics(best, d, label, conf);\n",
    ),
]

if 'cmd-metrics-card' in HTML_content:
    print('V6_Master_Pro_UI/index.html: already patched — skipping')
else:
    for i, (old, new) in enumerate(HTML_EDITS, 1):
        cnt = HTML_content.count(old)
        if cnt != 1:
            print(f'V6_Master_Pro_UI/index.html EDIT {i}: FAILED - expected 1 match, found {cnt}. Aborting, no changes written to this file.')
            sys.exit(1)
        HTML_content = HTML_content.replace(old, new, 1)
        print(f'V6_Master_Pro_UI/index.html EDIT {i}: applied OK')
    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(HTML_content)
    print('V6_Master_Pro_UI/index.html: all edits applied OK')

import shutil
try:
    shutil.copy2('V6_Master_Pro_UI/index.html', 'index.html')
    print('index.html (root copy): synced from V6_Master_Pro_UI/index.html')
except Exception as e:
    print(f'Root index.html sync skipped: {e}')

print('Done — Live Scalping Metrics + Countdown + Flash Alerts patch complete.')