import pandas as pd
import numpy as np
from config import *

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

def analyze(df):
    if df is None or len(df) < 50:
        return None

    df['rsi']      = calculate_rsi(df['close'])
    df['rsi_fast'] = calculate_rsi(df['close'], RSI_FAST)
    df['ema_fast'] = calculate_ema(df['close'], EMA_FAST)
    df['ema_slow'] = calculate_ema(df['close'], EMA_SLOW)
    df['ema_trend']= calculate_ema(df['close'], EMA_TREND)
    df['vol_avg']  = df['volume'].rolling(20).mean()

    last = df.iloc[-1]

    if pd.isna(last['rsi']) or pd.isna(last['ema_fast']):
        return None

    divergence = detect_divergence(df, df['rsi'])
    signal     = None

    # شروط الشراء
    if divergence == "BUY":
        if (last['rsi'] < RSI_OVERSOLD + 15 and
            last['close'] > last['ema_slow'] and
            last['ema_fast'] > last['ema_slow'] and
            last['volume'] > last['vol_avg'] * VOLUME_INCREASE):
            signal = "BUY"

    # شروط البيع
    elif divergence == "SELL":
        if (last['rsi'] > RSI_OVERBOUGHT - 15 and
            last['close'] < last['ema_slow'] and
            last['ema_fast'] < last['ema_slow'] and
            last['volume'] > last['vol_avg'] * VOLUME_INCREASE):
            signal = "SELL"

    if signal:
        return {
            "signal":   signal,
            "price":    last['close'],
            "rsi":      round(last['rsi'], 2),
            "ema_fast": round(last['ema_fast'], 6),
            "ema_slow": round(last['ema_slow'], 6),
        }
    return None
