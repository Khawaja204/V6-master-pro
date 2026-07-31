import sys
import re

MAIN_FILE = "main.py"

with open(MAIN_FILE, "r") as f:
    content = f.read()

if "_V6_UPGRADE" in content:
    print("[SKIP] main.py already patched.")
    sys.exit(0)

# 1. Add imports
old_import = '''from logic import (
    process_vmc_signals, process_whale_walls, push_to_google_sheets,
    fetch_btc_sentiment, push_midnight_report,
    compute_institutional_score, compute_tp_levels, compute_position_size,
    compute_whale_power, calculate_atr, fetch_order_book, calculate_obi,
    detect_obi_spike, compute_confidence_score, fetch_ticker_price,
    detect_market_regime, compute_vwap, detect_rsi_divergence, fetch_klines,
    fetch_macd_for_symbol, compute_v6_final_score,
    calculate_wall_proximity, detect_spoofing, blink_to_push_check,
    detect_whale_copy_signals, is_stablecoin_pair,
    fetch_ticker_24h, score_coin, fetch_rsi_for_symbol,
    estimate_time_to_target, fetch_large_trades, fetch_eth_exchange_flows,
)'''

new_import = '''from logic import (
    process_vmc_signals, process_whale_walls, push_to_google_sheets,
    fetch_btc_sentiment, push_midnight_report,
    compute_institutional_score, compute_tp_levels, compute_position_size,
    compute_whale_power, calculate_atr, fetch_order_book, calculate_obi,
    detect_obi_spike, compute_confidence_score, fetch_ticker_price,
    detect_market_regime, compute_vwap, detect_rsi_divergence, fetch_klines,
    fetch_macd_for_symbol, compute_v6_final_score,
    calculate_wall_proximity, detect_spoofing, blink_to_push_check,
    detect_whale_copy_signals, is_stablecoin_pair,
    fetch_ticker_24h, score_coin, fetch_rsi_for_symbol,
    estimate_time_to_target, fetch_large_trades, fetch_eth_exchange_flows,
)

# V6 UPGRADE IMPORTS (P0: SQLite + Crypto + OCO | P1: WS + Partial TP + MTF)
try:
    from v6_database import init_db, get_db
    from v6_crypto import encrypt, decrypt
    from v6_oco import OCOManager
    from v6_websocket import start_websocket_feed, get_ws_price
    from v6_partial_tp import PartialTPManager
    from v6_multitimeframe import get_mtf_signal
    _V6_UPGRADE = True
except Exception as _e:
    print("[V6 UPGRADE] Import warning: %s" % _e)
    _V6_UPGRADE = False

_V6_WS  = _V6_UPGRADE
_V6_OCO = _V6_UPGRADE
_V6_PTP = _V6_UPGRADE
_V6_MTF = _V6_UPGRADE'''

content = content.replace(old_import, new_import)
print("[PATCH] Imports added.")

# 2. Add init_db() after CONFIG load
config_load = '''with open("config.json") as f:
    CONFIG = json.load(f)'''

new_config_load = '''with open("config.json") as f:
    CONFIG = json.load(f)

# V6 UPGRADE: Initialize SQLite Database
if _V6_UPGRADE:
    try:
        init_db()
        log.info("[V6 DB] SQLite initialized.")
    except Exception as _e:
        log.warning("[V6 DB] init failed: %s" % _e)'''

content = content.replace(config_load, new_config_load)
print("[PATCH] SQLite init hook added.")

# 3. Add startup hooks before app.run()
startup = '''    # V6 UPGRADE: WebSocket + OCO + Partial TP + Multi-Timeframe
    if _V6_WS:
        threading.Thread(target=start_websocket_feed, daemon=True).start()
        log.info("[V6 WS] Price feed started.")
    if _V6_OCO:
        GLOBAL_DATA["oco_manager"] = OCOManager(
            paper_mode=GLOBAL_DATA.get("paper_mode", True),
            fund_limit_usdt=CONFIG.get("bot_fund_limit_usdt", 10.0)
        )
        log.info("[V6 OCO] Manager ready.")
    if _V6_PTP:
        GLOBAL_DATA["ptp_manager"] = PartialTPManager(CONFIG)
        log.info("[V6 PTP] Partial TP manager ready.")
    if _V6_MTF:
        GLOBAL_DATA["mtf_enabled"] = True
        log.info("[V6 MTF] Multi-timeframe enabled.")
    # end V6 upgrade'''

_APP_RUN_LINE = '    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)'
if _APP_RUN_LINE in content:
    content = content.replace(_APP_RUN_LINE, startup + "\n\n" + _APP_RUN_LINE)
    print("[PATCH] Startup hooks added.")
else:
    print("[SKIP] app.run() not found (gunicorn/Procfile setup) — hooks must be added manually.")

with open(MAIN_FILE, "w") as f:
    f.write(content)

print("[DONE] main.py patched successfully.")
