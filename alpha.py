"""
🐺👑 alpha.py v3
"""
import json, time, os, subprocess, logging, requests
from datetime import datetime
from config import *

logging.basicConfig(level=logging.INFO, format='%(asctime)s [ALPHA] %(message)s',
    handlers=[logging.FileHandler('/root/micro-scalping/alpha.log', encoding='utf-8'), logging.StreamHandler()])
log = logging.getLogger('alpha')

BASE = '/root/micro-scalping'
PERF = os.path.join(BASE, 'performance.json')
MEM = os.path.join(BASE, 'trade_memory.json')

def load_json(p, d=None):
    try:
        with open(p, 'r') as f: return json.load(f)
    except: return d if d is not None else {}

def save_json(p, d):
    with open(p, 'w') as f: json.dump(d, f, ensure_ascii=False, indent=2)

def send_tg(text):
    try: requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={"chat_id": REPORT_CHANNEL, "text": text, "parse_mode": "HTML"}, timeout=10)
    except: pass

def start_wolf(script):
    # اقتل أي نسخة قديمة أولاً!
    subprocess.run(['pkill', '-9', '-f', f'python3.*{script}'], capture_output=True)
    time.sleep(1)
    proc = subprocess.Popen(['python3', os.path.join(BASE, script)], cwd=BASE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log.info(f"🐺 {script} PID:{proc.pid}")
    return proc

def alive(proc): return proc is not None and proc.poll() is None

def run():
    log.info("🐺👑 === الألفا v3 ===")
    # اقتل الكل أولاً!
    subprocess.run(['pkill', '-9', '-f', 'python3.*hunter.py'], capture_output=True)
    subprocess.run(['pkill', '-9', '-f', 'python3.*guardian.py'], capture_output=True)
    time.sleep(2)
    
    HUNTER = start_wolf('hunter.py')
    GUARDIAN = start_wolf('guardian.py')
    send_tg("🐺👑 <b>الألفا v3 بدا!</b>\n🐺 صياد 6 مؤشرات + 🐺 حارس سريع")
    
    cycle = 0; last_report = 0; last_day = datetime.now().date()
    try:
        while True:
            cycle += 1
            now = datetime.now()
            if now.date() != last_day:
                save_json(PERF, {"today_pnl":0,"today_trades":0,"today_wins":0,"daily_loss":0,"date":str(now.date())})
                last_day = now.date()
            if not alive(HUNTER):
                log.warning("⚠️ الصياد مات!")
                HUNTER = start_wolf('hunter.py')
            if not alive(GUARDIAN):
                log.warning("⚠️ الحارس مات!")
                GUARDIAN = start_wolf('guardian.py')
            perf = load_json(PERF, {})
            if perf.get('daily_loss', 0) >= DAILY_LOSS_LIMIT:
                if alive(HUNTER):
                    HUNTER.terminate()
                    log.warning("🚫 حد الخسارة!")
                    send_tg("🚫 حد الخسارة!")
            if time.time() - last_report > 1800:
                p = load_json(PERF, {}); t=p.get('today_trades',0); w=p.get('today_wins',0)
                send_tg(f"🐺👑 <b>تقرير</b>\n📊 {t} trades WR:{w/t*100 if t else 0:.0f}%\n💰 ${p.get('today_pnl',0):+.2f}")
                last_report = time.time()
            if cycle % 10 == 0:
                p = load_json(PERF, {}); t=p.get('today_trades',0); w=p.get('today_wins',0)
                log.info(f"👑 {t}t WR:{w/t*100 if t else 0:.0f}% ${p.get('today_pnl',0):+.2f} H:{'✅' if alive(HUNTER) else '❌'} G:{'✅' if alive(GUARDIAN) else '❌'}")
            time.sleep(30)
    except KeyboardInterrupt: pass
    finally:
        if alive(HUNTER): HUNTER.terminate()
        if alive(GUARDIAN): GUARDIAN.terminate()

if __name__ == "__main__": run()
