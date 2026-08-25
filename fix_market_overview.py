import sys, ast

# ══════════════════════════════════════════════════════════════
# Top Market Status Cards (CMC-style)
# Adds 4 live cards above the Command tab: Total Market Cap (24h
# change), a Top-20 basket index (avg 24h change, labeled plainly
# rather than as the proprietary CMC20 index), an approximate
# Altcoin Season Index (% of top 50 alts beating BTC over 30D —
# closest free-tier proxy to the standard 90D definition), and
# the Fear & Greed Index (alternative.me, free, no key).
# Written for the post-refactor module layout: refresh logic in
# main.py, the /market_overview route in routes/api.py, and the
# 4 cards + JS in V6_Master_Pro_UI/index.html.
# ══════════════════════════════════════════════════════════════

# ── main.py ──
MAIN_PATH = 'main.py'
with open(MAIN_PATH, 'r', encoding='utf-8') as f:
    MAIN_content = f.read()

MAIN_EDITS = [
    (
        '    detect_whale_copy_signals, is_stablecoin_pair,\n',
        '    detect_whale_copy_signals, is_stablecoin_pair, DEFAULT_STABLECOIN_BASES,\n',
    ),
    (
        '    "top_coin_today": None,\n    "volume_surge":   [],\n',
        '    "top_coin_today": None,\n    "volume_surge":   [],\n    "market_overview": {},\n',
    ),
    (
        '    volume-based daily/weekly %)."""\n',
        '    volume-based daily/weekly %). Also refreshes the Top Market Status\n    cards (total market cap, top-20 basket index, an approximate\n    Altcoin Season Index, and the Fear & Greed Index) in the same cycle\n    since they\'re all sourced from CoinGecko/alternative.me and share\n    the same 6h cadence."""\n',
    ),
    (
        '                        "per_page": 250, "page": page, "sparkline": "false",\n                        "price_change_percentage": "24h,7d"},\n',
        '                        "per_page": 250, "page": page, "sparkline": "false",\n                        "price_change_percentage": "24h,7d,30d"},\n',
    ),
    (
        '                "price_chg_24h_pct": c.get("price_change_percentage_24h_in_currency"),\n                "price_chg_7d_pct": c.get("price_change_percentage_7d_in_currency"),\n',
        '                "price_chg_24h_pct": c.get("price_change_percentage_24h_in_currency"),\n                "price_chg_7d_pct": c.get("price_change_percentage_7d_in_currency"),\n                "price_chg_30d_pct": c.get("price_change_percentage_30d_in_currency"),\n',
    ),
    (
        '        log.warning(f"Market cap refresh failed: {e}")\n\n\n',
        '        log.warning(f"Market cap refresh failed: {e}")\n\n\ndef _refresh_market_overview(coins: list):\n    """Top Market Status cards: Total Market Cap (24h change), a Top-20\n    basket index (avg 24h change of the top 20 non-stablecoins — labeled\n    plainly rather than as the proprietary CMC20 index, since that figure\n    itself isn\'t publicly available without a paid CoinMarketCap key), an\n    approximate Altcoin Season Index (% of the top 50 non-stablecoin,\n    non-BTC coins that outperformed BTC over 30D — the closest window the\n    free CoinGecko markets endpoint offers to the standard 90D definition,\n    clearly labeled as an approximation), and the Fear & Greed Index\n    (alternative.me, free, no key)."""\n    import requests as _rq\n    overview = GLOBAL_DATA.get("market_overview", {})\n    try:\n        g = _rq.get("https://api.coingecko.com/api/v3/global", timeout=15)\n        if g.status_code == 200:\n            gd = g.json().get("data", {})\n            overview["total_market_cap_usd"] = gd.get("total_market_cap", {}).get("usd", 0)\n            overview["market_cap_change_24h_pct"] = round(gd.get("market_cap_change_percentage_24h_usd", 0) or 0, 2)\n    except Exception as e:\n        log.warning(f"[MARKET-OVERVIEW] global fetch failed: {e}")\n\n    try:\n        stables = set(DEFAULT_STABLECOIN_BASES)\n        non_stable = [c for c in coins if (c.get("symbol") or "").upper() not in stables]\n        top20 = non_stable[:20]\n        chg24 = [c.get("price_change_percentage_24h_in_currency") for c in top20\n                 if c.get("price_change_percentage_24h_in_currency") is not None]\n        overview["top20_basket_avg_24h_pct"] = round(sum(chg24) / len(chg24), 2) if chg24 else 0.0\n\n        btc = next((c for c in coins if (c.get("symbol") or "").upper() == "BTC"), None)\n        btc_30d = btc.get("price_change_percentage_30d_in_currency") if btc else None\n        top50_alts = [c for c in non_stable[:51] if (c.get("symbol") or "").upper() != "BTC"][:50]\n        if btc_30d is not None and top50_alts:\n            valid = [c for c in top50_alts if c.get("price_change_percentage_30d_in_currency") is not None]\n            outperformed = [c for c in valid if c["price_change_percentage_30d_in_currency"] > btc_30d]\n            overview["altcoin_season_index"] = round(len(outperformed) / len(valid) * 100) if valid else None\n        else:\n            overview["altcoin_season_index"] = None\n        overview["altcoin_season_note"] = "Approx. — % of top 50 alts beating BTC over 30D (free-tier data; standard index uses 90D)"\n    except Exception as e:\n        log.warning(f"[MARKET-OVERVIEW] basket/altseason calc failed: {e}")\n\n    try:\n        fg = _rq.get("https://api.alternative.me/fng/", timeout=10)\n        if fg.status_code == 200:\n            fgd = (fg.json().get("data") or [{}])[0]\n            overview["fear_greed_value"] = int(fgd.get("value", 0))\n            overview["fear_greed_label"] = fgd.get("value_classification", "—")\n    except Exception as e:\n        log.warning(f"[MARKET-OVERVIEW] fear&greed fetch failed: {e}")\n\n    overview["updated_at"] = _pkt_ts()\n    GLOBAL_DATA["market_overview"] = overview\n    log.info(f"[MARKET-OVERVIEW] Refreshed: {overview}")\n\n\n',
    ),
    (
        '        _refresh_market_cap_data()\n        time.sleep(6 * 3600)\n',
        '        _refresh_market_cap_data()\n        time.sleep(6 * 3600)\n\n\ndef market_overview_refresh_loop():\n    """Top Market Status cards (Total Market Cap, Top-20 basket index,\n    approx. Altcoin Season Index, Fear & Greed) refresh every 15 minutes —\n    much faster than the 6h per-coin market-cap cycle above, since these\n    are cheap aggregate stats users expect to look current. Uses its own\n    lightweight top-50 CoinGecko fetch rather than waiting on the heavy\n    top-500 cycle. Waits 90s on boot to stagger away from the other\n    startup fetches."""\n    import requests as _rq\n    time.sleep(90)\n    while True:\n        try:\n            r = _rq.get(\n                "https://api.coingecko.com/api/v3/coins/markets",\n                params={"vs_currency": "usd", "order": "market_cap_desc",\n                        "per_page": 50, "page": 1, "sparkline": "false",\n                        "price_change_percentage": "24h,30d"},\n                timeout=15,\n            )\n            coins50 = r.json() if r.status_code == 200 else []\n            _refresh_market_overview(coins50)\n        except Exception as e:\n            log.warning(f"[MARKET-OVERVIEW] loop failed: {e}")\n        time.sleep(15 * 60)\n',
    ),
    (
        '    threading.Thread(target=combo_check_loop,      daemon=True).start()\n    threading.Thread(target=market_cap_refresh_loop, daemon=True).start()\n',
        '    threading.Thread(target=combo_check_loop,      daemon=True).start()\n    threading.Thread(target=market_cap_refresh_loop, daemon=True).start()\n    threading.Thread(target=market_overview_refresh_loop, daemon=True).start()\n',
    ),
]

if 'market_overview_refresh_loop' in MAIN_content:
    print('main.py: already patched — skipping')
else:
    for i, (old, new) in enumerate(MAIN_EDITS, 1):
        cnt = MAIN_content.count(old)
        if cnt != 1:
            print(f'main.py EDIT {i}: FAILED - expected 1 match, found {cnt}. Aborting, no changes written to this file.')
            sys.exit(1)
        MAIN_content = MAIN_content.replace(old, new, 1)
        print(f'main.py EDIT {i}: applied OK')
    ast.parse(MAIN_content)
    with open(MAIN_PATH, 'w', encoding='utf-8') as f:
        f.write(MAIN_content)
    print('main.py: all edits applied OK')

# ── routes/api.py ──
API_PATH = 'routes/api.py'
with open(API_PATH, 'r', encoding='utf-8') as f:
    API_content = f.read()

API_EDITS = [
    (
        "_LOCAL_NAMES = {'chart_data', 'rsi_scan', 'get_data', 'status', 'whale_copy_data_route', 'live_score_route', 'large_trades_summary_route', 'api_wc_learning', 'dashboard_data', 'large_trades_data_route', 'sniper_data', 'focus_mode', 'health_check', 'focus_data', 'large_trades_list_route', 'combo_bot_data_route', 'v6_bot_data_route', 'whale_detail_route', 'api_onchain', 'eth_onchain_data_route', 'system_health'}\n",
        "_LOCAL_NAMES = {'chart_data', 'rsi_scan', 'get_data', 'status', 'whale_copy_data_route', 'live_score_route', 'large_trades_summary_route', 'api_wc_learning', 'dashboard_data', 'large_trades_data_route', 'sniper_data', 'focus_mode', 'health_check', 'focus_data', 'large_trades_list_route', 'combo_bot_data_route', 'v6_bot_data_route', 'whale_detail_route', 'api_onchain', 'eth_onchain_data_route', 'system_health', 'market_overview_route'}\n",
    ),
    (
        '        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),\n    })\n',
        '        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),\n    })\n\n\n@bp.route("/market_overview")\n@_sync_main_state\ndef market_overview_route():\n    return jsonify(GLOBAL_DATA.get("market_overview", {}))\n',
    ),
]

if 'market_overview_route' in API_content:
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
        '.next-pill{background:#1a1a2e;border:1px solid var(--border);padding:2px 8px;border-radius:10px;font-size:10px}\n.conn-dot{color:var(--green)}\n',
        '.next-pill{background:#1a1a2e;border:1px solid var(--border);padding:2px 8px;border-radius:10px;font-size:10px}\n.conn-dot{color:var(--green)}\n\n/* TOP MARKET STATUS CARDS */\n#market-overview-row{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;padding:6px 10px;background:#0a0a12;border-bottom:1px solid var(--border)}\n.mo-card{background:#0e0e18;border:1px solid var(--border);border-radius:2px;padding:7px 5px;text-align:center}\n.mo-label{font-size:8px;color:var(--grey);letter-spacing:.4px;text-transform:uppercase}\n.mo-value{font-size:14px;font-weight:bold;color:var(--white);margin-top:3px}\n.mo-sub{font-size:8px;color:var(--grey);margin-top:2px}\n@media(max-width:600px){#market-overview-row{grid-template-columns:1fr 1fr}}\n',
    ),
    (
        '    <span class="next-pill">next <span id="next-cnt">30</span>s <span class="blink" style="color:var(--green)">●</span></span>\n    <span><span class="conn-dot">●</span> connected: <span style="color:var(--orange)" id="sb-exch">BINANCE</span></span>\n',
        '    <span class="next-pill">next <span id="next-cnt">30</span>s <span class="blink" style="color:var(--green)">●</span></span>\n    <span><span class="conn-dot">●</span> connected: <span style="color:var(--orange)" id="sb-exch">BINANCE</span></span>\n  </div>\n</div>\n\n<!-- TOP MARKET STATUS CARDS -->\n<div id="market-overview-row">\n  <div class="mo-card">\n    <div class="mo-label">TOTAL MKT CAP</div>\n    <div class="mo-value" id="mo-mcap">—</div>\n    <div class="mo-sub" id="mo-mcap-chg">—</div>\n  </div>\n  <div class="mo-card">\n    <div class="mo-label">TOP 20 BASKET</div>\n    <div class="mo-value" id="mo-top20">—</div>\n    <div class="mo-sub">avg 24h chg</div>\n  </div>\n  <div class="mo-card">\n    <div class="mo-label">ALTCOIN SEASON</div>\n    <div class="mo-value" id="mo-altseason">—</div>\n    <div class="mo-sub">approx, 30D vs BTC</div>\n  </div>\n  <div class="mo-card">\n    <div class="mo-label">FEAR &amp; GREED</div>\n    <div class="mo-value" id="mo-fng">—</div>\n    <div class="mo-sub" id="mo-fng-label">—</div>\n',
    ),
    (
        '  setTimeout(function(){initChart();fetchChart();},500);\n  fetchAll();\n',
        '  setTimeout(function(){initChart();fetchChart();},500);\n  fetchAll();\n  fetchMarketOverview();\n  setInterval(fetchMarketOverview, 90000);\n',
    ),
    (
        "  if(accWhale && accWhale.style.display==='block') renderCmdWhale();\n  if(accHistory && accHistory.style.display==='block') renderCmdHistory();\n",
        "  if(accWhale && accWhale.style.display==='block') renderCmdWhale();\n  if(accHistory && accHistory.style.display==='block') renderCmdHistory();\n}\n\n/* ── Top Market Status Cards (Total Mkt Cap / Top-20 Basket / Altcoin Season / Fear&Greed) ── */\nfunction fmtBigUsd(n){\n  if(!n) return '—';\n  if(n>=1e12) return '$'+(n/1e12).toFixed(2)+'T';\n  if(n>=1e9)  return '$'+(n/1e9).toFixed(2)+'B';\n  if(n>=1e6)  return '$'+(n/1e6).toFixed(2)+'M';\n  return '$'+n.toLocaleString();\n}\n\nfunction fetchMarketOverview(){\n  fetch('/market_overview').then(r=>r.json()).then(d=>{\n    const mcapEl=document.getElementById('mo-mcap');\n    const mcapChgEl=document.getElementById('mo-mcap-chg');\n    if(mcapEl) mcapEl.textContent = fmtBigUsd(d.total_market_cap_usd);\n    if(mcapChgEl){\n      const chg=d.market_cap_change_24h_pct;\n      mcapChgEl.textContent = (chg===undefined||chg===null) ? '—' : (chg>=0?'+':'')+chg+'% 24h';\n      mcapChgEl.style.color = (chg===undefined||chg===null) ? 'var(--grey)' : (chg>=0 ? 'var(--green)' : 'var(--red)');\n    }\n    const top20El=document.getElementById('mo-top20');\n    if(top20El){\n      const v=d.top20_basket_avg_24h_pct;\n      top20El.textContent = (v===undefined||v===null) ? '—' : (v>=0?'+':'')+v+'%';\n      top20El.style.color = (v===undefined||v===null) ? 'var(--white)' : (v>=0 ? 'var(--green)' : 'var(--red)');\n    }\n    const altEl=document.getElementById('mo-altseason');\n    if(altEl){\n      const v=d.altcoin_season_index;\n      altEl.textContent = (v===null||v===undefined) ? '—' : v+'/100';\n      altEl.style.color = (v===null||v===undefined) ? 'var(--white)' : (v>=75 ? 'var(--green)' : v<=25 ? 'var(--red)' : 'var(--gold)');\n    }\n    const fngEl=document.getElementById('mo-fng');\n    const fngLblEl=document.getElementById('mo-fng-label');\n    if(fngLblEl) fngLblEl.textContent = d.fear_greed_label || '—';\n    if(fngEl){\n      const v=d.fear_greed_value;\n      fngEl.textContent = (v===undefined||v===null) ? '—' : v;\n      fngEl.style.color = (v===undefined||v===null) ? 'var(--white)' : (v>=55 ? 'var(--green)' : v<=45 ? 'var(--red)' : 'var(--gold)');\n    }\n  }).catch(()=>{});\n",
    ),
]

if 'market-overview-row' in HTML_content:
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

# Keep the auto-synced root-level copy in sync too (matches sync_ui()'s own behavior)
import shutil
try:
    shutil.copy2('V6_Master_Pro_UI/index.html', 'index.html')
    print('index.html (root copy): synced from V6_Master_Pro_UI/index.html')
except Exception as e:
    print(f'Root index.html sync skipped: {e}')

print('Done — Top Market Status Cards patch complete.')