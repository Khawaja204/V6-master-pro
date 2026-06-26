/* =============================================================================
   V6 MASTER PRO — UI CONFIGURATION
   Edit this file to change API endpoints, refresh timing, chart settings,
   layout, and the coins/clients shown on the dashboard.
   No other file needs to be edited for normal configuration changes.
   ============================================================================= */
window.V6_CONFIG = {
  /* ---- Backend API ------------------------------------------------------ *
   * base: leave "" when this UI is served by the same Flask backend.
   *       Set to a full origin (e.g. "https://your-app.replit.app") only if
   *       you host this UI separately AND the backend enables CORS.          */
  api: {
    base: "",
    endpoints: {
      dashboard: "/dashboard_data",
      systemHealth: "/system_health",
      chart: "/chart_data",
      sniper: "/sniper_data",
    },
  },

  /* ---- Refresh / polling ------------------------------------------------ */
  refresh: {
    intervalSec: 8, // how often live data is pulled from the backend (5-10s live cadence)
  },

  /* ---- Coin profile chart ---------------------------------------------- */
  chart: {
    interval: "1h", // candle interval requested from /chart_data
    limit: 60, // number of candles
  },

  /* ---- Coin profile selection ------------------------------------------ *
   * "auto" = highest-scoring institutional signal.
   * Or hard-code a symbol, e.g. "SOLUSDT".                                  */
  profileSymbol: "auto",

  /* ---- Layout ----------------------------------------------------------- */
  layout: {
    maxWidthPx: 1280, // max content width
    tableMaxRows: 25, // cap rows rendered in big tables
  },

  /* ---- Strategy watch cards (HIFI / DOGE style) ------------------------ *
   * Each card pulls live data for its symbol from the backend.             */
  watchCards: [
    { symbol: "HIFIUSDT", title: "HIFI / USDT" },
    { symbol: "DOGEUSDT", title: "DOGE / USDT" },
  ],

  /* ---- Client & API management (display) ------------------------------- */
  clients: [
    { name: "Client A", api: "APA / USDT", exchange: "Binance", status: "Synced" },
    { name: "Client X", api: "XPL / USDT", exchange: "Binance", status: "Synced" },
  ],
};
