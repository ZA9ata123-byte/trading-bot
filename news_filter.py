import requests
from config import CRYPTOPANIC_KEY
import logging

log = logging.getLogger(__name__)

BAD_KEYWORDS = [
    "hack", "breach", "ban", "lawsuit",
    "crash", "scam", "fraud", "bankrupt",
    "regulation", "sec", "shutdown"
]

def check_news(symbol):
    if not CRYPTOPANIC_KEY:
        return True  # لو ما عندكش API = اسمح دائماً

    try:
        coin = symbol.replace("/USDT", "")
        url  = f"https://cryptopanic.com/api/v1/posts/?auth_token={CRYPTOPANIC_KEY}&currencies={coin}&filter=important"
        r    = requests.get(url, timeout=5)
        data = r.json()

        for post in data.get("results", [])[:5]:
            title = post.get("title", "").lower()
            if any(kw in title for kw in BAD_KEYWORDS):
                log.warning(f"⚠️ خبر سلبي لـ {symbol}: {post['title']}")
                return False  # لا تدخل الصفقة

        return True  # أخبار نظيفة

    except Exception:
        return True  # في حال خطأ = اسمح
