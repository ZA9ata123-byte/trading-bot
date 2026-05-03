"""
hunter_v4.py - الصياد v4
يقرا watchlist من Spy، ويختار أحسن candidate للدخول
يبعث signals للـGuardian اللي كينفذ
"""
import ccxt
import json
import time
import logging
import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from config_v4 import *

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [HUNTER] %(message)s',
    handlers=[
        logging.FileHandler('/root/micro-scalping/hunter_v4.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger('hunter')

BASE = '/root/micro-scalping'
WATCHLIST_FILE = os.path.join(BASE, 'watchlist.json')
SIGNALS_FILE = os.path.join(BASE, 'signals.json')
OPEN_TRADES_FILE = os.path.join(BASE, 'open_trades.json')
MEMORY_FILE = os.path.join(BASE, 'trade_memory.json')


def load_json(path, default=None):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except:
        return default if default is not None else {}


def save_json(path, data):
    try:
        with open(path, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        log.error(f"Save error: {e}")


def send_tg(text, channel=None):
    ch = channel or TELEGRAM_CHANNEL_AR
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": ch, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
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
            'adjustForTimeDifference': True
        }
    })
    ex.load_time_difference()
    return ex


def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).ewm(com=period-1, min_periods=period).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(com=period-1, min_periods=period).mean()
    rs = gain / loss.replace(0, 1)
    rsi = 100 - 100 / (1 + rs)
    return round(float(rsi.iloc[-1]), 1)


def check_cooldown(exchange, symbol):
    """
    حظر ذكي (Dynamic Cooldown) لمدة 60 دقيقة بعد أي صفقة،
    إلا إذا استيقظت العملة وانفجرت (Volume 3x + كسر القمة).
    """
    try:
        mem = load_json(MEMORY_FILE, {'trades': []})
        recent_trades = [
            t for t in mem.get('trades', [])[-50:]
            if t.get('symbol') == symbol
        ]
        
        if not recent_trades:
            return False # لا يوجد حظر
            
        last_trade = recent_trades[-1]
        last_time_str = str(last_trade.get('time', '2020-01-01'))
        try:
            lt = datetime.fromisoformat(last_time_str.replace(' ', 'T').split('.')[0])
            minutes_since = (datetime.now() - lt).total_seconds() / 60
            
            if minutes_since >= 60:
                return False # انتهى الحظر
                
            # نحن في فترة الحظر. هل استيقظت العملة؟
            candles = exchange.fetch_ohlcv(symbol, '1m', limit=30)
            if len(candles) < 30:
                return True
                
            df = pd.DataFrame(candles, columns=['t', 'o', 'h', 'l', 'c', 'v'])
            current_price = float(df.iloc[-1]['c'])
            current_vol = float(df.iloc[-1]['v'])
            
            avg_vol = float(df['v'].iloc[:-1].mean())
            vol_breakout = current_vol > (avg_vol * 3)
            
            highest_30m = float(df['h'].iloc[:-1].max())
            price_breakout = current_price > highest_30m
            
            if vol_breakout and price_breakout:
                log.info(f"🧨 {symbol} كسرت الحظر! استيقظت من الغيبوبة")
                return False # كسر الحظر
                
            return True # ما زالت ميتة، الحظر مستمر
            
        except Exception as e:
            pass
            
    except Exception as e:
        log.error(f"Cooldown error: {e}")
        
    return False

def check_trap_memory(candidate, rsi_1m):
    """التعلم من الماضي: هل هذا السلوك سام؟"""
    try:
        mem = load_json(MEMORY_FILE, {'trades': []})
        symbol = candidate['symbol']
        past_trades = [t for t in mem.get('trades', []) if t.get('symbol') == symbol]
        if not past_trades:
            return False
            
        recent_3 = past_trades[-3:]
        if len(recent_3) == 3 and all(not t.get('won') for t in recent_3):
            return True # السلوك الحالي للعملة سام جداً
            
        similar_losses = [t for t in past_trades if not t.get('won') and abs(t.get('rsi_1m', 0) - rsi_1m) < 5]
        similar_wins = [t for t in past_trades if t.get('won') and abs(t.get('rsi_1m', 0) - rsi_1m) < 5]
        
        if len(similar_losses) >= 3 and len(similar_wins) == 0:
            return True # فخ تاريخي مثبت
            
    except Exception as e:
        log.error(f"Memory check error: {e}")
    return False

def is_falling_knife(exchange, symbol, current_price):
    """تحقق مما إذا كانت العملة قد انهارت للتو (تجنب الشراء بعد الـ Dump)"""
    try:
        candles = exchange.fetch_ohlcv(symbol, '15m', limit=8)
        if not candles: return False
        
        df = pd.DataFrame(candles, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        highest_high = float(df['h'].max())
        
        # السقوط من أعلى قمة بأكثر من 4%
        drop_pct = (highest_high - current_price) / highest_high
        if drop_pct > 0.04:
            return True
            
        # شمعة بيع ضخمة مؤخراً
        last_candle = df.iloc[-1]
        candle_drop = (float(last_candle['h']) - current_price) / float(last_candle['h'])
        if candle_drop > 0.02:
            return True
            
    except Exception as e:
        log.debug(f"Knife check error: {e}")
    return False


def validate_entry(exchange, candidate):
    """تحقق من الدخول على 1m timeframe"""
    symbol = candidate['symbol']
    try:
        candles_1m = exchange.fetch_ohlcv(symbol, '1m', limit=20)
        df = pd.DataFrame(candles_1m, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        
        if len(df) < 15:
            return None
        
        current_price = float(df.iloc[-1]['c'])
        
        # RSI 1m
        rsi_1m = calc_rsi(df['c'])
        
        # Price momentum (آخر 3 شمعات)
        last_3 = df.iloc[-3:]
        green_count = sum(1 for _, c in last_3.iterrows() if c['c'] > c['o'])
        
        # فلترة ذيول الرفض (Rejection Wicks)
        last_candle = df.iloc[-1]
        body_size = abs(last_candle['c'] - last_candle['o'])
        upper_wick = last_candle['h'] - max(last_candle['o'], last_candle['c'])
        has_toxic_wick = upper_wick > (body_size * 2) and upper_wick > 0
        
        # Volume على 1m
        vol_last = float(df.iloc[-1]['v'])
        vol_avg = float(df['v'].iloc[-10:].mean())
        vol_ratio_1m = round(vol_last / vol_avg, 1) if vol_avg > 0 else 1
        
        # ذاكرة الذئاب (هل هذا فخ؟)
        is_trap = check_trap_memory(candidate, rsi_1m)
        
        # النطاق الذهبي للـ RSI
        rsi_15m_ok = 32.5 <= candidate.get('rsi_15m', 40) <= 46.0
        
        # ترند الفريم الكبير (Multi-Timeframe)
        trend_1h = candidate.get('trend_1h', 'BULLISH')
        
        # هل هذا سقوط حر؟ (Falling Knife)
        falling_knife = is_falling_knife(exchange, symbol, current_price)
        
        # Micro-conditions للـentry
        conditions = {
            'rsi_15m_golden': rsi_15m_ok,
            'rsi_1m_ok': 25 <= rsi_1m <= 65,
            'green_candles_ok': green_count >= 1,
            'volume_ok': vol_ratio_1m >= 1.0,
            'no_toxic_wick': not has_toxic_wick,
            'not_a_historical_trap': not is_trap,
            'not_falling_knife': not falling_knife,
            'trend_1h_bullish': trend_1h != 'BEARISH'
        }
        
        all_ok = all(conditions.values())
        
        return {
            'price': current_price,
            'rsi_1m': rsi_1m,
            'green_count_1m': green_count,
            'vol_ratio_1m': vol_ratio_1m,
            'conditions': conditions,
            'can_enter': all_ok
        }
    except Exception as e:
        log.debug(f"Validation error {symbol}: {e}")
        return None


def create_signal(candidate, validation):
    """كتب signal للـGuardian"""
    symbol = candidate['symbol']
    price = validation['price']
    
    signal = {
        "symbol": symbol,
        "price": price,
        "score": candidate['score'],
        "rsi_15m": candidate['rsi_15m'],
        "rsi_1m": validation['rsi_1m'],
        "vol_ratio": candidate['vol_ratio'],
        "vol_ratio_1m": validation['vol_ratio_1m'],
        "near_support": candidate['near_support'],
        "near_resist": candidate['near_resist'],
        "trend_1h": candidate.get('trend_1h', '?'),
        "trend_4h": candidate.get('trend_4h', '?'),
        "bb_width": candidate.get('bb_width', 0),
        "time": str(datetime.now()),
        "status": "PENDING"
    }
    
    # اكتب فـsignals.json
    signals = load_json(SIGNALS_FILE, {"pending": [], "history": []})
    
    # تحقق من duplicate
    for p in signals.get("pending", []):
        if p.get("symbol") == symbol:
            log.info(f"Signal already pending for {symbol}")
            return False
    
    # تحقق من history (ماتبعتش نفس الcoin فـ5 دقائق)
    for h in signals.get("history", [])[-20:]:
        if h.get("symbol") == symbol:
            try:
                ht_str = str(h.get("time", "2020-01-01"))
                ht = datetime.fromisoformat(ht_str.replace(' ', 'T').split('.')[0])
                if (datetime.now() - ht).total_seconds() < 300:
                    return False
            except:
                pass
    
    signals.setdefault("pending", []).append(signal)
    signals["pending"] = signals["pending"][-5:]  # keep last 5
    save_json(SIGNALS_FILE, signals)
    
    log.info(
        f"Signal sent: {symbol} @ ${price:.6f} | "
        f"Score:{candidate['score']} RSI15m:{candidate['rsi_15m']} RSI1m:{validation['rsi_1m']}"
    )
    
    # Telegram entry message (قناة العربية)
    tp_price = price * (1 + TP_PCT)
    sl_price = price * (1 - SL_PCT)
    
    msg = (
        f"🐺 <b>دخول!</b>\n"
        f"🪙 <b>{symbol}</b>\n"
        f"💵 ${price:.6f}\n"
        f"📊 Score: {candidate['score']} | RSI 15m: {candidate['rsi_15m']} | RSI 1m: {validation['rsi_1m']}\n"
        f"🎯 TP: +{TP_PCT*100}% (${tp_price:.6f})\n"
        f"🛑 SL: -{SL_PCT*100}% (${sl_price:.6f})\n"
        f"⏰ {datetime.now().strftime('%H:%M')} UTC"
    )
    send_tg(msg, TELEGRAM_CHANNEL_AR)
    
    return True


def run():
    log.info("="*60)
    log.info("Hunter v4 started")
    log.info(f"Trade Amount: ${TRADE_AMOUNT} | Max Trades: {MAX_TRADES}")
    log.info(f"TP: {TP_PCT*100}% | SL: {SL_PCT*100}%")
    log.info("="*60)
    
    exchange = connect()
    cycle = 0
    last_log_time = 0
    
    while True:
        try:
            cycle += 1
            now = time.time()
            
            # 1. تحقق ماكايناش صفقة مفتوحة
            open_trades = load_json(OPEN_TRADES_FILE, [])
            if len(open_trades) >= MAX_TRADES:
                if now - last_log_time > 60:
                    log.info(f"Max trades ({MAX_TRADES}) already open, waiting...")
                    last_log_time = now
                time.sleep(SLEEP_TIME)
                continue
            
            # 2. اقرا watchlist
            wl_data = load_json(WATCHLIST_FILE, {"watchlist": []})
            watchlist = wl_data.get("watchlist", [])
            
            if not watchlist:
                if now - last_log_time > 120:
                    log.info("Watchlist empty, waiting for Spy...")
                    last_log_time = now
                time.sleep(SLEEP_TIME)
                continue
            
            # 3. تحقق من age ديال watchlist (ماخاصش تكون قديمة)
            wl_time_str = str(wl_data.get('updated_at', '2020-01-01'))
            try:
                wl_time = datetime.fromisoformat(wl_time_str.replace(' ', 'T').split('.')[0])
                wl_age_minutes = (datetime.now() - wl_time).total_seconds() / 60
                if wl_age_minutes > 10:
                    if now - last_log_time > 120:
                        log.info(f"Watchlist too old ({wl_age_minutes:.0f}m), skipping")
                        last_log_time = now
                    time.sleep(SLEEP_TIME)
                    continue
            except:
                pass
            
            # 4. جرب top candidates واحد بواحد
            open_symbols = {t.get('symbol') for t in open_trades}
            signal_created = False
            
            for candidate in watchlist[:5]:  # top 5
                symbol = candidate['symbol']
                
                # skip إلا كانت مفتوحة
                if symbol in open_symbols:
                    continue
                
                # skip cooldown
                if check_cooldown(exchange, symbol):
                    log.debug(f"Cooldown: {symbol}")
                    continue
                
                # تحقق micro-conditions
                validation = validate_entry(exchange, candidate)
                if not validation:
                    continue
                
                if not validation['can_enter']:
                    failed = [k for k, v in validation['conditions'].items() if not v]
                    log.debug(f"{symbol} entry failed: {failed}")
                    continue
                
                # Create signal!
                if create_signal(candidate, validation):
                    signal_created = True
                    break
            
            # 5. Log summary كل دقيقة
            if now - last_log_time > 60:
                log.info(
                    f"Cycle #{cycle} | Watchlist: {len(watchlist)} | "
                    f"Open: {len(open_trades)}/{MAX_TRADES} | "
                    f"Signal: {'✓' if signal_created else '-'}"
                )
                last_log_time = now
            
            time.sleep(SLEEP_TIME)
            
        except KeyboardInterrupt:
            log.info("Stopped by user")
            break
        except Exception as e:
            log.error(f"Cycle error: {e}")
            time.sleep(10)


if __name__ == "__main__":
    run()
