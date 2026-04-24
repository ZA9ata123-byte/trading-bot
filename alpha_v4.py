"""
🐺👑 alpha_v4.py — القائد v4
مسؤول عن:
  1. تشغيل الذئاب (spy, hunter, guardian)
  2. مراقبتهم بدون infinite loop موت
  3. تقارير Telegram دورية
  4. Daily loss protection عقلاني
"""
import json
import time
import os
import subprocess
import logging
import requests
from datetime import datetime
from config_v4 import *

# ═══════════════════════════════════════════
# Setup
# ═══════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [ALPHA] %(message)s',
    handlers=[
        logging.FileHandler('/root/micro-scalping/alpha_v4.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger('alpha')

BASE = '/root/micro-scalping'
PERF_FILE = os.path.join(BASE, 'performance.json')
MEM_FILE = os.path.join(BASE, 'trade_memory.json')

# ═══════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════
def load_json(path, default=None):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except:
        return default if default is not None else {}

def save_json(path, data):
    try:
        with open(path, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Save error {path}: {e}")

def send_tg(text, channel=None):
    """Send Telegram message"""
    ch = channel or REPORT_CHANNEL
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": ch, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception as e:
        log.debug(f"TG error: {e}")

def kill_existing(script_name):
    """اقتل أي نسخة قديمة من script"""
    subprocess.run(['pkill', '-9', '-f', f'python3.*{script_name}'],
                   capture_output=True)
    time.sleep(0.5)

def start_wolf(script_name):
    """شغل ذئب جديد"""
    kill_existing(script_name)
    try:
        log_file = open(f'/root/micro-scalping/{script_name.replace(".py","")}_stderr.log', 'a')
        proc = subprocess.Popen(
            ['python3', os.path.join(BASE, script_name)],
            cwd=BASE,
            stdout=log_file,
            stderr=log_file
        )
        log.info(f"🐺 {script_name} بدا PID:{proc.pid}")
        return proc
    except Exception as e:
        log.error(f"❌ خطأ تشغيل {script_name}: {e}")
        return None

def is_alive(proc):
    """هل الprocess باقي خدام؟"""
    return proc is not None and proc.poll() is None

def reset_daily_if_needed():
    """reset performance إلا بدا يوم جديد"""
    perf = load_json(PERF_FILE, {})
    today = str(datetime.now().date())
    if perf.get('date') != today:
        log.info(f"📅 يوم جديد! reset performance")
        save_json(PERF_FILE, {
            "today_pnl": 0,
            "today_trades": 0,
            "today_wins": 0,
            "daily_loss": 0,
            "date": today,
            "paused": False
        })
        return True
    return False

def should_pause(perf):
    """واش خاصنا نوقفو اليوم؟"""
    daily_loss = perf.get('daily_loss', 0)
    if daily_loss >= DAILY_LOSS_LIMIT:
        return True, f"daily_loss ${daily_loss:.2f} >= limit ${DAILY_LOSS_LIMIT}"
    return False, ""

# ═══════════════════════════════════════════
# Main Loop
# ═══════════════════════════════════════════
def run():
    log.info("="*60)
    log.info("🐺👑 === الألفا v4 بدا ===")
    log.info(f"⚙️  TP:{TP_PCT*100}% | SL:{SL_PCT*100}% | Trade:${TRADE_AMOUNT}")
    log.info(f"💰 Daily Loss Limit: ${DAILY_LOSS_LIMIT}")
    log.info("="*60)
    
    # reset performance إلا لازم
    reset_daily_if_needed()
    
    # شغل الذئاب
    wolves = {
        'spy_v4.py': None,
        'hunter_v4.py': None,
        'guardian_v4.py': None,
    }
    
    for name in wolves:
        wolves[name] = start_wolf(name)
        time.sleep(2)  # wait between starts
    
    send_tg(
        "🐺👑 <b>الألفا v4 بدا!</b>\n"
        f"🎯 TP: {TP_PCT*100}% | 🛑 SL: {SL_PCT*100}%\n"
        f"💰 Trade: ${TRADE_AMOUNT} | Max Loss: ${DAILY_LOSS_LIMIT}/day\n"
        f"🐺 3 ذئاب خدامين: Spy + Hunter + Guardian"
    )
    
    # متغيرات المراقبة
    cycle = 0
    last_report = time.time()
    last_restart = {name: 0 for name in wolves}
    paused_announced = False
    
    try:
        while True:
            cycle += 1
            now = time.time()
            
            # ═══ 1. reset يومي ═══
            if reset_daily_if_needed():
                paused_announced = False
                send_tg("📅 <b>يوم جديد!</b>\nالأرباح تصفرت، نبداو من جديد.")
            
            # ═══ 2. شوف performance ═══
            perf = load_json(PERF_FILE, {})
            paused, reason = should_pause(perf)
            
            if paused:
                if not paused_announced:
                    log.warning(f"🛑 PAUSED: {reason}")
                    send_tg(f"🛑 <b>توقف!</b>\n{reason}\nنستنى حتى غداً.")
                    paused_announced = True
                    # أوقف hunter فقط (guardian خاصو يسد الصفقات المفتوحة)
                    kill_existing('hunter_v4.py')
                    wolves['hunter_v4.py'] = None
                time.sleep(ALPHA_SLEEP)
                continue
            
            # ═══ 3. راقب الذئاب (بدون قتل spam) ═══
            for name, proc in wolves.items():
                if paused and name == 'hunter_v4.py':
                    continue  # hunter متوقف عادي
                
                if not is_alive(proc):
                    # تجنب restart loop - استنى 60 ثانية بين restarts
                    if now - last_restart[name] < 60:
                        continue
                    
                    log.warning(f"⚠️  {name} طاح - إعادة تشغيل")
                    wolves[name] = start_wolf(name)
                    last_restart[name] = now
            
            # ═══ 4. تقرير كل 30 دقيقة ═══
            if now - last_report > 1800:
                t = perf.get('today_trades', 0)
                w = perf.get('today_wins', 0)
                wr = (w/t*100) if t else 0
                pnl = perf.get('today_pnl', 0)
                
                status_spy = "✅" if is_alive(wolves['spy_v4.py']) else "❌"
                status_hunter = "✅" if is_alive(wolves['hunter_v4.py']) else "❌"
                status_guard = "✅" if is_alive(wolves['guardian_v4.py']) else "❌"
                
                msg = (
                    f"🐺👑 <b>تقرير الألفا</b>\n"
                    f"📊 Trades: {t} | WR: {wr:.0f}%\n"
                    f"💰 P&L: ${pnl:+.2f}\n"
                    f"🐺 Spy:{status_spy} Hunter:{status_hunter} Guard:{status_guard}"
                )
                send_tg(msg)
                last_report = now
            
            # ═══ 5. log حالة كل 10 cycles ═══
            if cycle % 10 == 0:
                t = perf.get('today_trades', 0)
                w = perf.get('today_wins', 0)
                wr = (w/t*100) if t else 0
                pnl = perf.get('today_pnl', 0)
                log.info(
                    f"👑 {t}t WR:{wr:.0f}% ${pnl:+.2f} "
                    f"S:{'✅' if is_alive(wolves['spy_v4.py']) else '❌'} "
                    f"H:{'✅' if is_alive(wolves['hunter_v4.py']) else '❌'} "
                    f"G:{'✅' if is_alive(wolves['guardian_v4.py']) else '❌'}"
                )
            
            time.sleep(ALPHA_SLEEP)
            
    except KeyboardInterrupt:
        log.info("⌨️  Ctrl+C - توقف طوعي")
    finally:
        log.info("🛑 إيقاف الذئاب...")
        for name, proc in wolves.items():
            if is_alive(proc):
                proc.terminate()
                log.info(f"🛑 {name} توقف")
        send_tg("🛑 <b>الألفا v4 توقف</b>")

if __name__ == "__main__":
    run()
