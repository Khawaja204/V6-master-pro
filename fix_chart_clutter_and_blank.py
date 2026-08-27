import sys

# ══════════════════════════════════════════════════════════════
# Fix 1: Chart indicator overlap — pivot levels (P/S1-S3/R1-R3)
# and whale BUY/SELL walls were drawn as on-chart price-line
# labels, which Lightweight Charts stacks/overlaps when their
# prices sit close together (exactly what was happening). Moved
# both to clean text panels below the chart instead — zero
# collision risk since it's a plain list, not chart overlays.
# EMA9/EMA21/VWAP remain as actual line traces on the chart
# (those never caused overlap; only the axis-label price lines did).
#
# Fix 2: Command tab's BTC + Manual charts rendering blank/black —
# hardened chart init with an explicit width/height fallback, a
# delayed resize safety net, a longer init delay (50ms -> 300ms)
# to avoid a layout-timing race right after the accordion opens,
# and error messages now surface in the status line instead of
# failing silently — so if this recurs, the exact cause will be
# visible on-screen instead of just a blank box.
# ══════════════════════════════════════════════════════════════

HTML_PATH = 'V6_Master_Pro_UI/index.html'
with open(HTML_PATH, 'r', encoding='utf-8') as f:
    html_content = f.read()

HTML_EDITS = [
    (
        '  <button class="pivot-btn" data-basis="hourly" onclick="setPivotBasis(\'hourly\')" style="background:#0a0a14;border:1px solid #333;color:#aaa;padding:2px 7px;font-size:9px;cursor:pointer;border-radius:2px">Hourly</button>\n</div>\n',
        '  <button class="pivot-btn" data-basis="hourly" onclick="setPivotBasis(\'hourly\')" style="background:#0a0a14;border:1px solid #333;color:#aaa;padding:2px 7px;font-size:9px;cursor:pointer;border-radius:2px">Hourly</button>\n</div>\n<div id="key-levels-panel" style="background:#0a0a14;border:1px solid #1e1e2e;border-radius:2px;padding:6px 8px;margin-bottom:5px">\n  <div style="color:var(--grey);font-size:9px">Loading key levels...</div>\n</div>\n<div id="whale-wall-panel" style="background:#0a0a14;border:1px solid #1e1e2e;border-radius:2px;padding:6px 8px;margin-bottom:5px">\n  <div style="color:var(--grey);font-size:9px">Loading whale walls...</div>\n</div>\n',
    ),
    (
        "    if(window._pivotLines) window._pivotLines.forEach(l=>{try{candleSeries.removePriceLine(l);}catch(e){}});\n    window._pivotLines=[];\n    const confEl=document.getElementById('sr-confidence-val');\n    if(!pv.available){\n      if(confEl){ confEl.textContent='No data'; confEl.style.color='var(--grey)'; }\n      return;\n    }\n    const levels=[\n      {key:'s1',label:'S1',price:pv.s1,color:'#00ff88'},\n      {key:'s2',label:'S2',price:pv.s2,color:'#00cc66'},\n      {key:'s3',label:'S3',price:pv.s3,color:'#009944'},\n      {key:'r1',label:'R1',price:pv.r1,color:'#ff2244'},\n      {key:'r2',label:'R2',price:pv.r2,color:'#dd1133'},\n      {key:'r3',label:'R3',price:pv.r3,color:'#bb0022'},\n      {key:'pivot',label:'P',price:pv.pivot,color:'#ffd700'},\n    ];\n    let minDistPct=Infinity;\n    levels.forEach(lv=>{\n      if(!lv.price) return;\n      const distPct=currentPrice?Math.abs(currentPrice-lv.price)/currentPrice*100:100;\n      const near=distPct<=0.3;\n      const primary=['pivot','s1','r1'].includes(lv.key);\n      if(distPct<minDistPct) minDistPct=distPct;\n      const ln=candleSeries.createPriceLine({\n        price:lv.price, color:lv.color,\n        lineWidth:near?3:1, lineStyle:near?0:2,\n        axisLabelVisible: near||primary,\n        title: near ? ('🔥 '+lv.label+' '+fmt6(lv.price)) : (primary ? lv.label : ''),\n      });\n      window._pivotLines.push(ln);\n    });\n",
        '    const confEl=document.getElementById(\'sr-confidence-val\');\n    const panel=document.getElementById(\'key-levels-panel\');\n    if(!pv.available){\n      if(confEl){ confEl.textContent=\'No data\'; confEl.style.color=\'var(--grey)\'; }\n      if(panel) panel.innerHTML=\'<div style="color:var(--grey);font-size:9px">No pivot data available</div>\';\n      return;\n    }\n    const levels=[\n      {label:\'R3\',price:pv.r3,color:\'var(--red)\'},\n      {label:\'R2\',price:pv.r2,color:\'var(--red)\'},\n      {label:\'R1\',price:pv.r1,color:\'var(--red)\'},\n      {label:\'P\', price:pv.pivot,color:\'var(--gold)\'},\n      {label:\'S1\',price:pv.s1,color:\'var(--green)\'},\n      {label:\'S2\',price:pv.s2,color:\'var(--green)\'},\n      {label:\'S3\',price:pv.s3,color:\'var(--green)\'},\n    ];\n    let minDistPct=Infinity;\n    const rows=levels.filter(lv=>lv.price).map(lv=>{\n      const distPct=currentPrice?Math.abs(currentPrice-lv.price)/currentPrice*100:100;\n      const near=distPct<=0.3;\n      if(distPct<minDistPct) minDistPct=distPct;\n      return `<div style="display:flex;justify-content:space-between;padding:2px 0;font-size:9px;${near?\'background:rgba(255,215,0,0.12);border-radius:2px;padding-left:3px\':\'\'}">\n        <span style="color:${lv.color};font-weight:${near?\'bold\':\'normal\'}">${near?\'🔥 \':\'\'}${lv.label}</span>\n        <span style="color:${near?\'var(--white)\':\'var(--grey)\'};font-weight:${near?\'bold\':\'normal\'}">${fmt6(lv.price)}</span>\n      </div>`;\n    }).join(\'\');\n    if(panel) panel.innerHTML=rows;\n',
    ),
    (
        "        if(window._whaleLines) window._whaleLines.forEach(l=>{try{candleSeries.removePriceLine(l);}catch(e){}});\n        window._whaleLines=[];\n        const _bidWall=(wd.walls||[]).find(w=>w.side==='BID');\n        const _askWall=(wd.walls||[]).find(w=>w.side==='ASK');\n        [_bidWall,_askWall].filter(Boolean).forEach(w=>{\n          const ln=candleSeries.createPriceLine({\n            price: w.price_level, color: w.side==='BID'?'#00ff88':'#ff2244',\n            lineWidth:1, lineStyle:2, axisLabelVisible:true,\n            title:(w.side==='BID'?'BUY ':'SELL ')+Math.round((w.size_usdt||0)/1000)+'K'\n          });\n          window._whaleLines.push(ln);\n        });\n",
        '        const _bidWall=(wd.walls||[]).find(w=>w.side===\'BID\');\n        const _askWall=(wd.walls||[]).find(w=>w.side===\'ASK\');\n        const wallPanel=document.getElementById(\'whale-wall-panel\');\n        if(wallPanel){\n          const wallRows=[_bidWall,_askWall].filter(Boolean).map(w=>{\n            const label=w.side===\'BID\'?\'BUY wall\':\'SELL wall\';\n            const color=w.side===\'BID\'?\'var(--green)\':\'var(--red)\';\n            return `<div style="display:flex;justify-content:space-between;padding:2px 0;font-size:9px">\n              <span style="color:${color}">${label}</span>\n              <span style="color:var(--grey)">${fmt6(w.price_level)} ($${Math.round((w.size_usdt||0)/1000)}K)</span>\n            </div>`;\n          }).join(\'\');\n          wallPanel.innerHTML = wallRows || \'<div style="color:var(--grey);font-size:9px">No walls nearby</div>\';\n        }\n',
    ),
    (
        '    <div id="${idPrefix}-status" style="font-size:8px;color:#666"></div>\n  `;\n\n  function initChartInstance(){\n    const box=document.getElementById(idPrefix+\'-box\');\n    if(!box || typeof LightweightCharts===\'undefined\') return;\n    try{\n      chart=LightweightCharts.createChart(box,{\n        autoSize:true,\n',
        '    <div id="${idPrefix}-levels" style="background:#0a0a14;border:1px solid #1e1e2e;border-radius:2px;padding:5px 7px;margin-bottom:5px">\n      <div style="color:var(--grey);font-size:8px">Loading key levels...</div>\n    </div>\n    <div id="${idPrefix}-status" style="font-size:8px;color:#666"></div>\n  `;\n\n  function initChartInstance(){\n    const box=document.getElementById(idPrefix+\'-box\');\n    const st=document.getElementById(idPrefix+\'-status\');\n    if(!box){ if(st) st.textContent=\'Chart container not found\'; return; }\n    if(typeof LightweightCharts===\'undefined\'){ if(st) st.textContent=\'Chart library not loaded\'; return; }\n    try{\n      const w = box.clientWidth || box.offsetWidth || 300;\n      const h = box.clientHeight || box.offsetHeight || 220;\n      chart=LightweightCharts.createChart(box,{\n        width:w, height:h, autoSize:true,\n',
    ),
    (
        "    }catch(e){console.warn('Scalp chart widget init failed:',e);}\n",
        "      // belt-and-suspenders: force a resize shortly after in case the\n      // container had 0 width at creation time (e.g. inside a just-opened\n      // accordion where layout hadn't settled yet)\n      setTimeout(()=>{\n        try{ if(chart) chart.resize(box.clientWidth||w, box.clientHeight||h); }catch(e){}\n      }, 300);\n    }catch(e){\n      console.warn('Scalp chart widget init failed:',e);\n      if(st) st.textContent='Chart init error: '+e.message;\n    }\n",
    ),
    (
        "      if(!candleSeries) return;\n      pivotLines.forEach(l=>{try{candleSeries.removePriceLine(l);}catch(e){}});\n      pivotLines=[];\n      const confEl=document.getElementById(idPrefix+'-conf');\n      if(!pv.available){ if(confEl) confEl.textContent='S/R Conf: no data'; return; }\n      const levels=[\n        {key:'s1',label:'S1',price:pv.s1,color:'#00ff88'},{key:'s2',label:'S2',price:pv.s2,color:'#00cc66'},{key:'s3',label:'S3',price:pv.s3,color:'#009944'},\n        {key:'r1',label:'R1',price:pv.r1,color:'#ff2244'},{key:'r2',label:'R2',price:pv.r2,color:'#dd1133'},{key:'r3',label:'R3',price:pv.r3,color:'#bb0022'},\n        {key:'pivot',label:'P',price:pv.pivot,color:'#ffd700'},\n      ];\n      let minDist=Infinity;\n      levels.forEach(lv=>{\n        if(!lv.price) return;\n        const distPct=currentPrice?Math.abs(currentPrice-lv.price)/currentPrice*100:100;\n        const near=distPct<=0.3;\n        const primary=['pivot','s1','r1'].includes(lv.key);\n        if(distPct<minDist) minDist=distPct;\n        const ln=candleSeries.createPriceLine({price:lv.price,color:lv.color,lineWidth:near?3:1,lineStyle:near?0:2,axisLabelVisible:near||primary,title:near?('🔥 '+lv.label):(primary?lv.label:'')});\n        pivotLines.push(ln);\n      });\n",
        '      const confEl=document.getElementById(idPrefix+\'-conf\');\n      const panel=document.getElementById(idPrefix+\'-levels\');\n      if(!pv.available){\n        if(confEl) confEl.textContent=\'S/R Conf: no data\';\n        if(panel) panel.innerHTML=\'<div style="color:var(--grey);font-size:8px">No pivot data</div>\';\n        return;\n      }\n      const levels=[\n        {label:\'R3\',price:pv.r3,color:\'var(--red)\'},{label:\'R2\',price:pv.r2,color:\'var(--red)\'},{label:\'R1\',price:pv.r1,color:\'var(--red)\'},\n        {label:\'P\', price:pv.pivot,color:\'var(--gold)\'},\n        {label:\'S1\',price:pv.s1,color:\'var(--green)\'},{label:\'S2\',price:pv.s2,color:\'var(--green)\'},{label:\'S3\',price:pv.s3,color:\'var(--green)\'},\n      ];\n      let minDist=Infinity;\n      const rows=levels.filter(lv=>lv.price).map(lv=>{\n        const distPct=currentPrice?Math.abs(currentPrice-lv.price)/currentPrice*100:100;\n        const near=distPct<=0.3;\n        if(distPct<minDist) minDist=distPct;\n        return `<div style="display:flex;justify-content:space-between;padding:1px 0;font-size:8px;${near?\'background:rgba(255,215,0,0.12);border-radius:2px;padding-left:3px\':\'\'}">\n          <span style="color:${lv.color};font-weight:${near?\'bold\':\'normal\'}">${near?\'🔥 \':\'\'}${lv.label}</span>\n          <span style="color:${near?\'var(--white)\':\'var(--grey)\'}">${fmt6(lv.price)}</span>\n        </div>`;\n      }).join(\'\');\n      if(panel) panel.innerHTML=rows;\n',
    ),
    (
        '  setTimeout(()=>{ initChartInstance(); load(); startCountdown(); }, 50);\n',
        "  setTimeout(()=>{\n    try{\n      initChartInstance();\n      load();\n      startCountdown();\n    }catch(e){\n      console.warn('Scalp widget deferred init failed:', e);\n      const st=document.getElementById(idPrefix+'-status');\n      if(st) st.textContent='Widget init error: '+e.message;\n    }\n  }, 300);\n",
    ),
]

if 'key-levels-panel' in html_content:
    print('index.html: chart declutter + blank-chart fix already present — skipping')
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

print('Done — chart declutter + blank Command-chart fix complete.')