import sys

# ══════════════════════════════════════════════════════════════
# Command tab charts robustness fix — the BTC/Manual charts were
# staying blank with no visible reason. Adds: an immediate
# 'Preparing chart…' status shown synchronously (so we can tell
# if init even runs), and a refresh() method that force-resizes
# + reloads the chart every time the accordion is reopened —
# covers the case where the chart lost its dimensions while its
# container sat hidden (display:none) during the accordion's
# closed state, which autoSize alone doesn't always recover from.
# ══════════════════════════════════════════════════════════════

HTML_PATH = 'V6_Master_Pro_UI/index.html'
with open(HTML_PATH, 'r', encoding='utf-8') as f:
    html_content = f.read()

HTML_EDITS = [
    (
        '  };\n\n  window.__scalpWidgets = window.__scalpWidgets || {};\n  window.__scalpWidgets[idPrefix] = api;\n',
        "    refresh(){\n      // Called every time the accordion is reopened. If the chart was\n      // never created (first run failed) or lost its dimensions while\n      // hidden (display:none), this re-inits or force-resizes it.\n      try{\n        if(!chart){ initChartInstance(); }\n        setTimeout(()=>{\n          try{\n            const box=document.getElementById(idPrefix+'-box');\n            if(chart && box) chart.resize(box.clientWidth||300, box.clientHeight||220);\n            load();\n          }catch(e){\n            const st=document.getElementById(idPrefix+'-status');\n            if(st) st.textContent='Refresh error: '+e.message;\n          }\n        }, 100);\n      }catch(e){\n        const st=document.getElementById(idPrefix+'-status');\n        if(st) st.textContent='Refresh error: '+e.message;\n      }\n    },\n  };\n\n  window.__scalpWidgets = window.__scalpWidgets || {};\n  window.__scalpWidgets[idPrefix] = api;\n\n  const initialStatus=document.getElementById(idPrefix+'-status');\n  if(initialStatus) initialStatus.textContent='Preparing chart…';\n",
    ),
    (
        "  if(container.querySelector('#cmd-btc-widget')) return; // already built — widgets manage their own refresh\n",
        "  if(container.querySelector('#cmd-btc-widget')){\n    // already built — force a resize+reload every time the accordion is\n    // reopened, in case the chart lost its dimensions while its container\n    // was hidden (display:none) during the accordion's closed state\n    if(window.__scalpWidgets){\n      if(window.__scalpWidgets['cmdbtc']) window.__scalpWidgets['cmdbtc'].refresh();\n      if(window.__scalpWidgets['cmdman']) window.__scalpWidgets['cmdman'].refresh();\n    }\n    return;\n  }\n",
    ),
]

if 'Preparing chart' in html_content:
    print('index.html: chart robustness fix already present — skipping')
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

print('Done — Command tab chart robustness fix complete.')