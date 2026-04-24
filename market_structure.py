"""
market_structure.py - فهم السوق الحقيقي
- Swing Lows/Highs detection
- Support/Resistance clustering  
- Smart SL/TP placement
"""
import pandas as pd


def find_swing_lows(df, lookback=3):
    """لقى swing lows: نقاط أدنى من ±lookback candles"""
    if len(df) < lookback * 2 + 1:
        return []
    
    swing_lows = []
    lows = df['l'].values if 'l' in df.columns else df['low'].values
    
    for i in range(lookback, len(lows) - lookback):
        window_lows = lows[i-lookback:i+lookback+1]
        if lows[i] == min(window_lows):
            swing_lows.append(float(lows[i]))
    
    return swing_lows


def find_swing_highs(df, lookback=3):
    """لقى swing highs"""
    if len(df) < lookback * 2 + 1:
        return []
    
    swing_highs = []
    highs = df['h'].values if 'h' in df.columns else df['high'].values
    
    for i in range(lookback, len(highs) - lookback):
        window_highs = highs[i-lookback:i+lookback+1]
        if highs[i] == max(window_highs):
            swing_highs.append(float(highs[i]))
    
    return swing_highs


def cluster_levels(levels, tolerance=0.005):
    """جمع levels قريبين كـsupport/resistance واحد"""
    if not levels:
        return []
    
    sorted_levels = sorted(levels)
    clusters = []
    current_cluster = [sorted_levels[0]]
    
    for level in sorted_levels[1:]:
        avg = sum(current_cluster) / len(current_cluster)
        if abs(level - avg) / avg < tolerance:
            current_cluster.append(level)
        else:
            clusters.append({
                'level': sum(current_cluster) / len(current_cluster),
                'touches': len(current_cluster),
                'strength': 'strong' if len(current_cluster) >= 3 else 'weak'
            })
            current_cluster = [level]
    
    # آخر cluster
    clusters.append({
        'level': sum(current_cluster) / len(current_cluster),
        'touches': len(current_cluster),
        'strength': 'strong' if len(current_cluster) >= 3 else 'weak'
    })
    
    return clusters


def find_nearest_support(price, swing_lows, max_distance_pct=2.5):
    """لقى أقرب support تحت السعر"""
    below_price = [l for l in swing_lows if l < price]
    
    if not below_price:
        return None
    
    nearest = max(below_price)
    distance_pct = (price - nearest) / price * 100
    
    if distance_pct > max_distance_pct:
        return None
    
    return {
        'level': nearest,
        'distance_pct': round(distance_pct, 2)
    }


def find_nearest_resistance(price, swing_highs, max_distance_pct=3.0):
    """لقى أقرب resistance فوق السعر"""
    above_price = [h for h in swing_highs if h > price]
    
    if not above_price:
        return None
    
    nearest = min(above_price)
    distance_pct = (nearest - price) / price * 100
    
    if distance_pct > max_distance_pct:
        return None
    
    return {
        'level': nearest,
        'distance_pct': round(distance_pct, 2)
    }


def calculate_smart_sl(entry_price, df_15m, buffer_pct=0.005, max_sl_pct=0.02, min_sl_pct=0.004):
    """
    حساب SL ذكي:
    - تحت أقرب swing low
    - buffer 0.2%
    - إذا بعيد > 1.5% = reject
    
    Returns: (sl_price, support_used) أو (None, None) = reject
    """
    if df_15m is None or len(df_15m) < 20:
        return None, None
    
    swing_lows = find_swing_lows(df_15m, lookback=3)
    if not swing_lows:
        return None, None
    
    support_info = find_nearest_support(entry_price, swing_lows, max_distance_pct=2.5)
    if not support_info:
        return None, None
    
    support_level = support_info['level']
    sl_price = support_level * (1 - buffer_pct)
    
    # تحقق SL distance (min & max)
    sl_distance = (entry_price - sl_price) / entry_price
    if sl_distance > max_sl_pct:
        return None, None
    if sl_distance < min_sl_pct:
        return None, None  # SL قريب بزاف = stop hunt zone
    
    return round(sl_price, 10), support_info


def calculate_smart_tp(entry_price, df_15m, min_rr=1.5, fallback_tp_pct=0.008):
    """
    حساب TP ذكي:
    - على أقرب resistance
    - إذا ماكاينش = fallback 0.8%
    """
    if df_15m is None or len(df_15m) < 20:
        return entry_price * (1 + fallback_tp_pct), None
    
    swing_highs = find_swing_highs(df_15m, lookback=3)
    resistance_info = find_nearest_resistance(entry_price, swing_highs, max_distance_pct=3.0)
    
    if not resistance_info:
        return round(entry_price * (1 + fallback_tp_pct), 10), None
    
    # TP قبل resistance بـ0.1% (ماشي مباشرة عليه)
    tp_price = resistance_info['level'] * 1.002  # قليلاً فوق resistance
    
    return round(tp_price, 10), resistance_info


def analyze_structure(df_1h, df_15m, current_price):
    """تحليل شامل - يرجع dict كامل"""
    result = {
        'swing_lows_15m': find_swing_lows(df_15m),
        'swing_highs_15m': find_swing_highs(df_15m),
        'swing_lows_1h': find_swing_lows(df_1h),
        'swing_highs_1h': find_swing_highs(df_1h),
    }
    
    # Clustering support/resistance
    all_lows = result['swing_lows_15m'] + result['swing_lows_1h']
    all_highs = result['swing_highs_15m'] + result['swing_highs_1h']
    
    result['support_zones'] = cluster_levels(all_lows, tolerance=0.008)
    result['resistance_zones'] = cluster_levels(all_highs, tolerance=0.008)
    
    # Nearest levels
    result['nearest_support'] = find_nearest_support(current_price, all_lows)
    result['nearest_resistance'] = find_nearest_resistance(current_price, all_highs)
    
    return result
