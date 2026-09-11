import sys

# ══════════════════════════════════════════════════════════════
# Dynamic Auto Support/Resistance (TradingView-style) — replaces
# the fixed daily-pivot-formula S/R lines with levels computed
# from REAL swing highs/lows in the candle data (fractal-style:
# a candle whose high/low is more extreme than 3 candles on
# either side). Nearby swing prices are clustered together and
# ranked by how many times price has touched that zone —  more
# touches = stronger level. Top 3 support (below price) and top
# 3 resistance (above price) are drawn as 'Auto S1/S2/S3' and
# 'Auto R1/R2/R3', same near-price highlighting as before. Pure
# client-side — reuses the already-fetched candles, no backend
# calls needed (the old /pivot_points fetch was removed).
#
# Also adds an Engulfing + Auto-S/R confluence alert: when a
# Bullish Engulfing forms right at an Auto Support level (or a
# Bearish Engulfing at Auto Resistance), a highlighted callout
# appears in the pattern box, e.g. '🎯 Bullish Engulfing at
# Support S1!'
# ══════════════════════════════════════════════════════════════

HTML_PATH = 'V6_Master_Pro_UI/index.html'
with open(HTML_PATH, 'r', encoding='utf-8') as f:
    html_content = f.read()

HTML_EDITS = [
    (
        '      <div id="scalp-volume-alert" style="display:none;margin-top:6px;padding:5px 7px;border-radius:2px;font-size:11px;font-weight:bold"></div>\n',
        '      <div id="scalp-volume-alert" style="display:none;margin-top:6px;padding:5px 7px;border-radius:2px;font-size:11px;font-weight:bold"></div>\n      <div id="scalp-confluence-alert" style="display:none;margin-top:6px;padding:5px 7px;border-radius:2px;border:1px solid;font-size:11px;font-weight:bold;background:rgba(0,0,0,0.3)"></div>\n',
    ),
    (
        '  fetch(`/pivot_points?symbol=${sym}&type=daily`).then(r=>r.json()).then(pv=>{\n    window._scalpState.pivotData = pv.available ? pv : null;\n  }).catch(()=>{ window._scalpState.pivotData = null; });\n\n',
        '',
    ),
    (
        '    s.pivotLines.push(ln);\n  });\n}\n\n',
        '    s.pivotLines.push(ln);\n  });\n}\n\n/* ── Auto Support/Resistance from real swing highs/lows (TradingView-style\n   dynamic S/R, not the fixed daily-pivot formula) — pure client-side,\n   reuses the same candles already fetched for the chart, no extra\n   backend calls. A "swing high" is a candle whose high is higher than\n   `lookback` candles on both sides (a real local turning point); nearby\n   swing prices are clustered into one level, and levels touched more\n   often are treated as stronger. ── */\nfunction scalpDetectSwingLevels(candles, lookback, tolerancePct){\n  lookback=lookback||3; tolerancePct=tolerancePct||0.4;\n  const swingHighs=[], swingLows=[];\n  if(candles.length < lookback*2+1) return {supportClusters:[], resistanceClusters:[]};\n  for(let i=lookback;i<candles.length-lookback;i++){\n    const c=candles[i];\n    let isHigh=true, isLow=true;\n    for(let j=i-lookback;j<=i+lookback;j++){\n      if(j===i) continue;\n      if(candles[j].high>=c.high) isHigh=false;\n      if(candles[j].low<=c.low) isLow=false;\n    }\n    if(isHigh) swingHighs.push(c.high);\n    if(isLow) swingLows.push(c.low);\n  }\n  function cluster(prices){\n    const sorted=[...prices].sort((a,b)=>a-b);\n    const clusters=[];\n    sorted.forEach(p=>{\n      const existing=clusters.find(cl=>Math.abs(cl.price-p)/p*100<=tolerancePct);\n      if(existing){ existing.price=(existing.price*existing.touches+p)/(existing.touches+1); existing.touches++; }\n      else clusters.push({price:p, touches:1});\n    });\n    return clusters.sort((a,b)=>b.touches-a.touches);\n  }\n  return {supportClusters:cluster(swingLows), resistanceClusters:cluster(swingHighs)};\n}\n\nfunction scalpDrawAutoSR(currentPrice){\n  const s=window._scalpState;\n  if(!s.candleSeries) return;\n  (s.pivotLines||[]).forEach(l=>{try{s.candleSeries.removePriceLine(l);}catch(e){}});\n  s.pivotLines=[];\n  const {supportClusters, resistanceClusters}=scalpDetectSwingLevels(s.candles, 3, 0.4);\n  const support=supportClusters.filter(c=>c.price<currentPrice).slice(0,3);\n  const resistance=resistanceClusters.filter(c=>c.price>currentPrice).slice(0,3);\n  s.autoSR={support, resistance};\n\n  const levels=[\n    ...resistance.map((c,i)=>({label:\'Auto R\'+(i+1), price:c.price, color:\'#ff2244\', touches:c.touches})),\n    ...support.map((c,i)=>({label:\'Auto S\'+(i+1), price:c.price, color:\'#00ff88\', touches:c.touches})),\n  ];\n  levels.forEach(lv=>{\n    const distPct=currentPrice?Math.abs(currentPrice-lv.price)/currentPrice*100:100;\n    const near=distPct<=0.3;\n    const primary=lv.label===\'Auto S1\'||lv.label===\'Auto R1\';\n    const ln=s.candleSeries.createPriceLine({\n      price:lv.price, color:lv.color,\n      lineWidth:near?3:(lv.touches>=3?2:1), lineStyle:near?0:2,\n      axisLabelVisible:near||primary,\n      title:(near?\'🔥 \':\'\')+lv.label+\' (\'+lv.touches+\'x)\',\n    });\n    s.pivotLines.push(ln);\n  });\n}\n\nfunction scalpCheckEngulfingConfluence(pattern, currentPrice){\n  const s=window._scalpState;\n  const sr=s.autoSR||{support:[],resistance:[]};\n  const nearAny=(levels)=>levels.find(l=>currentPrice && Math.abs(currentPrice-l.price)/currentPrice*100<=0.3);\n  if(pattern.name===\'Bullish Engulfing\'){\n    const lvl=nearAny(sr.support);\n    if(lvl) return {text:\'🎯 Bullish Engulfing at Support S\'+(sr.support.indexOf(lvl)+1)+\'!\', color:\'var(--green)\'};\n  }\n  if(pattern.name===\'Bearish Engulfing\'){\n    const lvl=nearAny(sr.resistance);\n    if(lvl) return {text:\'🎯 Bearish Engulfing at Resistance R\'+(sr.resistance.indexOf(lvl)+1)+\'!\', color:\'var(--red)\'};\n  }\n  return null;\n}\n\n',
    ),
    (
        '    scalpDrawPivots(candles[candles.length-1].close);\n',
        '    scalpDrawAutoSR(candles[candles.length-1].close);\n',
    ),
    (
        "    if(predEl){ predEl.textContent='Next: '+pred.text; predEl.style.color=pred.color; }\n",
        "    if(predEl){ predEl.textContent='Next: '+pred.text; predEl.style.color=pred.color; }\n\n    const confluenceEl=document.getElementById('scalp-confluence-alert');\n    const confluence=scalpCheckEngulfingConfluence(pattern, lastPrice);\n    if(confluenceEl){\n      if(confluence){\n        confluenceEl.style.display='block';\n        confluenceEl.textContent=confluence.text;\n        confluenceEl.style.color=confluence.color;\n        confluenceEl.style.borderColor=confluence.color;\n      }else{\n        confluenceEl.style.display='none';\n      }\n    }\n",
    ),
]

if 'scalpDetectSwingLevels' in html_content:
    print('index.html: swing-based Auto S/R already present — skipping')
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

print('Done — dynamic swing-based Auto Support/Resistance + Engulfing confluence alert complete.')