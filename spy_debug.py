"""Debug version - يقول لينا بالضبط أش filter كيقطع"""
import ccxt
import pandas as pd
import time
from config_v4 import *

ex = ccxt.binance({'apiKey': BINANCE_API_KEY, 'secret': BINANCE_API_SECRET, 'enableRateLimit': True})
ex.load_time_difference()

def calc_rsi(s, p=14):
    d = s.diff()
    g = d.where(d>0,0).ewm(com=p-1,min_periods=p).mean()
    l = (-d.where(d<0,0)).ewm(com=p-1,min_periods=p).mean()
    return round(float((100-100/(1+g/l.replace(0,1))).iloc[-1]), 1)

def calc_ema(s, p):
    return s.ewm(span=p, adjust=False).mean().iloc[-1]

# جيب 30 عملة top volume
tickers = ex.fetch_tickers()
pairs = []
for sym, t in tickers.items():
    if not sym.endswith("/USDT"): continue
    base = sym.split("/")[0]
    if any(base.endswith(x) for x in ['UP','DOWN','BULL','BEAR','3L','3S','5L','5S']): continue
    if any(x in base for x in ['USD','USDC','USDT','DAI','TUSD','BUSD','FDUSD','EUR','GBP']): continue
    if sym in HARD_BLACKLIST: continue
    price = t.get('last',0) or 0
    volume = t.get('quoteVolume',0) or 0
    change = t.get('percentage',0) or 0
    if price <= MIN_PRICE or price > MAX_PRICE: continue
    if 0.99 < price < 1.01: continue
    if volume < MIN_VOLUME_USD: continue
    if change > MAX_CHANGE_PCT or change < MIN_CHANGE_PCT: continue
    pairs.append({"symbol":sym, "price":price, "volume":volume})

pairs.sort(key=lambda x: x['volume'], reverse=True)
pairs = pairs[:30]

print(f"Testing {len(pairs)} coins:\n")
print(f"{'Symbol':<15} {'Price':<12} {'EMA1h':<10} {'EMA4h':<10} {'Green4h':<10} {'Range4h':<10} {'RSI15m':<8} {'NearSup':<10} REJECT_REASON")
print("-" * 130)

passed = 0
rejects = {"ema_1h":0, "ema_4h":0, "green_candles":0, "range_4h":0, "rsi_range":0, "near_support":0, "ok":0}

for p in pairs:
    sym = p['symbol']
    try:
        c1h = ex.fetch_ohlcv(sym, '1h', limit=60)
        if len(c1h) < 50:
            print(f"{sym:<15} -- not enough data")
            continue
        df1h = pd.DataFrame(c1h, columns=['t','o','h','l','c','v'])
        price = float(df1h.iloc[-1]['c'])
        ema50 = float(calc_ema(df1h['c'], 50))
        
        c4h = ex.fetch_ohlcv(sym, '4h', limit=30)
        df4h = pd.DataFrame(c4h, columns=['t','o','h','l','c','v'])
        ema20_4h = float(calc_ema(df4h['c'], 20))
        last3 = df4h.iloc[-3:]
        green = sum(1 for _,c in last3.iterrows() if c['c']>c['o'])
        
        range4h = float((df1h['h'].iloc[-4:].max()-df1h['l'].iloc[-4:].min())/df1h['l'].iloc[-4:].min()*100)
        
        c15m = ex.fetch_ohlcv(sym, '15m', limit=30)
        df15 = pd.DataFrame(c15m, columns=['t','o','h','l','c','v'])
        rsi = calc_rsi(df15['c'])
        
        support = float(df1h['l'].rolling(20).min().iloc[-1])
        near_sup = round((price-support)/support*100, 2)
        
        # Check each filter
        reason = ""
        if price < ema50: 
            reason = "BELOW_EMA_1h"
            rejects["ema_1h"] += 1
        elif price < ema20_4h:
            reason = "BELOW_EMA_4h"
            rejects["ema_4h"] += 1
        elif green < 2:
            reason = f"GREEN_{green}/3"
            rejects["green_candles"] += 1
        elif range4h > 4:
            reason = f"RANGE_{range4h:.1f}%"
            rejects["range_4h"] += 1
        elif rsi < RSI_BUY_MIN or rsi > RSI_BUY_MAX:
            reason = f"RSI_{rsi}"
            rejects["rsi_range"] += 1
        else:
            reason = "PASSED ✓"
            rejects["ok"] += 1
            passed += 1
        
        print(f"{sym:<15} {price:<12.6f} {ema50:<10.6f} {ema20_4h:<10.6f} {green}/3{'':<7} {range4h:<10.2f} {rsi:<8} {near_sup:<10} {reason}")
        time.sleep(0.3)
    except Exception as e:
        print(f"{sym:<15} ERROR: {e}")

print("\n" + "=" * 60)
print("SUMMARY:")
for k, v in rejects.items():
    print(f"  {k:<20} {v}")
print(f"\nPassed: {passed}/{len(pairs)}")
