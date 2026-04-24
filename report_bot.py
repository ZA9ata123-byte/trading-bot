"""
report_bot.py v5
"""
import json, os, time, requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv('/root/micro-scalping/.env')

TOKEN = os.getenv('TELEGRAM_TOKEN', '8605696873:AAFLAY4_xI4D5BYb7dFdu0FV2hJDiMiQPGs')
CHAT  = '-1003756064073'

def send(msg):
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT, "text": msg, "parse_mode": "HTML"}, timeout=10)
    except: pass

def build_report():
    now = datetime.now()
    closed = []
    try:
        with open('/root/micro-scalping/trade_memory.json', 'r') as f:
            closed = json.load(f).get('trades', [])
    except: pass
    try: open_t = json.load(open('/root/micro-scalping/open_trades.json'))
    except: open_t = []
    wins = [t for t in closed if t.get('won')]
    losses = [t for t in closed if not t.get('won')]
    total_p = sum(t.get('profit', 0) for t in closed)
    wr = len(wins)/len(closed)*100 if closed else 0
    milk_t = [t for t in closed if t.get('is_milk')]
    milk_p = sum(t.get('profit', 0) for t in milk_t)
    tph = 0
    if closed:
        try:
            first = datetime.fromisoformat(closed[0].get('time', str(now)))
            hrs = max(1, (now - first).total_seconds() / 3600)
            tph = len(closed) / hrs
        except: pass
    msg = f"""🐺 <b>تقرير v5</b>
🕐 {now.strftime('%H:%M %d/%m')}
━━━━━━━━━━━━━━━━━━━━
✅ {len(wins)} | ❌ {len(losses)} | WR: <b>{wr:.0f}%</b>
💰 <b>${total_p:+.3f}</b> | ⚡ {tph:.1f}/h
🥛 Milk: {len(milk_t)} (${milk_p:+.3f})
💼 مفتوحة: {len(open_t)}"""
    for t in open_t:
        milk = " 🥛" if t.get('is_milk') else ""
        msg += f"\n🟢 <b>{t.get('symbol','?')}</b> RSI:{t.get('rsi',0)}{milk}"
    msg += "\n\n📝 آخر 5:"
    for t in closed[-5:]:
        em = "✅" if t.get('won') else "❌"
        milk = "🥛" if t.get('is_milk') else ""
        msg += f"\n{em}{milk} {t.get('symbol','?')} ${t.get('profit',0):+.4f}"
    if not closed: msg += "\nلا صفقات بعد"
    return msg

if __name__ == "__main__":
    print("🐺 Report v5!")
    while True:
        try:
            send(build_report())
            print(f"✅ {datetime.now().strftime('%H:%M')}")
        except Exception as e:
            print(f"❌ {e}")
        time.sleep(1800)
