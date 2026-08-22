import sys, ast

# ══════════════════════════════════════════════════════════════
# Scalping Strategy Advisor — adds EMA9/21 crossover + Bollinger
# squeeze detection to logic.py, wires them into main.py's scan
# loop + Sniper live-score path, and adds the 'Best Scalping
# Strategy' card (Sniper) + Strategy column (Scanner) to the UI.
# ══════════════════════════════════════════════════════════════

# ── 1. logic.py: append the 6 new strategy-advisor functions ──
LOGIC_PATH = 'logic.py'
with open(LOGIC_PATH, 'r', encoding='utf-8') as f:
    logic_content = f.read()

LOGIC_APPEND = '\n# ══════════════════════════════════════════════════════════════════════════════\n# SCALPING STRATEGY ADVISOR — matches current per-coin conditions against the\n# 6 classic scalping strategies (EMA cross, RSI, Bollinger squeeze, S/R bounce,\n# 1-min momentum, order-book) and picks the strongest current match.\n# Reuses existing indicators (RSI/ATR/OBI/walls/volume-surge) plus two new\n# lightweight ones (EMA 9/21, Bollinger Bands) computed from the same closes\n# list already being fetched — no extra API calls beyond one klines fetch.\n# ══════════════════════════════════════════════════════════════════════════════\n\ndef _ema_series(closes: list, period: int) -> list:\n    """EMA series aligned to `closes` (None-padded for the warm-up window),\n    seeded with a simple average over the first `period` closes."""\n    if len(closes) < period:\n        return [None] * len(closes)\n    ema = [None] * (period - 1)\n    seed = sum(closes[:period]) / period\n    ema.append(seed)\n    k = 2 / (period + 1)\n    for price in closes[period:]:\n        ema.append(ema[-1] * (1 - k) + price * k)\n    return ema\n\n\ndef detect_ema_crossover(closes: list, fast: int = 9, slow: int = 21, lookback: int = 3) -> dict:\n    """Detects a fresh EMA fast/slow crossover within the last `lookback`\n    candles. Returns cross direction + whether it JUST happened (fresh)."""\n    n = len(closes)\n    if n < slow + lookback:\n        return {"cross": None, "fresh": False, "fast": None, "slow": None}\n    ema_f = _ema_series(closes, fast)\n    ema_s = _ema_series(closes, slow)\n    diffs = []\n    for i in range(max(0, n - lookback - 1), n):\n        if ema_f[i] is None or ema_s[i] is None:\n            continue\n        diffs.append(ema_f[i] - ema_s[i])\n    if len(diffs) < 2:\n        return {"cross": None, "fresh": False, "fast": ema_f[-1], "slow": ema_s[-1]}\n    cross, fresh = None, False\n    for i in range(1, len(diffs)):\n        if diffs[i - 1] <= 0 and diffs[i] > 0:\n            cross, fresh = "BULLISH", True\n        elif diffs[i - 1] >= 0 and diffs[i] < 0:\n            cross, fresh = "BEARISH", True\n    if cross is None:\n        cross = "BULLISH" if diffs[-1] > 0 else "BEARISH"\n    return {\n        "cross": cross, "fresh": fresh,\n        "fast": round(ema_f[-1], 8) if ema_f[-1] is not None else None,\n        "slow": round(ema_s[-1], 8) if ema_s[-1] is not None else None,\n    }\n\n\ndef calculate_bollinger(closes: list, period: int = 20, num_std: float = 2.0) -> dict:\n    """Standard Bollinger Bands (SMA mid, +/- num_std population std-dev)."""\n    if len(closes) < period:\n        return {"upper": None, "lower": None, "mid": None, "bandwidth_pct": None}\n    window = closes[-period:]\n    mid = sum(window) / period\n    variance = sum((c - mid) ** 2 for c in window) / period\n    std = variance ** 0.5\n    upper = mid + num_std * std\n    lower = mid - num_std * std\n    bandwidth_pct = ((upper - lower) / mid * 100) if mid else 0\n    return {\n        "upper": round(upper, 8), "lower": round(lower, 8), "mid": round(mid, 8),\n        "bandwidth_pct": round(bandwidth_pct, 3),\n    }\n\n\ndef detect_bollinger_state(closes: list, period: int = 20, num_std: float = 2.0) -> dict:\n    """Current Bollinger bands + a squeeze flag (bandwidth contracted vs.\n    ~10 candles ago) + breakout flag (last close outside current bands).\n    No stored history needed — both windows come from the same closes list."""\n    if len(closes) < period + 10:\n        return {"squeeze": False, "breakout": None, "bandwidth_pct": None,\n                 "upper": None, "lower": None, "mid": None}\n    current = calculate_bollinger(closes, period, num_std)\n    prior = calculate_bollinger(closes[:-10], period, num_std)\n    squeeze = bool(\n        current["bandwidth_pct"] and prior["bandwidth_pct"]\n        and current["bandwidth_pct"] < prior["bandwidth_pct"] * 0.7\n    )\n    breakout = None\n    last_price = closes[-1]\n    if current["upper"] is not None and last_price > current["upper"]:\n        breakout = "UP"\n    elif current["lower"] is not None and last_price < current["lower"]:\n        breakout = "DOWN"\n    return {**current, "squeeze": squeeze, "breakout": breakout}\n\n\ndef fetch_strategy_indicators(symbol: str, interval: str = "5m", limit: int = 60) -> dict:\n    """Single klines fetch feeding both the EMA-crossover and Bollinger\n    detectors for the Scalping Strategy Advisor (kept separate from the\n    existing RSI/ATR fetches so callers can reuse a shorter scalp-friendly\n    timeframe like 5m without touching the 1h-based RSI/ATR pipeline)."""\n    klines = fetch_klines(symbol, interval, limit)\n    if not klines:\n        return {"ema": {"cross": None, "fresh": False}, "bollinger": {"squeeze": False, "breakout": None}}\n    closes = [float(k[4]) for k in klines]\n    return {\n        "ema": detect_ema_crossover(closes),\n        "bollinger": detect_bollinger_state(closes),\n    }\n\n\ndef pick_best_strategy(rsi: float, ema_state: dict, boll_state: dict,\n                        walls: list, obi_r: dict, in_volume_surge: bool,\n                        price: float, market_regime: str = "RANGING") -> dict:\n    """\n    Scores each of the 6 classic scalping strategies (per the reference\n    doc: EMA 9/21 crossover, RSI reversal, Bollinger squeeze/breakout,\n    Support/Resistance wall bounce, 1-min volume momentum, Order-book/OBI)\n    against the coin\'s current live conditions, 0-100 each, and returns the\n    strongest match plus every candidate for transparency. Pure heuristic —\n    no ML, mirrors the classic definitions of each strategy.\n    """\n    candidates = []\n\n    # 1. EMA 9/21 Crossover\n    ema_score, ema_reason = 0, "No fresh EMA 9/21 cross"\n    if ema_state and ema_state.get("cross") and ema_state.get("fresh"):\n        ema_score = 80 if market_regime == "TRENDING" else 60\n        ema_reason = f"Fresh {ema_state[\'cross\'].lower()} EMA 9/21 cross"\n    candidates.append({"strategy": "EMA 9/21 Crossover", "score": ema_score, "reason": ema_reason})\n\n    # 2. RSI Scalping\n    rsi_score, rsi_reason = 0, "RSI not at a reversal extreme"\n    if rsi is not None:\n        if rsi <= 32:\n            rsi_score = 70\n            rsi_reason = f"RSI {rsi} near oversold — watch for bounce"\n        elif rsi >= 68:\n            rsi_score = 70\n            rsi_reason = f"RSI {rsi} near overbought — watch for pullback"\n    candidates.append({"strategy": "RSI Scalping", "score": rsi_score, "reason": rsi_reason})\n\n    # 3. Bollinger Bands Squeeze\n    boll_score, boll_reason = 0, "No squeeze/breakout detected"\n    if boll_state:\n        if boll_state.get("breakout"):\n            boll_score = 85\n            boll_reason = (f"Bollinger breakout {boll_state[\'breakout\']} after squeeze"\n                            if boll_state.get("squeeze") else f"Bollinger breakout {boll_state[\'breakout\']}")\n        elif boll_state.get("squeeze"):\n            boll_score = 55\n            boll_reason = "Bands squeezing — breakout may be near"\n    candidates.append({"strategy": "Bollinger Bands Squeeze", "score": boll_score, "reason": boll_reason})\n\n    # 4. Support/Resistance Bounce (whale order-book walls)\n    sr_score, sr_reason = 0, "No strong wall nearby"\n    if walls and price:\n        nearest_bid = next((w for w in walls if w.get("side") == "BID"), None)\n        nearest_ask = next((w for w in walls if w.get("side") == "ASK"), None)\n        if nearest_bid and nearest_bid.get("dist_pct", 99) <= 0.5:\n            sr_score = 75\n            sr_reason = f"Price within {nearest_bid[\'dist_pct\']}% of bid wall support (${nearest_bid.get(\'size_usdt\',0):,.0f})"\n        if nearest_ask and nearest_ask.get("dist_pct", 99) <= 0.5 and nearest_ask.get("dist_pct", 99) < (nearest_bid.get("dist_pct", 99) if nearest_bid else 99):\n            sr_score = 75\n            sr_reason = f"Price within {nearest_ask[\'dist_pct\']}% of ask wall resistance (${nearest_ask.get(\'size_usdt\',0):,.0f})"\n    candidates.append({"strategy": "Support/Resistance Bounce", "score": sr_score, "reason": sr_reason})\n\n    # 5. 1-Minute Momentum (volume surge)\n    mom_score = 90 if in_volume_surge else 0\n    mom_reason = "Active volume surge — momentum play" if in_volume_surge else "No volume surge right now"\n    candidates.append({"strategy": "1-Minute Momentum", "score": mom_score, "reason": mom_reason})\n\n    # 6. Order Book / Level 2 (OBI)\n    ob_score, ob_reason = 0, "No strong order-book imbalance"\n    obi_val = (obi_r or {}).get("obi", 0) or 0\n    if obi_r and obi_r.get("spike"):\n        ob_score = 80\n        ob_reason = f"OBI spike detected ({obi_r.get(\'direction\',\'\')})"\n    elif abs(obi_val) > 0.15:\n        ob_score = 55\n        ob_reason = f"Notable order-book imbalance (OBI {obi_val:.2f})"\n    candidates.append({"strategy": "Order Book / Level 2", "score": ob_score, "reason": ob_reason})\n\n    candidates.sort(key=lambda c: c["score"], reverse=True)\n    best = candidates[0]\n    return {\n        "best_strategy": best["strategy"] if best["score"] > 0 else "No strong scalp setup right now",\n        "best_score": best["score"],\n        "best_reason": best["reason"],\n        "candidates": candidates,\n    }\n'

if 'def pick_best_strategy(' in logic_content:
    print('logic.py: strategy advisor functions already present — skipping append')
else:
    logic_content += LOGIC_APPEND
    with open(LOGIC_PATH, 'w', encoding='utf-8') as f:
        f.write(logic_content)
    ast.parse(logic_content)
    print('logic.py: appended OK, syntax-checked OK')

# ── 2. main.py: wire strategy advisor into scan loop + live-score ──
MAIN_PATH = 'main.py'
with open(MAIN_PATH, 'r', encoding='utf-8') as f:
    main_content = f.read()

MAIN_EDITS = [
    (
        '    estimate_time_to_target, fetch_large_trades, fetch_eth_exchange_flows,\n    detect_combo_signals,\n',
        '    estimate_time_to_target, fetch_large_trades, fetch_eth_exchange_flows,\n    detect_combo_signals,\n    fetch_strategy_indicators, pick_best_strategy,\n',
    ),
    (
        '    sizing = compute_position_size(inst, CONFIG)\n\n',
        '    sizing = compute_position_size(inst, CONFIG)\n\n    _strat_ind = fetch_strategy_indicators(symbol)\n    mkt_reg_early = GLOBAL_DATA.get("market_regime", "RANGING")\n    _surge_syms = {v["symbol"] for v in GLOBAL_DATA.get("volume_surge", [])}\n    scalping = pick_best_strategy(\n        rsi=rsi, ema_state=_strat_ind["ema"], boll_state=_strat_ind["bollinger"],\n        walls=walls, obi_r=obi_r, in_volume_surge=(symbol in _surge_syms),\n        price=price, market_regime=mkt_reg_early,\n    )\n\n',
    ),
    (
        '        "macd_hist": macd_d.get("hist", 0.0), "tp_zones": tp,\n        "inst": inst, "sizing": sizing, "confidence": conf, "pattern": pattern_d,\n',
        '        "macd_hist": macd_d.get("hist", 0.0), "tp_zones": tp,\n        "inst": inst, "sizing": sizing, "confidence": conf, "pattern": pattern_d,\n        "scalping_strategy": scalping,\n',
    ),
    (
        '                        except Exception as _me:\n                            log.debug(f"[V6 MTF] {sym} failed: {_me}")\n',
        '                        except Exception as _me:\n                            log.debug(f"[V6 MTF] {sym} failed: {_me}")\n                    try:\n                        _strat_ind = fetch_strategy_indicators(sym)\n                        _in_surge  = sym in {v["symbol"] for v in GLOBAL_DATA.get("volume_surge", [])}\n                        scalping   = pick_best_strategy(\n                            rsi=coin.get("rsi", 50), ema_state=_strat_ind["ema"],\n                            boll_state=_strat_ind["bollinger"], walls=walls, obi_r=obi_r,\n                            in_volume_surge=_in_surge, price=price,\n                            market_regime=GLOBAL_DATA.get("market_regime", "RANGING"),\n                        )\n                    except Exception as _se:\n                        log.debug(f"[Strategy Advisor] {sym} failed: {_se}")\n                        scalping = {"best_strategy": "—", "best_score": 0, "best_reason": "", "candidates": []}\n',
    ),
    (
        '                        "mtf":        _mtf_result,\n                        "pattern":    pattern_d,\n',
        '                        "mtf":        _mtf_result,\n                        "pattern":    pattern_d,\n                        "scalping_strategy": scalping,\n',
    ),
]

if 'fetch_strategy_indicators, pick_best_strategy' in main_content:
    print('main.py: strategy advisor already wired — skipping edits')
else:
    for i, (old, new) in enumerate(MAIN_EDITS, 1):
        cnt = main_content.count(old)
        if cnt != 1:
            print(f'main.py EDIT {i}: FAILED - expected 1 match, found {cnt}. Aborting, no changes written to main.py.')
            sys.exit(1)
        main_content = main_content.replace(old, new, 1)
        print(f'main.py EDIT {i}: applied OK')
    ast.parse(main_content)
    with open(MAIN_PATH, 'w', encoding='utf-8') as f:
        f.write(main_content)
    print('main.py: all edits applied, syntax-checked OK')

# ── 3. V6_Master_Pro_UI/index.html: Sniper card + Scanner column ──
HTML_PATH = 'V6_Master_Pro_UI/index.html'
with open(HTML_PATH, 'r', encoding='utf-8') as f:
    html_content = f.read()

HTML_EDITS = [
    (
        '          <button class="exec-btn panic exec-btn-secondary" onclick="openPanicModal()">⛔ PANIC – CANCEL ALL</button>\n        </div>\n      </div>\n    </div>\n  </div>\n\n',
        '          <button class="exec-btn panic exec-btn-secondary" onclick="openPanicModal()">⛔ PANIC – CANCEL ALL</button>\n        </div>\n      </div>\n    </div>\n  </div>\n\n  <!-- SCALPING STRATEGY ADVISOR -->\n  <div class="card" style="margin-top:8px">\n    <div class="ch" style="font-size:10px">🧭 Best Scalping Strategy Right Now</div>\n    <div class="cb">\n      <div id="strat-best-box" style="background:#0a0a14;border:1px solid var(--border);border-radius:2px;padding:10px;margin-bottom:8px">\n        <div id="strat-best-name" style="font-size:13px;font-weight:bold;color:var(--grey)">Waiting for data...</div>\n        <div id="strat-best-reason" style="font-size:10px;color:var(--grey);margin-top:3px">—</div>\n      </div>\n      <div id="strat-candidates" style="font-size:9px"></div>\n    </div>\n  </div>\n\n',
    ),
    (
        '      <tr><th>#</th><th>Coin</th><th>Folder</th><th>Light</th><th>Inst%</th><th>Conf%</th><th>WhalePow</th><th>OFI</th><th>SL</th><th>TP1</th><th>TP2</th><th>TP3</th><th>Action</th></tr>\n',
        '      <tr><th>#</th><th>Coin</th><th>Folder</th><th>Light</th><th>Inst%</th><th>Conf%</th><th>WhalePow</th><th>OFI</th><th>Strategy</th><th>SL</th><th>TP1</th><th>TP2</th><th>TP3</th><th>Action</th></tr>\n',
    ),
    (
        '      <tr><td colspan="13" style="text-align:center;color:var(--grey);padding:20px">Loading scanner data...</td></tr>\n',
        '      <tr><td colspan="14" style="text-align:center;color:var(--grey);padding:20px">Loading scanner data...</td></tr>\n',
    ),
    (
        '      }).catch(()=>{});\n  });\n}\n\n',
        '      }).catch(()=>{});\n  });\n}\n\nfunction renderStrategyAdvisor(scalping){\n  const nameEl=document.getElementById(\'strat-best-name\');\n  const reasonEl=document.getElementById(\'strat-best-reason\');\n  const listEl=document.getElementById(\'strat-candidates\');\n  if(!scalping || !nameEl){\n    if(nameEl){ nameEl.textContent=\'Waiting for data...\'; nameEl.style.color=\'var(--grey)\'; }\n    if(reasonEl) reasonEl.textContent=\'—\';\n    if(listEl) listEl.innerHTML=\'\';\n    return;\n  }\n  const hasMatch = (scalping.best_score||0) > 0;\n  nameEl.textContent = (hasMatch?\'🎯 \':\'\') + (scalping.best_strategy||\'—\');\n  nameEl.style.color = hasMatch ? \'var(--green)\' : \'var(--grey)\';\n  if(reasonEl) reasonEl.textContent = scalping.best_reason || \'—\';\n  const cands = scalping.candidates || [];\n  if(listEl){\n    listEl.innerHTML = cands.map(c=>{\n      const on = c.score>0;\n      return `<div style="display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #111">\n        <span style="color:${on?\'var(--white)\':\'var(--grey)\'}">${c.strategy}</span>\n        <span style="color:${on?\'var(--green)\':\'var(--grey)\'}">${c.score}%</span>\n      </div>`;\n    }).join(\'\');\n  }\n}\n\n',
    ),
    (
        "        drawGauge('g-bsp',bp2,bp2>50?'#00ff88':'#ff2244');\n        set('g-bsp-val', bp2>50?'YES':'NO');\n",
        "        drawGauge('g-bsp',bp2,bp2>50?'#00ff88':'#ff2244');\n        set('g-bsp-val', bp2>50?'YES':'NO');\n        renderStrategyAdvisor(match.scalping_strategy);\n",
    ),
    (
        "            const wb=document.getElementById('warn-box'); if(wb) wb.style.display='none';\n            set('reason-txt','No institutional signal for this coin yet');\n",
        "            const wb=document.getElementById('warn-box'); if(wb) wb.style.display='none';\n            set('reason-txt','No institutional signal for this coin yet');\n            renderStrategyAdvisor(null);\n",
    ),
    (
        '            try{candleSeries.setMarkers(lmarkers);}catch(e){}\n          }\n',
        '            try{candleSeries.setMarkers(lmarkers);}catch(e){}\n          }\n          renderStrategyAdvisor(ls.scalping_strategy);\n',
    ),
    (
        "\nlet _lastMSKey='';\n",
        "\nlet _lastMSKey='';\n/* ── PANIC button double-confirmation modal ── */\n",
    ),
    (
        '  if(!coins.length){tbody.innerHTML=\'<tr><td colspan="13" style="text-align:center;color:var(--grey);padding:16px">Waiting for data...</td></tr>\';return;}\n',
        '  if(!coins.length){tbody.innerHTML=\'<tr><td colspan="14" style="text-align:center;color:var(--grey);padding:16px">Waiting for data...</td></tr>\';return;}\n',
    ),
    (
        "    const sym=(c.symbol||'').replace('USDT','');\n    const rowCls=wp>70?'hot':lbl==='AVOID'?'avoid':'';\n",
        '    const sym=(c.symbol||\'\').replace(\'USDT\',\'\');\n    const rowCls=wp>70?\'hot\':lbl===\'AVOID\'?\'avoid\':\'\';\n    const scalp=c.scalping_strategy||{};\n    const scalpOn=(scalp.best_score||0)>0;\n    const scalpTag=scalpOn\n      ? `<span style="color:var(--green);font-size:8px" title="${(scalp.best_reason||\'\').replace(/"/g,\'\')}">${scalp.best_strategy}</span>`\n      : `<span style="color:var(--grey);font-size:8px">—</span>`;\n',
    ),
    (
        '      <td>${wp}%<div><span class="mb-wrap"><span class="mb" style="width:${Math.min(wp,100)}%;background:${wc}"></span></span></div></td>\n      <td style="color:var(--grey)">${inst.ofi_score?parseFloat(inst.ofi_score).toFixed(1):\'—\'}</td>\n',
        '      <td>${wp}%<div><span class="mb-wrap"><span class="mb" style="width:${Math.min(wp,100)}%;background:${wc}"></span></span></div></td>\n      <td style="color:var(--grey)">${inst.ofi_score?parseFloat(inst.ofi_score).toFixed(1):\'—\'}</td>\n      <td>${scalpTag}</td>\n',
    ),
]

if 'Best Scalping Strategy Right Now' in html_content:
    print('index.html: strategy advisor UI already present — skipping edits')
else:
    for i, (old, new) in enumerate(HTML_EDITS, 1):
        cnt = html_content.count(old)
        if cnt != 1:
            print(f'index.html EDIT {i}: FAILED - expected 1 match, found {cnt}. Aborting, no changes written to index.html.')
            sys.exit(1)
        html_content = html_content.replace(old, new, 1)
        print(f'index.html EDIT {i}: applied OK')
    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print('index.html: all edits applied OK')

print('Done — Scalping Strategy Advisor patch complete.')