import os
from dotenv import load_dotenv
load_dotenv()

# API Keys
BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")
CRYPTOPANIC_KEY    = os.getenv("CRYPTOPANIC_API_KEY")

# وضع التداول
PAPER_TRADING = os.getenv("PAPER_TRADING", "True") == "True"

# إعدادات رأس المال
CAPITAL          = float(os.getenv("CAPITAL", 200))
TRADE_AMOUNT     = float(os.getenv("TRADE_AMOUNT", 20))
MAX_TRADES       = int(os.getenv("MAX_TRADES", 10))
DAILY_LOSS_LIMIT = float(os.getenv("DAILY_LOSS_LIMIT", 20))

# إعدادات RSI
RSI_PERIOD    = 14
RSI_FAST      = 6
RSI_OVERSOLD  = 30
RSI_OVERBOUGHT = 70

# إعدادات EMA
EMA_FAST = 9
EMA_SLOW = 21
EMA_TREND = 200

# إعدادات التداول
TIMEFRAME         = "1h"
TOP_SYMBOLS_COUNT = 300
QUOTE_CURRENCY    = "USDT"
MIN_VOLUME_USD    = 1_000_000
SLEEP_TIME        = 60
VOLUME_INCREASE   = 1.20

# Trailing Stop
TRAILING_LEVELS = [
    (0.10, 0.05),
    (0.20, 0.15),
    (0.30, 0.25),
]

# قاعدة 24 ساعة
MAX_TRADE_HOURS = 24
