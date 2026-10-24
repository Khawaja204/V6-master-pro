import os

BINANCE_BASE_URL = "https://api.binance.com"

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT",
    "AVAXUSDT", "LINKUSDT", "NEARUSDT", "DOTUSDT", "POLUSDT",
]
TIMEFRAMES = ["15m", "1h"]

KLINE_LIMIT = 500
EMA_FAST = 21
EMA_SLOW = 50
RSI_LEN = 14
RSI_BULL = 50.0
VOL_LEN = 20
RVOL_MIN = 1.5

POLL_SECONDS = 30
MAX_CONCURRENT = 5

# Secrets are read only from environment variables (set them in Replit Secrets).
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN_2", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID_2", "")
