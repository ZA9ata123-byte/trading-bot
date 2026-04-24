"""
bot.py — الذئب المنفرد 🐺 ضرب وهرب!
═══════════════════════════════════════════
الاستراتيجية: شراء التصحيح فعملة صاعدة!
Top Gainer + RSI نزل = ندخلو → 5 pips → نخرجو!
═══════════════════════════════════════════
"""
import ccxt, pandas as pd, time, logging, json, os, sys, fcntl, requests
from datetime import datetime
from config import *
from scanner import scan_all, calculate_rsi, get_price_tier

# ─── Smart Exit ───────────────────────────────────────────
try:
    from smart_exit import (
        smart_check, should_enter, learn_locally,
        daily_ai_analysis, get_smart_summary, get_symbol_params,
    )
    SMART = True
    print("🧠⚡ Smart Exit v2 — ACTIVE!")
except Exception as e:
    SMART = False
    print(f"⚠️ Smart Exit OFF: {e}")

# ─── PID Lock — instance واحدة فقط! ──────────────────────
LOCK_FILE = '/root/micro-scalping/bot.lock'
lock_fp = open(LOCK_FILE, 'w')
try:
    fcntl.flock(lock_fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
    lock_fp.write(str(os.getpid()))
    lock_fp.flush()
except IOError:
    print("⚠️ البوت شغّال بالفعل! instance واحدة فقط.")
    sys.exit(1)

# ─── AI Learning ──────────────────────────────────────────
try:
    from ai_learner import analyze_trade
    AI_ENABLED = not SMART  # إلا SMART خدّام، AI القديم يتطفى!
except:
    AI_ENABLED = False

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('micro_log.txt', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


def send_tg(text):
    for ch in [TELEGRAM_CHANNEL_AR, TELEGRAM_CHANNEL_EN]:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": ch, "text": text, "parse_mode": "HTML"},
                timeout=10)
        except:
            pass


def connect():
    ex = ccxt.binance({
        'apiKey': BINANCE_API_KEY,
        'secret': BINANCE_API_SECRET,
        'enableRateLimit': True,
        'options': {
            'defaultType': 'spot',
            'recvWindow': 60000,
            'adjustForTimeDifference': True,
        },
    })
    ex.load_time_difference()
    log.info(f"⏱️ Time offset: {ex.options.get('timeDifference', 0)}ms")
    return ex


# ─── حفظ/تحميل ───────────────────────────────────────────
def save_trades(trades):
    with open('open_trades.json', 'w') as f:
        json.dump(trades, f, ensure_ascii=False, indent=2)

def load_trades():
    try:
        return json.load(open('open_trades.json'))
    except:
        return []


# ─── RSI الحالي ───────────────────────────────────────────
def get_current_rsi(exchange, symbol):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, "1m", limit=20)
        df = pd.DataFrame(ohlcv, columns=['t', 'o', 'h', 'l', 'close', 'v'])
        return round(calculate_rsi(df['close']).iloc[-1], 1)
    except:
        return 50


# ═══════════════════════════════════════════════════════════
# تنفيذ الصفقة
# ═══════════════════════════════════════════════════════════
def execute_trade(exchange, signal, open_trades):
    # منع pump & dump
    if signal.get('change_pct', 0) > 10:
        log.info(f"⚠️ {signal['symbol']} pump +{signal.get('change_pct',0):.0f}% — skip!")
        return None
    # حماية الدخول المكرر
    if any(t['symbol'] == signal['symbol'] for t in open_trades):
        return None

    # ═══ Smart: فحص الدخول ═══
    if SMART:
        _chk = should_enter(signal['symbol'], signal.get('rsi',0),
                            signal.get('score',0), get_price_tier(signal['price']).get('tier_key','DEFAULT'))
        if not _chk.get('enter', True):
            log.info(f"🧠🚫 {signal['symbol']}: {', '.join(_chk.get('reasons',[]))}")
            return None

    price = signal['price']
    tier = get_price_tier(price)
    tp_pct = tier.get('tp_pct', TP_PCT)
    sl_pct = tier.get('sl_pct', SL_PCT)
    score = signal.get('score', 0)

    # SL حسب Score
    if score >= 80:
        if SMART:
            sl = round(price * (1 - sl_pct * 0.5), 8)
            sl_policy = "🧠 Smart SL"
        else:
            sl = round(price * (1 + BREAKEVEN_FEE), 8)
            sl_policy = "لا خسارة 🔒"
    else:
        sl = round(price * (1 - min(sl_pct, 0.003)), 8)
        sl_policy = f"SL -{sl_pct*100}%"

    tp = round(price * (1 + tp_pct), 8)

    trade = {
        "symbol": signal['symbol'],
        "entry_price": price,
        "stop_loss": sl,
        "take_profit": tp,
        "tp_pct": tp_pct,
        "sl_pct": sl_pct,
        "highest": price,
        "lowest": price,
        "capital": TRADE_AMOUNT,
        "open_time": str(datetime.now()),
        "rsi": signal['rsi'],
        "score": score,
        "strength": signal['strength'],
        "tier": tier.get('tier_key', 'DEFAULT'),
        "tier_name": tier.get('name', ''),
        "status": "ACTIVE",
        "sl_policy": sl_policy,
        "candles": signal.get('candles', []),
        "change_pct": signal.get('change_pct', 0),
    }

    log.info(
        f"🐺 دخول | {signal['symbol']} "
        f"[+{signal.get('change_pct',0):.1f}%] | "
        f"RSI:{signal['rsi']} | Score:{score} | {sl_policy}"
    )

    send_tg(
        f"🐺 <b>دخول ضرب وهرب!</b>\n"
        f"🪙 <b>{signal['symbol']}</b> ({tier.get('name','')})\n"
        f"📈 Top Gainer +{signal.get('change_pct',0):.1f}%\n"
        f"📊 RSI: <b>{signal['rsi']}</b> | Score: {score}\n"
        f"💵 ${price:.6f} | 🎯 +{tp_pct*100}% | {sl_policy}\n"
        f"🕯️ {' '.join(signal.get('candles', []))}"
    )

    open_trades.append(trade)
    save_trades(open_trades)
    return trade


# ═══════════════════════════════════════════════════════════
# إغلاق الصفقة
# ═══════════════════════════════════════════════════════════
def close_trade(trade, open_trades, closed_trades, price, reason,
                daily_loss, blacklist):
    # حذف فوراً
    if trade in open_trades:
        open_trades.remove(trade)
        save_trades(open_trades)

    entry = trade['entry_price']
    pnl = (price - entry) / entry
    profit = round(TRADE_AMOUNT * pnl - TRADE_AMOUNT * BREAKEVEN_FEE, 4)
    emoji = "🎯" if "TP" in reason or "RSI" in reason else (
        "✅" if profit > 0 else "❌")
    mins = 0
    try:
        mins = (datetime.now() - datetime.fromisoformat(
            trade['open_time'])).total_seconds() / 60
    except:
        pass

    log.info(f"{reason} | {trade['symbol']} | {emoji} ${profit} | {mins:.0f}m")

    send_tg(
        f"{emoji} <b>نتيجة</b>\n"
        f"🪙 <b>{trade['symbol']}</b>\n"
        f"💵 ${entry:.6f} → ${price:.6f} | "
        f"{'+' if pnl > 0 else ''}{pnl*100:.2f}%\n"
        f"💰 <b>${profit}</b> | ⏱️ {mins:.0f}m\n"
        f"📝 {reason}"
    )

    # Blacklist + Daily loss
    if profit < 0:
        daily_loss[0] += abs(profit)
        blacklist[trade['symbol']] = time.time()

    closed_trades.append({
        **trade, "exit_price": price, "profit": profit,
        "exit_reason": reason, "duration_min": round(mins, 1),
    })

    # Learning
    try:
        from learning import save_trade_result
        save_trade_result(trade, profit, profit > 0, extra={
            "exit_price": price, "exit_reason": reason,
            "duration_min": round(mins, 1),
            "max_gain": round(
                (trade.get('highest', entry) - entry) / entry * 100, 2),
            "max_loss": round(
                (trade.get('lowest', entry) - entry) / entry * 100, 2),
        })
    except Exception as e:
        log.error(f"خطأ learning: {e}")

    # ═══ Smart: تعلم محلي ═══
    if SMART:
        try:
            learn_locally({
                "symbol": trade.get("symbol",""), "won": profit > 0,
                "profit": profit, "rsi": trade.get("rsi",0),
                "score": trade.get("score",0), "exit_reason": reason,
                "duration_min": round(mins,1), "tier": trade.get("tier",""),
                "max_gain": round((trade.get('highest',entry)-entry)/entry*100,2),
                "max_loss": round((trade.get('lowest',entry)-entry)/entry*100,2),
            })
        except Exception as e:
            log.error(f"🧠 learn: {e}")

    # AI Learning
    if AI_ENABLED:
        try:
            analyze_trade({
                "symbol": trade.get("symbol", ""),
                "won": profit > 0, "profit": profit,
                "rsi": trade.get("rsi", 0),
                "score": trade.get("score", 0),
                "exit_reason": reason,
                "duration_min": round(mins, 1),
                "max_gain": round(
                    (trade.get('highest', entry) - entry) / entry * 100, 2),
                "max_loss": round(
                    (trade.get('lowest', entry) - entry) / entry * 100, 2),
                "tier": trade.get("tier", ""),
                "candles": trade.get("candles", []),
            })
        except Exception as e:
            log.error(f"🧠 AI error: {e}")


# ═══════════════════════════════════════════════════════════
# متابعة الصفقات
# ═══════════════════════════════════════════════════════════
def monitor_trades(exchange, open_trades, closed_trades,
                   daily_loss, blacklist):
    for trade in open_trades[:]:
        try:
            ticker = exchange.fetch_ticker(trade['symbol'])
            price = ticker['last']
            entry = trade['entry_price']

            if price > trade.get('highest', entry):
                trade['highest'] = price
            if price < trade.get('lowest', entry):
                trade['lowest'] = price

            reason = None

            if SMART:
                # ═══ Smart Exit — يتحكم في كلشي ═══
                current_rsi = get_current_rsi(exchange, trade['symbol'])
                reason, _ = smart_check(trade, price, current_rsi)

            else:
                # ═══ Legacy — غير إلا SMART معطل ═══
                gain = (price - entry) / entry
                mins = (datetime.now() - datetime.fromisoformat(
                    trade['open_time'])).total_seconds() / 60
                score = trade.get('score', 0)

                if gain <= -FORCE_EXIT_LOSS:
                    reason = f"🚨 FORCE {gain*100:.2f}%"
                if not reason and price >= trade['take_profit']:
                    reason = f"🎯 TP +{gain*100:.2f}%"
                if not reason:
                    current_rsi = get_current_rsi(exchange, trade['symbol'])
                    if current_rsi >= RSI_SELL and gain > BREAKEVEN_FEE:
                        reason = f"📊 RSI={current_rsi} +{gain*100:.2f}%"
                    elif current_rsi >= RSI_OVERBOUGHT and gain > 0:
                        reason = f"📊 RSI={current_rsi} OB! +{gain*100:.2f}%"
                if not reason:
                    if score >= 80:
                        breakeven = entry * (1 + BREAKEVEN_FEE)
                        if trade['stop_loss'] > breakeven and price <= trade['stop_loss']:
                            reason = f"🔒 Trail +{(trade['stop_loss']-entry)/entry*100:.2f}%"
                    else:
                        if price <= trade['stop_loss']:
                            reason = f"🛑 SL {gain*100:.2f}%"
                if not reason and gain > 0:
                    if gain >= BE_LOCK_PCT:
                        be = round(entry * (1 + BREAKEVEN_FEE), 8)
                        if trade['stop_loss'] < be:
                            trade['stop_loss'] = be
                    if gain >= 0.003:
                        half = round(entry * (1 + gain * 0.5), 8)
                        if half > trade['stop_loss']:
                            trade['stop_loss'] = half
                    if gain >= TRAILING_ACTIVATION:
                        ns = round(price * 0.997, 8)
                        if ns > trade['stop_loss']:
                            trade['stop_loss'] = ns
                if not reason and mins >= MAX_TRADE_MINS:
                    if gain > BREAKEVEN_FEE:
                        reason = f"⏰ {MAX_TRADE_MINS}m +{gain*100:.2f}%"
                    elif gain > 0:
                        reason = f"⏰ {MAX_TRADE_MINS}m BE"
                    elif score >= 80:
                        trade['status'] = 'HOLDING'
                    else:
                        reason = f"⏰ {MAX_TRADE_MINS}m {gain*100:.2f}%"
                if not reason and trade.get('status') == 'HOLDING':
                    if gain >= BREAKEVEN_FEE + 0.001:
                        reason = f"🔄 Recovery +{gain*100:.2f}%"
                    elif mins >= MAX_HOLD_MINS:
                        reason = f"⏰ MAX {MAX_HOLD_MINS}m {gain*100:.2f}%"

            if reason:
                close_trade(trade, open_trades, closed_trades,
                            price, reason, daily_loss, blacklist)

        except Exception as e:
            log.error(f"خطأ {trade.get('symbol', '?')}: {e}")


def count_active(trades):
    return sum(1 for t in trades if t.get('status', 'ACTIVE') == 'ACTIVE')

def print_stats(closed, open_trades, scan):
    if not closed:
        return
    total = sum(t['profit'] for t in closed)
    wins = [t for t in closed if t['profit'] > 0]
    wr = len(wins) / len(closed) * 100
    tph = len(closed) / max(1, scan * SLEEP_TIME / 3600)
    holding = sum(1 for t in open_trades if t.get('status') == 'HOLDING')

    log.info(
        f"🐺 #{scan} | ✅{len(wins)} ❌{len(closed)-len(wins)} "
        f"WR:{wr:.0f}% | ${total:.3f} | "
        f"{tph:.1f}/h | نشط:{count_active(open_trades)} عالق:{holding}"
    )


# ═══════════════════════════════════════════════════════════
# الحلقة الرئيسية
# ═══════════════════════════════════════════════════════════
def run():
    log.info("🐺 الذئب المنفرد — ضرب وهرب!")
    log.info(f"{'📝 Paper' if PAPER_TRADING else '💰 Live'} | "
             f"${TRADE_AMOUNT}/صفقة × {MAX_TRADES}")
    log.info(f"RSI: شراء < {RSI_BUY} | بيع > {RSI_SELL} | "
             f"Trend: 15m+1h")
    log.info(f"Top Gainers: +{MIN_CHANGE_PCT}% | "
             f"سعر < ${MAX_PRICE} | 🧠 AI: {'ON' if AI_ENABLED else 'OFF'}")

    exchange = connect()
    open_trades = load_trades()
    closed_trades = []
    daily_loss = [0]
    blacklist = {}
    scan_count = 0
    last_day = datetime.now().date()

    while True:
        try:
            scan_count += 1

            # يوم جديد
            if datetime.now().date() != last_day:
                daily_loss[0] = 0
                last_day = datetime.now().date()
                log.info("🔄 يوم جديد!")

            # ═══ تحليل AI يومي ═══
            if SMART and scan_count == 1:
                try:
                    daily_ai_analysis()
                except:
                    pass

            # حد الخسارة اليومي
            if daily_loss[0] >= DAILY_LOSS_LIMIT:
                if scan_count % 100 == 0:
                    log.info(f"🚫 حد الخسارة ${daily_loss[0]:.2f}")
                monitor_trades(exchange, open_trades, closed_trades,
                               daily_loss, blacklist)
                time.sleep(SLEEP_TIME)
                continue

            # متابعة
            monitor_trades(exchange, open_trades, closed_trades,
                           daily_loss, blacklist)

            # دخول
            active = count_active(open_trades)
            # ═══ BTC Filter — ما ندخلوش ملي السوق نازل! ═══
            btc_ok = True
            if scan_count % 6 == 0 or not hasattr(run, '_btc_ok'):
                try:
                    btc = exchange.fetch_ohlcv("BTC/USDT", "15m", limit=4)
                    btc_chg = (btc[-1][4] - btc[0][4]) / btc[0][4] * 100
                    btc_ok = btc_chg > -0.3
                    run._btc_ok = btc_ok
                    if not btc_ok:
                        if scan_count % 60 == 0:
                            log.info(f"🛑 BTC نازل {btc_chg:.2f}% — لا دخول!")
                except:
                    btc_ok = run._btc_ok if hasattr(run, '_btc_ok') else True
            else:
                btc_ok = run._btc_ok if hasattr(run, '_btc_ok') else True

            hour_ok = 10 <= __import__("datetime").datetime.now().hour < 20
            if not hour_ok and scan_count % 120 == 0:
                log.info("🌙 ساعات الراحة — لا دخول")
            if active < MAX_TRADES and btc_ok and hour_ok:
                try:
                    from learning import get_learned_advice
                    signal = scan_all(exchange, blacklist, open_trades)
                    if signal:
                        # RSI عالي = دخول ضعيف
                        advice = get_learned_advice(signal['symbol'])
                        if advice.get('avoid'):
                            log.info(
                                f"🧠 تجنب {signal['symbol']}: "
                                f"{advice['reason']}")
                        elif not any(t['symbol'] == signal['symbol']
                                     for t in open_trades):
                            execute_trade(exchange, signal, open_trades)
                except Exception as e:
                    log.error(f"خطأ scan: {e}")

            # إحصائيات كل 30 دورة
            if scan_count % 30 == 0:
                print_stats(closed_trades, open_trades, scan_count)

            time.sleep(SLEEP_TIME)

        except KeyboardInterrupt:
            log.info("⛔ إيقاف")
            break
        except Exception as e:
            log.error(f"خطأ: {e}")
            time.sleep(30)


if __name__ == "__main__":
    run()
