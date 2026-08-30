import sys

# ══════════════════════════════════════════════════════════════
# Numbered strategy buttons (1-5) + 6th Confluence filter + auto
# Pivot S/R lines (S1-S3 green, R1-R3 red) integrated directly
# into the Scalping Chart, with proximity highlighting.
#
# - Strategy Filter buttons now read '1. 1m Momentum Breakout',
#   '2. Order Flow Scalp', etc., with a stronger glow highlight
#   on the active button.
# - New 6th button '6. Confluence (Multi-Match)' lists coins that
#   match 2+ of the 5 strategies, showing which strategy NUMBERS
#   matched (e.g. 'Matching Strategies: 1, 3, 5') — names are
#   readable from the numbered buttons above, as requested.
# - Pattern coloring (bullish=green/bearish=red) was already
#   correct from the prior consolidated chart patch — verified,
#   no change needed there.
# - Pivot points fetched once per symbol/timeframe load (not
#   re-fetched on every live WebSocket tick) and redrawn with
#   fresh price on every render for accurate near-level
#   highlighting, matching the same declutter pattern used
#   elsewhere (only P/S1/R1 always labeled, others label only
#   when price is actually close).
# ══════════════════════════════════════════════════════════════

HTML_PATH = 'V6_Master_Pro_UI/index.html'
with open(HTML_PATH, 'r', encoding='utf-8') as f:
    html_content = f.read()

HTML_EDITS = [
    (
        '.strategy-btn:hover,.strategy-btn.active{background:#003311;border-color:var(--green);color:var(--green)}\n',
        '.strategy-btn:hover,.strategy-btn.active{background:#003311;border-color:var(--green);color:var(--green);font-weight:bold;box-shadow:0 0 6px rgba(0,255,136,0.5)}\n.strategy-btn.confluence-btn{border-color:#a855f7;color:#c084fc}\n.strategy-btn.confluence-btn:hover,.strategy-btn.confluence-btn.active{background:#1a0a2e;border-color:#a855f7;color:#c084fc;box-shadow:0 0 6px rgba(168,85,247,0.5)}\n',
    ),
    (
        '      <button class="strategy-btn" data-strategy="momentum" onclick="filterStrategies(\'momentum\')">1m MOMENTUM BREAKOUT</button>\n      <button class="strategy-btn" data-strategy="order-flow" onclick="filterStrategies(\'order-flow\')">ORDER FLOW SCALP</button>\n      <button class="strategy-btn" data-strategy="range-grid" onclick="filterStrategies(\'range-grid\')">RANGE GRID SCALP</button>\n      <button class="strategy-btn" data-strategy="volume-surge" onclick="filterStrategies(\'volume-surge\')">VOLUME SURGE SCALP</button>\n      <button class="strategy-btn" data-strategy="trend-pullback" onclick="filterStrategies(\'trend-pullback\')">TREND PULLBACK SCALP</button>\n',
        '      <button class="strategy-btn" data-strategy="momentum" onclick="filterStrategies(\'momentum\')">1. 1m Momentum Breakout</button>\n      <button class="strategy-btn" data-strategy="order-flow" onclick="filterStrategies(\'order-flow\')">2. Order Flow Scalp</button>\n      <button class="strategy-btn" data-strategy="range-grid" onclick="filterStrategies(\'range-grid\')">3. Range Grid Scalp</button>\n      <button class="strategy-btn" data-strategy="volume-surge" onclick="filterStrategies(\'volume-surge\')">4. Volume Surge Scalp</button>\n      <button class="strategy-btn" data-strategy="trend-pullback" onclick="filterStrategies(\'trend-pullback\')">5. Trend Pullback Scalp</button>\n      <button class="strategy-btn confluence-btn" data-strategy="confluence" onclick="filterStrategies(\'confluence\')">6. Confluence (Multi-Match)</button>\n',
    ),
    (
        '  candles: [], ws: null,\n',
        '  candles: [], ws: null,\n  pivotData: null, pivotLines: [],\n',
    ),
    (
        '  if(!window._scalpState.chart) scalpInitChart();\n\n',
        '  if(!window._scalpState.chart) scalpInitChart();\n\n  fetch(`/pivot_points?symbol=${sym}&type=daily`).then(r=>r.json()).then(pv=>{\n    window._scalpState.pivotData = pv.available ? pv : null;\n  }).catch(()=>{ window._scalpState.pivotData = null; });\n\n',
    ),
    (
        "  }).catch(()=>{ if(st) st.textContent='Chart fetch failed'; });\n",
        "  }).catch(()=>{ if(st) st.textContent='Chart fetch failed'; });\n}\n\nfunction scalpDrawPivots(currentPrice){\n  const s=window._scalpState;\n  if(!s.candleSeries) return;\n  (s.pivotLines||[]).forEach(l=>{try{s.candleSeries.removePriceLine(l);}catch(e){}});\n  s.pivotLines=[];\n  const pv=s.pivotData;\n  if(!pv) return;\n  const levels=[\n    {label:'R3',price:pv.r3,color:'#ff2244'},{label:'R2',price:pv.r2,color:'#ff2244'},{label:'R1',price:pv.r1,color:'#ff2244'},\n    {label:'P', price:pv.pivot,color:'#ffd700'},\n    {label:'S1',price:pv.s1,color:'#00ff88'},{label:'S2',price:pv.s2,color:'#00ff88'},{label:'S3',price:pv.s3,color:'#00ff88'},\n  ];\n  levels.forEach(lv=>{\n    if(!lv.price) return;\n    const distPct=currentPrice?Math.abs(currentPrice-lv.price)/currentPrice*100:100;\n    const near=distPct<=0.3;\n    const primary=['P','S1','R1'].includes(lv.label);\n    const ln=s.candleSeries.createPriceLine({\n      price:lv.price, color:lv.color,\n      lineWidth:near?3:1, lineStyle:near?0:2,\n      axisLabelVisible:near||primary,\n      title:(near?'🔥 ':'')+lv.label,\n    });\n    s.pivotLines.push(ln);\n  });\n",
    ),
    (
        "    if(s.volumeSeries) s.volumeSeries.setData(candles.map(c=>({time:c.time,value:c.volume,color:c.close>=c.open?'rgba(0,204,68,0.6)':'rgba(204,34,0,0.6)'})));\n",
        "    if(s.volumeSeries) s.volumeSeries.setData(candles.map(c=>({time:c.time,value:c.volume,color:c.close>=c.open?'rgba(0,204,68,0.6)':'rgba(204,34,0,0.6)'})));\n    scalpDrawPivots(candles[candles.length-1].close);\n",
    ),
    (
        "  return candidates.find(c=>(c.strategy||'').toLowerCase()===name.toLowerCase())||null;\n}\n\n",
        "  return candidates.find(c=>(c.strategy||'').toLowerCase()===name.toLowerCase())||null;\n}\n\nconst STRATEGY_KEYS_NUMBERED=[\n  {key:'momentum', num:1, label:'1m Momentum Breakout'},\n  {key:'order-flow', num:2, label:'Order Flow Scalp'},\n  {key:'range-grid', num:3, label:'Range Grid Scalp'},\n  {key:'volume-surge', num:4, label:'Volume Surge Scalp'},\n  {key:'trend-pullback', num:5, label:'Trend Pullback Scalp'},\n];\n\nfunction matchingStrategyNumbers(coin, d){\n  return STRATEGY_KEYS_NUMBERED.filter(s=>strategyMatch(coin, s.key, d)).map(s=>s.num);\n}\n\n",
    ),
    (
        "  if(key==='all') return best.best_score>0;\n",
        "  if(key==='all') return best.best_score>0;\n  if(key==='confluence') return matchingStrategyNumbers(coin,d).length>=2;\n",
    ),
    (
        '  if(meta) meta.textContent=`${coins.length} ${label.toLowerCase()}`;\n',
        '  if(meta) meta.textContent=`${coins.length} ${label.toLowerCase()}`;\n  if(activeStrategyFilter===\'confluence\'){\n    list.innerHTML=coins.slice(0,12).map(c=>{\n      const sym=(c.symbol||\'\').replace(\'USDT\',\'\');\n      const nums=matchingStrategyNumbers(c,d);\n      return `<button class="strategy-match" onclick="selectStrategyCoin(\'${c.symbol}\')" title="Load ${c.symbol} in COMMAND">\n        <b>${sym}</b><span>Matching Strategies: ${nums.join(\', \')}</span>\n        <em>${nums.length} strategies confirm this setup</em>\n      </button>`;\n    }).join(\'\')||\'<span class="strategy-empty">No coins currently match 2+ strategies.</span>\';\n    return;\n  }\n',
    ),
]

if 'scalpDrawPivots' in html_content:
    print('index.html: numbered strategies + confluence + chart S/R already present — skipping')
else:
    for i, (old, new) in enumerate(HTML_EDITS, 1):
        cnt = html_content.count(old)
        if cnt != 1:
            print(f'EDIT {i}: FAILED - expected 1 match, found {cnt}. Aborting, no changes written.')
            sys.exit(1)
        html_content = html_content.replace(old, new, 1)
        print(f'EDIT {i}: applied OK')
    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print('index.html: all edits applied OK')

import shutil
try:
    shutil.copy2('V6_Master_Pro_UI/index.html', 'index.html')
    print('index.html (root copy): synced from V6_Master_Pro_UI/index.html')
except Exception as e:
    print(f'Root index.html sync skipped: {e}')

print('Done — numbered strategies, confluence filter, and chart S/R lines complete.')