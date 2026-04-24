"""
🐺 guardian.py v3 — الحارس السريع
SL فوري + TP 0.8% + RSI exit + Timeout 3m
"""
import ccxt, json, time, logging, os, requests
import pandas as pd
from datetime import datetime, timedelta
from config import *

logging.basicConfig(level=logging.INFO, format='%(asctime)s [GUARD] %(message)s',
    handlers=[logging.FileHandler('/root/micro-scalping/guardian.log', encoding='utf-8'), logging.StreamHandler()])
log = logging.getLogger('guardian')

SIGNALS_FILE = '/root/micro-scalping/signals.json'
OPEN_TRADES_FILE = '/root/micro-scalping/open_trades.json'
MEMORY_FILE = '/root/micro-scalping/trade_memory.json'
PERFORMANCE_FILE = '/root/micro-scalping/performance.json'
INTEL_FILE = '/root/micro-scalping/coin_intelligence.json'

def load_json(path, default=None):
    try:
        with open(path, 'r') as f: return json.load(f)
    except: return default if default is not None else {}

def save_json(path, data):
    with open(path, 'w') as f: json.dump(data, f, ensure_ascii=False, indent=2)

def send_tg(text):
    for ch in [TELEGRAM_CHANNEL_AR]:
        try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": ch, "text": text, "parse_mode": "HTML"}, timeout=10)
        except: pass

def connect():
    ex = ccxt.binance({'apiKey': BINANCE_API_KEY, 'secret': BINANCE_API_SECRET, 'enableRateLimit': True,
        'options': {'defaultType': 'spot', 'recvWindow': 60000, 'adjustForTimeDifference': True}})
    ex.load_time_difference()
    return ex

def calc_rsi(series):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).ewm(com=13).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(com=13).mean()
    return round((100 - 100 / (1 + gain / loss.replace(0, 1))).iloc[-1], 1)

def get_rsi(exchange, symbol):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, "1m", limit=20)
        df = pd.DataFrame(ohlcv, columns=['t','o','h','l','close','v'])
        return calc_rsi(df['close'])
    except: return 50

def process_signals(exchange):
    signals = load_json(SIGNALS_FILE, {"pending": [], "history": []})
    open_trades = load_json(OPEN_TRADES_FILE, [])
    if len(open_trades) >= MAX_TRADES: return
    pending = signals.get("pending", [])
    if not pending: return
    sig = pending.pop(0)
    symbol = sig['symbol']
    if any(t['symbol'] == symbol for t in open_trades):
        save_json(SIGNALS_FILE, signals); return
    # cooldown check
    mem = load_json(MEMORY_FILE, {'trades':[]})
    recent = [t for t in mem.get('trades',[])[-20:] if t.get('symbol')==symbol and not t.get('won')]
    if recent:
        try:
            lt = datetime.fromisoformat(recent[-1].get('time','2020-01-01'))
            if (datetime.now() - lt).total_seconds() < 600:
                log.info(f"⏸ Skip {symbol} — cooldown")
                save_json(SIGNALS_FILE, signals); return
        except: pass
    try:
        ticker = exchange.fetch_ticker(symbol)
        price = ticker['last']
    except:
        save_json(SIGNALS_FILE, signals); return
    trade = {"symbol": symbol, "entry_price": price,
        "stop_loss": round(price * (1 - SL_PCT), 8),
        "take_profit": round(price * (1 + TP_PCT), 8),
        "highest": price, "lowest": price, "capital": TRADE_AMOUNT,
        "open_time": str(datetime.now()),
        "rsi": sig.get('rsi', 0), "score": sig.get('score', 0),
        "accumulation": sig.get('accumulation', False),
        "status": "ACTIVE"}
    open_trades.append(trade)
    save_json(OPEN_TRADES_FILE, open_trades)
    sig['status'] = 'EXECUTED'
    signals.setdefault("history", []).append(sig)
    signals["history"] = signals["history"][-50:]
    save_json(SIGNALS_FILE, signals)
    log.info(f"🐺 دخول | {symbol} @ ${price:.6f} | RSI:{sig.get('rsi',0)} Score:{sig.get('score',0)}")
    send_tg(f"🐺 <b>دخول!</b>\n🪙 <b>{symbol}</b>\n💵 ${price:.6f}\n📊 RSI:{sig.get('rsi',0)} Score:{sig.get('score',0)}\n🎯 +{TP_PCT*100}% | 🛑 -{SL_PCT*100}%")

def close_trade(trade, price, reason, open_trades):
    entry = trade['entry_price']
    pnl_pct = (price - entry) / entry
    profit = round(TRADE_AMOUNT * pnl_pct - TRADE_AMOUNT * 0.002, 4)
    won = profit > 0
    mins = 0
    try: mins = (datetime.now() - datetime.fromisoformat(trade['open_time'])).total_seconds() / 60
    except: pass
    emoji = "🎯" if "TP" in reason else ("✅" if won else "❌")
    log.info(f"{emoji} {reason} | {trade['symbol']} | ${profit:+.4f} | {mins:.0f}m")
    send_tg(f"{emoji} <b>نتيجة</b>\n🪙 <b>{trade['symbol']}</b>\n💵 ${entry:.6f} → ${price:.6f} | {pnl_pct*100:+.2f}%\n💰 <b>${profit:+.4f}</b> | ⏱️ {mins:.0f}m\n📝 {reason}")
    try:
        memory = load_json(MEMORY_FILE, {"trades": [], "symbols": {}})
        rec = {"symbol": trade['symbol'], "won": won, "profit": profit, "rsi": trade.get('rsi',0),
            "score": trade.get('score',0), "exit_reason": reason, "duration_min": round(mins,1),
            "time": str(datetime.now()),
            "max_gain": round((trade.get('highest',entry)-entry)/entry*100, 2),
            "max_loss": round((trade.get('lowest',entry)-entry)/entry*100, 2)}
        memory["trades"].append(rec)
        save_json(MEMORY_FILE, memory)
    except Exception as e: log.error(f"خطأ memory: {e}")
    if trade in open_trades: open_trades.remove(trade)
    save_json(OPEN_TRADES_FILE, open_trades)
    perf = load_json(PERFORMANCE_FILE, {"today_pnl":0,"today_trades":0,"today_wins":0,"daily_loss":0})
    perf["today_pnl"] = round(perf.get("today_pnl",0) + profit, 4)
    perf["today_trades"] = perf.get("today_trades",0) + 1
    if won: perf["today_wins"] = perf.get("today_wins",0) + 1
    if not won: perf["daily_loss"] = round(perf.get("daily_loss",0) + abs(profit), 4)
    save_json(PERFORMANCE_FILE, perf)

def run():
    log.info(f"🐺 === الحارس v3 === TP:{TP_PCT*100}% SL:{SL_PCT*100}% Timeout:{MAX_TRADE_MINS}m")
    exchange = connect()
    cycle = 0
    while True:
        try:
            cycle += 1
            process_signals(exchange)
            open_trades = load_json(OPEN_TRADES_FILE, [])
            for trade in open_trades[:]:
                try:
                    ticker = exchange.fetch_ticker(trade['symbol'])
                    price = ticker['last']
                    entry = trade['entry_price']
                    gain = (price - entry) / entry
                    mins = (datetime.now() - datetime.fromisoformat(trade['open_time'])).total_seconds() / 60
                    
                    if price > trade.get('highest', entry): trade['highest'] = price
                    if price < trade.get('lowest', entry): trade['lowest'] = price
                    
                    reason = None
                    # 1. SL فوري
                    if gain <= -SL_PCT: reason = f"🛑 SL {gain*100:.2f}%"
                    # 2. TP
                    if not reason and gain >= TP_PCT: reason = f"🎯 TP +{gain*100:.2f}%"
                    # 3. RSI exit
                    if not reason:
                        rsi = get_rsi(exchange, trade['symbol'])
                        if rsi >= 65 and gain >= 0.003: reason = f"📊 RSI={rsi} +{gain*100:.2f}%"
                        if rsi >= 75 and gain > 0.001: reason = f"📊 RSI={rsi} +{gain*100:.2f}%"
                    # 4. Trail فوق +0.6%
                    if not reason and gain >= 0.006:
                        ns = round(price * (1 - 0.004), 8)
                        if ns > trade.get('stop_loss', 0): trade['stop_loss'] = ns
                    if not reason and trade.get('stop_loss',0) > entry and price <= trade['stop_loss'] and gain >= 0.005:
                        reason = f"🔒 Trail +{(trade['stop_loss']-entry)/entry*100:.2f}%"
                    # 5. Timeout
                    if not reason and mins >= MAX_TRADE_MINS:
                        if gain > 0.002: reason = f"⏰ {mins:.0f}m +{gain*100:.2f}%"
                        elif mins >= MAX_TRADE_MINS + 1: reason = f"⏰ MAX {mins:.0f}m {gain*100:.2f}%"
                    
                    if reason: close_trade(trade, price, reason, open_trades)
                    else: save_json(OPEN_TRADES_FILE, open_trades)
                except Exception as e: log.error(f"خطأ {trade.get('symbol','?')}: {e}")
            if cycle % 60 == 0:
                perf = load_json(PERFORMANCE_FILE, {})
                t = perf.get('today_trades',0); w = perf.get('today_wins',0)
                log.info(f"📊 {t} trades | WR:{w/t*100 if t else 0:.0f}% | ${perf.get('today_pnl',0):+.2f}")
            time.sleep(1)
        except KeyboardInterrupt: break
        except Exception as e: log.error(f"خطأ: {e}"); time.sleep(5)

if __name__ == "__main__": run()
