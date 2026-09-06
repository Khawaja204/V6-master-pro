import sys

# ══════════════════════════════════════════════════════════════
# Fix 1: 'Next: Neutral' always showing — the prediction logic
# required price to already be BEYOND the Bollinger Band AND RSI
# at an extreme AND the pattern to match one of only 3 exact
# names, all at once — too strict to ever fire in practice.
# Loosened to use the pattern's bullish/bearish DIRECTION and a
# 'near the band' zone instead of 'already pierced it', plus a
# milder bias tier so it gives a real read more often.
#
# Fix 2: Chart resetting to original zoom on double-click — this
# is Lightweight Charts' default double-click-to-reset behavior,
# which is easy to trigger by accident on a touchscreen while
# pinch-zooming/panning. Disabled via handleScale.axisDoubleClickReset.
# ══════════════════════════════════════════════════════════════

HTML_PATH = 'V6_Master_Pro_UI/index.html'
with open(HTML_PATH, 'r', encoding='utf-8') as f:
    html_content = f.read()

HTML_EDITS = [
    (
        "      timeScale:{borderColor:'#1e1e2e',timeVisible:true},\n",
        "      timeScale:{borderColor:'#1e1e2e',timeVisible:true},\n      handleScale:{axisDoubleClickReset:false},\n",
    ),
    (
        "function scalpPredictNext(pattern, rsi, price, bbUpper, bbLower){\n  const bullishPatterns=['Bullish Engulfing','Hammer','Morning Star'];\n  const bearishPatterns=['Bearish Engulfing','Shooting Star','Evening Star'];\n  if(price<=bbLower && rsi<30 && bullishPatterns.includes(pattern)) return {text:'Bullish Bounce', color:'var(--green)'};\n  if(price>=bbUpper && rsi>70 && bearishPatterns.includes(pattern)) return {text:'Bearish Reversal', color:'var(--red)'};\n",
        'function scalpPredictNext(patternDir, rsi, price, bbUpper, bbLower, bbMid){\n  // Near-band proximity instead of requiring price to have already\n  // pierced the band (rare) — within 15% of the band-to-mid distance\n  // counts as "near". Uses the pattern\'s bullish/bearish DIRECTION\n  // rather than a narrow whitelist of exact pattern names, so any\n  // bullish/bearish candle read at a stretched level counts — the\n  // strict version almost never fired in practice.\n  const band=Math.abs((bbMid!==undefined?bbMid:(bbUpper+bbLower)/2)-bbLower)||1;\n  const nearLower = price <= bbLower + band*0.15;\n  const nearUpper = price >= bbUpper - band*0.15;\n  if(nearLower && rsi<40 && patternDir===\'bullish\') return {text:\'Bullish Bounce\', color:\'var(--green)\'};\n  if(nearUpper && rsi>60 && patternDir===\'bearish\') return {text:\'Bearish Reversal\', color:\'var(--red)\'};\n  if(patternDir===\'bullish\' && rsi<45) return {text:\'Mild Bullish Bias\', color:\'var(--green)\'};\n  if(patternDir===\'bearish\' && rsi>55) return {text:\'Mild Bearish Bias\', color:\'var(--red)\'};\n',
    ),
    (
        '    const pred=scalpPredictNext(pattern.name, lastRsi, lastPrice, lastBBUpper, lastBBLower);\n',
        '    const pred=scalpPredictNext(pattern.dir, lastRsi, lastPrice, lastBBUpper, lastBBLower);\n',
    ),
]

if 'axisDoubleClickReset' in html_content:
    print('index.html: prediction fix + double-click fix already present — skipping')
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

print('Done — Next-candle prediction fixed, double-click zoom reset disabled.')