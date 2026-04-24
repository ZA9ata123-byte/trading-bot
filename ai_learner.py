"""
ai_learner.py — العقل الذكي 🧠
يستعمل Claude API لتحليل كل صفقة:
- علاش ربحت؟ علاش خسرت؟
- شنو الدرس؟
- شنو القاعدة الجديدة؟
"""
import json, os, logging, time, requests
from datetime import datetime

log = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv("/root/micro-scalping/.env")
API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-20250514"
LESSONS_FILE = "/root/micro-scalping/ai_lessons.json"
MAX_LESSONS = 200

def load_lessons():
    try:
        with open(LESSONS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"lessons": [], "rules": [], "stats": {"analyzed": 0, "total_saved": 0}}

def save_lessons(data):
    with open(LESSONS_FILE, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def analyze_trade(trade_data, market_context=""):
    """
    يسيفط الصفقة لـ Claude للتحليل
    يرجع: السبب + الدرس + قاعدة جديدة
    """
    if not API_KEY:
        log.warning("🧠 لا API Key — التعلم الذكي معطل")
        return None

    won = trade_data.get('won', False)
    profit = trade_data.get('profit', 0)
    symbol = trade_data.get('symbol', '?')

    prompt = f"""أنت محلل تداول عملات رقمية خبير. حلل هذه الصفقة وأعطني:

## بيانات الصفقة:
- العملة: {symbol}
- النتيجة: {"ربح ✅" if won else "خسارة ❌"} ${profit:+.4f}
- RSI عند الدخول: {trade_data.get('rsi', 0)}
- Score: {trade_data.get('score', 0)}
- سبب الخروج: {trade_data.get('exit_reason', '')}
- المدة: {trade_data.get('duration_min', 0):.0f} دقيقة
- أعلى ربح وصلت ليه: {trade_data.get('max_gain', 0):.2f}%
- أعلى خسارة وصلت ليها: {trade_data.get('max_loss', 0):.2f}%
- الفئة: {trade_data.get('tier', '')}
- الشموع: {trade_data.get('candles', [])}
{f"- سياق السوق: {market_context}" if market_context else ""}

## أجب بـ JSON فقط بدون أي شيء آخر:
{{
    "analysis": "جملة واحدة: لماذا ربحت أو خسرت",
    "lesson": "جملة واحدة: الدرس المستفاد",
    "rule": {{
        "type": "AVOID أو PREFER",
        "condition": "الشرط بالتحديد مثلاً: RSI > 35 AND trend_4h = bearish",
        "confidence": 0.0-1.0
    }},
    "rsi_verdict": "GOOD أو BAD أو NEUTRAL",
    "timing_verdict": "TOO_EARLY أو TOO_LATE أو GOOD",
    "exit_verdict": "GOOD أو SHOULD_HOLD أو SHOULD_EXIT_EARLIER"
}}"""

    try:
        response = requests.post(API_URL,
            headers={
                "Content-Type": "application/json",
                "x-api-key": API_KEY,
                "anthropic-version": "2023-06-01"
            },
            json={
                "model": MODEL,
                "max_tokens": 500,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )

        if response.status_code != 200:
            log.error(f"🧠 API Error: {response.status_code}")
            return None

        data = response.json()
        text = data['content'][0]['text']

        # نظف الجواب
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]

        result = json.loads(text)

        # سجل الدرس
        lessons = load_lessons()
        lesson_entry = {
            "time": str(datetime.now()),
            "symbol": symbol,
            "won": won,
            "profit": profit,
            "rsi": trade_data.get('rsi', 0),
            "analysis": result.get('analysis', ''),
            "lesson": result.get('lesson', ''),
            "rule": result.get('rule', {}),
            "rsi_verdict": result.get('rsi_verdict', ''),
            "timing_verdict": result.get('timing_verdict', ''),
            "exit_verdict": result.get('exit_verdict', ''),
        }

        lessons['lessons'].append(lesson_entry)
        lessons['stats']['analyzed'] += 1

        # أضف القاعدة إذا الثقة عالية
        rule = result.get('rule', {})
        if rule.get('confidence', 0) >= 0.7:
            lessons['rules'].append({
                "added": str(datetime.now()),
                "type": rule['type'],
                "condition": rule['condition'],
                "confidence": rule['confidence'],
                "from_trade": symbol,
            })
            lessons['stats']['total_saved'] += 1

        # حافظ على الحجم
        if len(lessons['lessons']) > MAX_LESSONS:
            lessons['lessons'] = lessons['lessons'][-MAX_LESSONS:]

        save_lessons(lessons)

        emoji = "✅" if won else "❌"
        log.info(f"🧠 AI: {emoji} {symbol} | {result.get('analysis', '')[:60]}")
        log.info(f"🧠 درس: {result.get('lesson', '')[:60]}")
        if rule.get('confidence', 0) >= 0.7:
            log.info(f"🧠 قاعدة جديدة: {rule['type']} | {rule['condition']}")

        return result

    except json.JSONDecodeError:
        log.error(f"🧠 JSON parse error")
        return None
    except Exception as e:
        log.error(f"🧠 AI Error: {e}")
        return None

def should_enter_ai(symbol, rsi, score, tier):
    """
    يتشيك القواعد المتعلمة قبل الدخول
    """
    lessons = load_lessons()
    rules = lessons.get('rules', [])

    warnings = []
    for rule in rules[-50:]:  # آخر 50 قاعدة
        if rule['type'] == 'AVOID' and rule.get('confidence', 0) >= 0.7:
            cond = rule['condition'].lower()

            # تشيك RSI
            if 'rsi' in cond:
                try:
                    if 'rsi >' in cond:
                        limit = float(cond.split('rsi >')[1].split()[0])
                        if rsi > limit:
                            warnings.append(f"🧠 Rule: RSI {rsi} > {limit}")
                except: pass

            # تشيك العملة بالاسم
            if symbol.lower().split('/')[0] in cond.lower():
                warnings.append(f"🧠 Rule: {symbol} ممنوع")

    if warnings:
        return {"ok": False, "reasons": warnings}
    return {"ok": True, "reasons": []}

def get_ai_summary():
    """ملخص التعلم"""
    lessons = load_lessons()
    total = lessons['stats'].get('analyzed', 0)
    rules_count = len(lessons.get('rules', []))

    # إحصائيات الأحكام
    verdicts = {"GOOD": 0, "BAD": 0, "NEUTRAL": 0}
    for l in lessons.get('lessons', [])[-50:]:
        v = l.get('rsi_verdict', 'NEUTRAL')
        verdicts[v] = verdicts.get(v, 0) + 1

    return {
        "total_analyzed": total,
        "total_rules": rules_count,
        "recent_verdicts": verdicts,
    }
