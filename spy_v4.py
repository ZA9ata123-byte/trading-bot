"""
spy_v4.py - الجاسوس v4
EMA filter + multi-timeframe + writes watchlist.json for Hunter
"""
import ccxt
import json
import time
import logging
import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from config_v4 import *

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [SPY] %(message)s',
    handlers=[
        logging.FileHandler('/root/micro-scalping/spy_v4.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger('spy')

BASE = '/root/micro-scalping'
WATCHLIST_FILE = os.path.join(BASE, 'watchlist.json')


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


def calc_ema(series, period):
    return series.ewm(span=period, adjust=False).mean().iloc[-1]


def get_candidates(exchange):
    try:
        tickers = exchange.fetch_tickers()
        pairs = []
        for symbol, t in tickers.items():
            if not symbol.endswith("/USDT"):
                continue
            base = symbol.split("/")[0]
            if any(base.endswith(x) for x in ['UP','DOWN','BULL','BEAR','3L','3S','5L','5S']):
                continue
            if any(x in base for x in ['USD','USDC','USDT','DAI','TUSD','BUSD','FDUSD','EUR','GBP','BRL','TRY']):
                continue
            if symbol in HARD_BLACKLIST:
                continue
            price = t.get('last', 0) or 0
            volume = t.get('quoteVolume', 0) or 0
            change = t.get('percentage', 0) or 0
            if price <= MIN_PRICE or price > MAX_PRICE:
                continue
            if 0.99 < price < 1.01:
                continue
            if volume < MIN_VOLUME_USD:
                continue
            if change > MAX_CHANGE_PCT or change < MIN_CHANGE_PCT:
                continue
            pairs.append({
                "symbol": symbol,
                "price": price,
                "volume": volume,
                "change": change
            })
        whitelist_pairs = [p for p in pairs if p['symbol'] in SOFT_WHITELIST]
        other_pairs = [p for p in pairs if p['symbol'] not in SOFT_WHITELIST]
        other_pairs.sort(key=lambda x: x['volume'], reverse=True)
        return whitelist_pairs + other_pairs[:100]
    except Exception as e:
        log.error(f"Error get_candidates: {e}")
        return []


def analyze_coin(exchange, symbol):
    try:
        candles_1h = exchange.fetch_ohlcv(symbol, '1h', limit=60)
        if len(candles_1h) < 50:
            return None
        df_1h = pd.DataFrame(candles_1h, columns=['t','o','h','l','c','v'])
        price = float(df_1h.iloc[-1]['c'])
        ema_50_1h = float(calc_ema(df_1h['c'], EMA_PERIOD_1H))
        if EMA_FILTER_ENABLED and price < ema_50_1h:
            log.info(f"  DBG {symbol}: REJECT EMA_1h price={price:.6f} < ema={ema_50_1h:.6f}")
            return None
        candles_4h = exchange.fetch_ohlcv(symbol, '4h', limit=30)
        if len(candles_4h) < 25:
            return None
        df_4h = pd.DataFrame(candles_4h, columns=['t','o','h','l','c','v'])
        ema_20_4h = float(calc_ema(df_4h['c'], EMA_PERIOD_4H))
        if price < ema_20_4h:
            log.info(f"  DBG {symbol}: REJECT EMA_4h price={price:.6f} < ema4h={ema_20_4h:.6f}")
            return None
        last_3_4h = df_4h.iloc[-3:]
        green_count = sum(1 for _, c in last_3_4h.iterrows() if c['c'] > c['o'])
        if green_count < 2:
            log.info(f"  DBG {symbol}: REJECT green={green_count}/3")
            return None
        last_4h_range = float(
            (df_1h['h'].iloc[-4:].max() - df_1h['l'].iloc[-4:].min()) /
            df_1h['l'].iloc[-4:].min() * 100
        )
        if last_4h_range > 4:
            log.info(f"  DBG {symbol}: REJECT range_4h={last_4h_range:.2f}%")
            return None
        vol_last_2h = float(df_1h['v'].iloc[-2:].mean())
        vol_avg = float(df_1h['v'].iloc[-20:-2].mean())
        vol_ratio = round(vol_last_2h / vol_avg, 1) if vol_avg > 0 else 1
        candles_15m = exchange.fetch_ohlcv(symbol, '15m', limit=30)
        df_15m = pd.DataFrame(candles_15m, columns=['t','o','h','l','c','v'])
        rsi_15m = calc_rsi(df_15m['c'])
        if rsi_15m < RSI_BUY_MIN or rsi_15m > RSI_BUY_MAX:
            log.info(f"  DBG {symbol}: REJECT rsi_15m={rsi_15m} (range {RSI_BUY_MIN}-{RSI_BUY_MAX})")
            return None
        sma20 = float(df_15m['c'].rolling(20).mean().iloc[-1])
        std20 = float(df_15m['c'].rolling(20).std().iloc[-1])
        bb_upper = sma20 + 2 * std20
        bb_lower = sma20 - 2 * std20
        bb_width = round((bb_upper - bb_lower) / sma20 * 100, 2) if sma20 > 0 else 0
        support = float(df_1h['l'].rolling(20).min().iloc[-1])
        resistance = float(df_1h['h'].rolling(20).max().iloc[-1])
        near_support = round((price - support) / support * 100, 2)
        near_resist = round((resistance - price) / price * 100, 2)
        
        # Support distance - use as score, not hard reject
        # (Guardian will decide with Smart SL)
        score = 0
        if price > ema_50_1h * 1.005:
            score += 20
        if price > ema_20_4h * 1.01:
            score += 15
        if last_4h_range < 1.5:
            score += 25
        elif last_4h_range < 2.5:
            score += 15
        if vol_ratio >= 2.0:
            score += 20
        elif vol_ratio >= 1.5:
            score += 15
        elif vol_ratio >= MIN_VOL_RATIO:
            score += 10
        if 32 <= rsi_15m <= 40:
            score += 20
        elif 30 <= rsi_15m <= 45:
            score += 10
        if bb_width < 1.5:
            score += 15
        elif bb_width < 2.5:
            score += 8
        if near_support < 1.0:
            score += 20
        elif near_support < 2.0:
            score += 10
        if near_resist > 3:
            score += 10
        elif near_resist < 0.5:
            score -= 20
        if symbol in SOFT_WHITELIST:
            score += 15
        log.info(f"  DBG {symbol}: PASSED all filters, score={score}")
        return {
            "symbol": symbol,
            "price": price,
            "score": score,
            "rsi_15m": rsi_15m,
            "vol_ratio": vol_ratio,
            "ema_50_1h": round(ema_50_1h, 8),
            "ema_20_4h": round(ema_20_4h, 8),
            "range_4h": round(last_4h_range, 2),
            "bb_width": bb_width,
            "near_support": near_support,
            "near_resist": near_resist,
            "trend_1h": "up" if price > ema_50_1h else "down",
            "trend_4h": "up" if price > ema_20_4h else "down",
            "green_candles_4h": green_count,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        log.debug(f"Analyze error {symbol}: {e}")
        return None



def send_periodic_report():
    """تقرير دوري كل 30 دقيقة"""
    try:
        # اقرا performance
        perf = load_json(os.path.join(BASE, 'performance.json'), {})
        mem = load_json(os.path.join(BASE, 'trade_memory.json'), {'trades':[]})
        
        today = str(datetime.now().date())
        today_trades_count = perf.get('today_trades', 0)
        today_wins = perf.get('today_wins', 0)
        today_pnl = perf.get('today_pnl', 0)
        today_losses = today_trades_count - today_wins
        wr = (today_wins/today_trades_count*100) if today_trades_count else 0
        
        # آخر 5 صفقات
        recent = mem.get('trades', [])[-5:]
        recent_lines = []
        for t in recent:
            emoji = "✅" if t.get('won') else "❌"
            sym = t.get('symbol', '?')[:10]
            profit = t.get('profit', 0)
            recent_lines.append(f"{emoji} {sym} ${profit:+.2f}")
        
        # watchlist الحالية
        wl_data = load_json(os.path.join(BASE, 'watchlist.json'), {})
        wl_count = len(wl_data.get('watchlist', []))
        wl_top = wl_data.get('watchlist', [])[:3]
        wl_lines = []
        for w in wl_top:
            wl_lines.append(f"🎯 {w['symbol']} Score:{w['score']} RSI:{w['rsi_15m']}")
        
        msg_parts = [
            "🐺 <b>تقرير الذئاب - كل 30 دقيقة</b>",
            f"📅 {datetime.now().strftime('%H:%M')}",
            "",
            "📊 <b>اليوم:</b>",
            f"   صفقات: {today_trades_count}",
            f"   ✅ رابحة: {today_wins}",
            f"   ❌ خاسرة: {today_losses}",
            f"   📈 WR: {wr:.0f}%",
            f"   💰 P&L: ${today_pnl:+.2f}",
        ]
        
        if recent_lines:
            msg_parts.append("")
            msg_parts.append("🕐 <b>آخر 5 صفقات:</b>")
            msg_parts.extend([f"   {line}" for line in recent_lines])
        
        msg_parts.append("")
        msg_parts.append(f"👁️ <b>Watchlist:</b> {wl_count} عملة")
        if wl_lines:
            msg_parts.extend([f"   {line}" for line in wl_lines])
        else:
            msg_parts.append("   (ماكايناش فرص حالياً - market bearish)")
        
        send_tg("\n".join(msg_parts), TELEGRAM_CHANNEL_AR)
        log.info("Periodic report sent to Telegram")
    except Exception as e:
        log.error(f"Report error: {e}")


def run():
    log.info("="*60)
    log.info("Spy v4 started")
    log.info(f"EMA Filter: {EMA_FILTER_ENABLED}")
    log.info(f"RSI Range: {RSI_BUY_MIN}-{RSI_BUY_MAX}")
    log.info(f"Price Range: ${MIN_PRICE}-${MAX_PRICE}")
    log.info("="*60)
    exchange = connect()
    cycle = 0
    last_report_time = 0
    while True:
        try:
            cycle += 1
            start_time = time.time()
            candidates = get_candidates(exchange)
            log.info(f"Cycle #{cycle}: scanning {len(candidates)} coins...")
            opportunities = []
            for i, pair in enumerate(candidates):
                result = analyze_coin(exchange, pair['symbol'])
                if result and result['score'] >= 60:
                    opportunities.append(result)
                time.sleep(0.3)
                if (i+1) % 25 == 0:
                    log.info(f"  Progress {i+1}/{len(candidates)} - found {len(opportunities)}")
            opportunities.sort(key=lambda x: x['score'], reverse=True)
            top_10 = opportunities[:10]
            watchlist_data = {
                "updated_at": datetime.now().isoformat(),
                "cycle": cycle,
                "total_scanned": len(candidates),
                "total_found": len(opportunities),
                "watchlist": top_10
            }
            save_json(WATCHLIST_FILE, watchlist_data)
            if top_10:
                log.info(f"Found {len(opportunities)} opportunities, top 10 saved:")
                for i, opp in enumerate(top_10[:5]):
                    sym = opp['symbol']
                    rsi_v = opp['rsi_15m']
                    vol_v = opp['vol_ratio']
                    bb_v = opp['bb_width']
                    sup_v = opp['near_support']
                    log.info(f"  #{i+1} {sym} Score:{opp['score']} RSI:{rsi_v} Vol:{vol_v}x BB:{bb_v}% Sup:{sup_v}%")
                if top_10:
                    msg_lines = ["<b>Spy found opportunities!</b>"]
                    for i, opp in enumerate(top_10[:3]):
                        priority = "FIRE" if opp['score'] >= 80 else "TGT"
                        wl_mark = "*" if opp['symbol'] in SOFT_WHITELIST else ""
                        line = (f"[{priority}] <b>{opp['symbol']}</b> {wl_mark} "
                                f"${opp['price']:.6f} Score:{opp['score']} "
                                f"RSI:{opp['rsi_15m']} Vol:{opp['vol_ratio']}x")
                        msg_lines.append(line)
                    send_tg("\n".join(msg_lines))
            else:
                log.info("No opportunities found this cycle")
            # Periodic report كل 30 دقيقة
            if time.time() - last_report_time > 1800:
                send_periodic_report()
                last_report_time = time.time()
            
            elapsed = time.time() - start_time
            sleep_time = max(0, SPY_SLEEP - elapsed)
            log.info(f"Cycle done in {elapsed:.0f}s - sleeping {sleep_time:.0f}s")
            time.sleep(sleep_time)
        except KeyboardInterrupt:
            log.info("Stopped by user")
            break
        except Exception as e:
            log.error(f"Cycle error: {e}")
            time.sleep(60)


if __name__ == "__main__":
    run()
