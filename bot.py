import ccxt
import pandas as pd
import time
import logging
from datetime import datetime, timedelta
from config import *
from strategy import analyze
from news_filter import check_news

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('bot_log.txt'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ===================== الاتصال =====================
def connect():
    return ccxt.binance({
        'apiKey': BINANCE_API_KEY,
        'secret': BINANCE_API_SECRET,
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })

# ===================== جلب العملات =====================
def get_top_symbols(exchange):
    try:
        tickers = exchange.fetch_tickers()
        data = [
            {"symbol": s, "volume": t.get('quoteVolume', 0)}
            for s, t in tickers.items()
            if s.endswith(f"/{QUOTE_CURRENCY}")
            and (t.get('quoteVolume') or 0) >= MIN_VOLUME_USD
        ]
        data.sort(key=lambda x: x['volume'], reverse=True)
        symbols = [d['symbol'] for d in data[:TOP_SYMBOLS_COUNT]]
        log.info(f"✅ {len(symbols)} عملة | أفضل 5: {symbols[:5]}")
        return symbols
    except Exception as e:
        log.error(f"خطأ جلب العملات: {e}")
        return ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT"]

# ===================== جلب البيانات =====================
def get_ohlcv(exchange, symbol):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception:
        return None

# ===================== Trailing Stop =====================
def update_trailing_stop(trade, current_price):
    entry  = trade['entry_price']
    signal = trade['signal']
    gain   = (current_price - entry) / entry if signal == "BUY" else (entry - current_price) / entry

    for threshold, new_stop_pct in TRAILING_LEVELS:
        if gain >= threshold:
            if signal == "BUY":
                new_stop = entry * (1 + new_stop_pct)
                if new_stop > trade['stop_loss']:
                    trade['stop_loss'] = round(new_stop, 6)
                    log.info(f"📈 Trailing Stop → ${trade['stop_loss']}")
            else:
                new_stop = entry * (1 - new_stop_pct)
                if new_stop < trade['stop_loss']:
                    trade['stop_loss'] = round(new_stop, 6)
                    log.info(f"📉 Trailing Stop → ${trade['stop_loss']}")

# ===================== تنفيذ الصفقة =====================
def execute_trade(exchange, symbol, signal_data, open_trades):
    signal = signal_data['signal']
    price  = signal_data['price']

    take_profit = price * (1 + 0.30) if signal == "BUY" else price * (1 - 0.30)
    stop_loss   = price * (1 - 0.10) if signal == "BUY" else price * (1 + 0.10)

    trade = {
        "symbol":      symbol,
        "signal":      signal,
        "entry_price": price,
        "take_profit": round(take_profit, 6),
        "stop_loss":   round(stop_loss, 6),
        "capital":     TRADE_AMOUNT,
        "open_time":   datetime.now(),
        "status":      "OPEN",
        "profit":      0
    }

    if PAPER_TRADING:
        log.info(f"""
╔══════════════════════════════════╗
  📊 صفقة جديدة | Paper Trading
  العملة:  {symbol}
  {'🟢 شراء' if signal == 'BUY' else '🔴 بيع'}
  RSI:     {signal_data['rsi']}
  دخول:    ${price}
  هدف:     ${trade['take_profit']}
  حماية:   ${trade['stop_loss']}
  رأسمال:  ${TRADE_AMOUNT}
╚══════════════════════════════════╝""")
    else:
        try:
            qty   = TRADE_AMOUNT / price
            side  = 'buy' if signal == 'BUY' else 'sell'
            order = exchange.create_order(symbol, 'market', side, qty)
            trade['order_id'] = order['id']
            log.info(f"✅ Live Trade: {order['id']}")
        except Exception as e:
            log.error(f"❌ خطأ تنفيذ: {e}")
            return None

    open_trades.append(trade)
    return trade

# ===================== متابعة الصفقات =====================
def monitor_trades(exchange, open_trades, closed_trades, daily_loss):
    for trade in open_trades[:]:
        if trade['status'] != 'OPEN':
            continue
        try:
            ticker        = exchange.fetch_ticker(trade['symbol'])
            current_price = ticker['last']
            signal        = trade['signal']
            hours_open    = (datetime.now() - trade['open_time']).seconds / 3600

            # تحديث Trailing Stop
            update_trailing_stop(trade, current_price)

            hit_tp = (signal == 'BUY'  and current_price >= trade['take_profit']) or \
                     (signal == 'SELL' and current_price <= trade['take_profit'])
            hit_sl = (signal == 'BUY'  and current_price <= trade['stop_loss'])  or \
                     (signal == 'SELL' and current_price >= trade['stop_loss'])
            hit_time = hours_open >= MAX_TRADE_HOURS

            reason = None
            if hit_tp:   reason = "🎯 هدف الربح"
            elif hit_sl: reason = "🛑 وقف الخسارة"
            elif hit_time: reason = "⏰ 24 ساعة"

            if reason:
                pnl = (current_price - trade['entry_price']) / trade['entry_price']
                pnl = pnl if signal == 'BUY' else -pnl
                profit = round(trade['capital'] * pnl, 2)

                trade.update({
                    "status":     "CLOSED",
                    "exit_price": current_price,
                    "profit":     profit
                })

                if profit < 0:
                    daily_loss[0] += abs(profit)

                log.info(f"{reason} | {trade['symbol']} | {'✅' if profit > 0 else '❌'} ${profit}")
                closed_trades.append(trade)
                open_trades.remove(trade)

        except Exception as e:
            log.error(f"خطأ متابعة {trade['symbol']}: {e}")

# ===================== إحصائيات =====================
def print_stats(open_trades, closed_trades, scan_count):
    if not closed_trades:
        return
    total  = sum(t['profit'] for t in closed_trades)
    wins   = len([t for t in closed_trades if t['profit'] > 0])
    losses = len([t for t in closed_trades if t['profit'] <= 0])
    wr     = wins / len(closed_trades) * 100

    log.info(f"""
╔══════════════════════════════════╗
  📈 إحصائيات | مسح #{scan_count}
  الصفقات:   {len(closed_trades)}
  ✅ ربح:    {wins} | ❌ خسارة: {losses}
  Win Rate:  {wr:.1f}%
  💰 الصافي: ${total:.2f}
  مفتوحة:    {len(open_trades)}
╚══════════════════════════════════╝""")

# ===================== الدالة الرئيسية =====================
def run():
    log.info("🚀 البوت شغال!")
    log.info(f"{'📝 Paper Trading' if PAPER_TRADING else '💰 Live Trading'}")

    exchange      = connect()
    open_trades   = []
    closed_trades = []
    daily_loss    = [0]
    scan_count    = 0

    symbols             = get_top_symbols(exchange)
    last_symbols_update = time.time()
    last_day            = datetime.now().date()

    while True:
        try:
            scan_count += 1

            # إعادة تعيين الخسارة اليومية
            if datetime.now().date() != last_day:
                daily_loss[0] = 0
                last_day = datetime.now().date()
                log.info("🔄 يوم جديد — إعادة تعيين الحدود")

            # تحديث العملات كل 6 ساعات
            if time.time() - last_symbols_update > 21600:
                symbols = get_top_symbols(exchange)
                last_symbols_update = time.time()

            log.info(f"\n🔍 مسح #{scan_count} | مفتوحة: {len(open_trades)} | خسارة اليوم: ${daily_loss[0]:.2f}")

            # التحقق من حد الخسارة اليومية
            if daily_loss[0] >= DAILY_LOSS_LIMIT:
                log.warning(f"🛑 وصلنا حد الخسارة اليومية ${DAILY_LOSS_LIMIT} — انتظار...")
                time.sleep(3600)
                continue

            # متابعة الصفقات
            monitor_trades(exchange, open_trades, closed_trades, daily_loss)

            # البحث عن إشارات
            if len(open_trades) < MAX_TRADES:
                symbols_open = [t['symbol'] for t in open_trades]

                for i, symbol in enumerate(symbols):
                    if symbol in symbols_open:
                        continue
                    if len(open_trades) >= MAX_TRADES:
                        break
                    if i % 10 == 0 and i > 0:
                        time.sleep(1)

                    # فلتر الأخبار
                    if not check_news(symbol):
                        continue

                    df          = get_ohlcv(exchange, symbol)
                    signal_data = analyze(df)

                    if signal_data:
                        log.info(f"📡 {signal_data['signal']} | {symbol} | RSI: {signal_data['rsi']}")
                        execute_trade(exchange, symbol, signal_data, open_trades)

            if scan_count % 10 == 0:
                print_stats(open_trades, closed_trades, scan_count)

            time.sleep(SLEEP_TIME)

        except KeyboardInterrupt:
            log.info("⛔ إيقاف البوت")
            print_stats(open_trades, closed_trades, scan_count)
            break
        except Exception as e:
            log.error(f"خطأ: {e}")
            time.sleep(30)

if __name__ == "__main__":
    run()
