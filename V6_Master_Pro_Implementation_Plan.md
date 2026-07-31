# V6 Master Pro - Institutional-Grade Trading Bot Master Plan

## Phase A: SQLite Foundation + WAL + Migrations + Audit Log + Encryption Core
- Files: db.py (new), main.py (modify), logic.py (modify)
- Key Features & Implementation Details:
  * Database & WAL Mode: init_db() initializes all tables and enables SQLite Write-Ahead Logging (WAL) for high concurrency, fast reads/writes, and zero data corruption.
  * Migrations Support: Automated schema checking to safely update legacy structures without data loss.
  * Audit Log (audit_log): Tracks major system events, trade states, state changes, and config updates.
  * Core Database Methods: save_trade(), get_open_trades(), close_trade(), save_backtest_signal(), get_pending_signals().
  * Secure API Key Encryption Layer: Uses symmetric Fernet encryption (from the cryptography library). The master encryption key (SECRET_KEY) is securely derived from environment variables (.env). Functions: save_api_key_encrypted() and get_api_key_decrypted().

## Phase B: OCO Order Engine + Retry + Slippage Protection
- Files: main.py (trade execution)
- Key Features & Implementation Details:
  * Binance Spot OCO Limitation Resolution (Option B Strategy): Since Binance Spot OCO APIs natively support only 1 TP and 1 SL per order, the execution engine splits position quantities (40% for TP1, 30% for TP2, 30% for TP3) and manages individual OCO/limit pairings accordingly.
  * Execution Function: _execute_real_binance_oco(symbol, side, qty, tp_list, sl)
  * Exponential Backoff Retry Logic: Built into all exchange communication wrappers to gracefully handle rate limits (429), network drops, and transient connection errors.
  * Slippage Protection: Safe execution buffers applied during high-volatility market windows.
  * Tracking & Admin View: Stores oco_order_id in the database and reflects an active "OCO Status" column in the Admin Portal.

## Phase C: Auto-Sync + Orphan Cleanup + Circuit Breaker
- Files: main.py (startup sequence & risk management)
- Key Features & Implementation Details:
  * Startup Reconciliation: _sync_binance_orders() executes on boot to match live exchange open positions against local database state.
  * Orphaned Order Cleanup: Automatically cancels lingering, un-tracked open orders found on the exchange that have no corresponding record in the local database.
  * Global Circuit Breaker: Instantly halts automated trading and triggers an emergency lockdown if consecutive losses cross the safety threshold (3-4 consecutive losses).
  * Telegram Startup Summary: Dispatches boot notifications: "Bot resumed. 3 open positions synced. 1 TP hit while offline."

## Phase D: WebSocket Live Feeds + Multi-Timeframe + ATR Trailing + Heat Check
- Files: logic.py
- Key Features & Implementation Details:
  * WebSocket Live Price Feed: Integrates real-time streams (@trade or @kline_1m) into logic.py to allow instantaneous reactions to stop-loss triggers instead of waiting for delayed scan cycles.
  * Multi-Timeframe Confluence: Cross-checks signals across multiple timeframes (15m + 1h + 4h) to effectively filter out false signals.
  * ATR-based Trailing Stop: Dynamic trailing logic that evaluates market volatility and updates every 5 minutes via a controlled cancel + replace order sequence.
  * "Sharp Mode" Toggle: Automatically tightens trailing parameters when historical win-rate exceeds 65%, or widens stop-loss margins if win-rate drops below 45%.
  * Portfolio Heat Check: Continuously monitors total capital exposure to prevent over-leveraging and excessive simultaneous market risk.

## Phase E: Uptime + Graceful Shutdown + Restart Alerts
- Files: main.py (health endpoint & lifecycle management)
- Key Features & Implementation Details:
  * Graceful Shutdown: Intercepts system termination signals (SIGINT/SIGTERM) to cleanly close database connections, dump active states, and exit without file locks or corruption.
  * Health Monitoring: Built-in health check endpoints configured for 24/7 external uptime monitoring (e.g., via UptimeRobot).
  * Instant Restart Alerts: Dispatches immediate alert notifications via Telegram upon system reboot or unexpected recovery.
