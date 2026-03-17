import pandas as pd
import numpy as np
import re
import logging
from config import *

log = logging.getLogger(__name__)

def calculate_rsi(series, period=RSI_PERIOD):
    delta    = series.diff()
    gain     = delta.where(delta > 0, 0)
    loss     = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs       = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def detect_divergence(df, rsi, lookback=5):
    if len(df) < lookback + 2:
        return None

    price_now  = df['close'].iloc[-1]
    price_prev = df['close'].iloc[-lookback]
    rsi_now    = rsi.iloc[-1]
    rsi_prev   = rsi.iloc[-lookback]

    # Bullish Divergence → شراء
    if (price_now < price_prev and
        rsi_now > rsi_prev and
        rsi_now < RSI_OVERSOLD + 10):
        return "BUY"

    # Bearish Divergence → بيع
    if (price_now > price_prev and
        rsi_now < rsi_prev and
        rsi_now > RSI_OVERBOUGHT - 10):
        return "SELL"

    return None

def analyze_liquidity(df):
    """
    تحليل السيولة:
    - Volume Surge: الحجم زاد بشكل غير عادي
    - Spread: الفرق بين High و Low
    - Buy Pressure: ضغط الشراء
    """
    last     = df.iloc[-1]
    vol_avg  = df['volume'].rolling(20).mean().iloc[-1]
    
    # Volume Surge = السيولة تدخل
    volume_surge = last['volume'] > vol_avg * 1.5
    
    # Spread ضيق = سيولة عالية
    spread = (last['high'] - last['low']) / last['close']
    good_spread = spread < 0.05
    
    # Buy Pressure = الشمعة خضراء قوية
    candle_body = abs(last['close'] - last['open'])
    candle_range = last['high'] - last['low']
    buy_pressure = (last['close'] > last['open'] and 
                   candle_body > candle_range * 0.5) if candle_range > 0 else False

    return {
        "volume_surge": volume_surge,
        "good_spread":  good_spread,
        "buy_pressure": buy_pressure,
        "spread":       round(spread * 100, 2),
        "volume_ratio": round(last['volume'] / vol_avg, 2) if vol_avg > 0 else 0
    }

def detect_pump(df):
    """
    كشف البومب المبكر:
    - السعر يكسر EMA من تحت لفوق
    - Volume يزيد بشكل كبير
    - RSI يبدأ يصعد من منطقة منخفضة
    """
    if len(df) < 10:
        return False
    
    last     = df.iloc[-1]
    prev     = df.iloc[-2]
    vol_avg  = df['volume'].rolling(20).mean().iloc[-1]
    
    # السعر كسر EMA للأعلى
    price_crossed_ema = (prev['close'] < prev['ema_slow'] and 
                         last['close'] > last['ema_slow'])
    
    # Volume ضعف أو أكثر
    volume_spike = last['volume'] > vol_avg * 2
    
    # RSI صاعد من منطقة منخفضة
    rsi_rising = (last['rsi'] > prev['rsi'] and last['rsi'] < 50)
    
    return price_crossed_ema and volume_spike and rsi_rising

def analyze(df):
    if df is None or len(df) < 50:
        return None

    # حساب المؤشرات
    df['rsi']       = calculate_rsi(df['close'])
    df['rsi_fast']  = calculate_rsi(df['close'], RSI_FAST)
    df['ema_fast']  = calculate_ema(df['close'], EMA_FAST)
    df['ema_slow']  = calculate_ema(df['close'], EMA_SLOW)
    df['ema_trend'] = calculate_ema(df['close'], EMA_TREND)
    df['vol_avg']   = df['volume'].rolling(20).mean()

    last = df.iloc[-1]

    if pd.isna(last['rsi']) or pd.isna(last['ema_fast']):
        return None

    # تحليل السيولة
    liquidity = analyze_liquidity(df)
    
    # كشف البومب المبكر
    pump_detected = detect_pump(df)

    # كشف Divergence
    divergence = detect_divergence(df, df['rsi'])
    signal     = None
    strength   = "NORMAL"  # قوة الإشارة

    # شروط الشراء
    if divergence == "BUY":
        if (last['rsi'] < RSI_OVERSOLD + 15 and
            last['close'] > last['ema_slow'] and
            last['ema_fast'] > last['ema_slow']):
            
            # إشارة عادية
            signal = "BUY"
            
            # إشارة قوية = سيولة + بومب مبكر
            if liquidity['volume_surge'] and liquidity['good_spread']:
                strength = "STRONG"
            
            # إشارة قوية جداً = كل الشروط متوفرة
            if pump_detected and liquidity['volume_surge']:
                strength = "VERY_STRONG"

    elif divergence == "SELL":
        if (last['rsi'] > RSI_OVERBOUGHT - 15 and
            last['close'] < last['ema_slow'] and
            last['ema_fast'] < last['ema_slow']):
            signal = "SELL"

    if signal:
        return {
            "signal":       signal,
            "strength":     strength,
            "price":        last['close'],
            "rsi":          round(last['rsi'], 2),
            "ema_fast":     round(last['ema_fast'], 6),
            "ema_slow":     round(last['ema_slow'], 6),
            "volume_ratio": liquidity['volume_ratio'],
            "spread":       liquidity['spread'],
            "pump":         pump_detected,
        }
    return None
```

---

## 🎯 الجديد في هاذا الملف:
```
✅ تحليل السيولة (Volume + Spread + Buy Pressure)
✅ كشف البومب المبكر (pump_detected)
✅ تصنيف قوة الإشارة:
   NORMAL = إشارة عادية
   STRONG = سيولة + إشارة
   VERY_STRONG = بومب + سيولة + إشارة 🚀
