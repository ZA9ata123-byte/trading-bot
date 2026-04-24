"""
analysis.py v3 — تحليل شامل متعدد الأطر (Fixed)
═══════════════════════════════════════════════════
[FIX] near_resist يمنع الدخول دائماً
[FIX] أولوية العمليات صحيحة
"""
import pandas as pd
import logging
log = logging.getLogger(__name__)

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain  = delta.where(delta > 0, 0).ewm(com=period-1, min_periods=period).mean()
    loss  = (-delta.where(delta < 0, 0)).ewm(com=period-1, min_periods=period).mean()
    rs    = gain / loss.replace(0, 1)
    return 100 - (100 / (1 + rs))

def get_candle_pattern(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    o, h, l, c = last['open'], last['high'], last['low'], last['close']
    body   = abs(c - o)
    total  = h - l
    
    patterns = []
    
    if (c > o and prev['close'] < prev['open'] and
        c > prev['open'] and o < prev['close']):
        patterns.append("Bullish Engulfing 🟢")
    
    lower_wick = min(o, c) - l
    if lower_wick > body * 2 and total > 0:
        patterns.append("Hammer 🔨")
    
    if body < total * 0.1 and total > 0:
        patterns.append("Doji ⚖️")
    
    if c > o and body > total * 0.7:
        patterns.append("شمعة صاعدة قوية 💪")
    
    if c < o and body > total * 0.7:
        patterns.append("شمعة هابطة قوية ⚠️")
    
    return patterns if patterns else ["عادية"]

def get_support_resistance(df, lookback=20):
    highs  = df['high'].rolling(lookback).max().iloc[-1]
    lows   = df['low'].rolling(lookback).min().iloc[-1]
    pivot  = (highs + lows + df['close'].iloc[-1]) / 3
    r1     = 2 * pivot - lows
    s1     = 2 * pivot - highs
    
    return {
        "resistance": round(highs, 8),
        "support":    round(lows, 8),
        "pivot":      round(pivot, 8),
        "r1":         round(r1, 8),
        "s1":         round(s1, 8),
    }

def analyze_timeframe(exchange, symbol, tf, limit=100):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, tf, limit=limit)
        df    = pd.DataFrame(ohlcv,
                columns=['timestamp','open','high','low','close','volume'])
        
        df['ma7']     = df['close'].rolling(7).mean()
        df['ma25']    = df['close'].rolling(25).mean()
        df['ma99']    = df['close'].rolling(99).mean()
        df['rsi']     = calculate_rsi(df['close'])
        df['rsi6']    = calculate_rsi(df['close'], 6)
        df['vol_avg'] = df['volume'].rolling(20).mean()
        df['ema12']   = df['close'].ewm(span=12).mean()
        df['ema26']   = df['close'].ewm(span=26).mean()
        df['macd']    = df['ema12'] - df['ema26']
        df['signal']  = df['macd'].ewm(span=9).mean()
        
        last  = df.iloc[-1]
        prev  = df.iloc[-2]
        price = last['close']
        
        ma7   = last['ma7']
        ma25  = last['ma25']
        ma99  = last['ma99']
        rsi   = last['rsi']
        
        vol_ratio    = last['volume'] / last['vol_avg'] if last['vol_avg'] > 0 else 1
        ma7_distance = (price - ma7) / ma7 * 100 if ma7 > 0 else 0
        
        macd_bullish = last['macd'] > last['signal'] and prev['macd'] <= prev['signal']
        patterns = get_candle_pattern(df)
        sr = get_support_resistance(df)
        
        near_support = abs(price - sr['support']) / price < 0.02
        near_resist  = abs(price - sr['resistance']) / price < 0.02
        
        score = 0
        if ma7 > ma25 > ma99:      score += 25
        if 40 < rsi < 60:          score += 20    # خفضنا من 65
        elif 35 < rsi < 65:        score += 10
        if vol_ratio >= 1.5:       score += 20
        elif vol_ratio >= 1.0:     score += 10
        if last['rsi6'] > prev['rsi6']: score += 15
        if macd_bullish:           score += 15
        if near_support:           score += 10
        if price > ma7:            score += 5
        if near_resist:            score -= 25    # زدنا العقوبة!
        if ma7_distance > 3:       score -= 15
        
        return {
            "ok":           score >= 65 and not near_resist,
            "score":        score,
            "rsi":          round(rsi, 1),
            "vol_ratio":    round(vol_ratio, 2),
            "ma7":          round(ma7, 8),
            "ma25":         round(ma25, 8),
            "ma99":         round(ma99, 8),
            "ma_aligned":   ma7 > ma25 > ma99,
            "macd_bullish": macd_bullish,
            "near_support": near_support,
            "near_resist":  near_resist,
            "ma7_distance": round(ma7_distance, 2),
            "patterns":     patterns,
            "support":      sr['support'],
            "resistance":   sr['resistance'],
            "pivot":        sr['pivot'],
        }
    except Exception as e:
        log.error(f"خطأ {tf} {symbol}: {e}")
        return {"ok": False, "score": 0, "near_resist": False}

def full_analysis(exchange, symbol):
    tf1h  = analyze_timeframe(exchange, symbol, "1h",  limit=100)
    tf15m = analyze_timeframe(exchange, symbol, "15m", limit=100)
    tf5m  = analyze_timeframe(exchange, symbol, "5m",  limit=50)
    tf1m  = analyze_timeframe(exchange, symbol, "1m",  limit=30)
    
    trend_ok = tf1h.get('ma_aligned', False)
    
    total_score = (
        tf1h.get('score',  0) * 0.30 +
        tf15m.get('score', 0) * 0.35 +
        tf5m.get('score',  0) * 0.20 +
        tf1m.get('score',  0) * 0.15
    )
    
    bullish_candle = any(p in ['شمعة صاعدة قوية 💪', 'Bullish Engulfing 🟢', 'Hammer 🔨'] 
                      for p in tf15m.get('patterns', []))
    
    # ═══ FIX: near_resist يمنع الدخول دائماً! ═════════════════
    near_resist = tf15m.get('near_resist', True)
    
    # ممنوع الدخول عند المقاومة — حتى لو Score عالي!
    if near_resist:
        enter = False
    else:
        condition_full = (
            total_score >= 45 and
            bullish_candle and
            trend_ok and
            tf15m.get('ok', False)
        )
        condition_strong = (
            total_score >= 75 and
            tf15m.get('ok', False)
        )
        enter = condition_full or condition_strong
    
    log.info(
        f"📊 {symbol} | "
        f"1h:{tf1h.get('score',0)} | "
        f"15m:{tf15m.get('score',0)} | "
        f"5m:{tf5m.get('score',0)} | "
        f"Total:{total_score:.0f} | "
        f"Resist:{near_resist} | "
        f"Enter:{enter}"
    )
    
    return {
        "enter":      enter,
        "score":      round(total_score, 1),
        "trend_ok":   trend_ok,
        "rsi":        tf15m.get('rsi', 50),
        "vol_ratio":  tf15m.get('vol_ratio', 1),
        "ma7":        tf15m.get('ma7', 0),
        "support":    tf15m.get('support', 0),
        "resistance": tf15m.get('resistance', 0),
        "patterns":   tf15m.get('patterns', []),
        "near_support": tf15m.get('near_support', False),
        "near_resist":  near_resist,
        "1h_score":   tf1h.get('score', 0),
        "15m_score":  tf15m.get('score', 0),
    }
