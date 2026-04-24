"""
🐺 hunter.py v3 — الصياد بـ 6 مؤشرات
RSI + Volume + Support + BB + Accumulation + Resistance
"""
import ccxt, json, time, logging, os
import pandas as pd, numpy as np
from datetime import datetime, timedelta
from config import *

logging.basicConfig(level=logging.INFO, format='%(asctime)s [HUNTER] %(message)s',
    handlers=[logging.FileHandler('/root/micro-scalping/hunter.log', encoding='utf-8'), logging.StreamHandler()])
log = logging.getLogger('hunter')

SIGNALS_FILE = '/root/micro-scalping/signals.json'
OPEN_TRADES_FILE = '/root/micro-scalping/open_trades.json'
MEMORY_FILE = '/root/micro-scalping/trade_memory.json'

def load_json(path, default=None):
    try:
        with open(path, 'r') as f: return json.load(f)
    except: return default if default is not None else {}

def save_json(path, data):
    with open(path, 'w') as f: json.dump(data, f, ensure_ascii=False, indent=2)

def connect():
    ex = ccxt.binance({'apiKey': BINANCE_API_KEY, 'secret': BINANCE_API_SECRET, 'enableRateLimit': True,
        'options': {'defaultType': 'spot', 'recvWindow': 60000, 'adjustForTimeDifference': True}})
    ex.load_time_difference()
    return ex

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).ewm(com=period-1, min_periods=period).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(com=period-1, min_periods=period).mean()
    return (100 - 100 / (1 + gain / loss.replace(0, 1))).iloc[-1]

def full_analysis(exchange, symbol):
    """تحليل كامل بـ 6 مؤشرات"""
    try:
        candles = exchange.fetch_ohlcv(symbol, '15m', limit=50)
        df = pd.DataFrame(candles, columns=['t','o','h','l','c','v'])
        if len(df) < 20: return None
        
        price = df.iloc[-1]['c']
        score = 0
        details = {}
        
        # 1. RSI على 1m
        c1m = exchange.fetch_ohlcv(symbol, '1m', limit=20)
        df1m = pd.DataFrame(c1m, columns=['t','o','h','l','c','v'])
        rsi = round(calc_rsi(df1m['c']), 1)
        details['rsi'] = rsi
        if rsi < 30: score += 35
        elif rsi < 35: score += 25
        elif rsi < 40: score += 10
        if rsi > 45: score -= 20
        
        # 2. Volume spike
        vol_now = df.iloc[-1]['v']
        vol_avg = df['v'].rolling(20).mean().iloc[-1]
        vol_ratio = round(vol_now / vol_avg, 1) if vol_avg > 0 else 1
        details['vol_ratio'] = vol_ratio
        if vol_ratio >= 2.0: score += 25
        elif vol_ratio >= 1.5: score += 15
        
        # 3. قرب الدعم
        support = df['l'].rolling(20).min().iloc[-1]
        near_support = round((price - support) / support * 100, 2)
        details['near_support'] = float(near_support)
        if near_support < 0.5: score += 30
        elif near_support < 1.5: score += 20
        elif near_support < 3: score += 10
        
        # 4. Bollinger Bands
        sma20 = df['c'].rolling(20).mean().iloc[-1]
        std20 = df['c'].rolling(20).std().iloc[-1]
        bb_upper = sma20 + 2 * std20
        bb_lower = sma20 - 2 * std20
        bb_pos = round((price - bb_lower) / (bb_upper - bb_lower) * 100, 0) if bb_upper != bb_lower else 50
        details['bb_position'] = float(bb_pos)
        if bb_pos < 15: score += 25
        elif bb_pos < 30: score += 15
        if bb_pos > 85: score -= 25
        
        # 5. تجميع: سعر ثابت + حجم عالي
        last5_range = (df['c'].iloc[-5:].max() - df['c'].iloc[-5:].min()) / df['c'].iloc[-5:].min() * 100
        last5_vol = df['v'].iloc[-5:].mean()
        accumulation = last5_range < 1.5 and last5_vol > vol_avg * 1.2
        details['accumulation'] = bool(accumulation)
        if accumulation: score += 30
        
        # 6. مقاومة
        resistance = df['h'].rolling(20).max().iloc[-1]
        near_resist = round((resistance - price) / price * 100, 2)
        details['near_resist'] = near_resist
        if near_resist < 0.5: score -= 30
        elif near_resist < 1: score -= 15
        
        details['score'] = score
        details['price'] = price
        
        return details
    except Exception as e:
        log.debug(f"Analysis error {symbol}: {e}")
        return None

def get_top_gainers(exchange):
    try:
        tickers = exchange.fetch_tickers()
        coins = []
        for symbol, t in tickers.items():
            if not symbol.endswith("/USDT"): continue
            base = symbol.split("/")[0]
            if any(base.endswith(x) for x in ['UP','DOWN','BULL','BEAR','3L','3S','5L','5S']): continue
            price = t.get('last', 0) or 0
            change = t.get('percentage', 0) or 0
            volume = t.get('quoteVolume', 0) or 0
            if (MIN_PRICE < price <= MAX_PRICE and MIN_CHANGE_PCT <= change <= MAX_CHANGE_PCT and volume >= MIN_VOLUME_USD):
                coins.append({"symbol": symbol, "price": price, "change": change, "volume": volume})
        coins.sort(key=lambda x: x['change'] * x['volume'], reverse=True)
        return coins[:TOP_GAINERS]
    except: return []

def check_cooldown(symbol):
    """cooldown 10 دقائق بعد خسارة"""
    try:
        m = load_json(MEMORY_FILE, {'trades':[]})
        losses = [t for t in m.get('trades',[])[-20:] if t.get('symbol')==symbol and not t.get('won')]
        if losses:
            lt = datetime.fromisoformat(losses[-1].get('time','2020-01-01'))
            if (datetime.now() - lt).total_seconds() < 600: return True
    except: pass
    return False

def send_signal(sig):
    signals = load_json(SIGNALS_FILE, {"pending": [], "history": []})
    sym = sig.get("symbol","")
    for p in signals.get("pending", []):
        if p.get("symbol") == sym: return
    for h in signals.get("history", [])[-20:]:
        if h.get("symbol") == sym:
            try:
                ht = datetime.fromisoformat(h.get("time","2020-01-01"))
                if (datetime.now() - ht).total_seconds() < 300: return
            except: pass
    sig["time"] = str(datetime.now())
    sig["status"] = "PENDING"
    signals["pending"].append(sig)
    signals["pending"] = signals["pending"][-5:]
    save_json(SIGNALS_FILE, signals)
    log.info(f"📨 Signal → {sym} Score:{sig.get('score',0)} RSI:{sig.get('rsi',0)}")

def check_btc(exchange):
    try:
        btc = exchange.fetch_ohlcv("BTC/USDT", "15m", limit=4)
        return (btc[-1][4] - btc[0][4]) / btc[0][4] * 100 > -0.5
    except: return True

def run():
    log.info("🐺 === الصياد v3 — 6 مؤشرات! ===")
    exchange = connect()
    scan_count = 0
    while True:
        try:
            scan_count += 1
            if scan_count % 10 == 0 and not check_btc(exchange):
                if scan_count % 60 == 0: log.info("🛑 BTC نازل")
                time.sleep(SLEEP_TIME); continue
            open_trades = load_json(OPEN_TRADES_FILE, [])
            if len(open_trades) >= MAX_TRADES:
                time.sleep(SLEEP_TIME); continue
            coins = get_top_gainers(exchange)
            open_symbols = {t.get("symbol") for t in open_trades}
            
            for coin in coins:
                symbol = coin['symbol']
                if symbol in open_symbols: continue
                if check_cooldown(symbol):
                    log.debug(f"⏸ {symbol} cooldown"); continue
                
                analysis = full_analysis(exchange, symbol)
                if not analysis: continue
                
                score = analysis['score']
                rsi = analysis['rsi']
                
                if score < 60:
                    if scan_count % 30 == 0 and score > 30:
                        log.debug(f"📊 {symbol} score:{score} — ناقص")
                    continue
                
                if rsi > RSI_BUY: continue
                
                log.info(f"🎯 {symbol} [+{coin['change']:.1f}%] Score:{score} "
                    f"RSI:{rsi} Vol:{analysis['vol_ratio']}x "
                    f"Dعم:{analysis['near_support']:.1f}% "
                    f"BB:{analysis['bb_position']:.0f}% "
                    f"{'🔥تجميع' if analysis['accumulation'] else ''}")
                
                send_signal({
                    "symbol": symbol, "price": analysis['price'],
                    "rsi": rsi, "score": score,
                    "strength": "STRONG" if score >= 80 else "NORMAL",
                    "change_pct": coin['change'],
                    "vol_ratio": analysis['vol_ratio'],
                    "accumulation": analysis['accumulation'],
                    "bb_position": analysis['bb_position'],
                    "near_support": analysis['near_support'],
                })
                break
            
            if scan_count % 60 == 0:
                log.info(f"🔍 #{scan_count} | Open:{len(open_trades)}")
            time.sleep(SLEEP_TIME)
        except KeyboardInterrupt: break
        except Exception as e: log.error(f"خطأ: {e}"); time.sleep(10)

if __name__ == "__main__": run()
