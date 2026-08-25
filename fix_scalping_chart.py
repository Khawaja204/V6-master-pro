import sys, ast

# ══════════════════════════════════════════════════════════════
# Professional Scalping Chart Upgrade
# - EMA9/EMA21/VWAP overlays on the main candlestick chart
# - 8h/1d timeframe buttons + 'ALL / Multi-TF' RSI mini strip
# - Auto Pivot Points (Daily/Hourly toggle): S1-S3 green, R1-R3
#   red, price lines auto-highlight when price is near a level
# - S/R confidence mini-bar below the chart
# - BID/ASK renamed to BUY/SELL everywhere in the UI, with clear
#   green/buy vs red/sell coloring
# - Live candle-close countdown timer in the chart corner
# - Removed EXECUTE TRADE NOW / PANIC-CANCEL ALL buttons (Render
#   hosting can't safely support live/fake execution) — replaced
#   with a plain 'Analysis Only' note; dashboard is pure analysis
# ══════════════════════════════════════════════════════════════

# ── routes/api.py ──
API_PATH = 'routes/api.py'
with open(API_PATH, 'r', encoding='utf-8') as f:
    API_content = f.read()

API_EDITS = [
    (
        "_LOCAL_NAMES = {'chart_data', 'rsi_scan', 'get_data', 'status', 'whale_copy_data_route', 'live_score_route', 'large_trades_summary_route', 'api_wc_learning', 'dashboard_data', 'large_trades_data_route', 'sniper_data', 'focus_mode', 'health_check', 'focus_data', 'large_trades_list_route', 'combo_bot_data_route', 'v6_bot_data_route', 'whale_detail_route', 'api_onchain', 'eth_onchain_data_route', 'system_health', 'market_overview_route', 'oi_data_route'}\n",
        "_LOCAL_NAMES = {'chart_data', 'rsi_scan', 'get_data', 'status', 'whale_copy_data_route', 'live_score_route', 'large_trades_summary_route', 'api_wc_learning', 'dashboard_data', 'large_trades_data_route', 'sniper_data', 'focus_mode', 'health_check', 'focus_data', 'large_trades_list_route', 'combo_bot_data_route', 'v6_bot_data_route', 'whale_detail_route', 'api_onchain', 'eth_onchain_data_route', 'system_health', 'market_overview_route', 'oi_data_route', 'rsi_multi_tf_route', 'pivot_points_route'}\n",
    ),
    (
        '        "open_interest": oi_now,\n        "change_pct_5m": change_pct,\n',
        '        "open_interest": oi_now,\n        "change_pct_5m": change_pct,\n    })\n\n\n@bp.route("/rsi_multi_tf")\n@_sync_main_state\ndef rsi_multi_tf_route():\n    """RSI for ALL 7 timeframes at once, for a single symbol — powers the\n    Command/Sniper chart\'s \'ALL / Multi-TF\' mini strip. One symbol at a\n    time keeps this cheap (7 klines fetches total vs. scanning every coin\n    per timeframe like /rsi_scan does)."""\n    from logic import fetch_klines as _fk\n    symbol = request.args.get("symbol", "").upper()\n    if not symbol:\n        return jsonify({"error": "symbol required"}), 400\n\n    def _rsi(klines, period=14):\n        closes = [float(k[4]) for k in klines if len(k) > 4]\n        if len(closes) < period + 1:\n            return None\n        gains, losses = [], []\n        for i in range(1, len(closes)):\n            d = closes[i] - closes[i - 1]\n            gains.append(max(d, 0)); losses.append(max(-d, 0))\n        avg_gain = sum(gains[:period]) / period\n        avg_loss = sum(losses[:period]) / period\n        for i in range(period, len(gains)):\n            avg_gain = (avg_gain * (period - 1) + gains[i]) / period\n            avg_loss = (avg_loss * (period - 1) + losses[i]) / period\n        if avg_loss == 0:\n            return 100.0\n        rs = avg_gain / avg_loss\n        return round(100 - (100 / (1 + rs)), 1)\n\n    timeframes = ["1m", "5m", "15m", "1h", "4h", "8h", "1d"]\n    out = {}\n    for tf in timeframes:\n        try:\n            klines = _fk(symbol, tf, 30)\n            out[tf] = _rsi(klines)\n        except Exception as e:\n            log.debug(f"[rsi_multi_tf] {symbol} {tf} failed: {e}")\n            out[tf] = None\n    return jsonify({"symbol": symbol, "rsi": out})\n\n\n@bp.route("/pivot_points")\n@_sync_main_state\ndef pivot_points_route():\n    """Classic floor-trader pivot points (P, R1-R3, S1-S3) computed from\n    the previous CLOSED daily or hourly candle\'s High/Low/Close — the\n    standard basis for intraday pivot levels, no paid data source needed."""\n    from logic import fetch_klines as _fk\n    symbol   = request.args.get("symbol", "").upper()\n    basis    = request.args.get("type", "daily").lower()\n    if not symbol:\n        return jsonify({"error": "symbol required"}), 400\n    if basis not in ("daily", "hourly"):\n        return jsonify({"error": "type must be daily or hourly"}), 400\n\n    interval = "1d" if basis == "daily" else "1h"\n    try:\n        klines = _fk(symbol, interval, 3)\n        if len(klines) < 2:\n            return jsonify({"symbol": symbol, "basis": basis, "available": False})\n        prev = klines[-2]  # last CLOSED period (most recent element is the still-forming current one)\n        h, l, c = float(prev[2]), float(prev[3]), float(prev[4])\n    except Exception as e:\n        return jsonify({"symbol": symbol, "basis": basis, "available": False, "error": str(e)})\n\n    p  = (h + l + c) / 3\n    r1 = 2 * p - l\n    s1 = 2 * p - h\n    r2 = p + (h - l)\n    s2 = p - (h - l)\n    r3 = h + 2 * (p - l)\n    s3 = l - 2 * (h - p)\n    return jsonify({\n        "symbol": symbol, "basis": basis, "available": True,\n        "pivot": round(p, 8),\n        "r1": round(r1, 8), "r2": round(r2, 8), "r3": round(r3, 8),\n        "s1": round(s1, 8), "s2": round(s2, 8), "s3": round(s3, 8),\n',
    ),
    (
        '    allowed = {"1m", "5m", "1h", "4h", "8h", "1d"}\n',
        '    allowed = {"1m", "5m", "15m", "1h", "4h", "8h", "1d"}\n',
    ),
]

if 'pivot_points_route' in API_content:
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
        '      <button id="cmd-execute-btn" disabled class="exec-btn go pg exec-btn-primary" onclick="cmdExecuteTrade()" style="margin-top:12px;opacity:.4;cursor:not-allowed;background:#222;color:#666;border-color:#333">\n        EXECUTE TRADE NOW\n      </button>\n',
        '      <div style="margin-top:12px;padding:8px;background:#0a0a14;border:1px solid #333;border-radius:2px;text-align:center;font-size:9px;color:var(--grey)">\n        📊 Analysis Only — this dashboard does not place trades automatically\n      </div>\n',
    ),
    (
        '          <div style="display:flex;gap:4px;margin-bottom:5px">\n',
        '          <div style="display:flex;gap:4px;margin-bottom:5px;flex-wrap:wrap">\n',
    ),
    (
        '<button class="tf-btn" data-tf="1h" onclick="setTimeframe(\'1h\')" style="background:#0a0a14;border:1px solid #333;color:#aaa;padding:3px 8px;font-size:9px;cursor:pointer;border-radius:2px">1h</button>\n<button class="tf-btn" data-tf="4h" onclick="setTimeframe(\'4h\')" style="background:#0a0a14;border:1px solid #333;color:#aaa;padding:3px 8px;font-size:9px;cursor:pointer;border-radius:2px">4h</button>\n',
        '<button class="tf-btn" data-tf="1h" onclick="setTimeframe(\'1h\')" style="background:#0a0a14;border:1px solid #333;color:#aaa;padding:3px 8px;font-size:9px;cursor:pointer;border-radius:2px">1h</button>\n<button class="tf-btn" data-tf="4h" onclick="setTimeframe(\'4h\')" style="background:#0a0a14;border:1px solid #333;color:#aaa;padding:3px 8px;font-size:9px;cursor:pointer;border-radius:2px">4h</button>\n<button class="tf-btn" data-tf="8h" onclick="setTimeframe(\'8h\')" style="background:#0a0a14;border:1px solid #333;color:#aaa;padding:3px 8px;font-size:9px;cursor:pointer;border-radius:2px">8h</button>\n<button class="tf-btn" data-tf="1d" onclick="setTimeframe(\'1d\')" style="background:#0a0a14;border:1px solid #333;color:#aaa;padding:3px 8px;font-size:9px;cursor:pointer;border-radius:2px">1d</button>\n<button id="tf-all-btn" onclick="toggleMultiTfStrip()" style="background:#1a0a2e;border:1px solid #a855f7;color:#c084fc;padding:3px 8px;font-size:9px;cursor:pointer;border-radius:2px;font-weight:bold">ALL / Multi-TF</button>\n',
    ),
    (
        '<div id="chart-box" style="background:#040408;height:180px;border:1px solid #1e1e2e;border-radius:2px;margin-bottom:5px;overflow:hidden"></div>\n',
        '<div id="chart-box-wrap" style="position:relative;margin-bottom:5px">\n  <div id="chart-box" style="background:#040408;height:180px;border:1px solid #1e1e2e;border-radius:2px;overflow:hidden"></div>\n  <div id="candle-countdown" style="position:absolute;top:4px;right:6px;background:rgba(10,10,20,0.85);border:1px solid #333;border-radius:2px;padding:2px 6px;font-size:9px;color:var(--gold);z-index:5">⏱ —</div>\n</div>\n<div id="multi-tf-strip" style="display:none;background:#0a0a14;border:1px solid #1e1e2e;border-radius:2px;padding:6px;margin-bottom:5px;font-size:9px">\n  <div style="color:var(--grey);margin-bottom:4px">RSI ACROSS ALL TIMEFRAMES</div>\n  <div id="multi-tf-strip-body" style="display:grid;grid-template-columns:repeat(7,1fr);gap:4px;text-align:center">\n    <div>1m<br><span data-tf-rsi="1m">—</span></div>\n    <div>5m<br><span data-tf-rsi="5m">—</span></div>\n    <div>15m<br><span data-tf-rsi="15m">—</span></div>\n    <div>1h<br><span data-tf-rsi="1h">—</span></div>\n    <div>4h<br><span data-tf-rsi="4h">—</span></div>\n    <div>8h<br><span data-tf-rsi="8h">—</span></div>\n    <div>1d<br><span data-tf-rsi="1d">—</span></div>\n  </div>\n</div>\n<div style="display:flex;gap:4px;margin-bottom:5px;align-items:center">\n  <span style="font-size:8px;color:var(--grey)">PIVOT BASIS:</span>\n  <button class="pivot-btn active" data-basis="daily" onclick="setPivotBasis(\'daily\')" style="background:#003311;border:1px solid #00ff88;color:#00ff88;padding:2px 7px;font-size:9px;cursor:pointer;border-radius:2px">Daily</button>\n  <button class="pivot-btn" data-basis="hourly" onclick="setPivotBasis(\'hourly\')" style="background:#0a0a14;border:1px solid #333;color:#aaa;padding:2px 7px;font-size:9px;cursor:pointer;border-radius:2px">Hourly</button>\n</div>\n<div id="sr-confidence-bar" style="background:#0a0a14;border:1px solid #1e1e2e;border-radius:2px;padding:5px 8px;margin-bottom:5px;font-size:9px;display:flex;justify-content:space-between;align-items:center">\n  <span style="color:var(--grey)">S/R LEVEL CONFIDENCE</span>\n  <span id="sr-confidence-val" style="font-weight:bold;color:var(--grey)">—</span>\n</div>\n',
    ),
    (
        '          <!-- STEP 3: ACTION BUTTONS -->\n          <div class="eng-step-lbl">STEP 3 · ACTION BUTTONS</div>\n          <button class="exec-btn go pg exec-btn-primary">✅ EXECUTE TRADE NOW</button>\n          <button class="exec-btn panic exec-btn-secondary" onclick="openPanicModal()">⛔ PANIC – CANCEL ALL</button>\n',
        '          <!-- STEP 3: SETUP SUMMARY (analysis only — no auto-execution) -->\n          <div class="eng-step-lbl">STEP 3 · SETUP SUMMARY</div>\n          <div style="padding:8px;background:#0a0a14;border:1px solid #333;border-radius:2px;text-align:center;font-size:9px;color:var(--grey)">\n            📊 Analysis Only — this dashboard does not place trades automatically\n          </div>\n',
    ),
    (
        '    </div>\n  </div>\n\n  <!-- PANIC double-confirmation modal -->\n  <div id="panic-modal-backdrop" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:9999;align-items:center;justify-content:center">\n    <div style="background:#0a0a14;border:1px solid #ff2244;border-radius:4px;padding:18px;max-width:320px;width:88%;text-align:center">\n      <div style="font-size:26px;margin-bottom:6px">⚠️</div>\n      <div style="font-weight:bold;color:#ff2244;font-size:13px;margin-bottom:6px">Cancel ALL open positions?</div>\n      <div style="font-size:11px;color:var(--grey);margin-bottom:14px">This will attempt to cancel every open trade. This cannot be undone. Are you sure?</div>\n      <button onclick="confirmPanicAction()" style="width:100%;padding:10px;background:#440000;color:var(--red);border:1px solid #ff2244;border-radius:2px;font-weight:bold;font-size:12px;margin-bottom:8px;cursor:pointer">Yes, Cancel All</button>\n      <button onclick="closePanicModal()" style="width:100%;padding:8px;background:#0a0a14;color:#aaa;border:1px solid #333;border-radius:2px;font-size:11px;cursor:pointer">Never mind</button>\n',
        '',
    ),
    (
        "let chart=null, candleSeries=null, countdown=8, timer=null, currentTF='15m', activeStrategyFilter='all';\n",
        "let chart=null, candleSeries=null, ema9Series=null, ema21Series=null, vwapSeries=null, countdown=8, timer=null, currentTF='15m', activeStrategyFilter='all', pivotBasis='daily';\nwindow._pivotLines=[];\n",
    ),
    (
        '  setInterval(fetchMarketOverview, 90000);\n  startCandleCountdown();\n',
        '  setInterval(fetchMarketOverview, 90000);\n  startCandleCountdown();\n  startChartCandleCountdown();\n',
    ),
    (
        "      wickUpColor:'#00cc44',wickDownColor:'#cc2200',\n    });\n",
        "      wickUpColor:'#00cc44',wickDownColor:'#cc2200',\n    });\n    ema9Series=chart.addLineSeries({color:'#00bfff',lineWidth:1,priceLineVisible:false,lastValueVisible:false,title:'EMA9'});\n    ema21Series=chart.addLineSeries({color:'#ff9900',lineWidth:1,priceLineVisible:false,lastValueVisible:false,title:'EMA21'});\n    vwapSeries=chart.addLineSeries({color:'#c084fc',lineWidth:1,lineStyle:2,priceLineVisible:false,lastValueVisible:false,title:'VWAP'});\n",
    ),
    (
        '  const rs=avgG/avgL;\n  return 100-(100/(1+rs));\n',
        "  const rs=avgG/avgL;\n  return 100-(100/(1+rs));\n}\n\nfunction calcEMASeries(candles, period){\n  if(candles.length<period) return [];\n  let ema=candles.slice(0,period).reduce((s,c)=>s+c.close,0)/period;\n  const k=2/(period+1);\n  const out=[{time:candles[period-1].time, value:ema}];\n  for(let i=period;i<candles.length;i++){\n    ema=candles[i].close*k+ema*(1-k);\n    out.push({time:candles[i].time, value:ema});\n  }\n  return out;\n}\n\n/* ── Pivot Points (S1-S3 green / R1-R3 red) with proximity highlighting ── */\nfunction setPivotBasis(basis){\n  pivotBasis=basis;\n  document.querySelectorAll('.pivot-btn').forEach(b=>{\n    const on=b.dataset.basis===basis;\n    b.style.background=on?'#003311':'#0a0a14';\n    b.style.borderColor=on?'#00ff88':'#333';\n    b.style.color=on?'#00ff88':'#aaa';\n  });\n  fetchChart();\n}\n\nfunction updatePivotLevels(symbol, currentPrice){\n  fetch(`/pivot_points?symbol=${symbol}&type=${pivotBasis}`).then(r=>r.json()).then(pv=>{\n    if(window._pivotLines) window._pivotLines.forEach(l=>{try{candleSeries.removePriceLine(l);}catch(e){}});\n    window._pivotLines=[];\n    const confEl=document.getElementById('sr-confidence-val');\n    if(!pv.available){\n      if(confEl){ confEl.textContent='No data'; confEl.style.color='var(--grey)'; }\n      return;\n    }\n    const levels=[\n      {key:'s1',label:'S1',price:pv.s1,color:'#00ff88'},\n      {key:'s2',label:'S2',price:pv.s2,color:'#00cc66'},\n      {key:'s3',label:'S3',price:pv.s3,color:'#009944'},\n      {key:'r1',label:'R1',price:pv.r1,color:'#ff2244'},\n      {key:'r2',label:'R2',price:pv.r2,color:'#dd1133'},\n      {key:'r3',label:'R3',price:pv.r3,color:'#bb0022'},\n      {key:'pivot',label:'P',price:pv.pivot,color:'#ffd700'},\n    ];\n    let minDistPct=Infinity;\n    levels.forEach(lv=>{\n      if(!lv.price) return;\n      const distPct=currentPrice?Math.abs(currentPrice-lv.price)/currentPrice*100:100;\n      const near=distPct<=0.3;\n      if(distPct<minDistPct) minDistPct=distPct;\n      const ln=candleSeries.createPriceLine({\n        price:lv.price, color:lv.color,\n        lineWidth:near?3:1, lineStyle:near?0:2,\n        axisLabelVisible:true,\n        title:(near?'🔥 ':'')+lv.label+' '+fmt6(lv.price),\n      });\n      window._pivotLines.push(ln);\n    });\n    if(confEl){\n      const score=Math.max(0, Math.round(100-Math.min(minDistPct,5)*20));\n      confEl.textContent=score+'% ('+(minDistPct<0.3?'price near a key level':'no level nearby')+')';\n      confEl.style.color=score>=70?'var(--green)':score>=40?'var(--gold)':'var(--grey)';\n    }\n  }).catch(()=>{\n    const confEl=document.getElementById('sr-confidence-val');\n    if(confEl){ confEl.textContent='Fetch failed'; confEl.style.color='var(--grey)'; }\n  });\n}\n\n/* ── Multi-Timeframe RSI strip ── */\nfunction toggleMultiTfStrip(){\n  const strip=document.getElementById('multi-tf-strip');\n  const btn=document.getElementById('tf-all-btn');\n  if(!strip) return;\n  const show=strip.style.display==='none';\n  strip.style.display=show?'block':'none';\n  if(btn){ btn.style.background=show?'#a855f7':'#1a0a2e'; btn.style.color=show?'#fff':'#c084fc'; }\n  if(show) fetchMultiTfRsi();\n}\n\nfunction fetchMultiTfRsi(){\n  const symbol=(document.getElementById('coin-inp')?.value||'BTCUSDT').toUpperCase().replace(/[^A-Z0-9]/g,'');\n  const sym=symbol.includes('USDT')?symbol:symbol+'USDT';\n  fetch(`/rsi_multi_tf?symbol=${sym}`).then(r=>r.json()).then(d=>{\n    const rsi=d.rsi||{};\n    document.querySelectorAll('[data-tf-rsi]').forEach(el=>{\n      const tf=el.dataset.tfRsi;\n      const v=rsi[tf];\n      if(v===null||v===undefined){ el.textContent='—'; el.style.color='var(--grey)'; return; }\n      el.textContent=v;\n      el.style.color=v>=70?'var(--red)':v<=30?'var(--green)':'var(--gold)';\n    });\n  }).catch(()=>{});\n}\n\n/* ── Live candle-close countdown (chart corner, tracks currentTF) ── */\nconst TF_SECONDS={'1m':60,'5m':300,'15m':900,'1h':3600,'4h':14400,'8h':28800,'1d':86400};\nfunction startChartCandleCountdown(){\n  function tick(){\n    const el=document.getElementById('candle-countdown');\n    if(!el) return;\n    const dur=TF_SECONDS[currentTF]||900;\n    const secs=dur-Math.floor((Date.now()/1000)%dur);\n    const m=Math.floor(secs/60), s=secs%60;\n    el.textContent='⏱ '+(m>0?m+'m ':'')+s+'s';\n  }\n  tick();\n  setInterval(tick,1000);\n",
    ),
    (
        "      candleSeries.setData(candles);\n      if(_st) _st.textContent=candles.length+' candles loaded ('+symbol+' '+currentTF+')';\n",
        "      candleSeries.setData(candles);\n      if(_st) _st.textContent=candles.length+' candles loaded ('+symbol+' '+currentTF+')';\n      try{\n        if(ema9Series) ema9Series.setData(calcEMASeries(candles,9));\n        if(ema21Series) ema21Series.setData(calcEMASeries(candles,21));\n        if(vwapSeries && d.vwap_line && d.vwap_line.length) vwapSeries.setData(d.vwap_line);\n      }catch(e){console.warn('Indicator overlay failed:',e);}\n      updatePivotLevels(symbol, candles[candles.length-1].close);\n",
    ),
    (
        "            price: w.price_level, color: w.side==='BID'?'#00aaff':'#ff8800',\n",
        "            price: w.price_level, color: w.side==='BID'?'#00ff88':'#ff2244',\n",
    ),
    (
        "            title:(w.side==='BID'?'BID ':'ASK ')+Math.round((w.size_usdt||0)/1000)+'K'\n",
        "            title:(w.side==='BID'?'BUY ':'SELL ')+Math.round((w.size_usdt||0)/1000)+'K'\n",
    ),
    (
        '      <span style="color:${w.side===\'BID\'?\'var(--green)\':\'var(--red)\'}">${w.side} @ ${fmt6(w.price_level)}</span>\n',
        '      <span style="color:${w.side===\'BID\'?\'var(--green)\':\'var(--red)\'}">${w.side===\'BID\'?\'BUY\':\'SELL\'} @ ${fmt6(w.price_level)}</span>\n',
    ),
    (
        "}\n\nfunction cmdExecuteTrade(){\n  if(!window._cmdCoin) return;\n  // TODO: wire to a real trade-execution endpoint reachable from the main\n  // dashboard (the existing /admin/manual_trade route requires an admin\n  // login session, which this page doesn't have) — flag for a backend\n  // decision before enabling live execution here.\n  console.log('EXECUTE TRADE NOW requested for', window._cmdCoin);\n  alert('Execute wiring pending — see chat notes on /admin/manual_trade auth.');\n",
        '',
    ),
    (
        "}\nfunction openPanicModal(){\n  const el = document.getElementById('panic-modal-backdrop');\n  if(el) el.style.display = 'flex';\n}\nfunction closePanicModal(){\n  const el = document.getElementById('panic-modal-backdrop');\n  if(el) el.style.display = 'none';\n}\nfunction confirmPanicAction(){\n  closePanicModal();\n  // TODO: wire to a real cancel-all-positions backend endpoint when one exists.\n  console.log('PANIC confirmed — cancel all positions requested');\n",
        '',
    ),
]

if 'candle-countdown' in HTML_content:
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

print('Done — Professional Scalping Chart Upgrade complete.')