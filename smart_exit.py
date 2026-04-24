"""
smart_exit.py — v5 SL 0.2% + Kill 0.3%
"""
import json, os, logging, requests
from datetime import datetime, timedelta
from collections import defaultdict

log = logging.getLogger(__name__)

BASE_DIR = "/root/micro-scalping"
MEMORY_FILE = os.path.join(BASE_DIR, "trade_memory.json")
LEARNED_FILE = os.path.join(BASE_DIR, "learned_params.json")
AI_LESSONS_FILE = os.path.join(BASE_DIR, "ai_lessons.json")
DAILY_REPORT_DATA = os.path.join(BASE_DIR, "daily_ai_report.json")

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))
API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-20250514"

DEFAULT_PARAMS = {
    "tp_pct": 0.008,
    "sl_pct": 0.002,
    "trail_activation": 0.004,
    "trail_distance": 0.003,
    "be_lock_pct": 0.003,
    "force_exit_pct": 0.003,
    "max_hold_min": 8,
    "timeout_min": 8,
}

FEE = 0.002


def _load_json(path, default=None):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except:
        return default if default is not None else {}

def _save_json(path, data):
    try:
        with open(path, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"خطأ حفظ {path}: {e}")


def get_symbol_params(symbol, tier="DEFAULT"):
    learned = _load_json(LEARNED_FILE, {"symbols": {}, "tiers": {}})
    if symbol in learned.get("symbols", {}):
        sp = learned["symbols"][symbol]
        if sp.get("trades_count", 0) >= 3:
            result = {**DEFAULT_PARAMS, **sp}
            result["sl_pct"] = min(result["sl_pct"], 0.004)
            result["force_exit_pct"] = min(result.get("force_exit_pct", 0.003), 0.005)
            return result
    if tier in learned.get("tiers", {}):
        tp = learned["tiers"][tier]
        if tp.get("trades_count", 0) >= 5:
            result = {**DEFAULT_PARAMS, **tp}
            result["sl_pct"] = min(result["sl_pct"], 0.004)
            return result
    memory = _load_json(MEMORY_FILE, {"trades": []})
    sym_trades = [t for t in memory.get("trades", []) if t.get("symbol") == symbol]
    if len(sym_trades) >= 3:
        return _calc_params(sym_trades)
    return DEFAULT_PARAMS.copy()


def _calc_params(trades):
    params = DEFAULT_PARAMS.copy()
    if not trades:
        return params
    wins = [t for t in trades if t.get("won")]
    wr = len(wins) / len(trades)
    if wins:
        mg = [t.get("max_gain", 0) for t in wins if t.get("max_gain", 0) > 0]
        if mg:
            params["tp_pct"] = min(max(sum(mg)/len(mg)/100*0.75, 0.005), 0.012)
    if wins:
        dips = sorted([abs(t.get("max_loss", 0)) for t in wins if t.get("max_loss", 0) < 0])
        if dips:
            p90 = dips[int(len(dips)*0.9)] if len(dips) > 1 else dips[0]
            params["sl_pct"] = min(max(p90/100+0.001, 0.002), 0.004)
    if wins:
        durs = [t.get("duration_min", 0) for t in wins]
        if durs:
            avg_d = sum(durs)/len(durs)
            params["max_hold_min"] = min(max(int(avg_d*1.5), 6), 15)
            params["timeout_min"] = min(max(int(avg_d*1.2), 6), 12)
    if wr < 0.3 and len(trades) >= 5:
        params["sl_pct"] = min(params["sl_pct"], 0.002)
        params["max_hold_min"] = min(params["max_hold_min"], 8)
        params["force_exit_pct"] = 0.003
    if wr > 0.6:
        params["sl_pct"] = max(params["sl_pct"], 0.003)
        params["max_hold_min"] = max(params["max_hold_min"], 12)
    params["trades_count"] = len(trades)
    params["win_rate"] = round(wr*100, 1)
    return params


def should_enter(symbol, rsi, score, tier):
    reasons = []
    BAD_COINS = ['NOM', 'TURTLE', 'HFT', 'NIGHT', 'SXT', 'BANK', 'D', 'HUMA', 'SOLV']
    if symbol.split('/')[0] in BAD_COINS:
        reasons.append("عملة سامة")
    memory = _load_json(MEMORY_FILE, {"trades": [], "symbols": {}})
    sd = memory.get("symbols", {}).get(symbol, {})
    if sd.get("streak", 0) <= -3:
        reasons.append(f"streak {sd['streak']}")
    total = sd.get("total", 0)
    w = sd.get("wins", 0)
    if total >= 5 and w/total < 0.25:
        reasons.append(f"WR {w}/{total} = {w/total*100:.0f}%")
    if total >= 3 and sd.get("profit", 0) < -1.00:
        reasons.append(f"PnL ${sd['profit']:.2f}")
    lessons = _load_json(AI_LESSONS_FILE, {"rules": []})
    for rule in lessons.get("rules", [])[-30:]:
        if rule.get("confidence", 0) < 0.75 or rule.get("type") != "AVOID":
            continue
        cond = rule.get("condition", "").lower()
        sym_short = symbol.lower().split("/")[0]
        if sym_short in cond:
            reasons.append(f"AI: {cond[:40]}")
            break
    all_sym = [t for t in memory.get("trades", []) if t.get("symbol") == symbol]
    if all_sym:
        force3 = sum(1 for t in all_sym[-3:] if "FORCE" in t.get("exit_reason",""))
        if force3 >= 2: reasons.append(f"FORCE {force3}/3")
        if len(all_sym) >= 5:
            fr = sum(1 for t in all_sym if "FORCE" in t.get("exit_reason",""))
            if fr/len(all_sym) >= 0.4: reasons.append(f"FORCE prone {fr}/{len(all_sym)}")
    recent_losses = [t2 for t2 in memory.get("trades",[])[-20:]
                     if t2.get("symbol") == symbol and not t2.get("won")]
    if recent_losses:
        last_loss_time = recent_losses[-1].get("time","")
        try:
            if datetime.fromisoformat(last_loss_time) > datetime.now() - timedelta(minutes=45):
                reasons.append("cooldown بعد خسارة")
        except: pass
    if reasons:
        return {"enter": False, "reasons": reasons}
    return {"enter": True, "reasons": []}


def smart_check(trade, current_price, current_rsi):
    entry = trade["entry_price"]
    gain = (current_price - entry) / entry
    symbol = trade.get("symbol", "")
    mins = 0
    try:
        mins = (datetime.now() - datetime.fromisoformat(
            trade["open_time"])).total_seconds() / 60
    except:
        pass
    highest = trade.get("highest", entry)
    if current_price > highest:
        trade["highest"] = current_price
        highest = current_price
    if current_price < trade.get("lowest", entry):
        trade["lowest"] = current_price

    if gain <= -0.003:
        return f"🚨 KILL {gain*100:.2f}%", True
    if gain <= -0.002:
        return f"🛑 SL {gain*100:.2f}%", True

    tp_pct = trade.get("smart_params", {}).get("tp_pct", 0.008)
    if current_price >= entry * (1 + tp_pct):
        return f"🎯 TP +{gain*100:.2f}%", True

    if current_rsi >= 60 and gain > 0.005:
        return f"📊 RSI={current_rsi} +{gain*100:.2f}%", True
    if current_rsi >= 75 and gain > 0.003:
        return f"📊 RSI={current_rsi} OB! +{gain*100:.2f}%", True

    if gain > 0:
        if gain >= 0.003:
            be_price = round(entry * (1 + FEE + 0.0005), 8)
            if trade.get("stop_loss", 0) < be_price:
                trade["stop_loss"] = be_price
        if gain >= 0.004:
            new_sl = round(current_price * (1 - 0.0015), 8)
            if new_sl > trade.get("stop_loss", 0):
                trade["stop_loss"] = new_sl
    if trade.get("stop_loss", 0) > entry and current_price <= trade["stop_loss"]:
        tg = (trade["stop_loss"] - entry) / entry
        return f"🔒 Trail +{tg*100:.2f}%", True

    if mins >= 3:
        if gain > FEE:
            return f"⏰ {mins:.0f}m +{gain*100:.2f}%", True
        elif gain > 0 and mins >= 4:
            return f"⏰ {mins:.0f}m BE {gain*100:.2f}%", True
        elif gain <= 0 and mins >= 4:
            return f"⏰ MAX {mins:.0f}m {gain*100:.2f}%", True

    return None, False


def learn_locally(trade_data):
    symbol = trade_data.get("symbol", "")
    tier = trade_data.get("tier", "DEFAULT")
    learned = _load_json(LEARNED_FILE, {"symbols": {}, "tiers": {}})
    memory = _load_json(MEMORY_FILE, {"trades": []})
    sym_trades = [t for t in memory.get("trades", []) if t.get("symbol") == symbol]
    if len(sym_trades) >= 3:
        new_p = _calc_params(sym_trades)
        if symbol in learned.get("symbols", {}):
            old = learned["symbols"][symbol]
            for k in ["tp_pct","sl_pct","trail_distance","trail_activation",
                       "max_hold_min","force_exit_pct","be_lock_pct","timeout_min"]:
                if k in new_p and k in old:
                    new_p[k] = round(old[k]*0.7 + new_p[k]*0.3, 6)
        learned.setdefault("symbols", {})[symbol] = new_p
    tier_trades = [t for t in memory.get("trades", []) if t.get("tier") == tier]
    if len(tier_trades) >= 5:
        learned.setdefault("tiers", {})[tier] = _calc_params(tier_trades)
    _save_json(LEARNED_FILE, learned)
    log.info(f"🧠 تعلم: {symbol} | {len(sym_trades)} صفقات")


def daily_ai_analysis():
    if not API_KEY:
        log.warning("🧠 لا API Key")
        return None
    report = _load_json(DAILY_REPORT_DATA, {})
    today = str(datetime.now().date())
    if report.get("last_analysis") == today:
        log.info("🧠 التحليل اليومي تم")
        return report.get("last_result")
    memory = _load_json(MEMORY_FILE, {"trades": []})
    yesterday = datetime.now() - timedelta(hours=24)
    recent = []
    for t in memory.get("trades", []):
        try:
            if datetime.fromisoformat(t.get("time", "2020-01-01")) >= yesterday:
                recent.append(t)
        except: pass
    if len(recent) < 5:
        log.info(f"🧠 {len(recent)} صفقات فقط")
        return None
    wins = [t for t in recent if t.get("won")]
    total_pnl = sum(t.get("profit", 0) for t in recent)
    exit_stats = defaultdict(lambda: {"c": 0, "p": 0, "w": 0})
    for t in recent:
        r = t.get("exit_reason", "?")
        for k in ["TP","RSI","Trail","FORCE","MAX","SL","Momentum","BE","KILL"]:
            if k in r: r = k; break
        exit_stats[r]["c"] += 1
        exit_stats[r]["p"] += t.get("profit", 0)
        if t.get("won"): exit_stats[r]["w"] += 1
    exit_txt = "\n".join([f"  {k}: {v['c']}trades WR={v['w']}/{v['c']} ${v['p']:.2f}"
                          for k, v in sorted(exit_stats.items(), key=lambda x: x[1]["p"])])
    sym_pnl = defaultdict(lambda: {"c": 0, "p": 0, "w": 0})
    for t in recent:
        s = t.get("symbol", "?")
        sym_pnl[s]["c"] += 1
        sym_pnl[s]["p"] += t.get("profit", 0)
        if t.get("won"): sym_pnl[s]["w"] += 1
    sym_txt = "\n".join([f"  {k}: {v['c']}trades WR={v['w']}/{v['c']} ${v['p']:.2f}"
                         for k, v in sorted(sym_pnl.items(), key=lambda x: x[1]["p"])[:10]])
    prompt = f"""أنت محلل scalping خبير. حلل نتائج 24 ساعة.
الصفقات: {len(recent)} | WR: {len(wins)/len(recent)*100:.0f}% | PnL: ${total_pnl:.2f}
أسباب الخروج:
{exit_txt}
العملات:
{sym_txt}
أعطني JSON فقط:
{{"analysis": "ملخص 2 جمل", "verdict": "GOOD/NEEDS_WORK/BAD", "param_adjustments": {{"tp_pct": null, "sl_pct": null, "trail_distance": null, "max_hold_min": null, "force_exit_pct": null}}, "avoid_symbols": [], "prefer_symbols": [], "new_rules": [{{"type": "AVOID/PREFER", "condition": "...", "confidence": 0.0-1.0}}]}}"""
    try:
        resp = requests.post(API_URL,
            headers={"Content-Type": "application/json",
                     "x-api-key": API_KEY,
                     "anthropic-version": "2023-06-01"},
            json={"model": MODEL, "max_tokens": 600,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=45)
        if resp.status_code != 200:
            log.error(f"🧠 API {resp.status_code}")
            return None
        text = resp.json()["content"][0]["text"].strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        result = json.loads(text)
        learned = _load_json(LEARNED_FILE, {"symbols": {}, "tiers": {}})
        for k, v in result.get("param_adjustments", {}).items():
            if v is not None and isinstance(v, (int, float)):
                if k == "sl_pct" and v > 0.004: v = 0.004
                if k == "force_exit_pct" and v > 0.005: v = 0.005
                learned.setdefault("defaults", {})[k] = v
        _save_json(LEARNED_FILE, learned)
        lessons = _load_json(AI_LESSONS_FILE, {"lessons": [], "rules": [], "stats": {"analyzed": 0}})
        for rule in result.get("new_rules", []):
            if rule.get("confidence", 0) >= 0.6:
                lessons["rules"].append({**rule, "added": str(datetime.now()), "from": "daily_analysis"})
        lessons["lessons"].append({
            "time": str(datetime.now()), "type": "daily",
            "trades": len(recent), "pnl": f"${total_pnl:.2f}",
            "verdict": result.get("verdict", ""), "analysis": result.get("analysis", ""),
        })
        lessons["stats"]["analyzed"] += len(recent)
        if len(lessons["rules"]) > 200:
            lessons["rules"] = lessons["rules"][-200:]
        _save_json(AI_LESSONS_FILE, lessons)
        report["last_analysis"] = today
        report["last_result"] = result
        _save_json(DAILY_REPORT_DATA, report)
        log.info(f"🧠📊 يومي: {result.get('verdict','?')} | {result.get('analysis','')[:60]}")
        return result
    except Exception as e:
        log.error(f"🧠 Daily error: {e}")
        return None


def get_smart_summary():
    learned = _load_json(LEARNED_FILE, {"symbols": {}})
    lessons = _load_json(AI_LESSONS_FILE, {"rules": [], "stats": {}})
    return {
        "symbols": len(learned.get("symbols", {})),
        "rules": len(lessons.get("rules", [])),
        "analyzed": lessons.get("stats", {}).get("analyzed", 0),
    }
