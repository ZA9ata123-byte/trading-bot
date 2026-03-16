"""
🤖 البوت الثاني — سكالبينغ سريع
الفريم: 15 دقيقة
RSI < 30 + EMA + Volume
"""

import ccxt
import pandas as pd
import time
import logging
from datetime import datetime
from config import *
from strategy import calculate_rsi, calculate_ema
from news_filter import check_news

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | BOT2 | %(message)s',
    handlers=[
        logging.FileHandler('bot2_log.txt'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# إعدادات البوت 2 مختلفة
TIMEFRAME2     = "15m"
CAPITAL2       = 100       # $100 فقط
TRADE_AMOUNT2  = 10        # $10 لكل صفقة
MAX_TRADES2    = 5         # أقصى 5 صفقات متزامنة
TAKE_PROFIT2   = 0.008     # 0.8% هدف سريع
STOP_LOSS2     = 0.005     # 0.5% وقف خسارة
RSI_ENTRY2     = 28        # RSI أقل من 28

def connect():
    return ccxt.binance({
        'apiKey': BINANCE_API_KEY,
        'secret': BINANCE_API_SECRET,
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })

def get_ohlcv(exchange, symbol):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME2, limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception:
        return None

def get_top_symbols(exchange):
    try:
        tickers = exchange.fetch_tickers()
        data = [
            {"symbol": s, "volume": t.get('quoteVolume', 0)}
            for s, t in tickers.items()
            if s.endswith("/USDT")
            and (t.get('quoteVolume') or 0) >= MIN_VOLUME_USD
        ]
        data.sort(key=lambda x: x['volume'], reverse=True)
        return [d['symbol'] for d in data[:100]]  # أفضل 100 فقط للسرعة
    except Exception:
        return ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT"]

def analyze_scalp(exchange, symbol):
    df = get_ohlcv(exchange, symbol)
    if df is None or len(df) < 50:
        return None

    df['rsi']      = calculate_rsi(df['close'])
    df['ema_fast'] = calculate_ema(df['close'], 9)
    df['ema_slow'] = calculate_ema(df['close'], 21)
    df['vol_avg']  = df['volume'].rolling(20).mean()

    last = df.iloc[-1]

    if pd.isna(last['rsi']):
        return None

    # شروط الدخول السريع
    if (last['rsi'] < RSI_ENTRY2 and
        last['close'] > last['ema_slow'] and
        last['volume'] > last['vol_avg'] * 1.3):

        return {
            "signal": "BUY",
            "price":  last['close'],
            "rsi":    round(last['rsi'], 2),
        }
    return None

def monitor_trades(exchange, open_trades, closed_trades, daily_loss):
    for trade in open_trades[:]:
        try:
            ticker        = exchange.fetch_ticker(trade['symbol'])
            current_price = ticker['last']
            entry         = trade['entry_price']
            gain          = (current_price - entry) / entry

            hit_tp = gain >= TAKE_PROFIT2
            hit_sl = gain <= -STOP_LOSS2

            if hit_tp or hit_sl:
                profit = round(TRADE_AMOUNT2 * gain, 2)
                trade.update({
                    "status":     "CLOSED",
                    "exit_price": current_price,
                    "profit":     profit
                })
                if profit < 0:
                    daily_loss[0] += abs(profit)
                icon = "🎯" if profit > 0 else "🛑"
                log.info(f"{icon} {trade['symbol']} | ${profit:+.2f} | RSI كان: {trade['rsi']}")
                closed_trades.append(trade)
                open_trades.remove(trade)

        except Exception as e:
            log.error(f"خطأ: {e}")

def print_stats(closed_trades, scan_count):
    if not closed_trades:
        return
    total  = sum(t['profit'] for t in closed_trades)
    wins   = len([t for t in closed_trades if t['profit'] > 0])
    losses = len(closed_trades) - wins
    wr     = wins / len(closed_trades) * 100 if closed_trades else 0
    log.info(f"""
╔══════════════════════════════════╗
  🏃 البوت 2 — سكالبينغ سريع
  مسح #{scan_count}
  الصفقات:  {len(closed_trades)}
  ✅ ربح:   {wins} | ❌ خسارة: {losses}
  Win Rate: {wr:.1f}%
  💰 الصافي: ${total:.2f}
╚══════════════════════════════════╝""")

def run():
    log.info("🏃 البوت 2 شغال! فريم 15 دقيقة")
    log.info(f"{'📝 Paper Trading' if PAPER_TRADING else '💰 Live Trading'}")

    exchange      = connect()
    open_trades   = []
    closed_trades = []
    daily_loss    = [0]
    scan_count    = 0

    symbols             = get_top_symbols(exchange)
    last_update         = time.time()
    last_day            = datetime.now().date()

    while True:
        try:
            scan_count += 1

            # إعادة تعيين يومية
            if datetime.now().date() != last_day:
                daily_loss[0] = 0
                last_day = datetime.now().date()

            # تحديث العملات كل ساعة
            if time.time() - last_update > 3600:
                symbols     = get_top_symbols(exchange)
                last_update = time.time()

            log.info(f"🔍 مسح #{scan_count} | مفتوحة: {len(open_trades)} | خسارة اليوم: ${daily_loss[0]:.2f}")

            # حد الخسارة اليومية
            if daily_loss[0] >= 15:
                log.warning("🛑 حد الخسارة اليومية $15 — انتظار...")
                time.sleep(1800)
                continue

            # متابعة الصفقات
            monitor_trades(exchange, open_trades, closed_trades, daily_loss)

            # البحث عن إشارات
            if len(open_trades) < MAX_TRADES2:
                symbols_open = [t['symbol'] for t in open_trades]

                for i, symbol in enumerate(symbols):
                    if symbol in symbols_open:
                        continue
                    if len(open_trades) >= MAX_TRADES2:
                        break
                    if i % 10 == 0 and i > 0:
                        time.sleep(0.5)

                    if not check_news(symbol):
                        continue

                    signal_data = analyze_scalp(exchange, symbol)

                    if signal_data:
                        price  = signal_data['price']
                        tp     = round(price * (1 + TAKE_PROFIT2), 6)
                        sl     = round(price * (1 - STOP_LOSS2), 6)

                        trade = {
                            "symbol":      symbol,
                            "signal":      "BUY",
                            "entry_price": price,
                            "take_profit": tp,
                            "stop_loss":   sl,
                            "capital":     TRADE_AMOUNT2,
                            "open_time":   datetime.now(),
                            "rsi":         signal_data['rsi'],
                            "status":      "OPEN",
                            "profit":      0
                        }

                        if PAPER_TRADING:
                            log.info(f"""
╔══════════════════════════════════╗
  🏃 صفقة سكالبينغ | Paper
  العملة:  {symbol}
  RSI:     {signal_data['rsi']}
  دخول:    ${price}
  هدف:     ${tp} (+0.8%)
  حماية:   ${sl} (-0.5%)
╚══════════════════════════════════╝""")
                        open_trades.append(trade)

            if scan_count % 20 == 0:
                print_stats(closed_trades, scan_count)

            time.sleep(30)  # كل 30 ثانية للسرعة

        except KeyboardInterrupt:
            log.info("⛔ إيقاف البوت 2")
            print_stats(closed_trades, scan_count)
            break
        except Exception as e:
            log.error(f"خطأ: {e}")
            time.sleep(15)

if __name__ == "__main__":
    run()
