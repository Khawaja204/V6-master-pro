---
name: V6 Master Pro Architecture
description: Core server architecture, file layout, and key design decisions
---

## Stack
- Pure Python Flask, `python3 main.py`, binds 0.0.0.0:8080
- BOT_TOKEN (Telegram), SECRET_KEY (admin password), SESSION_SECRET (Replit secrets)
- CHAT_ID hardcoded fallback "8743601537"

## File Layout
- `main.py` — all backend: Flask routes, scan loop, Telegram bot, GLOBAL_DATA
- `index.html` — main dashboard (served by Flask `send_file`)
- `focus.html` — focus mode page (served by Flask `send_file`)
- `config.json` — all tuning params (ATR multipliers, thresholds, risk %)
- `learning_data.json` — paper mode learning persistence (auto-created)
- `api_keys.json` — exchange API key storage, masked (auto-created)

## Key Routes
`/`, `/dashboard_data`, `/focus`, `/focus_data`, `/chart_data`, `/whale_detail`, `/sniper_data`, `/admin`, `/client`

## GLOBAL_DATA
Single dict that holds all live state. scan_loop writes it every cycle. All routes read it.
Key fields: vmc, whale, inst_signals, backtest, hot_coins, btc, market_regime, price_alerts, learning_data, upgrade_log, paper_mode, volume_surge, smart_divergence

## Scan Loop (data_refresh_loop)
Runs every 60s in a background thread. Order:
1. process_vmc_signals → vmc_data (9 folders)
2. process_whale_walls → whale_data
3. Build inst_signals (score, tp_zones, confidence, sizing)
4. RSI-OBI confluence boost
5. determine_trading_strategy per coin
6. Update GLOBAL_DATA
7. self_upgrade_cycle
8. check_price_alerts
9. update_paper_learning
10. Fire Telegram alerts (VIP + Whale)

**Why:** This order ensures price alert checks use freshest prices, and learning data sees the latest backtest outcomes.
