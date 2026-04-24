import os
from dotenv import load_dotenv
load_dotenv("/root/micro-scalping/.env")
BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")
TELEGRAM_TOKEN      = os.getenv("TELEGRAM_TOKEN", "8605696873:AAFLAY4_xI4D5BYb7dFdu0FV2hJDiMiQPGs")
TELEGRAM_CHANNEL_AR = "-1003818709859"
TELEGRAM_CHANNEL_EN = "-1003771026934"
REPORT_CHANNEL      = "-1003756064073"
PAPER_TRADING = os.getenv("PAPER_TRADING", "True") == "True"
CAPITAL           = 500
TRADE_AMOUNT     = 150
MAX_TRADES       = 1
DAILY_LOSS_LIMIT = 2
MAX_TRADE_MINS     = 3
BREAKEVEN_FEE      = 0.002
TP_PCT             = 0.008
SL_PCT             = 0.0015
FORCE_EXIT_LOSS    = 0.003
MAX_HOLD_MINS      = 6
RSI_BUY            = 45
RSI_SELL           = 70
RSI_OVERBOUGHT     = 70
RSI_PERIOD         = 14
TREND_MIN_SCORE    = 30
ENABLE_4H_FILTER   = False
MIN_4H_GAIN_PCT    = 0.5
SCANNER_TOP_N      = 4
MIN_PRICE          = 0.005
MAX_PRICE          = 1.00
MIN_VOLUME_USD     = 2_000_000
MIN_CHANGE_PCT     = 2
MAX_CHANGE_PCT     = 15
TOP_GAINERS        = 30
QUOTE_CURRENCY     = "USDT"
SLEEP_TIME         = 2
BLACKLIST_MINS     = 30
TRAILING_ACTIVATION = 0.005
BE_LOCK_PCT        = 0.003
AUTO_BLACKLIST_MIN_TRADES = 5
AUTO_BLACKLIST_MIN_WR     = 0.25
AUTO_BLACKLIST_MAX_LOSS   = -1.50
PRICE_TIERS = {
    "TIER_A": {
        "name": "$0.05-$1.00",
        "min_price": 0.05, "max_price": 1.00,
        "tp_pct": 0.008, "sl_pct": 0.002,
        "min_volume": 3_000_000,
    },
    "TIER_B": {
        "name": "$0.01-$0.049",
        "min_price": 0.01, "max_price": 0.049,
        "tp_pct": 0.010, "sl_pct": 0.002,
        "min_volume": 2_000_000,
    },
    "TIER_C": {
        "name": "$0.005-$0.0099",
        "min_price": 0.005, "max_price": 0.0099,
        "tp_pct": 0.012, "sl_pct": 0.002,
        "min_volume": 1_500_000,
    },
}
LEARNING_FILE    = "trade_memory.json"
MIN_TRADES_LEARN = 15
