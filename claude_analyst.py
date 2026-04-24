"""
claude_analyst.py — موقوف مؤقتاً
البوت يشتغل بالتحليل التقني فقط
"""
import logging
log = logging.getLogger(__name__)

def should_enter(exchange, symbol, price, rsi, ma7, ma25, ma99, vol_ratio, change_pct, score):
    """موقوف — يرجع True دائماً"""
    return {
        "enter": True,
        "confidence": 80,
        "sl_price": price * 0.97,
        "tp_price": price * 1.006,
        "whale_support": True,
        "reason": "تحليل تقني فقط"
    }

def analyze_trade(*args, **kwargs):
    return {"decision": "ENTER", "confidence": 80,
            "sl_price": 0, "tp_price": 0,
            "whale_support": True, "reason": "موقوف"}
