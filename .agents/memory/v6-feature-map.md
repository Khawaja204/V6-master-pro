---
name: V6 Feature Map
description: Complete feature inventory — all 39 original + 7 new tasks with integration points
---

## 7 New Tasks (Session 2)

| # | Feature | Integration Point |
|---|---------|------------------|
| 1 | Price Alert System | PRICE_ALERTS global, check_price_alerts(), /admin/set_price_alert + /admin/delete_price_alert routes, admin portal card |
| 2 | Simple View Default + Urdu/English redesign | _svActive=true, getSimpleReason(), calcProfitRR(), renderSimpleView() in index.html |
| 3 | Profit % + R/R on cards | calcProfitRR() in index.html, expPct/rskPct/rrRat/curPnl in focus.html renderList |
| 4 | API Key Management | _API_KEYS dict, _save_api_keys(), /admin/set_api_key, /admin/test_connection, admin portal card |
| 5 | Smart Trading Engine (SPOT vs SPOT_GRID) | determine_trading_strategy() called per coin in scan loop; trading_strategy + trading_strategy_reason on each inst_signal |
| 6 | Paper Mode Intelligence | update_paper_learning(), _save_learning_data(), LEARNING_DATA in GLOBAL_DATA, Telegram alert at 65%+, admin portal card |
| 7 | Auto-review loop | self_upgrade_cycle() runs every scan (was already implemented; now enhanced with learning data context) |

## Key Data Paths
- inst_signals[n].trading_strategy → "SPOT" or "SPOT_GRID"
- inst_signals[n].trading_strategy_reason → explanation string
- GLOBAL_DATA["price_alerts"] → synced from PRICE_ALERTS global after each check
- GLOBAL_DATA["learning_data"] → dict with paper_trades, paper_win_rate, wp_threshold, conf_threshold, adjustment_log, ready_for_real

**Why:** All learning data is persisted to learning_data.json on every update — survives server restarts. Never reset.
