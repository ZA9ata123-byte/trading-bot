"""
🕵️ spy.py — الجاسوس
كيدوّر على عملات فالتجميع قبل ما تقلع
بدل Top Gainers (اللي طلعات) → كيلقى اللي غادي تطلع
"""
import ccxt, json, time, logging, os, requests
import pandas as pd, numpy as np
from datetime import datetime
from config import *

logging.basicConfig(level=logging.INFO, format='%(asctime)s [SPY] %(message)s',
    handlers=[logging.FileHandler('/root/micro-scalping/spy.log', encoding='utf-8'), logging.StreamHandler()])
log = logging.getLogger('spy')

def send_tg(text):
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHANNEL_AR, "text": text, "parse_mode": "HTML"}, timeout=10)
    except: pass

def connect():
    ex = ccxt.binance({'apiKey': BINANCE_API_KEY, 'secret': BINANCE_API_SECRET, 'enableRateLimit': True,
        'options': {'defaultType': 'spot', 'recvWindow': 60000, 'adjustForTimeDifference': True}})
    ex.load_time_difference()
    return ex

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).ewm(com=period-1, min_periods=period).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(com=period-1, min_periods=period).mean()
    return round(float((100 - 100 / (1 + gain / loss.replace(0, 1))).iloc[-1]), 1)

def get_all_usdt_pairs(exchange):
    """كل عملات USDT فـ Binance"""
    try:
        tickers = exchange.fetch_tickers()
        pairs = []
        for symbol, t in tickers.items():
            if not symbol.endswith("/USDT"): continue
            base = symbol.split("/")[0]
            if any(base.endswith(x) for x in ['UP','DOWN','BULL','BEAR','3L','3S','5L','5S']): continue
            price = t.get('last', 0) or 0
            volume = t.get('quoteVolume', 0) or 0
            change = t.get('percentage', 0) or 0
            # حيّد stablecoins
            if any(x in base for x in ['USD','USDC','USDT','DAI','TUSD','BUSD','FDUSD','RLUSD','XUSD','EUR','GBP','BRL','TRY','ARS','NGN','PLN','UAH','AEUR']): continue
            if 0.99 < price < 1.01: continue  # أي عملة قريبة من  = stable
            if price > 0.0005 and price < 2.0 and volume >= 500000:
                pairs.append({"symbol": symbol, "price": price, "volume": volume, "change": change})
        pairs.sort(key=lambda x: x['volume'], reverse=True)
        return pairs[:100]
    except Exception as e:
        log.error(f"خطأ tickers: {e}")
        return []

def detect_accumulation(exchange, symbol):
    """
    كيشوف واش العملة فالتجميع:
    1. سعر ثابت (range < 2%) فآخر 4 ساعات
    2. حجم كيزيد (آخر ساعة > متوسط)
    3. RSI نازل (oversold)
    4. BB ضيّقين (squeeze)
    5. قريبة من الدعم
    """
    try:
        # 1H candles — آخر 24 ساعة
        candles_1h = exchange.fetch_ohlcv(symbol, '1h', limit=24)
        if len(candles_1h) < 12: return None
        df = pd.DataFrame(candles_1h, columns=['t','o','h','l','c','v'])
        
        price = float(df.iloc[-1]['c'])
        
        # === 1. سعر ثابت فآخر 4 ساعات ===
        last4 = df.iloc[-4:]
        price_range = float((last4['h'].max() - last4['l'].min()) / last4['l'].min() * 100)
        if price_range > 3: return None  # ماشي تجميع — كيتحرك بزاف
        
        # === 2. حجم كيزيد ===
        vol_last2 = float(df['v'].iloc[-2:].mean())
        vol_avg = float(df['v'].iloc[:-2].mean())
        vol_ratio = round(vol_last2 / vol_avg, 1) if vol_avg > 0 else 1
        
        # === 3. RSI على 15m ===
        candles_15m = exchange.fetch_ohlcv(symbol, '15m', limit=30)
        df15 = pd.DataFrame(candles_15m, columns=['t','o','h','l','c','v'])
        rsi = calc_rsi(df15['c'])
        
        # === 4. Bollinger Bands squeeze ===
        sma20 = float(df15['c'].rolling(20).mean().iloc[-1])
        std20 = float(df15['c'].rolling(20).std().iloc[-1])
        bb_upper = sma20 + 2 * std20
        bb_lower = sma20 - 2 * std20
        bb_width = round((bb_upper - bb_lower) / sma20 * 100, 2)
        bb_pos = round(float((price - bb_lower) / (bb_upper - bb_lower) * 100), 0) if bb_upper != bb_lower else 50
        
        # === 5. دعم ومقاومة ===
        support = float(df['l'].rolling(20).min().iloc[-1])
        resistance = float(df['h'].rolling(20).max().iloc[-1])
        near_support = round((price - support) / support * 100, 2)
        near_resist = round((resistance - price) / price * 100, 2)
        
        # === 6. شمعات أخيرة: خضراء بعد حمراء = انعكاس ===
        last3 = df.iloc[-3:]
        reversal = (last3.iloc[-1]['c'] > last3.iloc[-1]['o'] and  # آخر شمعة خضراء
                   last3.iloc[-2]['c'] < last3.iloc[-2]['o'])       # قبلها حمراء
        
        # === SCORE ===
        score = 0
        
        # تجميع (سعر ثابت)
        if price_range < 1.0: score += 30
        elif price_range < 1.5: score += 20
        elif price_range < 2.0: score += 10
        
        # حجم كيزيد
        if vol_ratio >= 2.0: score += 25
        elif vol_ratio >= 1.5: score += 15
        elif vol_ratio >= 1.2: score += 10
        
        # RSI oversold
        if rsi < 25: score += 30
        elif rsi < 30: score += 25
        elif rsi < 35: score += 15
        elif rsi < 40: score += 5
        
        # BB squeeze (ضيّقين = انفجار قريب)
        if bb_width < 1.0: score += 25
        elif bb_width < 2.0: score += 15
        elif bb_width < 3.0: score += 5
        
        # قريب من الدعم
        if near_support < 0.5: score += 25
        elif near_support < 1.0: score += 15
        elif near_support < 2.0: score += 10
        
        # مقاومة (سلبي إلا قريب)
        if near_resist < 0.5: score -= 20
        elif near_resist < 1.0: score -= 10
        
        # انعكاس
        if reversal: score += 15
        
        if score < 50: return None
        
        return {
            "symbol": symbol, "price": price, "score": score,
            "rsi": rsi, "vol_ratio": vol_ratio,
            "price_range": price_range, "bb_width": bb_width,
            "bb_pos": bb_pos, "near_support": near_support,
            "near_resist": near_resist, "reversal": reversal,
            "accumulation": price_range < 2 and vol_ratio > 1.2
        }
    except Exception as e:
        log.debug(f"Error {symbol}: {e}")
        return None

def run():
    log.info("🕵️ === الجاسوس بدا! كيدوّر على التجميع ===")
    exchange = connect()
    cycle = 0
    found_today = {}
    
    while True:
        try:
            cycle += 1
            pairs = get_all_usdt_pairs(exchange)
            log.info(f"🔍 سكان {len(pairs)} عملة...")
            
            opportunities = []
            for pair in pairs:
                result = detect_accumulation(exchange, pair['symbol'])
                if result and result['score'] >= 60:
                    opportunities.append(result)
                time.sleep(0.5)  # rate limit
            
            opportunities.sort(key=lambda x: x['score'], reverse=True)
            
            if opportunities:
                log.info(f"🎯 لقيت {len(opportunities)} فرصة تجميع!")
                for opp in opportunities[:5]:
                    sym = opp['symbol']
                    # ما تبعتش نفس العملة كل 30 دقيقة
                    if sym in found_today:
                        if (datetime.now() - found_today[sym]).total_seconds() < 1800: continue
                    found_today[sym] = datetime.now()
                    
                    emoji = "🔥" if opp['score'] >= 80 else "🎯"
                    accum = "✅ تجميع!" if opp['accumulation'] else ""
                    rev = "↩️ انعكاس!" if opp['reversal'] else ""
                    
                    msg = (f"{emoji} <b>فرصة تجميع!</b>\n"
                           f"🪙 <b>{sym}</b> ${opp['price']:.6f}\n"
                           f"📊 Score: {opp['score']}/150\n"
                           f"📈 RSI: {opp['rsi']} | Vol: {opp['vol_ratio']}x\n"
                           f"📉 Range: {opp['price_range']:.1f}% | BB: {opp['bb_width']:.1f}%\n"
                           f"🎯 دعم: {opp['near_support']:.1f}% | مقاومة: {opp['near_resist']:.1f}%\n"
                           f"{accum} {rev}")
                    
                    send_tg(msg)
                    log.info(f"{emoji} {sym} Score:{opp['score']} RSI:{opp['rsi']} "
                        f"Vol:{opp['vol_ratio']}x Range:{opp['price_range']:.1f}% "
                        f"BB:{opp['bb_width']:.1f}% {accum} {rev}")
            else:
                log.info("📊 ما كاين تجميع واضح دابا")
            
            # سكان كل 5 دقائق (100 عملة × 2 API calls = 200 call / 5 min = OK)
            log.info(f"💤 نعاود بعد 5 دقائق...")
            time.sleep(300)
            
        except KeyboardInterrupt: break
        except Exception as e:
            log.error(f"خطأ: {e}")
            time.sleep(60)

if __name__ == "__main__": run()
