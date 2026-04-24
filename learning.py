"""
learning.py — التعلم من الصفقات 🧠
"""
import json, os, logging
from datetime import datetime
from config import LEARNING_FILE, MIN_TRADES_LEARN
log = logging.getLogger(__name__)

def _load():
    try:
        with open(LEARNING_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"trades": [], "symbols": {}, "patterns": {"rsi": {}, "tiers": {}}}

def _save(m):
    with open(LEARNING_FILE, 'w') as f:
        json.dump(m, f, ensure_ascii=False, indent=2)

def save_trade_result(trade, profit, won, extra=None):
    m = _load()
    rec = {
        "symbol": trade.get('symbol', ''), "profit": profit, "won": won,
        "rsi": trade.get('rsi', 0), "score": trade.get('score', 0),
        "tier": trade.get('tier', ''), "time": str(datetime.now()),
    }
    if extra:
        rec.update(extra)
    m['trades'].append(rec)

    sym = trade.get('symbol', '')
    if sym not in m['symbols']:
        m['symbols'][sym] = {"total": 0, "wins": 0, "losses": 0,
                             "profit": 0, "streak": 0}
    s = m['symbols'][sym]
    s['total'] += 1
    s['profit'] = round(s['profit'] + profit, 4)
    if won:
        s['wins'] += 1
        s['streak'] = max(0, s.get('streak', 0)) + 1
    else:
        s['losses'] += 1
        s['streak'] = min(0, s.get('streak', 0)) - 1

    rsi = trade.get('rsi', 0)
    rng = f"{int(rsi // 10) * 10}-{int(rsi // 10) * 10 + 10}"
    m['patterns'].setdefault('rsi', {}).setdefault(rng, {"w": 0, "l": 0})
    if won:
        m['patterns']['rsi'][rng]['w'] += 1
    else:
        m['patterns']['rsi'][rng]['l'] += 1

    tier = trade.get('tier', '')
    m['patterns'].setdefault('tiers', {}).setdefault(
        tier, {"w": 0, "l": 0, "p": 0})
    if won:
        m['patterns']['tiers'][tier]['w'] += 1
    else:
        m['patterns']['tiers'][tier]['l'] += 1
    m['patterns']['tiers'][tier]['p'] = round(
        m['patterns']['tiers'][tier]['p'] + profit, 4)

    log.info(
        f"🧠 {sym} {'✅' if won else '❌'} ${profit} | "
        f"RSI:{rsi} | Streak:{s['streak']}")
    _save(m)

def get_learned_advice(symbol):
    m = _load()
    if len(m.get('trades', [])) < MIN_TRADES_LEARN:
        return {"avoid": False}
    s = m.get('symbols', {}).get(symbol, {})
    if s.get('streak', 0) <= -5:
        return {"avoid": True, "reason": f"streak {s['streak']}"}
    if s.get('total', 0) >= 5 and s.get('wins', 0) / s['total'] < 0.25:
        return {"avoid": True,
                "reason": f"WR {s['wins']}/{s['total']}"}
    return {"avoid": False}
