"""
daily_report.py v5 — تقرير مفصل لتلغرام
- كل ساعة: صفقات ديك الساعة فقط + تفاصيل دخول/خروج
- كل 00:00: تقرير يومي 24h كامل
"""
import json, os, time, requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv('/root/micro-scalping/.env')

TOKEN = os.getenv('TELEGRAM_TOKEN', '8605696873:AAFLAY4_xI4D5BYb7dFdu0FV2hJDiMiQPGs')
CHANNELS = ['-1003818709859', '-1003771026934', '-1003756064073']

def send(msg):
    for ch in CHANNELS:
        try:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                json={"chat_id": ch, "text": msg, "parse_mode": "HTML"}, timeout=10)
        except: pass

def load_data():
    trades = []
    opens = []
    try:
        with open('/root/micro-scalping/trade_memory.json', 'r') as f:
            trades = json.load(f).get('trades', [])
    except: pass
    try:
        opens = json.load(open('/root/micro-scalping/open_trades.json'))
    except: pass
    return trades, opens

def filter_by_hour(trades, hour):
    result = []
    for t in trades:
        try:
            h = int(t['time'].split(' ')[1].split(':')[0])
            if h == hour:
                result.append(t)
        except: pass
    return result

def filter_today(trades):
    today = datetime.now().replace(hour=0, minute=0, second=0)
    result = []
    for t in trades:
        try:
            tt = datetime.fromisoformat(t.get('time', ''))
            if tt >= today:
                result.append(t)
        except: pass
    return result

def trade_detail(t):
    emoji = "✅" if t.get('won') else "❌"
    mk = " 🥛" if t.get('is_milk') else ""
    sym = t.get('symbol', '?')
    profit = t.get('profit', 0)
    rsi = t.get('rsi', 0)
    entry = t.get('entry_price', 0)
    exit_p = t.get('exit_price', 0)
    reason = t.get('exit_reason', '')[:25]
    dur = t.get('duration_min', 0)
    enter_time = ''
    exit_time = ''
    try:
        enter_time = t.get('time', '').split(' ')[1][:5]
    except: pass
    try:
        if t.get('duration_min', 0) > 0 and t.get('time'):
            et = datetime.fromisoformat(t['time']) + timedelta(minutes=t['duration_min'])
            exit_time = et.strftime('%H:%M')
    except: pass
    return f"""{emoji}{mk} <b>{sym}</b>
   🕐 دخول: {enter_time} → خروج: {exit_time} ({dur:.0f}m)
   💵 ${entry:.6f} → ${exit_p:.6f}
   💰 <b>${profit:+.4f}</b> | RSI:{rsi}
   📝 {reason}"""

def hourly_report(trades, opens, hour):
    now = datetime.now()
    hour_trades = filter_by_hour(filter_today(trades), hour)

    if not hour_trades:
        return f"""🕐 <b>تقرير الساعة {hour:02d}:00</b>
{now.strftime('%d/%m/%Y')}
━━━━━━━━━━━━━━━━━━━
⏳ لا صفقات في هاد الساعة

💼 مفتوحة دبا: {len(opens)}
🐺 v5"""

    wins = [t for t in hour_trades if t.get('won')]
    losses = [t for t in hour_trades if not t.get('won')]
    total_p = sum(t.get('profit', 0) for t in hour_trades)
    wr = len(wins)/len(hour_trades)*100

    msg = f"""🕐 <b>تقرير الساعة {hour:02d}:00 - {hour:02d}:59</b>
{now.strftime('%d/%m/%Y')}
━━━━━━━━━━━━━━━━━━━━━━

📊 صفقات: <b>{len(hour_trades)}</b>
✅ {len(wins)} | ❌ {len(losses)} | WR: <b>{wr:.0f}%</b>
💰 ربح الساعة: <b>${total_p:+.3f}</b>

━━━━━━━━━━━━━━━━━━━━━━
📝 <b>التفاصيل:</b>
"""
    for t in hour_trades:
        msg += f"\n{trade_detail(t)}\n"

    msg += f"""━━━━━━━━━━━━━━━━━━━━━━
💼 مفتوحة دبا: {len(opens)}"""

    for o in opens:
        mk = " 🥛" if o.get('is_milk') else ""
        msg += f"\n   🟢{mk} {o.get('symbol','?')} RSI:{o.get('rsi',0)}"

    msg += "\n🐺 v5 | حلب العملة 🥛"
    return msg

def daily_24h_report(trades, opens):
    now = datetime.now()
    today_trades = filter_today(trades)

    if not today_trades:
        return f"""📋 <b>التقرير اليومي 24h</b>
{now.strftime('%d/%m/%Y')}
━━━━━━━━━━━━━━━━━━━
⏳ لا صفقات اليوم"""

    wins = [t for t in today_trades if t.get('won')]
    losses = [t for t in today_trades if not t.get('won')]
    total_p = sum(t.get('profit', 0) for t in today_trades)
    wr = len(wins)/len(today_trades)*100
    avg_w = sum(t['profit'] for t in wins)/len(wins) if wins else 0
    avg_l = sum(abs(t['profit']) for t in losses)/len(losses) if losses else 0
    milk = [t for t in today_trades if t.get('is_milk')]
    milk_p = sum(t.get('profit', 0) for t in milk)

    first = datetime.fromisoformat(today_trades[0].get('time', str(now)))
    hours = max(0.1, (now - first).total_seconds() / 3600)
    tph = len(today_trades) / hours

    msg = f"""📋 <b>التقرير اليومي الكامل 24h</b>
🕐 {now.strftime('%H:%M %d/%m/%Y')}
━━━━━━━━━━━━━━━━━━━━━━━

📊 <b>مجموع: {len(today_trades)} صفقة</b> في {hours:.1f}h
⚡ المعدل: <b>{tph:.1f} صفقة/ساعة</b>

━━━━━━━━━━━━━━━━━━━━━━━
✅ رابحة: <b>{len(wins)}</b> (+${sum(t['profit'] for t in wins):.3f})
❌ خاسرة: <b>{len(losses)}</b> (${sum(t['profit'] for t in losses):.3f})
🎯 Win Rate: <b>{wr:.1f}%</b>
📈 متوسط ربح: ${avg_w:.4f}
📉 متوسط خسارة: ${avg_l:.4f}

━━━━━━━━━━━━━━━━━━━━━━━
💰 <b>الربح الصافي: ${total_p:+.3f}</b>
🏦 الرأسمال: ${200 + total_p:.2f}
🥛 Milk: {len(milk)} صفقة (${milk_p:+.3f})

━━━━━━━━━━━━━━━━━━━━━━━
⏰ <b>ملخص كل ساعة:</b>"""

    hours_d = {}
    for t in today_trades:
        try:
            h = t['time'].split(' ')[1].split(':')[0]
            if h not in hours_d: hours_d[h] = {'w':0,'l':0,'p':0,'n':0}
            hours_d[h]['n'] += 1
            if t.get('won'): hours_d[h]['w'] += 1
            else: hours_d[h]['l'] += 1
            hours_d[h]['p'] = round(hours_d[h]['p'] + t.get('profit',0), 4)
        except: pass

    for h in sorted(hours_d.keys()):
        d = hours_d[h]
        emoji = "🟢" if d['p'] > 0 else "🔴"
        msg += f"\n{emoji} {h}:00 | {d['n']} صفقة | ✅{d['w']} ❌{d['l']} | ${d['p']:+.3f}"

    msg += "\n\n━━━━━━━━━━━━━━━━━━━━━━━"
    msg += "\n🏆 <b>أحسن 5:</b>"
    for t in sorted(today_trades, key=lambda x: x.get('profit',0), reverse=True)[:5]:
        mk = "🥛" if t.get('is_milk') else ""
        msg += f"\n  ✅{mk} {t.get('symbol','')} ${t['profit']:+.4f} ({t.get('duration_min',0):.0f}m)"

    msg += "\n💀 <b>أسوأ 5:</b>"
    for t in sorted(today_trades, key=lambda x: x.get('profit',0))[:5]:
        msg += f"\n  ❌ {t.get('symbol','')} ${t['profit']:+.4f} ({t.get('duration_min',0):.0f}m)"

    msg += f"\n\n🐺 v5 | التقرير اليومي 📋"
    return msg

if __name__ == "__main__":
    print("🐺 Report system v5 ON!")
    last_hour = -1
    last_daily = None

    # تقرير فوري عند التشغيل
    trades, opens = load_data()
    report = hourly_report(trades, opens, datetime.now().hour)
    send(report)
    print(f"✅ تقرير فوري تبعث")

    while True:
        try:
            now = datetime.now()
            trades, opens = load_data()

            # تقرير كل ساعة
            if now.hour != last_hour:
                prev_hour = (now.hour - 1) % 24
                report = hourly_report(trades, opens, prev_hour)
                send(report)
                last_hour = now.hour
                print(f"✅ ساعي {prev_hour:02d}:00 → {now.strftime('%H:%M')}")

            # تقرير يومي عند 00:00
            today = now.strftime('%Y-%m-%d')
            if now.hour == 0 and now.minute < 10 and last_daily != today:
                daily = daily_24h_report(trades, opens)
                send(daily)
                last_daily = today
                print(f"📋 يومي {today}")

        except Exception as e:
            print(f"❌ {e}")

        time.sleep(300)
